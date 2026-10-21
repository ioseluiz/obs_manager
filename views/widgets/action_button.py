"""Boton grande con icono + 2 lineas de texto para 'Acciones rapidas'.

Variants:

- "primary" (azul relleno)
- "danger"  (rojo relleno)
- "neutral" (blanco con borde — el QSS global agrega hover)
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from views.theme import COLORS, SPACING
from views.theme.icons import icon as load_icon


# Paleta corporativa alineada al mock: primary usa el navy del Canal
# (no el azul moderno #0D6EFD que compite visualmente con el sidebar),
# danger usa el brand_red del Canal (no el #DC3545 generico).
_VARIANTS = {
    "primary": {
        "bg": COLORS["brand_navy"],
        "hover": "#164973",            # navy + 10%
        "fg": COLORS["text_inverse"],
        "sub": "#B8CCE3",
    },
    "danger": {
        "bg": COLORS["brand_red"],
        "hover": "#A3091F",            # brand_red oscurecido
        "fg": COLORS["text_inverse"],
        "sub": "#F0B7BF",
    },
    "neutral": {
        "bg": COLORS["bg_panel"],
        "hover": "#F1F3F5",
        "fg": COLORS["text_primary"],
        "sub": COLORS["text_muted"],
    },
}


class ActionButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, icon_name: str, title: str, subtitle: str,
                 variant: str = "primary", parent: QWidget | None = None):
        super().__init__(parent)
        self._variant = variant if variant in _VARIANTS else "primary"
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(74)
        self._apply_stylesheet(hover=False)

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACING["lg"], SPACING["sm"],
                                SPACING["lg"], SPACING["sm"])
        row.setSpacing(SPACING["md"])

        v = _VARIANTS[self._variant]

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(36, 36)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet("background: transparent;")
        self._icon_label.setPixmap(
            load_icon(icon_name, color=v["fg"]).pixmap(QSize(28, 28))
        )
        row.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        self.lbl_title = QLabel(title, self)
        self.lbl_title.setStyleSheet(
            f"background: transparent; color: {v['fg']}; "
            "font-size: 14px; font-weight: bold;"
        )
        self.lbl_subtitle = QLabel(subtitle, self)
        self.lbl_subtitle.setStyleSheet(
            f"background: transparent; color: {v['sub']}; "
            "font-size: 11px;"
        )
        text_col.addWidget(self.lbl_title)
        text_col.addWidget(self.lbl_subtitle)
        row.addLayout(text_col, 1)

    def _apply_stylesheet(self, hover: bool) -> None:
        v = _VARIANTS[self._variant]
        bg = v["hover"] if hover else v["bg"]
        if self._variant == "neutral":
            border = f"border: 1px solid {COLORS['border_default']};"
        else:
            # Explicit border-width 0 — algunos engines combinan reglas
            # con el QSS global de QWidget si solo decimos "border: none;".
            border = "border-width: 0px; border-style: none;"
        self.setStyleSheet(
            f"ActionButton {{ background: {bg}; "
            f"border-radius: 10px; {border} }}"
        )

    # Eventos: hover + click.
    def enterEvent(self, event):  # noqa: N802 — Qt API
        self._apply_stylesheet(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._apply_stylesheet(hover=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
