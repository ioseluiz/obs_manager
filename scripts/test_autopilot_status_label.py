"""Smoke test del label de status bar del Autopilot (AUT-5).

Verifica los 3 estados: no instalado (oculto), standby (verde), active
(rojo con escena + segundos).

Uso: venv\\Scripts\\python.exe scripts\\test_autopilot_status_label.py
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


def main():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from views.main_window import MainWindow

    mw = MainWindow()

    # === Estado inicial: no instalado → label oculto ===
    print("\n[Estado inicial: label oculto]")
    _check(hasattr(mw, "lbl_autopilot"), "lbl_autopilot existe")
    _check(not mw.lbl_autopilot.isVisibleTo(mw.statusBar()) or
           mw.lbl_autopilot.isHidden(),
           "label arranca oculto")

    # === set_autopilot_ui(installed=False) → oculto ===
    print("\n[installed=False → oculto]")
    mw.set_autopilot_ui(installed=False)
    _check(mw.lbl_autopilot.isHidden(), "installed=False → label hidden")
    _check(mw.lbl_autopilot.text() == "", "text vacío")

    # === installed=True, mode=standby ===
    print("\n[installed=True, mode=standby → verde 'Autopilot listo']")
    mw.set_autopilot_ui(installed=True, mode="standby", script_version="1.0.0")
    _check(not mw.lbl_autopilot.isHidden(), "label visible")
    _check("Autopilot listo" in mw.lbl_autopilot.text(),
           f"texto standby (dio {mw.lbl_autopilot.text()!r})")
    _check("1.0.0" in mw.lbl_autopilot.text(), "muestra version")
    _check("#198754" in mw.lbl_autopilot.styleSheet(),
           "color verde en standby")

    # === installed=True, mode=active con datos ===
    print("\n[installed=True, mode=active → rojo con escena + segundos]")
    mw.set_autopilot_ui(installed=True, mode="active",
                        active_scene="TestScene", seconds_remaining=12)
    _check(not mw.lbl_autopilot.isHidden(), "label visible en active")
    _check("Autopilot activo" in mw.lbl_autopilot.text(),
           "texto active correcto")
    _check("TestScene" in mw.lbl_autopilot.text(),
           "muestra escena activa")
    _check("12s" in mw.lbl_autopilot.text(),
           "muestra segundos restantes")
    _check("#B02A37" in mw.lbl_autopilot.styleSheet(),
           "color rojo en active")

    # === active sin seconds_remaining (=0) ===
    print("\n[active con seconds_remaining=0 → texto sin sufijo (Ns)]")
    mw.set_autopilot_ui(installed=True, mode="active",
                        active_scene="X", seconds_remaining=0)
    _check("(0s)" not in mw.lbl_autopilot.text(),
           "no muestra '(0s)' redundante")
    _check("X" in mw.lbl_autopilot.text(), "muestra escena")

    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
