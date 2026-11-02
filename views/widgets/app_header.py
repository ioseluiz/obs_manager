"""Cabecera superior blanca del rediseno UI.

Lado izquierdo: logo app ("OBS Automation Manager / Division de
Ingenieria") con icono de monitor.
Lado derecho: branding "CANAL DE PANAMA" con franjas decorativas.
Botones de accion (Ajustes / Conectar / Exportar / Importar) viven
aqui tambien — se mueven desde el toolbar superior antiguo.

El header es parte del shell: lo usa el MainWindow pero no sabe de
pestanas ni de contenido. Expone los QPushButton como atributos
publicos (`btn_settings`, `btn_connect`, `btn_export`, `btn_import`)
para que el MainController los conecte igual que antes.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from views.theme import COLORS, SPACING
from views.theme.icons import apply_icon
from views.widgets.brand_image import BrandImage

_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"
_LOGO_APP = _ASSETS / "icono_app_tv.png"
_LOGO_CP = _ASSETS / "CP_hor_800px (1).png"

HEADER_HEIGHT = 72


class AppHeader(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(HEADER_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"AppHeader {{ background-color: {COLORS['bg_panel']}; "
            f"border-bottom: 1px solid {COLORS['border_default']}; }}"
        )

        self._root = QGridLayout(self)
        self._root.setContentsMargins(SPACING["xl"], SPACING["sm"], SPACING["xl"], SPACING["sm"])
        self._root.setHorizontalSpacing(SPACING["lg"])
        self._root.setVerticalSpacing(SPACING["sm"])
        self._app_logo = self._build_app_logo()
        self._actions = self._build_actions()
        self._cp_brand = self._build_cp_brand()
        self._root.addWidget(self._app_logo, 0, 0, Qt.AlignmentFlag.AlignLeft)
        self._root.addWidget(self._actions, 0, 1)
        self._root.addWidget(self._cp_brand, 0, 2)
        self._root.setColumnStretch(0, 1)
        self._two_rows = None

    # ------------------------------------------------------------------
    # Secciones del header
    # ------------------------------------------------------------------

    def _build_app_logo(self) -> QWidget:
        container = QFrame(self)
        container.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
        )
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING["md"])

        icon_label = QLabel(container)
        icon_label.setFixedSize(40, 40)
        pix = QPixmap(str(_LOGO_APP))
        if not pix.isNull():
            icon_label.setPixmap(pix.scaledToHeight(
                40, Qt.TransformationMode.SmoothTransformation))
        row.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        title = QLabel("OBS Automation Manager", container)
        self._app_title = title
        title.setStyleSheet(
            f"color: {COLORS['text_primary']}; "
            "font-size: 18px; font-weight: bold;"
        )
        subtitle = QLabel("División de Ingeniería", container)
        self._app_subtitle = subtitle
        subtitle.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px;"
        )
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        row.addLayout(text_col)

        return container

    def _build_actions(self) -> QWidget:
        container = QFrame(self)
        container.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
        )
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING["sm"])

        self.btn_settings = QPushButton(" Ajustes", container)
        self.btn_settings.setToolTip("Ajustes")
        self.btn_connect = QPushButton(" Conectar OBS", container)
        self.btn_connect.setToolTip("Conectar a OBS")
        self.btn_export = QPushButton(" Exportar", container)
        self.btn_export.setToolTip("Exportar todas las escenas a un archivo JSON")
        self.btn_import = QPushButton(" Importar", container)
        self.btn_import.setToolTip("Importar escenas desde un archivo JSON")

        for b in (self.btn_settings, self.btn_connect,
                   self.btn_export, self.btn_import):
            b.setMinimumHeight(36)
            b.setMinimumWidth(b.sizeHint().width())
            b.setStyleSheet(f"""
                QPushButton {{ background: {COLORS['toolbar_primary']}; color: white; }}
                QPushButton:hover {{ background: {COLORS['toolbar_hover']}; }}
                QPushButton:pressed {{ background: {COLORS['toolbar_pressed']}; }}
                QPushButton:disabled {{ background: {COLORS['bg_muted']}; color: {COLORS['text_muted']}; }}
            """)
            row.addWidget(b)

        # Iconos corporativos tintados en blanco (fondo primary azul).
        apply_icon(self.btn_settings, "configuracion", color="#FFFFFF")
        apply_icon(self.btn_connect, "conectar", color="#FFFFFF")
        apply_icon(self.btn_export, "subir", color="#FFFFFF")
        apply_icon(self.btn_import, "bajar", color="#FFFFFF")

        return container

    def _build_cp_brand(self) -> QWidget:
        container = QFrame(self)
        container.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
        )
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING["sm"])

        logo = BrandImage(_LOGO_CP, 240, 44, container)
        row.addWidget(logo)

        return container

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "_two_rows"):
            return
        two_rows = self.width() < 740
        self._app_title.setVisible(self.width() >= 1100)
        self._app_subtitle.setVisible(self.width() >= 1100)
        if two_rows == self._two_rows:
            return
        self._two_rows = two_rows
        for widget in (self._app_logo, self._actions, self._cp_brand):
            self._root.removeWidget(widget)
        if two_rows:
            self.setFixedHeight(116)
            self._root.addWidget(self._app_logo, 0, 0, Qt.AlignmentFlag.AlignLeft)
            self._root.addWidget(self._cp_brand, 0, 1, Qt.AlignmentFlag.AlignRight)
            self._root.addWidget(self._actions, 1, 0, 1, 2)
        else:
            self.setFixedHeight(HEADER_HEIGHT)
            self._root.addWidget(self._app_logo, 0, 0, Qt.AlignmentFlag.AlignLeft)
            self._root.addWidget(self._actions, 0, 1)
            self._root.addWidget(self._cp_brand, 0, 2)
