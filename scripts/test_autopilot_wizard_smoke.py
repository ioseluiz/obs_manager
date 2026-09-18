"""Smoke test del AutopilotInstallDialog (AUT-3). Sin OBS.

Verifica:
- El dialog se construye sin errores.
- La navegación entre páginas funciona.
- El botón "Guardar en Descargas" copia el .lua a la ubicación esperada.
- La detección/verificación llama a is_installed() y actualiza el label.
- Settings tiene el botón + signal install_autopilot_requested.

Uso: venv\\Scripts\\python.exe scripts\\test_autopilot_wizard_smoke.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok - {msg}")


class FakeReqClient:
    def __init__(self, sources=None):
        self._sources = dict(sources or {})
    def get_input_settings(self, name):
        if name not in self._sources:
            raise RuntimeError(f"input {name} does not exist")
        from types import SimpleNamespace
        return SimpleNamespace(input_settings={"text": self._sources[name]})
    def set_input_settings(self, name, settings, overlay):
        self._sources[name] = settings.get("text", "")


class FakeObsClient:
    def __init__(self, sources=None):
        self.client = FakeReqClient(sources)


def test_paths_helper():
    print("\n[core.autopilot_paths.autopilot_lua_path resuelve al script]")
    from core.autopilot_paths import autopilot_lua_path, default_downloads_dir
    p = autopilot_lua_path()
    _check(p.exists(), f"autopilot.lua existe en {p}")
    _check(p.name == "autopilot.lua", "nombre correcto")
    _check(p.stat().st_size > 100, f"tamaño razonable ({p.stat().st_size} bytes)")

    d = default_downloads_dir()
    _check(d.exists() or d == Path.home(), f"downloads dir resuelve ({d})")


def test_dialog_constructs():
    print("\n[AutopilotInstallDialog se construye]")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from views.autopilot_install_dialog import AutopilotInstallDialog

    dlg = AutopilotInstallDialog(FakeObsClient())
    _check(dlg.windowTitle() == "Instalar Autopilot en OBS",
           "windowTitle correcto")
    _check(dlg.stack.count() == 6, f"6 páginas (dio {dlg.stack.count()})")
    _check(dlg.stack.currentIndex() == 0, "arranca en la página 0 (bienvenida)")


def test_navigation():
    print("\n[Navegación siguiente/atrás]")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from views.autopilot_install_dialog import AutopilotInstallDialog

    dlg = AutopilotInstallDialog(FakeObsClient())
    _check(dlg.stack.currentIndex() == 0, "página 0 inicial")
    dlg._on_next()
    _check(dlg.stack.currentIndex() == 1, "next → página 1 (detect)")
    dlg._on_next()
    _check(dlg.stack.currentIndex() == 2, "next → página 2 (export)")
    dlg._on_back()
    _check(dlg.stack.currentIndex() == 1, "back → página 1")


def test_detect_installed():
    print("\n[Detección con Autopilot instalado]")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from views.autopilot_install_dialog import AutopilotInstallDialog
    from core.autopilot_client import CONFIG_SOURCE, STATE_SOURCE
    import json

    fake = FakeObsClient({
        CONFIG_SOURCE: "",
        STATE_SOURCE: json.dumps({"script_version": "1.0.0", "mode": "standby"}),
    })
    dlg = AutopilotInstallDialog(fake)
    dlg._go_to(1)  # forzar página de detect
    _check("ya está instalado" in dlg.lbl_detect_status.text(),
           f"detecta como instalado (dio {dlg.lbl_detect_status.text()!r})")
    _check("1.0.0" in dlg.lbl_detect_status.text(),
           "muestra la version reportada")


def test_detect_not_installed():
    print("\n[Detección con Autopilot NO instalado]")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from views.autopilot_install_dialog import AutopilotInstallDialog

    dlg = AutopilotInstallDialog(FakeObsClient())
    dlg._go_to(1)
    _check("no está instalado" in dlg.lbl_detect_status.text(),
           f"detecta como no instalado (dio {dlg.lbl_detect_status.text()!r})")


def test_export_to_downloads():
    print("\n[Export a tmpdir imita 'Guardar en Descargas']")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from views.autopilot_install_dialog import AutopilotInstallDialog

    dlg = AutopilotInstallDialog(FakeObsClient())
    tmp = Path(tempfile.mkdtemp(prefix="autopilot_export_"))
    target = tmp / "autopilot.lua"
    dlg._export_to(target)
    _check(target.exists(), f"archivo copiado a {target}")
    _check(target.stat().st_size > 100, "archivo tiene contenido")
    _check(dlg._exported_path == target, "estado interno registra la ruta")
    # isVisible requiere que el dialog esté shown; con dialog cerrado usamos
    # isHidden() que refleja el estado explícito seteado por _export_to.
    _check(not dlg.lbl_export_result.isHidden(), "label de resultado no está oculto")

    # Cleanup
    target.unlink()
    tmp.rmdir()


def test_settings_button_and_signal():
    print("\n[SettingsDialog: botón + signal Autopilot presentes]")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from views.settings_view import SettingsDialog

    dlg = SettingsDialog({
        "host": "localhost", "port": "4455", "password": "x",
        "obs_exe_path": "", "obs_autolaunch": True,
    })
    _check(hasattr(dlg, "btn_install_autopilot"),
           "btn_install_autopilot existe")
    _check(hasattr(dlg, "install_autopilot_requested"),
           "install_autopilot_requested signal existe")
    _check(hasattr(dlg, "set_autopilot_status"),
           "set_autopilot_status API existe")

    # Toggle status
    dlg.set_autopilot_status(True, "1.0.0")
    _check("instalado y corriendo" in dlg.lbl_autopilot_status.text(),
           "set_autopilot_status(True) refleja instalado")
    _check("1.0.0" in dlg.lbl_autopilot_status.text(),
           "muestra version reportada")
    dlg.set_autopilot_status(False)
    _check("no detectado" in dlg.lbl_autopilot_status.text(),
           "set_autopilot_status(False) refleja NO instalado")


def test_verify_success_advances_to_final_page():
    print("\n[Verificar exitoso avanza al paso Éxito]")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from views.autopilot_install_dialog import AutopilotInstallDialog
    from core.autopilot_client import CONFIG_SOURCE, STATE_SOURCE
    import json

    fake = FakeObsClient({
        CONFIG_SOURCE: "",
        STATE_SOURCE: json.dumps({"script_version": "1.0.0", "mode": "standby"}),
    })
    dlg = AutopilotInstallDialog(fake)
    dlg._go_to(4)  # página verify
    dlg._verify()
    _check(dlg._verified_ok is True, "was_verified True tras verify OK")
    _check(dlg.stack.currentIndex() == 5, "avanzó a la página Éxito")


def main():
    test_paths_helper()
    test_dialog_constructs()
    test_navigation()
    test_detect_installed()
    test_detect_not_installed()
    test_export_to_downloads()
    test_settings_button_and_signal()
    test_verify_success_advances_to_final_page()
    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
