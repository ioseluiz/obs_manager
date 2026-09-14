"""Motor headless de calibración de capacidad por encoder (Fase 2b).

Determina cuántos canales UDP simultáneos aguanta cada encoder en el
equipo actual, midiendo `output_skipped_frames_ratio` de OBS durante
una ventana sostenida por cada paso.

Flujo por encoder:
1. Crear escena baseline con color source neutro (1920×1080).
2. Loop N=1..MAX_N:
   a. Crear N filtros Source Record (udp_out_0..udp_out_{N-1}) apuntando
      a puertos loopback distintos. Nadie lee — sólo estresa el encoder.
   b. Esperar `per_step_seconds` (10s default) para que se estabilice.
   c. Medir `output_skipped_frames_ratio` sobre esa ventana.
   d. Si supera `lag_pct_threshold` (5% default) → nmax = N - 1, break.
   e. Si N == MAX_N sin cruzar → nmax = MAX_N.
3. Cleanup (remove filtros + remove escena baseline).

Retorna un `CapacityEntry` listo para persistir en `CapacityRepo`.

Contrato de progreso: el caller pasa un `progress_cb(event: dict)` que se
llama en cada transición importante. Los eventos tienen `type`:
- 'started', 'encoder_start', 'step_start', 'step_result',
- 'encoder_done', 'finished', 'error', 'cancelled'.

El motor NO importa PyQt — es puramente stdlib. La UI (2c) lo corre en
un QThread aparte y traduce los eventos a signals.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from core.capacity_repo import CapacityEntry, Fingerprint

log = logging.getLogger(__name__)


# Valores por defecto del motor. El caller puede sobrescribirlos.
DEFAULT_MAX_N = 6
DEFAULT_PER_STEP_SECONDS = 10
DEFAULT_LAG_PCT_THRESHOLD = 5.0
DEFAULT_BITRATE_KBPS = 2500

BASELINE_SCENE = "Calibration_Baseline"
BASELINE_INPUT = "Calibration_Color"

# Puerto base para los outputs loopback de calibración. Se elige alto para
# no colisionar con puertos productivos (9001..9999) que el user esté
# usando en canales reales.
CALIBRATION_PORT_BASE = 47000


class CancelledError(Exception):
    """El caller cancelo la calibracion via cancelled()."""


# ---------------------------------------------------------------------------
# Facade — abstracción de las operaciones OBS que el motor necesita
# ---------------------------------------------------------------------------

class ObsFacade(Protocol):
    """Contrato mínimo para poder calibrar. Implementación real en 2c."""

    def ensure_baseline_scene(self, scene_name: str, input_name: str) -> None: ...

    def remove_baseline_scene(self, scene_name: str, input_name: str) -> None: ...

    def apply_calibration_filter(
        self, scene_name: str, filter_name: str, encoder: str,
        server_url: str, bitrate_kbps: int,
    ) -> None: ...

    def remove_calibration_filter(self, scene_name: str, filter_name: str) -> None: ...

    def get_output_frame_stats(self) -> tuple[int, int]:
        """Devuelve (output_skipped_frames, output_total_frames)."""


# ---------------------------------------------------------------------------
# Resultado por encoder
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EncoderResult:
    """Resultado atómico de calibrar un encoder."""
    encoder: str
    nmax: int
    saturated_at_n: int | None  # None si nunca cruzó el umbral
    max_observed_lag_pct: float
    steps: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

class CalibrationEngine:
    """Corre la calibración; devuelve un CapacityEntry al terminar."""

    def __init__(
        self,
        facade: ObsFacade,
        *,
        max_n: int = DEFAULT_MAX_N,
        per_step_seconds: int = DEFAULT_PER_STEP_SECONDS,
        lag_pct_threshold: float = DEFAULT_LAG_PCT_THRESHOLD,
        bitrate_kbps: int = DEFAULT_BITRATE_KBPS,
        sleep_fn: Callable[[float], None] = time.sleep,
        port_base: int = CALIBRATION_PORT_BASE,
    ):
        self._facade = facade
        self._max_n = int(max_n)
        self._per_step_seconds = int(per_step_seconds)
        self._threshold = float(lag_pct_threshold)
        self._bitrate = int(bitrate_kbps)
        self._sleep = sleep_fn
        self._port_base = int(port_base)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def calibrate(
        self,
        encoders: list[str],
        fingerprint: Fingerprint,
        progress_cb: Callable[[dict], None] | None = None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> CapacityEntry:
        """Corre la calibración para todos los encoders y devuelve la entry.

        Si `cancelled()` devuelve True en cualquier check, aborta con
        CancelledError después de hacer cleanup. Los encoders ya calibrados
        se preservan en el resultado parcial vía notes.
        """
        cb = progress_cb or (lambda _: None)
        cb({"type": "started", "encoders": list(encoders)})

        entry = CapacityEntry.new(fingerprint, notes="")
        # Aleatorio para no chocar con puertos abandonados de sesiones previas.
        port_offset = random.randint(0, 500)

        try:
            self._facade.ensure_baseline_scene(BASELINE_SCENE, BASELINE_INPUT)
        except Exception as e:
            cb({"type": "error", "message": f"No se pudo crear escena baseline: {e}"})
            raise

        try:
            for encoder in encoders:
                self._check_cancelled(cancelled, cb)
                cb({"type": "encoder_start", "encoder": encoder})
                try:
                    result = self._calibrate_encoder(
                        encoder, port_offset, cb, cancelled,
                    )
                    entry = entry.with_encoder(encoder, result.nmax)
                    cb({
                        "type": "encoder_done",
                        "encoder": encoder,
                        "nmax": result.nmax,
                        "saturated_at_n": result.saturated_at_n,
                        "max_observed_lag_pct": result.max_observed_lag_pct,
                    })
                except CancelledError:
                    raise
                except Exception as e:
                    # Un encoder que peta (por ejemplo nvenc sin GPU NVIDIA)
                    # queda con nmax=0 y notes documenta el motivo.
                    log.warning("Encoder %r falló en calibración: %s", encoder, e)
                    entry = entry.with_encoder(encoder, 0)
                    cb({
                        "type": "encoder_done",
                        "encoder": encoder,
                        "nmax": 0,
                        "error": str(e),
                    })
                # Bump el port offset para el próximo encoder para evitar
                # reciclar puertos que el kernel podría no haber liberado.
                port_offset += self._max_n + 5
        except CancelledError:
            cb({"type": "cancelled"})
            entry_cancelled = CapacityEntry(
                fingerprint=entry.fingerprint,
                encoders=dict(entry.encoders),
                calibrated_at=entry.calibrated_at,
                notes="cancelled by user",
            )
            self._cleanup_all_filters()
            self._remove_baseline_safe()
            return entry_cancelled
        finally:
            # Cleanup final SIEMPRE — aun si falló todo.
            self._cleanup_all_filters()
            self._remove_baseline_safe()

        cb({"type": "finished", "entry": entry.as_dict()})
        return entry

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _calibrate_encoder(
        self,
        encoder: str,
        port_offset: int,
        cb: Callable[[dict], None],
        cancelled: Callable[[], bool],
    ) -> EncoderResult:
        """Loop de N=1..max_n para un encoder. Devuelve EncoderResult."""
        applied_filters: list[str] = []
        steps: list[dict[str, Any]] = []
        max_lag = 0.0
        saturated_at: int | None = None
        nmax = 0

        try:
            for n in range(1, self._max_n + 1):
                self._check_cancelled(cancelled, cb)

                # Añadir el N-ésimo filtro al conjunto existente.
                filter_name = f"udp_out_{n - 1}"
                port = self._port_base + port_offset + (n - 1)
                server_url = f"udp://127.0.0.1:{port}"
                cb({
                    "type": "step_start",
                    "encoder": encoder,
                    "current_n": n,
                    "port": port,
                })
                self._facade.apply_calibration_filter(
                    BASELINE_SCENE, filter_name, encoder, server_url, self._bitrate,
                )
                applied_filters.append(filter_name)

                # Snapshot inicial de stats
                skipped0, total0 = self._facade.get_output_frame_stats()

                # Esperar la ventana de medición, chequeando cancel periódicamente.
                self._interruptible_sleep(
                    self._per_step_seconds, cancelled, cb,
                )

                # Snapshot final
                skipped1, total1 = self._facade.get_output_frame_stats()
                d_skipped = max(0, skipped1 - skipped0)
                d_total = max(0, total1 - total0)
                lag_pct = (d_skipped / d_total * 100.0) if d_total > 0 else 0.0
                max_lag = max(max_lag, lag_pct)

                step_record = {
                    "n": n,
                    "delta_skipped": d_skipped,
                    "delta_total": d_total,
                    "lag_pct": lag_pct,
                }
                steps.append(step_record)
                cb({
                    "type": "step_result",
                    "encoder": encoder,
                    "current_n": n,
                    "lag_pct": lag_pct,
                    "delta_skipped": d_skipped,
                    "delta_total": d_total,
                })

                if lag_pct > self._threshold:
                    # Saturación: el paso anterior era el máximo sano.
                    nmax = n - 1
                    saturated_at = n
                    break
            else:
                # Nunca cruzó el umbral hasta max_n → el equipo lo sostiene.
                nmax = self._max_n
        finally:
            # Remover TODOS los filtros que agregamos para este encoder.
            for filter_name in applied_filters:
                try:
                    self._facade.remove_calibration_filter(
                        BASELINE_SCENE, filter_name,
                    )
                except Exception as e:
                    log.warning("cleanup filter %s falló: %s", filter_name, e)

        return EncoderResult(
            encoder=encoder,
            nmax=nmax,
            saturated_at_n=saturated_at,
            max_observed_lag_pct=max_lag,
            steps=steps,
        )

    def _interruptible_sleep(
        self, total_seconds: float,
        cancelled: Callable[[], bool],
        cb: Callable[[dict], None],
    ) -> None:
        """Duerme total_seconds pero chequea cancel cada ~250ms."""
        remaining = float(total_seconds)
        chunk = 0.25
        while remaining > 0:
            if cancelled():
                raise CancelledError()
            step = min(chunk, remaining)
            self._sleep(step)
            remaining -= step

    def _check_cancelled(
        self, cancelled: Callable[[], bool], cb: Callable[[dict], None],
    ) -> None:
        if cancelled():
            raise CancelledError()

    def _cleanup_all_filters(self) -> None:
        """Intenta remover cualquier filtro udp_out_* residual."""
        for n in range(self._max_n):
            try:
                self._facade.remove_calibration_filter(
                    BASELINE_SCENE, f"udp_out_{n}",
                )
            except Exception:
                pass  # ya no existe o no se puede remover — no es fatal.

    def _remove_baseline_safe(self) -> None:
        try:
            self._facade.remove_baseline_scene(BASELINE_SCENE, BASELINE_INPUT)
        except Exception as e:
            log.warning("No se pudo remover escena baseline: %s", e)


# ---------------------------------------------------------------------------
# Extrapolación entre resoluciones/fps
# ---------------------------------------------------------------------------

# Coeficientes fijos: cuánto "cuesta" cada preset respecto a 1080p30 (=1.0).
# Acordado en la memoria de Fase 2 — no se auto-calibra por resolución para
# mantener el motor rápido; extrapolar es suficientemente preciso.
_RESOLUTION_COEFFS = {
    "720p30": 0.5,
    "720p60": 1.0,
    "1080p30": 1.0,
    "1080p60": 2.0,
    "1440p30": 1.78,  # (1440/1080)^2 ≈ 1.78
    "1440p60": 3.56,
    "4k30": 4.0,
    "4k60": 8.0,
}


def budget_cost(preset: str) -> float:
    """Retorna el 'costo' en unidades de 1080p30 para un preset de resolución/fps.

    Un canal 1080p60 cuesta 2 unidades; un 720p30 cuesta 0.5. Usado por el
    validador de Fase 2d: suma el costo de todos los canales configurados y
    compara vs el `nmax` del encoder (que está anclado en 1080p30).
    """
    coeff = _RESOLUTION_COEFFS.get(preset.lower())
    if coeff is None:
        log.warning("Preset %r no tiene coeficiente conocido; se usa 1.0", preset)
        return 1.0
    return coeff
