"""Card compacta para 'Vista previa de canales' en la pestana Inicio.

Area de preview (color placeholder o pixmap si llega), chip 'En vivo'
cuando el canal esta transmitiendo, nombre canal + escena actual al pie.

En Fase 3 el area de preview es un degradado estatico — las miniaturas
live via `core/preview_worker.py` entran en una fase posterior.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from views.theme import COLORS, SPACING


def _gradient_pixmap(w: int, h: int, c1: str, c2: str) -> QPixmap:
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0.0, QColor(c1))
    g.setColorAt(1.0, QColor(c2))
    p.fillRect(0, 0, w, h, g)
    p.end()
    return pm


class ChannelPreviewCard(QFrame):
    PREVIEW_HEIGHT = 100

    def __init__(self, name: str, scene_name: str = "—",
                 is_live: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._name = name
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"ChannelPreviewCard {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; "
            f"border-radius: 8px; }}"
        )
        self.setMinimumWidth(220)

        col = QVBoxLayout(self)
        col.setContentsMargins(SPACING["sm"], SPACING["sm"],
                                SPACING["sm"], SPACING["md"])
        col.setSpacing(SPACING["sm"])

        self._preview = QLabel()
        self._preview.setFixedHeight(self.PREVIEW_HEIGHT)
        self._preview.setStyleSheet(
            f"background: transparent; border-radius: 6px;"
        )
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_preview_pixmap()
        col.addWidget(self._preview)

        # Fila con nombre canal + chip En vivo.
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.lbl_name = QLabel(name, self)
        self.lbl_name.setStyleSheet(
            f"background: transparent; color: {COLORS['text_primary']}; "
            "font-size: 13px; font-weight: bold;"
        )
        header.addWidget(self.lbl_name)
        header.addStretch(1)
        self.chip_live = QLabel("● En vivo", self)
        self._style_chip(is_live)
        header.addWidget(self.chip_live)
        col.addLayout(header)

        self.lbl_scene = QLabel(f"Escena actual: {scene_name}", self)
        self.lbl_scene.setStyleSheet(
            f"background: transparent; color: {COLORS['text_muted']}; "
            "font-size: 11px;"
        )
        self.lbl_scene.setWordWrap(True)
        col.addWidget(self.lbl_scene)

    def _refresh_preview_pixmap(self):
        # Placeholder: degradado de la paleta corporativa.
        pm = _gradient_pixmap(
            300, self.PREVIEW_HEIGHT,
            COLORS["brand_navy"], COLORS["brand_navy_dark"],
        )
        self._preview.setPixmap(pm)

    def _style_chip(self, is_live: bool) -> None:
        if is_live:
            self.chip_live.setStyleSheet(
                f"background: {COLORS['state_success_bg']}; "
                f"color: {COLORS['state_success_fg']}; "
                "font-size: 10px; font-weight: bold; "
                "padding: 2px 6px; border-radius: 999px;"
            )
            self.chip_live.setText("● En vivo")
        else:
            self.chip_live.setStyleSheet(
                f"background: {COLORS['bg_muted']}; "
                f"color: {COLORS['text_muted']}; "
                "font-size: 10px; font-weight: bold; "
                "padding: 2px 6px; border-radius: 999px;"
            )
            self.chip_live.setText("○ Detenido")

    # ------------------------------------------------------------------
    # API publica — permite al controller refrescar
    # ------------------------------------------------------------------

    def set_scene_name(self, scene_name: str) -> None:
        self.lbl_scene.setText(f"Escena actual: {scene_name}")

    def set_live(self, is_live: bool) -> None:
        self._style_chip(is_live)
