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

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


_ROTATOR_POLL_MS = 500


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
        # Poll el estado del rotador desde SceneController para reflejarlo
        # aquí: SceneView (donde vive el feedback original) está en modo
        # compacto y sus widgets ocultos, así que este panel se encarga
        # de mostrar el estado.
        self._rotator_poll = QTimer(self)
        self._rotator_poll.setInterval(_ROTATOR_POLL_MS)
        self._rotator_poll.timeout.connect(self._refresh_rotator_status)
        self._rotator_poll.start()
        # Primer refresh inmediato para no esperar 500ms al mostrar el widget
        self._refresh_rotator_status()

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

        # Estado del rotador global (running/paused/stopped + escena activa)
        # — se actualiza por poll del SceneController cada 500 ms.
        self.lbl_rotator = QLabel("Rotador: Detenido")
        self.lbl_rotator.setStyleSheet("color: #495057; font-weight: bold;")

        header_layout.addWidget(self.lbl_nombre)
        header_layout.addWidget(self.lbl_url)
        header_layout.addWidget(self.lbl_status)
        header_layout.addWidget(self.lbl_timecode)
        header_layout.addWidget(self.lbl_rotator)
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

    # ------------------------------------------------------------------
    # Poll del estado del rotador legacy
    # ------------------------------------------------------------------

    def _refresh_rotator_status(self) -> None:
        """Lee el estado del SceneController y refleja: lbl_rotator + btn_pause."""
        sc = self._scene_controller
        # Atributos que expone SceneController: timer (QTimer), is_paused (bool),
        # active_scene_name (str), time_left (int).
        try:
            timer = getattr(sc, "timer", None)
            is_running = bool(timer is not None and timer.isActive())
            is_paused = bool(getattr(sc, "is_paused", False))
            active_name = getattr(sc, "active_scene_name", None) or ""
            time_left = getattr(sc, "time_left", None)
        except Exception:
            return  # scene_controller aún no está listo o no expone estado

        if is_paused:
            self.lbl_rotator.setText(
                f"Rotador: ⏸ Pausado en «{active_name}»"
                + (f" ({time_left}s restantes)" if time_left is not None else "")
            )
            self.lbl_rotator.setStyleSheet("font-weight: bold; color: #FD7E14;")
        elif is_running:
            # time_left arranca en 0 durante la fracción de segundo entre
            # que el timer arranca y update_countdown hace su primer tick;
            # también puede aparecer 0 si la escena tiene duracion 0. En
            # cualquier caso, mostrar "0s" es más informativo que ocultar
            # los segundos, porque le confirma al user que el poll funciona.
            if time_left is None:
                secs_txt = ""
            elif time_left <= 0:
                secs_txt = " (arrancando…)"
            else:
                secs_txt = f" ({time_left}s restantes)"
            self.lbl_rotator.setText(
                f"Rotador: ▶ Reproduciendo «{active_name}»{secs_txt}"
            )
            self.lbl_rotator.setStyleSheet("font-weight: bold; color: #198754;")
        else:
            self.lbl_rotator.setText("Rotador: ⏹ Detenido")
            self.lbl_rotator.setStyleSheet("font-weight: bold; color: #6C757D;")

        # Sincronizar el checkable btn_pause con el estado real
        self.btn_pause.blockSignals(True)
        self.btn_pause.setChecked(is_paused)
        self.btn_pause.blockSignals(False)
