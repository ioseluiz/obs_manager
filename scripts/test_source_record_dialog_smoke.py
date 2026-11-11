"""Smoke test headless de SourceRecordInstallDialog y de la seccion en
SettingsDialog. Sin OBS: cliente falso + bundle falso en tmp.

Uso: QT_QPA_PLATFORM=offscreen venv\\Scripts\\python.exe scripts\\test_source_record_dialog_smoke.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok - {msg}")


class FakeObs:
    def __init__(self, present, connected=True, version="32.1.2"):
        self.present = present
        self.client = object() if connected else None
        self._version = version

    def has_source_record(self):
        return self.present


def main():
    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)

    from core import source_record_installer as sri
    from scripts.test_source_record_installer import make_fake_bundle, make_fake_obs
    from views.source_record_install_dialog import SourceRecordInstallDialog
    from views.settings_view import SettingsDialog

    tmp = Path(tempfile.mkdtemp(prefix="srdlg_"))
    vendor = make_fake_bundle(tmp)
    exe = make_fake_obs(tmp / "obsportable", portable=True)
    settings = {"host": "localhost", "obs_exe_path": str(exe)}

    with patch.object(sri, "bundled_root", return_value=vendor):
        # --- Plugin ausente, OBS local portable ---
        print("[local portable, plugin ausente]")
        dlg = SourceRecordInstallDialog(FakeObs(False), settings, is_local=True)
        _check("NO está cargado" in dlg.lbl_status.text(), "banner de advertencia")
        _check("portable" in dlg.lbl_context.text(), "contexto detecta OBS portable")
        _check(dlg.btn_install.isEnabled(), "Instalar habilitado (local + exe + bundle)")
        _check(dlg.btn_export.isEnabled(), "Exportar habilitado")

        # Instalar: confirmar Yes, informar no-op. Sin conexion real,
        # _obs_version cae a la version del exe (None en el fake) -> legacy
        # -> OBS portable <=32 -> arbol de la instalacion.
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
             patch.object(QMessageBox, "information") as info, \
             patch.object(QMessageBox, "warning") as warn:
            dlg.btn_install.click()
        _check(info.called and not warn.called, "instalacion informada sin warning")
        _check("abrir OBS" in info.call_args.args[2], "pide cerrar y abrir OBS")
        dll = tmp / "obsportable" / "obs-plugins" / "64bit" / "source-record.dll"
        _check(dll.is_file(), f"dll copiada al arbol portable ({dll})")
        _check((tmp / "obsportable" / "data" / "obs-plugins" / "source-record" / "manifest.json").is_file(),
               "data copiada al arbol portable")

        # Exportar: sin version conocida pregunta; No -> OBS32 -> zip legacy.
        out_dir = tmp / "downloads"
        with patch.object(dlg, "_downloads_dir", return_value=out_dir), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No), \
             patch.object(QMessageBox, "information") as info:
            dlg.btn_export.click()
        zips = list(out_dir.glob("source-record-*-OBS32.zip"))
        _check(len(zips) == 1, f"zip exportado para OBS32 ({zips})")
        _check(info.called and str(zips[0]) in info.call_args.args[2], "ruta del zip informada")
        dlg.close()

        # --- Plugin presente ---
        print("[plugin presente]")
        dlg = SourceRecordInstallDialog(FakeObs(True), settings, is_local=True)
        _check("✅" in dlg.lbl_status.text(), "banner verde")
        with patch.object(QMessageBox, "information") as info:
            dlg.btn_verify.click()
        _check(info.called and "verificado" in info.call_args.args[1].lower(), "verificar informa OK")
        dlg.close()

        # --- OBS remoto: solo exportar ---
        print("[remoto]")
        dlg = SourceRecordInstallDialog(FakeObs(None, connected=False), {"host": "10.1.2.3"}, is_local=False)
        _check("Sin conexión" in dlg.lbl_status.text(), "banner informativo sin conexion")
        _check("remoto en 10.1.2.3" in dlg.lbl_context.text(), "contexto remoto")
        _check(not dlg.btn_install.isEnabled(), "Instalar deshabilitado en remoto")
        _check(dlg.btn_export.isEnabled(), "Exportar habilitado en remoto")
        dlg.close()

        # --- Sin bundle: nada que instalar/exportar ---
        print("[sin bundle]")
        with patch.object(sri, "bundled_root", return_value=tmp / "nope"):
            dlg = SourceRecordInstallDialog(FakeObs(False), settings, is_local=True)
            _check(not dlg.btn_install.isEnabled() and not dlg.btn_export.isEnabled(),
                   "botones deshabilitados sin bundle")
            dlg.close()

    # --- Seccion en SettingsDialog ---
    print("[SettingsDialog]")
    sd = SettingsDialog({"host": "localhost", "port": 4455, "password": ""})
    _check(hasattr(sd, "btn_install_source_record"), "boton en Ajustes")
    emitted = []
    sd.install_source_record_requested.connect(lambda: emitted.append(1))
    sd.btn_install_source_record.click()
    _check(emitted == [1], "senal install_source_record_requested emitida")
    sd.set_source_record_status(False)
    _check("NO está cargado" in sd.lbl_source_record_status.text(), "estado False")
    sd.set_source_record_status(True)
    _check("✅" in sd.lbl_source_record_status.text(), "estado True")
    sd.set_source_record_status(None)
    _check("Conéctate" in sd.lbl_source_record_status.text(), "estado None")
    sd.close()

    print("\n✓ TODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
