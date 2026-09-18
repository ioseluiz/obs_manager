"""Wizard visual de instalación del Autopilot (AUT-3).

Se abre desde Ajustes → botón "🚀 Instalar Autopilot en OBS". Guía al
técnico paso a paso para dejar el `autopilot.lua` cargado en el OBS
remoto del servidor.

Estructura: QDialog modal con QStackedWidget interno para las páginas.
Botones Atrás / Siguiente / Finalizar / Cancelar arriba a la derecha.

Páginas:
1. Bienvenida — explica qué va a pasar.
2. Detección — chequea si ya está instalado (via AutopilotClient).
3. Exportar — botón "Guardar autopilot.lua en Descargas" (con file dialog).
4. Registrar en OBS — instrucciones + botón para copiar la ruta destino.
5. Verificar — botón "Verificar ahora" que llama is_installed().
6. Éxito — feedback final.

El dialog NO usa QWizard porque queremos control fino sobre navegación
y el estado (por ejemplo, saltar la página de export si ya está instalado
correctamente).
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from core.autopilot_client import AutopilotClient
from core.autopilot_paths import autopilot_lua_path, default_downloads_dir

log = logging.getLogger(__name__)


class AutopilotInstallDialog(QDialog):
    """Wizard de instalación del Autopilot."""

    def __init__(self, obs_client, parent=None):
        """
        obs_client: instancia de OBSClient con conexión activa. Se usa
            para chequear presencia del script y verificar tras la
            instalación. Si no está conectado, el wizard sigue funcionando
            pero la detección/verificación queda deshabilitada.
        """
        super().__init__(parent)
        self._obs = obs_client
        self._autopilot = AutopilotClient(obs_client)
        self._exported_path: Optional[Path] = None
        self._verified_ok = False
        self._setup_ui()
        self._go_to(0)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        self.setWindowTitle("Instalar Autopilot en OBS")
        self.setModal(True)
        self.resize(680, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # Header con el título del paso actual
        self.lbl_step = QLabel("")
        f = QFont(); f.setBold(True); f.setPointSize(15)
        self.lbl_step.setFont(f)
        root.addWidget(self.lbl_step)

        # Sub-header con progreso "Paso X de Y"
        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet("color: #6C757D;")
        root.addWidget(self.lbl_progress)

        # Contenido del paso (QStackedWidget)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_welcome())
        self.stack.addWidget(self._page_detect())
        self.stack.addWidget(self._page_export())
        self.stack.addWidget(self._page_register())
        self.stack.addWidget(self._page_verify())
        self.stack.addWidget(self._page_success())
        root.addWidget(self.stack, 1)

        # Botonera de navegación
        nav = QHBoxLayout()
        self.btn_back = QPushButton("← Atrás")
        self.btn_next = QPushButton("Siguiente →")
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_back.clicked.connect(self._on_back)
        self.btn_next.clicked.connect(self._on_next)
        self.btn_cancel.clicked.connect(self.reject)
        nav.addWidget(self.btn_cancel)
        nav.addStretch(1)
        nav.addWidget(self.btn_back)
        nav.addWidget(self.btn_next)
        root.addLayout(nav)

    # ------------------------------------------------------------------
    # Páginas
    # ------------------------------------------------------------------

    _STEPS = [
        ("Bienvenida", ""),
        ("Detectar instalación existente", ""),
        ("Guardar el script", "Copiar el archivo del Autopilot a la laptop"),
        ("Copiar al servidor y registrar en OBS", ""),
        ("Verificar instalación", ""),
        ("¡Listo!", ""),
    ]

    def _page_welcome(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        body = QLabel(
            "El <b>Autopilot</b> es un pequeño componente que se instala una "
            "vez en el OBS del servidor. Su única función es <b>mantener la "
            "rotación de escenas activa cuando esta app se cierra o cuando "
            "la laptop se apaga</b>.<br><br>"
            "Sin él, si apagás la laptop al final del día, OBS deja la última "
            "escena congelada y no rota más. Con él, la rotación sigue en el "
            "servidor 24/7.<br><br>"
            "Esta instalación se hace <b>una sola vez</b>. Después, la app "
            "se encarga sola de mantener el Autopilot sincronizado."
        )
        body.setWordWrap(True)
        v.addWidget(body)

        info = QLabel(
            "El proceso tiene <b>4 pasos rápidos</b> y toma unos 3 minutos. "
            "Te vamos a guiar paso a paso — no necesitás conocimientos "
            "técnicos avanzados."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #495057; padding: 10px; background-color: #E7F3FE; border-radius: 4px;")
        v.addWidget(info)

        v.addStretch(1)
        return w

    def _page_detect(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        self.lbl_detect_status = QLabel("Chequeando…")
        self.lbl_detect_status.setStyleSheet("font-weight: bold; font-size: 14px;")
        v.addWidget(self.lbl_detect_status)

        self.lbl_detect_detail = QLabel("")
        self.lbl_detect_detail.setWordWrap(True)
        self.lbl_detect_detail.setStyleSheet("color: #495057;")
        v.addWidget(self.lbl_detect_detail)

        btn_row = QHBoxLayout()
        self.btn_recheck = QPushButton("↻ Re-detectar")
        self.btn_recheck.clicked.connect(self._detect)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_recheck)
        v.addLayout(btn_row)

        v.addStretch(1)
        return w

    def _page_export(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        body = QLabel(
            "Vamos a guardar el archivo <b>autopilot.lua</b> en tu laptop. "
            "En el próximo paso lo vas a copiar al servidor de OBS "
            "(por RDP, USB o cualquier método que uses habitualmente)."
        )
        body.setWordWrap(True)
        v.addWidget(body)

        btn_row = QHBoxLayout()
        self.btn_save_to_downloads = QPushButton("💾 Guardar en Descargas")
        self.btn_save_to_downloads.setMinimumHeight(40)
        self.btn_save_to_downloads.clicked.connect(self._save_to_downloads)
        self.btn_save_as = QPushButton("Guardar en otra carpeta…")
        self.btn_save_as.clicked.connect(self._save_as)
        btn_row.addWidget(self.btn_save_to_downloads)
        btn_row.addWidget(self.btn_save_as)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.lbl_export_result = QLabel("")
        self.lbl_export_result.setWordWrap(True)
        self.lbl_export_result.setStyleSheet(
            "color: #198754; font-weight: bold; padding: 10px; "
            "background-color: #d1e7dd; border-radius: 4px;"
        )
        self.lbl_export_result.setVisible(False)
        v.addWidget(self.lbl_export_result)

        v.addStretch(1)
        return w

    def _page_register(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        body = QLabel(
            "En el servidor donde corre OBS, hacé estos 4 pasos:<br><br>"
            "1. Copiá <b>autopilot.lua</b> (el archivo que guardaste) al "
            "servidor. Podés usar <b>RDP + copiar/pegar</b>, USB, email, "
            "OneDrive o el método que uses habitualmente.<br><br>"
            "2. Poné el archivo en cualquier carpeta accesible del servidor. "
            "Recomendamos crear una carpeta <b>scripts</b> al lado del "
            "ejecutable de OBS.<br><br>"
            "3. Abrí <b>OBS Studio</b> en el servidor.<br><br>"
            "4. Menú <b>Herramientas → Scripts</b> → botón <b>+</b> → "
            "seleccionar el <b>autopilot.lua</b> que copiaste."
        )
        body.setWordWrap(True)
        v.addWidget(body)

        info = QLabel(
            "Después de registrarlo en OBS, en la ventana Herramientas → "
            "Scripts vas a ver la descripción <b>\"OBS Automation Manager "
            "— Autopilot\"</b>. Si aparece, ya está listo."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color: #495057; padding: 10px; background-color: #E7F3FE; "
            "border-radius: 4px;"
        )
        v.addWidget(info)

        v.addStretch(1)
        return w

    def _page_verify(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        body = QLabel(
            "Ahora vamos a verificar desde la app que el Autopilot está "
            "corriendo en OBS. Después de hacer los 4 pasos anteriores, "
            "hacé click en <b>Verificar ahora</b>."
        )
        body.setWordWrap(True)
        v.addWidget(body)

        btn_row = QHBoxLayout()
        self.btn_verify = QPushButton("✓ Verificar ahora")
        self.btn_verify.setMinimumHeight(40)
        self.btn_verify.clicked.connect(self._verify)
        btn_row.addWidget(self.btn_verify)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.lbl_verify_result = QLabel("")
        self.lbl_verify_result.setWordWrap(True)
        self.lbl_verify_result.setVisible(False)
        v.addWidget(self.lbl_verify_result)

        v.addStretch(1)
        return w

    def _page_success(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        title = QLabel("✓ Autopilot instalado correctamente")
        f = QFont(); f.setBold(True); f.setPointSize(16)
        title.setFont(f)
        title.setStyleSheet("color: #198754;")
        v.addWidget(title)

        body = QLabel(
            "El Autopilot está corriendo en el servidor. A partir de ahora, "
            "cuando cerrés la app o apagués la laptop, la rotación de "
            "escenas sigue funcionando en OBS.<br><br>"
            "No necesitás hacer nada más. La app se encarga sola de "
            "mantener el Autopilot sincronizado con tu playlist."
        )
        body.setWordWrap(True)
        v.addWidget(body)

        v.addStretch(1)
        return w

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------

    def _go_to(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        step_title, _ = self._STEPS[index]
        self.lbl_step.setText(step_title)
        self.lbl_progress.setText(f"Paso {index + 1} de {len(self._STEPS)}")

        # Ajustar botones según el paso
        self.btn_back.setVisible(index > 0 and index < len(self._STEPS) - 1)
        self.btn_cancel.setVisible(index < len(self._STEPS) - 1)
        if index == len(self._STEPS) - 1:
            self.btn_next.setText("Finalizar")
        elif index == len(self._STEPS) - 2:
            self.btn_next.setText("Terminar sin verificar")
            self.btn_next.setEnabled(True)
        else:
            self.btn_next.setText("Siguiente →")
            self.btn_next.setEnabled(True)

        # Lógica específica por página
        if index == 1:
            self._detect()
        elif index == 2:
            # Reset del estado de export si volvieron atrás
            self.lbl_export_result.setVisible(False)
            self.btn_next.setEnabled(self._exported_path is not None)
        elif index == 4:
            # Verificar reset
            self.lbl_verify_result.setVisible(False)

    def _on_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            # Si estamos en detect (idx=1) y ya está instalado, volver a welcome
            self._go_to(idx - 1)

    def _on_next(self):
        idx = self.stack.currentIndex()
        if idx == len(self._STEPS) - 1:
            self.accept()
            return
        self._go_to(idx + 1)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _detect(self):
        try:
            installed = self._autopilot.is_installed()
        except Exception as e:
            installed = False
            log.warning("is_installed() falló: %s", e)

        if installed:
            version = self._autopilot.script_version() or "?"
            self.lbl_detect_status.setText(f"✓ Autopilot ya está instalado (v{version})")
            self.lbl_detect_status.setStyleSheet("color: #198754; font-weight: bold; font-size: 14px;")
            self.lbl_detect_detail.setText(
                "El script está cargado y corriendo en OBS. Si querés "
                "re-instalarlo o actualizarlo (por ejemplo tras un update de "
                "esta app), continuá con los próximos pasos. Si no, podés "
                "cerrar este wizard."
            )
        else:
            self.lbl_detect_status.setText("⚠ Autopilot no está instalado")
            self.lbl_detect_status.setStyleSheet("color: #B02A37; font-weight: bold; font-size: 14px;")
            self.lbl_detect_detail.setText(
                "No detectamos el script corriendo en OBS. Vamos a instalarlo "
                "en los próximos pasos."
            )

    def _save_to_downloads(self):
        target = default_downloads_dir() / "autopilot.lua"
        self._export_to(target)

    def _save_as(self):
        default = default_downloads_dir() / "autopilot.lua"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Guardar autopilot.lua", str(default),
            "Script Lua (*.lua);;Todos los archivos (*)",
        )
        if path_str:
            self._export_to(Path(path_str))

    def _export_to(self, target: Path) -> None:
        try:
            source = autopilot_lua_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        except Exception as e:
            QMessageBox.critical(
                self, "Guardar", f"No se pudo guardar el archivo:\n{e}"
            )
            return
        self._exported_path = target
        self.lbl_export_result.setText(
            f"✓ Guardado en:\n{target}\n\n"
            "Ahora seguí al siguiente paso para copiarlo al servidor."
        )
        self.lbl_export_result.setVisible(True)
        self.btn_next.setEnabled(True)
        log.info("autopilot.lua exportado a %s", target)

    def _verify(self):
        try:
            installed = self._autopilot.is_installed()
        except Exception as e:
            installed = False
            log.warning("Verify falló: %s", e)

        if installed:
            version = self._autopilot.script_version() or "?"
            self.lbl_verify_result.setText(
                f"✓ Autopilot detectado correctamente (v{version}).\n\n"
                "Podés terminar el wizard."
            )
            self.lbl_verify_result.setStyleSheet(
                "color: #198754; font-weight: bold; padding: 10px; "
                "background-color: #d1e7dd; border-radius: 4px;"
            )
            self._verified_ok = True
            # Ir al paso de éxito
            self._go_to(5)
        else:
            self.lbl_verify_result.setText(
                "⚠ No se detectó el Autopilot en OBS.\n\n"
                "Verificá que:\n"
                "• OBS Studio esté abierto en el servidor.\n"
                "• Copiaste el archivo autopilot.lua al servidor.\n"
                "• En OBS: Herramientas → Scripts → + → seleccionaste el archivo.\n\n"
                "Volvé a intentar cuando lo hayas registrado."
            )
            self.lbl_verify_result.setStyleSheet(
                "color: #B02A37; font-weight: bold; padding: 10px; "
                "background-color: #f8d7da; border-radius: 4px;"
            )
        self.lbl_verify_result.setVisible(True)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def was_verified(self) -> bool:
        """True si el wizard terminó con verificación exitosa."""
        return self._verified_ok
