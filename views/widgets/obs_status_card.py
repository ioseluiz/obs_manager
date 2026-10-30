"""OBS connection details with a compact layout for laptop screens."""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from views.theme import COLORS
from views.theme.icons import apply_icon
from views.widgets.brand_image import BrandImage

_LOGO = Path(__file__).resolve().parents[2] / "assets" / "logo_obs_studio_referencia.png"


class ObsStatusCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeObsCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#HomeObsCard {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; border-radius: 10px; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(16, 16, 16, 16)
        col.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("Estado de OBS Studio")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.badge = QLabel()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.badge)
        col.addLayout(header)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {COLORS['border_default']}; border: none;")
        col.addWidget(line)

        self.body = QGridLayout()
        self.body.setHorizontalSpacing(12)
        self.body.setVerticalSpacing(12)
        self.logo = BrandImage(_LOGO, 92, 100)
        self.logo.setAccessibleName("Logo de OBS Studio")
        self.body.addWidget(self.logo, 0, 0, Qt.AlignmentFlag.AlignTop)
        details = QWidget()
        details.setStyleSheet("background: transparent;")
        grid = QGridLayout(details)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.version = QLabel("OBS Studio")
        self.version.setWordWrap(True)
        self.version.setStyleSheet(f"font-weight: bold; color: {COLORS['brand_navy']};")
        grid.addWidget(self.version, 0, 0, 1, 2)
        self.values = {}
        for row, (key, caption) in enumerate([
            ("address", "Dirección:"), ("profile", "Perfil:"),
            ("scenes", "Escenas cargadas:"), ("elapsed", "Tiempo conectado:"),
        ], 1):
            label = QLabel(caption)
            label.setStyleSheet(f"font-size: 12px; color: {COLORS['brand_navy']};")
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
            grid.addWidget(label, row, 0)
            grid.addWidget(value, row, 1)
            self.values[key] = value
        grid.setColumnStretch(1, 1)
        self.body.addWidget(details, 0, 1)
        self.body.setColumnStretch(1, 1)

        self.actions = QWidget()
        self.actions.setStyleSheet("background: transparent;")
        self.action_layout = QVBoxLayout(self.actions)
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        self.action_layout.setSpacing(8)
        self.btn_settings = QPushButton(" Configuración")
        self.btn_disconnect = QPushButton(" Desconectar")
        for button, name in [(self.btn_settings, "configuracion"),
                             (self.btn_disconnect, "conectar")]:
            apply_icon(button, name, color=COLORS['brand_navy'])
            button.setMinimumHeight(36)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(f"""
                QPushButton {{ background: #F1F4F8; color: {COLORS['brand_navy']};
                    border: 1px solid {COLORS['border_default']}; border-radius: 6px;
                    font-size: 12px; font-weight: 500; }}
                QPushButton:hover {{ background: #E3ECF5; }}
                QPushButton:disabled {{ color: {COLORS['text_muted']}; background: {COLORS['bg_app']}; }}
            """)
            self.action_layout.addWidget(button)
        self.body.addWidget(self.actions, 1, 0, 1, 2)
        col.addLayout(self.body)
        col.addStretch()
        self._wide = None
        self.set_status(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        wide = self.width() >= 560
        if wide == self._wide:
            return
        self._wide = wide
        self.body.removeWidget(self.actions)
        # Botones a la derecha en escritorio; debajo en paneles estrechos.
        self.action_layout.setDirection(
            QVBoxLayout.Direction.TopToBottom if wide else QVBoxLayout.Direction.LeftToRight)
        if wide:
            self.body.addWidget(self.actions, 0, 2)
        else:
            self.body.addWidget(self.actions, 1, 0, 1, 2)

    def set_status(self, connected, version="", host="", port=0,
                   scene_count=None, profile="", connected_seconds=None):
        color = COLORS['state_success'] if connected else COLORS['state_muted']
        self.badge.setText("● Conectado" if connected else "● Desconectado")
        self.badge.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
        self.version.setText(f"OBS Studio {version}" if version and connected else "OBS Studio")
        self.version.setToolTip("Versión del OBS conectado" if version else "La versión se consulta al conectar a OBS")
        self.values['address'].setText(f"{host}:{port}" if host and port else "—")
        self.values['profile'].setText(profile if connected and profile else "—")
        self.values['scenes'].setText(str(scene_count) if connected and scene_count is not None else "—")
        elapsed = "—"
        if connected and connected_seconds is not None:
            minutes = max(0, int(connected_seconds)) // 60
            elapsed = f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"
        self.values['elapsed'].setText(elapsed)
        self.btn_disconnect.setEnabled(connected)
