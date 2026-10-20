"""Dialogo para instalar el script Autopilot v2 en el OBS remoto.

Flujo simplificado respecto a los 6 pasos del wizard v1: una sola
ventana con el estado actual, un boton para exportar `autopilot_v2.lua`
a disco, instrucciones breves de registro en OBS, y un boton de
verificacion que confirma que los buzones v2 existen (lo que significa
que el script esta cargado y corriendo).

El dialogo detecta — sin tocarlo — si el autopilot v1 (`autopilot.lua`)
tambien esta instalado. Convivir con v1 es parte de las decisiones de
arquitectura del port (ver obs_scripts/PROTOCOL_v2.md).

Para uso: `AutopilotInstallV2Dialog(client, parent).exec()`.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.autopilot_paths import autopilot_v2_lua_path

log = logging.getLogger(__name__)


# Buzon del Autopilot v1 — solo lo chequeamos para informar al user que
# ambos conviviran. No se toca.
_CONFIG_SOURCE_V1 = "__autopilot_config__"


class AutopilotInstallV2Dialog(QDialog):
    def __init__(self, autopilot_client, parent=None):
        super().__init__(parent)
        self._ap = autopilot_client
        self.setWindowTitle("Instalar Autopilot v2 en OBS")
        self.setMinimumSize(640, 480)

        layout = QVBoxLayout(self)

        header = QLabel(
            "<b>Autopilot v2</b> es un script Lua que corre dentro de OBS "
            "y mantiene la rotación de canales activa cuando esta aplicación "
            "se cierra o la laptop se apaga."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet(
            "padding: 8px; border: 1px solid #DEE2E6; border-radius: 4px;"
        )
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        # Instrucciones de registro
        instr = QTextEdit()
        instr.setReadOnly(True)
        instr.setHtml(
            "<ol>"
            "<li><b>Exporta</b> el script a un lugar accesible desde la "
            "máquina donde corre OBS (botón abajo).</li>"
            "<li>En OBS: <b>Herramientas → Scripts</b>.</li>"
            "<li>Clic en <b>+</b> y selecciona el <code>autopilot_v2.lua</code> "
            "que acabas de exportar.</li>"
            "<li>El log de OBS mostrará "
            "<code>[autopilot_v2] cargando v2.0.0</code> seguido de "
            "<code>timers armados; a la espera de config v2 de la app</code>."
            "</li>"
            "<li>Vuelve aquí y pulsa <b>Verificar instalación</b>.</li>"
            "</ol>"
            "<p style='color:#6C757D;'>Nota: si tienes el Autopilot v1 "
            "(<code>autopilot.lua</code>) instalado, puede quedarse — v2 "
            "usa sus propios buzones y no interfieren.</p>"
        )
        layout.addWidget(instr)

        btn_row = QHBoxLayout()
        self.btn_export_downloads = QPushButton("📥 Exportar a Descargas")
        self.btn_export_as = QPushButton("💾 Exportar como…")
        self.btn_verify = QPushButton("🔎 Verificar instalación")
        self.btn_verify.setStyleSheet("background-color: #198754; color: white;")
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.setStyleSheet("background-color: #6C757D;")
        btn_row.addWidget(self.btn_export_downloads)
        btn_row.addWidget(self.btn_export_as)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_verify)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        self.btn_export_downloads.clicked.connect(self._on_export_downloads)
        self.btn_export_as.clicked.connect(self._on_export_as)
        self.btn_verify.clicked.connect(self._on_verify)
        self.btn_close.clicked.connect(self.accept)

        self._refresh_status()

    # ----------------------------------------------------------------------
    # Status + verificacion
    # ----------------------------------------------------------------------

    def _refresh_status(self):
        v1_present = self._detect_v1()
        if self._ap.is_installed():
            version = self._ap.script_version() or "?"
            msg = (
                f"✅ Autopilot v2 (v{version}) está instalado y corriendo "
                f"en OBS."
            )
            self.lbl_status.setStyleSheet(
                "padding: 8px; background-color: #D1E7DD; "
                "color: #0F5132; border: 1px solid #BADBCC; border-radius: 4px;"
            )
        else:
            msg = "⚠ Autopilot v2 todavía no está instalado en OBS."
            self.lbl_status.setStyleSheet(
                "padding: 8px; background-color: #FFF3CD; "
                "color: #664D03; border: 1px solid #FFECB5; border-radius: 4px;"
            )
        if v1_present:
            msg += (
                "<br><br><span style='color:#6C757D;'>Nota: también detectamos "
                "el Autopilot v1 instalado. Convivirán sin problemas.</span>"
            )
        self.lbl_status.setText(msg)

    def _detect_v1(self) -> bool:
        """True si el `__autopilot_config__` v1 existe en OBS. No afecta
        el flujo de v2 — solo nos permite informar al user."""
        try:
            self._ap._get_source_text(_CONFIG_SOURCE_V1)
            return True
        except Exception:
            return False

    # ----------------------------------------------------------------------
    # Export
    # ----------------------------------------------------------------------

    def _on_export_downloads(self):
        downloads = Path.home() / "Downloads"
        if not downloads.exists():
            downloads = Path.home()
        dest = downloads / "autopilot_v2.lua"
        self._do_export(dest)

    def _on_export_as(self):
        default = str(Path.home() / "Downloads" / "autopilot_v2.lua")
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar autopilot_v2.lua", default, "Script Lua (*.lua)",
        )
        if path:
            self._do_export(Path(path))

    def _do_export(self, dest: Path):
        source = autopilot_v2_lua_path()
        if not source.exists():
            QMessageBox.critical(
                self, "Error",
                f"No se encontró el script embebido en:\n{source}\n\n"
                "Si estás corriendo desde un .exe, puede faltar el bundle "
                "obs_scripts en el .spec de PyInstaller.",
            )
            return
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        except Exception as e:
            QMessageBox.critical(
                self, "Error al exportar", f"{dest}\n\n{e}",
            )
            return
        QMessageBox.information(
            self, "Exportado",
            f"Script copiado a:\n{dest}\n\n"
            "Ahora cárgalo en OBS: Herramientas → Scripts → +",
        )
        log.info("autopilot_v2.lua exportado a %s", dest)

    # ----------------------------------------------------------------------
    # Verify
    # ----------------------------------------------------------------------

    def _on_verify(self):
        if self._ap.is_installed():
            version = self._ap.script_version() or "?"
            state = self._ap.read_state() or {}
            mode = state.get("mode") or "?"
            canales = state.get("canales") or []
            QMessageBox.information(
                self, "Instalación verificada",
                f"✅ Autopilot v{version} corriendo en OBS.\n\n"
                f"Modo actual: {mode}\n"
                f"Canales conocidos: {len(canales)}\n\n"
                "Al cerrar la app, el script tomará control después de "
                "30 segundos.",
            )
        else:
            QMessageBox.warning(
                self, "No instalado todavía",
                "No encontramos los buzones del script v2 en OBS.\n\n"
                "Verifica que:\n"
                "• El archivo autopilot_v2.lua está cargado en "
                "Herramientas → Scripts.\n"
                "• No hay mensajes de error en el log del script.\n"
                "• Esta app está conectada a OBS (indicador verde en la "
                "barra inferior).",
            )
        self._refresh_status()
