"""Boton grande con icono + 2 lineas de texto para 'Acciones rapidas'.

Variants:

- "primary" (azul relleno)
- "danger"  (rojo relleno)
- "neutral" (blanco con borde — el QSS global agrega hover)
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from views.theme import COLORS, SPACING
from views.theme.icons import icon as load_icon


_VARIANTS = {
    "primary": {
        "bg": COLORS["accent_primary"],
        "hover": COLORS["accent_primary_hover"],
        "fg": COLORS["text_inverse"],
        "sub": "#D9E7FF",
    },
    "danger": {
        "bg": COLORS["state_danger"],
        "hover": COLORS["state_danger_hover"],
        "fg": COLORS["text_inverse"],
        "sub": "#FBD5DB",
    },
    "neutral": {
        "bg": COLORS["bg_panel"],
        "hover": COLORS["bg_muted"],
        "fg": COLORS["text_primary"],
        "sub": COLORS["text_muted"],
    },
}


class ActionButton(QFrame):
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
        border = (
            f"border: 1px solid {COLORS['border_default']};"
            if self._variant == "neutral" else "border: none;"
        )
        self.setStyleSheet(
            f"ActionButton {{ background: {bg}; border-radius: 8px; "
            f"{border} }}"
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
