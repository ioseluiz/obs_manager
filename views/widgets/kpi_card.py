"""Tarjeta KPI reutilizable para la pestana Inicio.

Icono circular tintado a la izquierda + numero grande + descripcion.
Variants ajustan el color del circulo tintado:

- "blue": accent primary (default)
- "red":  rojo CP
- "green": verde ok
- "orange": naranja aviso
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from views.theme import COLORS, SPACING
from views.theme.icons import icon as load_icon


_VARIANT_BG = {
    "blue": "#E7F0FF",
    "red":  "#FFE5EA",
    "green": "#DCF4E4",
    "orange": "#FFE9D6",
}
_VARIANT_FG = {
    "blue": COLORS["brand_navy"],      # Azul marino corporativo
    "red":  COLORS["brand_red"],
    "green": COLORS["state_success"],
    "orange": COLORS["state_warning"],
}


def _circle_badge(icon_name: str, variant: str, size: int = 56) -> QLabel:
    """Pixmap con circulo de color + icono tintado en el fg del variant."""
    bg_hex = _VARIANT_BG.get(variant, _VARIANT_BG["blue"])
    fg_hex = _VARIANT_FG.get(variant, _VARIANT_FG["blue"])

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(bg_hex))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()

    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setPixmap(pm)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # Icono encima del circulo
    icon_px = load_icon(icon_name, color=fg_hex).pixmap(QSize(28, 28))
    final = QPixmap(size, size)
    final.fill(Qt.GlobalColor.transparent)
    p = QPainter(final)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.drawPixmap(0, 0, pm)
    icon_x = (size - 28) // 2
    icon_y = (size - 28) // 2
    p.drawPixmap(icon_x, icon_y, icon_px)
    p.end()
    lbl.setPixmap(final)
    lbl.setStyleSheet("background: transparent;")
    return lbl


class KpiCard(QWidget):
    def __init__(self, icon_name: str, title: str, value: str = "0",
                 subtitle: str = "", variant: str = "blue", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"KpiCard {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; "
            f"border-radius: 10px; }}"
        )
        self.setMinimumHeight(100)

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACING["lg"], SPACING["md"],
                                SPACING["lg"], SPACING["md"])
        row.setSpacing(SPACING["lg"])

        badge = _circle_badge(icon_name, variant)
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(
            f"background: transparent; color: {COLORS['text_muted']}; "
            "font-size: 12px; font-weight: 500;"
        )

        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet(
            f"background: transparent; color: {COLORS['text_primary']}; "
            "font-size: 28px; font-weight: bold;"
        )

        self.lbl_subtitle = QLabel(subtitle)
        self.lbl_subtitle.setStyleSheet(
            f"background: transparent; color: {COLORS['text_muted']}; "
            "font-size: 11px;"
        )

        text_col.addWidget(self.lbl_title)
        text_col.addWidget(self.lbl_value)
        text_col.addWidget(self.lbl_subtitle)
        row.addLayout(text_col, 1)

    # API publica — permite al controller refrescar sin reconstruir.
    def set_value(self, value: str) -> None:
        self.lbl_value.setText(value)

    def set_subtitle(self, text: str) -> None:
        self.lbl_subtitle.setText(text)
