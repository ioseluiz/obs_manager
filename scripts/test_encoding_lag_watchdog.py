"""Smoke test del EncodingLagWatchdog (Fase 2f).

Sin OBS. Usa stats_provider mockeado que devuelve valores controlados +
time_fn inyectada para cooldown determinístico. Fuerza ticks vía
_force_tick() para no depender del QTimer.

Uso: venv\\Scripts\\python.exe scripts\\test_encoding_lag_watchdog.py
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


class FakeStats:
    """Contadores acumulativos configurable por segmento."""
    def __init__(self):
        self.skipped = 0
        self.total = 0
    def add(self, d_skipped, d_total):
        self.skipped += d_skipped
        self.total += d_total
    def __call__(self):
        return self.skipped, self.total


def main():
    from PyQt6.QtWidgets import QApplication
    from core.encoding_lag_watchdog import EncodingLagWatchdog

    app = QApplication.instance() or QApplication([])

    # === Test 1: no dispara alerta si el lag está debajo del umbral ===
    print("\n[Sin lag → sin alerta]")
    stats = FakeStats()
    alerts = []
    fake_time = [1000.0]
    wd = EncodingLagWatchdog(
        stats_provider=stats,
        consecutive_hits=2,
        lag_pct_threshold=5.0,
        cooldown_seconds=300,
        time_fn=lambda: fake_time[0],
    )
    wd.lag_alert.connect(lambda pct: alerts.append(pct))
    wd.start()

    # Primer tick: setea baseline, no dispara nada
    stats.add(0, 300)
    wd._force_tick()
    _check(alerts == [], "primer tick no dispara")

    # 2 ticks con 2% lag (bajo threshold)
    stats.add(6, 300)  # 2%
    wd._force_tick()
    stats.add(6, 300)  # 2%
    wd._force_tick()
    _check(alerts == [], "lag bajo threshold no dispara")

    # === Test 2: dispara alerta tras hits_needed=2 checks sobre threshold ===
    print("\n[Lag sostenido → alerta tras N hits]")
    stats.add(45, 300)  # 15% lag
    wd._force_tick()
    _check(alerts == [], "1er hit no dispara todavía (hits_needed=2)")
    stats.add(45, 300)  # 15% lag
    wd._force_tick()
    _check(len(alerts) == 1, f"2do hit dispara alerta (dio {len(alerts)})")
    _check(alerts[0] == 15, f"pct reportado = 15 (dio {alerts[0]})")

    # === Test 3: cooldown suprime alerta consecutiva ===
    print("\n[Cooldown suprime alertas repetidas]")
    stats.add(45, 300)
    wd._force_tick()  # 1er hit post-alert
    stats.add(45, 300)
    wd._force_tick()  # 2do hit post-alert
    # El motor requiere 2 hits → debería querer disparar, pero cooldown lo suprime.
    _check(len(alerts) == 1, f"cooldown NO permite 2da alerta inmediata (dio {len(alerts)})")

    # Avanzamos el reloj más allá del cooldown
    fake_time[0] += 400  # >300s
    stats.add(45, 300)
    wd._force_tick()
    stats.add(45, 300)
    wd._force_tick()
    _check(len(alerts) == 2, f"tras cooldown, alerta permitida (dio {len(alerts)})")

    # === Test 4: racha se rompe si baja del umbral ===
    print("\n[Racha rota reinicia contador]")
    stats2 = FakeStats()
    alerts2 = []
    fake_time2 = [2000.0]
    wd2 = EncodingLagWatchdog(
        stats_provider=stats2,
        consecutive_hits=3,
        lag_pct_threshold=5.0,
        cooldown_seconds=1,
        time_fn=lambda: fake_time2[0],
    )
    wd2.lag_alert.connect(lambda pct: alerts2.append(pct))
    wd2.start()
    stats2.add(0, 300)
    wd2._force_tick()  # baseline

    stats2.add(45, 300)  # 15%, hit 1
    wd2._force_tick()
    stats2.add(45, 300)  # 15%, hit 2
    wd2._force_tick()
    _check(alerts2 == [], "aún no dispara (hits_needed=3)")
    stats2.add(3, 300)   # 1%, rompe racha
    wd2._force_tick()
    _check(alerts2 == [], "racha rota, no dispara")
    stats2.add(45, 300)  # hit 1 nuevamente (contador reseteado)
    wd2._force_tick()
    _check(alerts2 == [], "hit 1 solo tras racha rota")

    # === Test 5: d_total=0 no cuenta como hit ni reset ===
    print("\n[d_total=0 no altera contador]")
    stats3 = FakeStats()
    alerts3 = []
    wd3 = EncodingLagWatchdog(
        stats_provider=stats3, consecutive_hits=2,
        cooldown_seconds=1, lag_pct_threshold=5.0,
        time_fn=lambda: 3000.0,
    )
    wd3.lag_alert.connect(lambda pct: alerts3.append(pct))
    wd3.start()
    stats3.add(0, 300)
    wd3._force_tick()
    stats3.add(45, 300)  # hit 1
    wd3._force_tick()
    stats3.add(0, 0)     # OBS no encodea (d_total=0) — no altera hits
    wd3._force_tick()
    stats3.add(45, 300)  # hit 2 → debería disparar
    wd3._force_tick()
    _check(len(alerts3) == 1, f"d_total=0 no rompe la racha (dio {len(alerts3)})")

    # === Test 6: stats_provider que lanza excepción no rompe ===
    print("\n[stats_provider con excepción]")
    def broken():
        raise RuntimeError("OBS desconectado")
    wd4 = EncodingLagWatchdog(stats_provider=broken)
    wd4.start()
    wd4._force_tick()  # No debe lanzar
    _check(wd4.is_running(), "watchdog sigue corriendo tras excepción del provider")
    wd4.stop()

    # === Test 7: is_running / start / stop ===
    print("\n[start / stop / is_running]")
    stats5 = FakeStats()
    wd5 = EncodingLagWatchdog(stats_provider=stats5)
    _check(wd5.is_running() is False, "no corre antes de start()")
    wd5.start()
    _check(wd5.is_running() is True, "corre tras start()")
    wd5.stop()
    _check(wd5.is_running() is False, "no corre tras stop()")

    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
