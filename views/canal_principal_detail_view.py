"""Panel de detalle del Canal Principal (rotador global legacy) — R-4.

En la pestaña "Producción", este es el widget que se muestra cuando el
user selecciona "Canal Principal (Global)" en el sidebar. A diferencia
de los canales regulares (`CanalDetailView`), Canal Principal usa el
mecanismo legacy: `SceneController` con `change_scene` alimentando el
recording global de OBS (Custom Output FFmpeg → UDP).

El panel expone:
- Header con nombre + descripción de mecanismo.
- Botón **▶ Transmitir** que dispara `MainController.toggle_recording`
  (el mismo del antiguo btn_record del toolbar).
- Controles ▶ ⏮ ⏸ ⏭ ⏹ que delegan a `SceneController.start_rotation`,
  `skip_previous`, `toggle_pause`, `skip_next`, `stop_rotation`.
- Info: apuntando al user a la pestaña Biblioteca para gestionar sus
  escenas (CRUD, edición, video ops, programación horaria).

El estado del botón Transmitir se sincroniza externamente via
`set_recording_ui(active, timecode)` desde MainController._sync_recording_state
y el record_timer poll.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class CanalPrincipalDetailView(QWidget):
    """Panel para el rotador legacy en la pestaña Producción."""

    def __init__(self, scene_controller,
                 on_transmit_toggle: Callable[[], None], parent=None):
        """
        scene_controller: instancia de SceneController — se usa para
            start_rotation / stop_rotation / toggle_pause / skip_next /
            skip_previous. NO se le pide su view (esa vive en Biblioteca).
        on_transmit_toggle: callback que dispara MainController.toggle_recording.
        """
        super().__init__(parent)
        self._scene_controller = scene_controller
        self._on_transmit_toggle = on_transmit_toggle
        self._is_recording = False
        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Header
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 8, 10, 8)

        self.lbl_nombre = QLabel("Canal Principal (Global)")
        f = QFont(); f.setBold(True); f.setPointSize(14)
        self.lbl_nombre.setFont(f)

        self.lbl_url = QLabel(
            "→ Recording global de OBS (Custom Output FFmpeg → UDP)"
        )
        self.lbl_url.setStyleSheet("color: #495057;")

        self.lbl_status = QLabel("● No transmitiendo")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #6C757D;")

        self.lbl_timecode = QLabel("")
        self.lbl_timecode.setStyleSheet("color: #495057; font-family: monospace;")

        header_layout.addWidget(self.lbl_nombre)
        header_layout.addWidget(self.lbl_url)
        header_layout.addWidget(self.lbl_status)
        header_layout.addWidget(self.lbl_timecode)
        root.addWidget(header_frame)

        # Controles
        toolbar = QHBoxLayout()

        self.btn_transmit = QPushButton("▶ Transmitir")
        self.btn_transmit.setCheckable(True)
        self.btn_transmit.setMinimumHeight(36)
        bold = QFont(); bold.setBold(True)
        self.btn_transmit.setFont(bold)
        self.btn_transmit.setToolTip(
            "Iniciar/detener el recording global de OBS"
        )
        toolbar.addWidget(self.btn_transmit)

        toolbar.addSpacing(20)

        self.btn_play = QPushButton("▶")
        self.btn_play.setToolTip("Iniciar rotador global")
        self.btn_prev = QPushButton("⏮")
        self.btn_prev.setToolTip("Escena anterior")
        self.btn_pause = QPushButton("⏸")
        self.btn_pause.setToolTip("Pausar / reanudar countdown")
        self.btn_next = QPushButton("⏭")
        self.btn_next.setToolTip("Escena siguiente")
        self.btn_stop = QPushButton("⏹")
        self.btn_stop.setToolTip("Detener rotador global")
        for b in (self.btn_play, self.btn_prev, self.btn_pause,
                  self.btn_next, self.btn_stop):
            b.setFixedWidth(46)
            b.setMinimumHeight(32)
            toolbar.addWidget(b)

        toolbar.addStretch(1)
        root.addLayout(toolbar)

        # Info banner
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        info_frame.setStyleSheet("background: #E7F3FE; padding: 8px;")
        info_layout = QVBoxLayout(info_frame)
        info_lbl = QLabel(
            "ℹ Las escenas del rotador global se gestionan en la pestaña "
            "<b>Biblioteca de Escenas</b>. Ahí se editan, se ordenan, se "
            "borran, se ajusta su programación horaria y se ven las "
            "miniaturas en tiempo real. Este panel opera la <b>salida</b> "
            "del rotador (Transmit) y sus <b>controles de reproducción</b>."
        )
        info_lbl.setWordWrap(True)
        info_layout.addWidget(info_lbl)
        root.addWidget(info_frame)

        root.addStretch(1)

    def _connect_signals(self):
        self.btn_transmit.clicked.connect(self._on_transmit_clicked)
        self.btn_play.clicked.connect(self._scene_controller.start_rotation)
        self.btn_prev.clicked.connect(self._scene_controller.skip_previous)
        self.btn_pause.clicked.connect(self._scene_controller.toggle_pause)
        self.btn_next.clicked.connect(self._scene_controller.skip_next)
        self.btn_stop.clicked.connect(self._scene_controller.stop_rotation)

    # ------------------------------------------------------------------
    # API pública — sincronización con MainController
    # ------------------------------------------------------------------

    def set_transmit_enabled(self, enabled: bool) -> None:
        """Habilita/deshabilita el botón Transmitir (según haya conexión OBS)."""
        self.btn_transmit.setEnabled(enabled)

    def set_recording_ui(self, active: bool, timecode: str = "00:00:00") -> None:
        """Sincroniza el UI del Transmitir con el estado real de OBS.

        MainController._sync_recording_state y el record_timer poll llaman
        esto para reflejar cambios (arrancado desde OBS, detenido, etc.).
        """
        self._is_recording = active
        self.btn_transmit.blockSignals(True)
        self.btn_transmit.setChecked(active)
        self.btn_transmit.blockSignals(False)
        if active:
            self.btn_transmit.setText("⏹ Detener transmisión")
            self.btn_transmit.setStyleSheet(
                "background-color: #DC3545; color: white; font-weight: bold;"
            )
            self.lbl_status.setText("● Transmitiendo")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #198754;")
            self.lbl_timecode.setText(f"⏱ {timecode}")
        else:
            self.btn_transmit.setText("▶ Transmitir")
            self.btn_transmit.setStyleSheet("")
            self.lbl_status.setText("● No transmitiendo")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #6C757D;")
            self.lbl_timecode.setText("")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_transmit_clicked(self):
        # Delegamos al MainController que sabe cómo manejar el estado real
        # (StartRecord/StopRecord de OBS, timer, sincronización).
        self._on_transmit_toggle()
