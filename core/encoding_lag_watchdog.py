"""Watchdog runtime de encoding_lag (Fase 2f).

Vigila el ratio `output_skipped_frames / output_total_frames` de OBS
durante producción. Si supera un umbral (default 5%) durante K checks
consecutivos (default 3), emite `lag_alert(pct)`. La UI muestra la
alerta como advertencia non-bloqueante — regla firme de Fase 2:
nunca auto-degradar.

Cooldown post-alert (default 5 min) evita spamear si la degradación
persiste. El watchdog sigue midiendo silencioso durante el cooldown.

Se corre en el main thread vía QTimer (poll ligero — sólo un
get_stats). No usa threading para no complicar la sincronía.

Uso típico::

    watchdog = EncodingLagWatchdog(
        stats_provider=facade.get_output_frame_stats,
    )
    watchdog.lag_alert.connect(on_lag_alert)
    watchdog.start()
    ...
    watchdog.stop()  # al desconectar OBS

`stats_provider` puede lanzar excepción (OBS desconectado a mitad); el
watchdog lo trata como snapshot no-computable y sigue.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger(__name__)


DEFAULT_POLL_INTERVAL_MS = 10_000    # cada 10s
DEFAULT_LAG_PCT_THRESHOLD = 5.0
DEFAULT_CONSECUTIVE_HITS = 3         # 3 checks seguidos > threshold
DEFAULT_COOLDOWN_SECONDS = 5 * 60    # 5 min entre alertas


class EncodingLagWatchdog(QObject):
    """Poll periódico de stats de OBS con detección de degradación sostenida."""

    # Emitido cuando se detecta lag sostenido. int: porcentaje redondeado.
    lag_alert = pyqtSignal(int)
    # Emitido en cada tick con el pct actual (útil para status bar).
    tick = pyqtSignal(float)

    def __init__(
        self,
        stats_provider: Callable[[], tuple[int, int]],
        *,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        lag_pct_threshold: float = DEFAULT_LAG_PCT_THRESHOLD,
        consecutive_hits: int = DEFAULT_CONSECUTIVE_HITS,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        time_fn: Callable[[], float] = time.time,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._stats = stats_provider
        self._threshold = float(lag_pct_threshold)
        self._hits_needed = int(consecutive_hits)
        self._cooldown = int(cooldown_seconds)
        self._time = time_fn

        self._timer = QTimer(self)
        self._timer.setInterval(int(poll_interval_ms))
        self._timer.timeout.connect(self._on_tick)

        # Estado
        self._last_snapshot: tuple[int, int] | None = None
        self._consecutive_hits = 0
        self._last_alert_ts: float = 0.0

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Arranca el poll. Reseteando estado — no continua un run anterior."""
        self.reset()
        self._timer.start()
        log.info("EncodingLagWatchdog iniciado (interval=%dms, threshold=%.1f%%, "
                 "hits=%d)", self._timer.interval(), self._threshold,
                 self._hits_needed)

    def stop(self) -> None:
        """Detiene el poll."""
        self._timer.stop()
        log.info("EncodingLagWatchdog detenido")

    def reset(self) -> None:
        """Reinicia contadores. Útil al reconectar OBS."""
        self._last_snapshot = None
        self._consecutive_hits = 0
        # No resetear last_alert_ts — el cooldown atraviesa reconexiones para
        # que un reconnect no dispare alerta inmediata si acabábamos de tener una.

    def is_running(self) -> bool:
        return self._timer.isActive()

    # Método público para tests: fuerza un tick sin esperar el QTimer.
    def _force_tick(self) -> None:
        self._on_tick()

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------

    def _on_tick(self) -> None:
        try:
            skipped, total = self._stats()
        except Exception as e:
            log.debug("stats_provider falló en watchdog: %s", e)
            return

        if self._last_snapshot is None:
            self._last_snapshot = (skipped, total)
            return

        prev_skipped, prev_total = self._last_snapshot
        d_skipped = max(0, skipped - prev_skipped)
        d_total = max(0, total - prev_total)
        self._last_snapshot = (skipped, total)

        if d_total <= 0:
            # OBS no está encodeando (ni streaming ni recording) o los
            # contadores se resetearon. No cuenta ni como hit ni como reset.
            return

        pct = d_skipped / d_total * 100.0
        self.tick.emit(pct)

        if pct > self._threshold:
            self._consecutive_hits += 1
            log.debug("Lag tick: %.2f%% (%d/%d) — hits=%d/%d",
                      pct, self._consecutive_hits, self._hits_needed,
                      d_skipped, d_total)
            if self._consecutive_hits >= self._hits_needed:
                # Chequear cooldown
                now = self._time()
                if now - self._last_alert_ts < self._cooldown:
                    log.debug("Lag alert suprimido por cooldown "
                              "(%.0fs restantes)",
                              self._cooldown - (now - self._last_alert_ts))
                    return
                self._last_alert_ts = now
                log.warning("ALERTA lag sostenido: %.1f%% durante %d checks",
                            pct, self._consecutive_hits)
                self.lag_alert.emit(int(round(pct)))
                # Resetear contador para requerir otra racha sostenida
                # tras el cooldown.
                self._consecutive_hits = 0
        else:
            # Reset del contador — la racha se cortó.
            if self._consecutive_hits > 0:
                log.debug("Lag racha rota: %.2f%% (<%.1f%% threshold)",
                          pct, self._threshold)
            self._consecutive_hits = 0
