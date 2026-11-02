"""Hero section reutilizable para la cabecera de cada vista.

Icono circular tintado a la izquierda + titulo + subtitulo + franjas
decorativas corporativas (`assets/decoracion_cabecera.png`) sobre el
borde derecho.

Variants ajustan el color del circulo tintado:

- "blue":   azul marino corporativo (`brand_navy`).
- "red":    rojo CP.
- "green":  verde ok.
- "orange": naranja aviso.
- "navy":   alias de blue.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from views.theme import COLORS, SPACING
from views.theme.icons import icon as load_icon

_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"
_DECOR_PATH = _ASSETS / "decoracion_cabecera.png"

_VARIANT_BG = {
    "blue":   "#E7F0FF",
    "navy":   "#E7F0FF",
    "red":    "#FFE5EA",
    "green":  "#DCF4E4",
    "orange": "#FFE9D6",
}
_VARIANT_FG = {
    "blue":   COLORS["brand_navy"],
    "navy":   COLORS["brand_navy"],
    "red":    COLORS["brand_red"],
    "green":  COLORS["state_success"],
    "orange": COLORS["state_warning"],
}


def _circle_badge(icon_name: str, variant: str, size: int = 64) -> QLabel:
    """Pixmap con circulo de color + icono tintado al centro."""
    bg_hex = _VARIANT_BG.get(variant, _VARIANT_BG["blue"])
    fg_hex = _VARIANT_FG.get(variant, _VARIANT_FG["blue"])

    final = QPixmap(size, size)
    final.fill(Qt.GlobalColor.transparent)
    painter = QPainter(final)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(bg_hex))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size, size)
    # Icono tintado al centro.
    icon_size = int(size * 0.5)
    icon_px = load_icon(icon_name, color=fg_hex).pixmap(
        QSize(icon_size, icon_size))
    offset = (size - icon_size) // 2
    painter.drawPixmap(offset, offset, icon_px)
    painter.end()

    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setPixmap(final)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


class HeroHeader(QWidget):
    def __init__(self, icon_name: str, title: str, subtitle: str,
                 variant: str = "blue", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("HeroHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#HeroHeader {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; "
            f"border-radius: 10px; }}"
        )
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACING["xl"], SPACING["md"],
                                SPACING["sm"], SPACING["md"])
        row.setSpacing(SPACING["lg"])

        badge = _circle_badge(icon_name, variant)
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        self.lbl_title = QLabel(title, self)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet(
            f"color: {COLORS['text_primary']}; "
            "font-size: 22px; font-weight: bold;"
        )
        self.lbl_subtitle = QLabel(subtitle, self)
        self.lbl_subtitle.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 13px;"
        )
        self.lbl_subtitle.setWordWrap(True)
        text_col.addStretch(1)
        text_col.addWidget(self.lbl_title)
        text_col.addWidget(self.lbl_subtitle)
        text_col.addStretch(1)
        row.addLayout(text_col, 1)

        decor = self._build_decor()
        self._decor = decor
        if decor is not None:
            row.addWidget(decor, 0, Qt.AlignmentFlag.AlignVCenter
                           | Qt.AlignmentFlag.AlignRight)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_decor", None) is not None:
            self._decor.setVisible(self.width() >= 700)

    def _build_decor(self) -> QLabel | None:
        pix = QPixmap(str(_DECOR_PATH))
        if pix.isNull():
            return None
        lbl = QLabel(self)
        # Escalar por alto para que las franjas respiren con el hero.
        scaled = pix.scaledToHeight(
            80, Qt.TransformationMode.SmoothTransformation)
        lbl.setPixmap(scaled)
        lbl.setStyleSheet("background: transparent;")
        lbl.setFixedWidth(min(scaled.width(), 280))
        lbl.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        return lbl

    # API publica — permite al controller cambiar texto si hace falta.
    def set_title(self, text: str) -> None:
        self.lbl_title.setText(text)

    def set_subtitle(self, text: str) -> None:
        self.lbl_subtitle.setText(text)
