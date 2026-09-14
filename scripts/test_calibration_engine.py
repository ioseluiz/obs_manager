"""Smoke test headless del calibration_engine (Fase 2b).

Sin OBS, sin PyQt. Usa FakeFacade que simula un encoder con capacidad
configurable. Verifica:
- Escalado N=1..MAX_N con detección de saturación en el N correcto.
- Cleanup de filtros al terminar (éxito o fallo).
- Cancelación limpia.
- Encoder que peta → nmax=0.
- budget_cost devuelve coeficientes correctos.

Uso: venv\\Scripts\\python.exe scripts\\test_calibration_engine.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok - {msg}")


class FakeFacade:
    """Simula OBS con encoders de capacidad configurable.

    saturation_map: {encoder: N_max_soporta} — al aplicar más de ese N,
    los frames skipped empiezan a acumular >5% del total.
    """

    def __init__(self, saturation_map: dict[str, int], failing_encoders: set[str] = None):
        self._saturation = saturation_map
        self._failing = failing_encoders or set()
        self.active_filters: dict[tuple[str, str], dict] = {}
        self.baseline_created = False
        self.ensure_calls = 0
        self.remove_baseline_calls = 0
        # Contadores acumulados de frames — crecen entre snapshots.
        self._skipped = 0
        self._total = 0

    # ---- ObsFacade contract ----

    def ensure_baseline_scene(self, scene_name: str, input_name: str) -> None:
        self.baseline_created = True
        self.ensure_calls += 1

    def remove_baseline_scene(self, scene_name: str, input_name: str) -> None:
        self.baseline_created = False
        self.remove_baseline_calls += 1

    def apply_calibration_filter(self, scene_name, filter_name, encoder,
                                  server_url, bitrate_kbps) -> None:
        if encoder in self._failing:
            raise RuntimeError(f"Encoder '{encoder}' no disponible en este equipo")
        self.active_filters[(scene_name, filter_name)] = {
            "encoder": encoder, "url": server_url, "bitrate": bitrate_kbps,
        }

    def remove_calibration_filter(self, scene_name, filter_name) -> None:
        self.active_filters.pop((scene_name, filter_name), None)

    def get_output_frame_stats(self) -> tuple[int, int]:
        """Simula frames. Cada llamada avanza el contador según cantidad
        de filtros activos y su encoder.
        """
        # Determinar el N activo (asume que todos los filtros son del mismo
        # encoder — cierto en la calibración).
        n_active = len(self.active_filters)
        if n_active == 0:
            self._total += 300  # ~10s a 30fps
            return self._skipped, self._total

        # Todos los filtros activos son del mismo encoder — leemos el primero.
        encoder = next(iter(self.active_filters.values()))["encoder"]
        sat_at = self._saturation.get(encoder, 1)

        frames_per_snapshot = 300
        self._total += frames_per_snapshot
        if n_active > sat_at:
            # Saturado: 15% de los frames se pierden (>5% threshold).
            self._skipped += int(frames_per_snapshot * 0.15)
        # Si N <= sat_at, no se pierden frames — no incrementa skipped.
        return self._skipped, self._total


def test_saturation_at_correct_n():
    """FakeFacade dice que x264 aguanta 3 → engine debe devolver nmax=3."""
    print("\n[Sat correcta] x264 con saturación en N=3 → nmax=3")
    from core.calibration_engine import CalibrationEngine
    from core.capacity_repo import detect_fingerprint

    fake = FakeFacade(saturation_map={"x264": 3})
    engine = CalibrationEngine(
        facade=fake,
        max_n=6,
        per_step_seconds=1,          # irrelevante con sleep_fn=noop
        sleep_fn=lambda s: None,     # no dormir en tests
        port_base=47000,
    )
    fp = detect_fingerprint(obs_major=30, gpu_override="FakeGPU")
    events = []
    entry = engine.calibrate(
        encoders=["x264"],
        fingerprint=fp,
        progress_cb=events.append,
    )
    _check(entry.encoders.get("x264") == 3,
           f"nmax=3 detectado (dio {entry.encoders.get('x264')})")
    _check(fake.baseline_created is False, "baseline eliminada en cleanup")
    _check(len(fake.active_filters) == 0, "todos los filtros removidos")


def test_never_saturates():
    """Encoder con capacidad infinita → nmax=max_n."""
    print("\n[No satura] max_n=4, capacidad=99 → nmax=4")
    from core.calibration_engine import CalibrationEngine
    from core.capacity_repo import detect_fingerprint

    fake = FakeFacade(saturation_map={"nvenc": 99})
    engine = CalibrationEngine(
        facade=fake, max_n=4, per_step_seconds=1,
        sleep_fn=lambda s: None,
    )
    fp = detect_fingerprint(obs_major=30, gpu_override="FakeGPU")
    entry = engine.calibrate(encoders=["nvenc"], fingerprint=fp)
    _check(entry.encoders.get("nvenc") == 4,
           f"nmax=max_n=4 (dio {entry.encoders.get('nvenc')})")


def test_failing_encoder():
    """Encoder que peta al aplicar filtro → nmax=0, cleanup limpio."""
    print("\n[Encoder rota] nvenc sin GPU NVIDIA → nmax=0")
    from core.calibration_engine import CalibrationEngine
    from core.capacity_repo import detect_fingerprint

    fake = FakeFacade(
        saturation_map={"x264": 2, "nvenc": 99},
        failing_encoders={"nvenc"},
    )
    engine = CalibrationEngine(
        facade=fake, max_n=4, per_step_seconds=1,
        sleep_fn=lambda s: None,
    )
    fp = detect_fingerprint(obs_major=30, gpu_override="FakeGPU")
    entry = engine.calibrate(encoders=["x264", "nvenc"], fingerprint=fp)
    _check(entry.encoders.get("x264") == 2, "x264 ok")
    _check(entry.encoders.get("nvenc") == 0, "nvenc marcado como nmax=0")
    _check(len(fake.active_filters) == 0, "cleanup dejó todo limpio")


def test_cancellation():
    """cancelled() devuelve True mid-run → CapacityEntry parcial con notes."""
    print("\n[Cancel mid-run] cancelar entre encoders")
    from core.calibration_engine import CalibrationEngine
    from core.capacity_repo import detect_fingerprint

    fake = FakeFacade(saturation_map={"x264": 3, "qsv": 3})
    engine = CalibrationEngine(
        facade=fake, max_n=6, per_step_seconds=1,
        sleep_fn=lambda s: None,
    )
    fp = detect_fingerprint(obs_major=30, gpu_override="FakeGPU")

    # Cancelar después de terminar x264
    call_count = [0]
    def cancelled():
        call_count[0] += 1
        # Retornar True sólo después de que x264 haya sido registrado
        return call_count[0] > 20

    entry = engine.calibrate(
        encoders=["x264", "qsv"],
        fingerprint=fp,
        cancelled=cancelled,
    )
    _check(entry.notes == "cancelled by user", f"notes marca cancel (dio {entry.notes!r})")
    _check(len(fake.active_filters) == 0, "cleanup post-cancel limpio")
    _check(fake.remove_baseline_calls >= 1, "baseline removed on cancel")


def test_budget_cost():
    """Coeficientes de extrapolación entre resoluciones."""
    print("\n[Budget cost] coeficientes de resolución")
    from core.calibration_engine import budget_cost

    _check(budget_cost("1080p30") == 1.0, "1080p30 = 1.0 (baseline)")
    _check(budget_cost("720p30") == 0.5, "720p30 = 0.5 (mitad)")
    _check(budget_cost("1080p60") == 2.0, "1080p60 = 2.0 (doble por fps)")
    _check(budget_cost("4k30") == 4.0, "4k30 = 4.0")
    # Preset desconocido devuelve 1.0 (conservador) con warning
    _check(budget_cost("random_preset") == 1.0, "preset desconocido = 1.0 fallback")


def main():
    test_saturation_at_correct_n()
    test_never_saturates()
    test_failing_encoder()
    test_cancellation()
    test_budget_cost()
    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
