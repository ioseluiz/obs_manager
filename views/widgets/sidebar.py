"""Sidebar vertical oscuro del rediseno UI.

Reemplaza al QTabWidget horizontal del MainWindow. Items navegables
apilados verticalmente, item activo marcado con una barra roja de
3px a la izquierda. Logo CP al pie.

Expone la senal `section_selected(int)` que el MainWindow conecta al
`QStackedWidget.setCurrentIndex` para cambiar la pagina visible.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from views.theme import COLORS, SPACING
from views.theme.icons import icon

# Logo del Canal procesado desde `CP_RGB_p_VerAlt (1).jpg` por el
# script del commit de assets: silueta blanca con fondo transparente,
# anti-aliasing preservado via alpha = 255 - luminosidad.
_LOGO_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "assets"
    / "logo_canal_blanco_transparent.png"
)

SIDEBAR_WIDTH = 240
ITEM_HEIGHT = 48
ICON_SIZE = 20


class _SectionButton(QPushButton):
    """Item navegable del sidebar — texto + icono blanco a la izquierda."""

    def __init__(self, name: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setText(f"  {name}")
        self.setIcon(icon(icon_name, color="#FFFFFF"))
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(ITEM_HEIGHT)
        self.setStyleSheet(self._qss())

    @staticmethod
    def _qss() -> str:
        c = COLORS
        s = SPACING
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {c["text_inverse"]};
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding: 0 {s["lg"]}px 0 {s["lg"]}px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 25);
            }}
            QPushButton:checked {{
                background-color: rgba(255, 255, 255, 40);
                border-left: 3px solid {c["brand_red"]};
                font-weight: bold;
            }}
        """


class Sidebar(QWidget):
    """Panel vertical izquierdo con items navegables + logo al pie."""

    section_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"Sidebar {{ background-color: {COLORS['brand_navy_dark']}; }}"
        )

        self._items: list[_SectionButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.section_selected)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, SPACING["lg"], 0, SPACING["lg"])
        root.setSpacing(SPACING["xs"])

        # Espaciado superior para alinear con el header de la ventana.
        root.addSpacing(SPACING["xl"])

        self._items_layout = QVBoxLayout()
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(SPACING["xs"])
        root.addLayout(self._items_layout)

        root.addStretch(1)

        # Logo CP al pie.
        root.addWidget(self._build_logo())

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def add_section(self, name: str, icon_name: str) -> int:
        """Agrega un item navegable al sidebar. Devuelve su indice."""
        idx = len(self._items)
        btn = _SectionButton(name, icon_name, self)
        self._items.append(btn)
        self._group.addButton(btn, idx)
        self._items_layout.addWidget(btn)
        if idx == 0:
            btn.setChecked(True)
        return idx

    def set_active(self, index: int) -> None:
        """Marca el item `index` como activo."""
        if 0 <= index < len(self._items):
            self._items[index].setChecked(True)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _build_logo(self) -> QWidget:
        container = QFrame(self)
        container.setStyleSheet("QFrame { background-color: transparent; border: none; }")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(SPACING["lg"], SPACING["sm"],
                                    SPACING["lg"], 0)
        layout.setSpacing(SPACING["xs"])
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        logo = QLabel(container)
        pix = QPixmap(str(_LOGO_PATH))
        if not pix.isNull():
            logo.setPixmap(pix.scaledToWidth(
                140, Qt.TransformationMode.SmoothTransformation))
            logo.setStyleSheet("background: transparent;")
        else:
            logo.setText("CANAL DE PANAMÁ")
            logo.setStyleSheet(
                f"background: transparent; color: {COLORS['text_inverse']}; "
                "font-weight: bold; letter-spacing: 1px;"
            )
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        subtitle = QLabel("DIVISIÓN DE INGENIERÍA", container)
        subtitle.setStyleSheet(
            "background: transparent; color: rgba(255, 255, 255, 180); "
            "font-size: 10px; letter-spacing: 2px;"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        return container
