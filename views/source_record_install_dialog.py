"""Asistente para instalar / verificar el plugin Source Record en OBS.

Misma forma que el dialogo del Autopilot v2: una ventana con el estado
actual, instrucciones y botones. Tres acciones:

- Instalar en este OBS: solo si OBS corre en esta maquina (host local) y
  se localiza obs64.exe. Copia el plugin embebido al lugar correcto segun
  instalado/portable y version (core.source_record_installer). Despues
  hay que cerrar y abrir OBS: la app lo verifica al reconectar.
- Exportar paquete: zip con la estructura lista para un OBS remoto.
- Verificar: pregunta a OBS si el filtro `source_record_filter` existe.

Uso: `SourceRecordInstallDialog(obs_client, settings, is_local, parent).exec()`.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextEdit,
    QVBoxLayout,
)

from core import source_record_installer as sri
from views.widgets.responsive_dialog import ResponsiveDialog

log = logging.getLogger(__name__)

_STYLE_OK = ("padding: 8px; background-color: #D1E7DD; color: #0F5132; "
             "border: 1px solid #BADBCC; border-radius: 4px;")
_STYLE_WARN = ("padding: 8px; background-color: #FFF3CD; color: #664D03; "
               "border: 1px solid #FFECB5; border-radius: 4px;")
_STYLE_INFO = ("padding: 8px; background-color: #E2E3E5; color: #41464B; "
               "border: 1px solid #D3D6D8; border-radius: 4px;")


class SourceRecordInstallDialog(ResponsiveDialog):
    def __init__(self, obs_client, settings: dict | None = None,
                 is_local: bool = True, parent=None):
        super().__init__(parent)
        self._obs = obs_client
        self._settings = settings or {}
        self._is_local = bool(is_local)
        self._local = sri.detect_local_obs(self._settings.get("obs_exe_path")) if self._is_local else None
        self.setWindowTitle("Plugin Source Record para OBS")
        self.setMinimumSize(660, 500)

        layout = QVBoxLayout(self)

        header = QLabel(
            "<b>Source Record</b> es el plugin de OBS (Exeldro, GPL-2.0) que permite "
            "que cada canal emita su propia salida UDP. Sin él, los canales "
            "multi-salida no pueden transmitir. Esta app lo lleva embebido "
            f"(versión {sri.PLUGIN_VERSION})."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        self.lbl_context = QLabel()
        self.lbl_context.setWordWrap(True)
        self.lbl_context.setProperty("role", "status-muted")
        layout.addWidget(self.lbl_context)

        instr = QTextEdit()
        instr.setReadOnly(True)
        instr.setHtml(
            "<p><b>Si OBS corre en este equipo:</b> pulsa <b>Instalar en este OBS</b>. "
            "La app copia el plugin al lugar correcto (instalación normal o portable, "
            "según la versión de OBS). Después <b>cierra y vuelve a abrir OBS</b>; "
            "al reconectar, la app comprueba que el plugin cargó.</p>"
            "<p><b>Si OBS corre en otro equipo:</b> pulsa <b>Exportar paquete</b>, "
            "lleva el zip a ese equipo y sigue el <code>LEEME.txt</code> que viene "
            "dentro (dice exactamente dónde descomprimirlo). Reinicia OBS allá y "
            "pulsa <b>Verificar</b> aquí.</p>"
            "<p style='color:#6C757D;'>Para comprobarlo a mano en OBS: clic derecho en "
            "una escena → Filtros → Añadir filtro → debe aparecer \"Source Record\".</p>"
        )
        layout.addWidget(instr)

        btn_row = QHBoxLayout()
        self.btn_install = QPushButton("🔌 Instalar en este OBS")
        self.btn_install.setProperty("role", "primary")
        self.btn_export = QPushButton("📦 Exportar paquete para OBS remoto…")
        self.btn_verify = QPushButton("🔎 Verificar")
        self.btn_verify.setProperty("role", "success")
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.setProperty("role", "muted")
        btn_row.addWidget(self.btn_install)
        btn_row.addWidget(self.btn_export)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_verify)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        self.btn_install.clicked.connect(self._on_install)
        self.btn_export.clicked.connect(self._on_export)
        self.btn_verify.clicked.connect(self._on_verify)
        self.btn_close.clicked.connect(self.accept)

        self._refresh_status()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def _obs_version(self) -> tuple[int, int, int] | None:
        """Versión de OBS vía WebSocket si hay conexión; si no, la del .exe local."""
        client = getattr(self._obs, "client", None)
        if client is not None:
            try:
                resp = client.get_version()
                parsed = sri.parse_version(getattr(resp, "obs_version", ""))
                if parsed:
                    return parsed
            except Exception as exc:
                log.debug("get_version falló: %s", exc)
        return self._local.version if self._local else None

    def _refresh_status(self) -> None:
        present = None
        try:
            present = self._obs.has_source_record()
        except Exception as exc:
            log.debug("has_source_record falló: %s", exc)
        if present is True:
            self.lbl_status.setText("✅ El plugin Source Record está cargado en OBS.")
            self.lbl_status.setStyleSheet(_STYLE_OK)
        elif present is False:
            self.lbl_status.setText(
                "⚠ OBS está conectado pero el plugin Source Record NO está cargado. "
                "Los canales multi-salida no funcionarán hasta instalarlo."
            )
            self.lbl_status.setStyleSheet(_STYLE_WARN)
        else:
            self.lbl_status.setText(
                "ℹ Sin conexión a OBS: no se puede comprobar si el plugin está cargado. "
                "Puedes instalarlo o exportar el paquete igualmente."
            )
            self.lbl_status.setStyleSheet(_STYLE_INFO)

        host = str(self._settings.get("host") or "")
        if self._is_local:
            if self._local:
                self.lbl_context.setText(f"OBS en este equipo: {self._local.describe()}")
            else:
                self.lbl_context.setText(
                    "OBS en este equipo, pero no se encontró obs64.exe (ni corriendo, ni en "
                    "el registro). Al pulsar Instalar podrás elegir el archivo obs64.exe."
                )
        else:
            self.lbl_context.setText(
                f"OBS remoto en {host or '?'}: solo es posible exportar el paquete."
            )
        bundled = sri.is_bundled()
        # Con OBS local el boton siempre esta activo: si aun no sabemos donde
        # esta obs64.exe, al pulsarlo se pide elegirlo (un boton gris sin
        # explicacion parece "no funciona").
        self.btn_install.setEnabled(self._is_local and bundled)
        self.btn_export.setEnabled(bundled)
        if not bundled:
            tip = ("El plugin no viene embebido en esta copia (falta vendor/source-record). "
                   "Si corres desde código fuente, ejecuta scripts\\bundle_source_record.py.")
        elif not self._is_local:
            tip = "OBS está en otro equipo: usa Exportar paquete."
        elif self._local is None:
            tip = "Se te pedirá la ubicación de obs64.exe."
        else:
            tip = f"Instala Source Record {sri.PLUGIN_VERSION} en {self._local.root}"
        self.btn_install.setToolTip(tip)

    def _ask_obs_executable(self) -> bool:
        """Pide al usuario el obs64.exe cuando no se pudo detectar. True si quedó fijado."""
        QMessageBox.information(
            self, "Ubicar OBS Studio",
            "No se encontró automáticamente el obs64.exe de este equipo (es normal con "
            "OBS portable cerrado). Selecciona el archivo obs64.exe de tu instalación "
            "(normalmente en <carpeta de OBS>\\bin\\64bit\\obs64.exe).",
        )
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona obs64.exe", "", "OBS Studio (obs64.exe);;Ejecutables (*.exe)",
        )
        if not path:
            return False
        local = sri.detect_local_obs(path)
        if local is None:
            QMessageBox.warning(self, "Archivo no válido", f"No se pudo usar:\n{path}")
            return False
        self._local = local
        self._refresh_status()
        return True

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _on_install(self) -> None:
        if self._local is None and not self._ask_obs_executable():
            return
        plan = sri.plan_install(self._local, obs_version=self._obs_version())
        answer = QMessageBox.question(
            self, "Instalar Source Record",
            f"Se instalará Source Record {sri.PLUGIN_VERSION} en:\n{plan.dll_target.parent}\n\n"
            f"({plan.description})\n\n¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        ok, msg = sri.install(plan)
        if ok:
            QMessageBox.information(
                self, "Plugin instalado",
                f"{msg}\n\nAhora CIERRA y vuelve a abrir OBS Studio para que cargue el "
                "plugin. Al reconectar, la app verificará que está disponible.",
            )
        else:
            QMessageBox.warning(self, "No se pudo instalar", msg)
        self._refresh_status()

    def _downloads_dir(self) -> Path:
        downloads = Path.home() / "Downloads"
        return downloads if downloads.exists() else Path.home()

    def _on_export(self) -> None:
        version = self._obs_version()
        major = version[0] if version else None
        if major is None:
            answer = QMessageBox.question(
                self, "Versión de OBS",
                "No se pudo detectar la versión de OBS del destino.\n\n"
                "¿El OBS remoto es la versión 33 o superior?\n"
                "(Sí = estructura nueva · No = OBS 32 o anterior)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            major = sri.NEW_LAYOUT_MIN_MAJOR if answer == QMessageBox.StandardButton.Yes else sri.NEW_LAYOUT_MIN_MAJOR - 1
        try:
            out = sri.export_package(self._downloads_dir(), major)
        except Exception as exc:
            QMessageBox.critical(self, "Error al exportar", str(exc))
            return
        QMessageBox.information(
            self, "Paquete exportado",
            f"Paquete guardado en:\n{out}\n\nLlévalo al equipo donde corre OBS y sigue "
            "el LEEME.txt incluido. Después reinicia OBS allá y pulsa Verificar aquí.",
        )

    def _on_verify(self) -> None:
        present = None
        try:
            present = self._obs.has_source_record()
        except Exception as exc:
            log.debug("has_source_record falló: %s", exc)
        if present is True:
            QMessageBox.information(self, "Plugin verificado",
                                    "✅ Source Record está cargado en OBS. Los canales "
                                    "multi-salida pueden transmitir.")
        elif present is False:
            QMessageBox.warning(self, "Plugin no detectado",
                                "OBS está conectado pero no expone el filtro Source Record.\n\n"
                                "Verifica que:\n• Instalaste el plugin en el lugar correcto.\n"
                                "• Cerraste y volviste a abrir OBS después de instalarlo.\n"
                                "• La versión del plugin corresponde a tu versión de OBS.")
        else:
            QMessageBox.information(self, "Sin conexión",
                                    "Conéctate a OBS (botón Conectar) para poder verificar.")
        self._refresh_status()
