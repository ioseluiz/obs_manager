"""Sidebar vertical oscuro del rediseno UI.

Reemplaza al QTabWidget horizontal del MainWindow. Items navegables
apilados verticalmente, item activo marcado con una barra roja de
3px a la izquierda. Fotografía del Canal con su branding al pie.

Expone la senal `section_selected(int)` que el MainWindow conecta al
`QStackedWidget.setCurrentIndex` para cambiar la pagina visible.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from views.theme import COLORS, SPACING
from views.theme.icons import icon

_BACKGROUND_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "assets"
    / "Canal de Panamá en azul profundo.png"
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
                background-color: rgba(32, 89, 139, 190);
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
        self._background = QPixmap(str(_BACKGROUND_PATH))

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

        # La imagen original ya incluye el logo y el crédito de Ingeniería.

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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(COLORS['brand_navy_dark']))
        if self._background.isNull():
            return
        # Ajustar por ancho conserva la foto y el branding completos al pie.
        height = self.width() * self._background.height() / self._background.width()
        top = self.height() - height
        painter.drawPixmap(QRectF(0, top, self.width(), height),
                           self._background, QRectF(self._background.rect()))
        fade = QLinearGradient(0, top, 0, top + height * 0.35)
        fade.setColorAt(0, QColor(COLORS['brand_navy_dark']))
        fade.setColorAt(1, QColor(10, 31, 61, 0))
        painter.fillRect(QRectF(0, top, self.width(), height * 0.35), fade)
