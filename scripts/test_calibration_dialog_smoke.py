"""Smoke test del CalibrationDialog (Fase 2c) — sin OBS.

Verifica:
- El diálogo se construye con inputs válidos.
- El worker corre el motor con FakeFacade y llega a 'finished'.
- El CapacityEntry resultante se persiste en el repo temporal.
- Los widgets se actualizan (progresos, log tiene contenido).

No abre la ventana visible — usa QApplication en modo evento loop breve.

Uso: venv\\Scripts\\python.exe scripts\\test_calibration_dialog_smoke.py
"""
from __future__ import annotations

import sys
import tempfile
import time
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
    """FakeFacade sencillo: encoder x264 satura en N=2."""
    def __init__(self):
        self.filters = {}
        self._skipped = 0
        self._total = 0
    def ensure_baseline_scene(self, *_): pass
    def remove_baseline_scene(self, *_): pass
    def apply_calibration_filter(self, scene, fname, encoder, url, br):
        self.filters[fname] = encoder
    def remove_calibration_filter(self, scene, fname):
        self.filters.pop(fname, None)
    def get_output_frame_stats(self):
        n = len(self.filters)
        self._total += 300
        if n > 2:
            self._skipped += 45  # 15% → saturación
        return self._skipped, self._total


def main():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from core.calibration_engine import CalibrationEngine
    from core.capacity_repo import (
        CapacityRepo, detect_fingerprint,
    )
    from views.calibration_dialog import CalibrationDialog

    app = QApplication.instance() or QApplication(sys.argv)

    tmp_dir = Path(tempfile.mkdtemp(prefix="cal_dlg_"))
    repo = CapacityRepo(path=tmp_dir / "calibrations.json")
    fp = detect_fingerprint(obs_major=30, gpu_override="FakeGPU")

    facade = FakeFacade()
    engine = CalibrationEngine(
        facade=facade,
        max_n=4,
        per_step_seconds=1,
        sleep_fn=lambda s: None,
    )

    dlg = CalibrationDialog(
        engine, encoders=["x264"], fingerprint=fp,
        capacity_repo=repo,
    )

    # Verificaciones antes de arrancar
    _check(dlg.pb_global.maximum() == 1, "barra global escala a 1 encoder")
    _check(dlg.pb_encoder.maximum() == 4, "barra encoder escala a max_n=4")
    _check(dlg.btn_start.isEnabled() is True, "btn_start habilitado al inicio")
    _check(dlg.btn_cancel.isEnabled() is False, "btn_cancel deshabilitado al inicio")

    # Disparar la calibración y esperar a que termine
    dlg._on_start()
    _check(dlg.btn_start.isEnabled() is False, "btn_start disabled durante running")
    _check(dlg.btn_cancel.isEnabled() is True, "btn_cancel enabled durante running")

    # Esperar a que el worker termine (max 8s de safety)
    deadline = time.time() + 8
    while time.time() < deadline:
        app.processEvents()
        if dlg._worker is not None and dlg._worker.isFinished():
            break
        time.sleep(0.02)
    app.processEvents()

    _check(dlg._worker is not None, "worker instanciado")
    _check(dlg._worker.isFinished(), "worker terminó")
    _check(dlg._result_entry is not None, "result_entry poblado")
    _check(dlg._result_entry.encoders.get("x264") == 2,
           f"nmax x264=2 (dio {dlg._result_entry.encoders.get('x264')})")
    _check(dlg.log.toPlainText() != "", "log tiene contenido")
    _check("nmax=2" in dlg.log.toPlainText(),
           "log menciona el nmax resultante")

    # Persistencia
    persisted = repo.get(fp)
    _check(persisted is not None, "entry persistida en el repo")
    _check(persisted.encoders.get("x264") == 2, "encoders persistidos correctamente")

    # UI post-finish
    _check(dlg.btn_close.isEnabled() is True, "btn_close reactivado al terminar")
    _check(dlg.btn_cancel.isEnabled() is False, "btn_cancel disabled al terminar")

    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
