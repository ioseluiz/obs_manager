"""Card compacta para 'Vista previa de canales' en la pestana Inicio.

Area de preview (color placeholder o pixmap si llega), chip 'En vivo'
cuando el canal esta transmitiendo, nombre canal + escena actual al pie.

Muestra la escena compuesta de cada canal recibida desde OBS.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QRect
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QStackedLayout, QSizePolicy, QVBoxLayout, QWidget

from views.theme import COLORS, SPACING
from views.theme.icons import icon as load_icon


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


class _PreviewArea(QWidget):
    def __init__(self):
        super().__init__()
        self.pixmap = QPixmap()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.pixmap.isNull():
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRect((self.width() - size.width()) // 2,
                       (self.height() - size.height()) // 2, size.width(), size.height())
        painter.drawPixmap(target, self.pixmap)


class ChannelPreviewCard(QWidget):
    PREVIEW_HEIGHT = 110

    def __init__(self, name: str, scene_name: str = "—",
                 is_live: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._name = name
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"ChannelPreviewCard {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; "
            f"border-radius: 10px; }}"
        )
        self.setMinimumWidth(180)

        col = QVBoxLayout(self)
        col.setContentsMargins(SPACING["sm"], SPACING["sm"],
                                SPACING["sm"], SPACING["md"])
        col.setSpacing(SPACING["sm"])

        self._preview = self._build_preview_block()
        col.addWidget(self._preview, 1)

        # Fila con nombre canal + chip En vivo.
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.lbl_name = QLabel(name, self)
        self.lbl_name.setStyleSheet(
            f"background: transparent; color: {COLORS['text_primary']}; "
            "font-size: 13px; font-weight: bold;"
        )
        self.lbl_name.setWordWrap(True)
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

    def _build_preview_block(self) -> QWidget:
        container = _PreviewArea()
        container.setMinimumHeight(self.PREVIEW_HEIGHT)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        container.setObjectName("ChannelPreviewArea")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setStyleSheet(
            f"#ChannelPreviewArea {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, "
            f"stop:0 {COLORS['brand_navy']}, stop:1 {COLORS['brand_navy_dark']}); border-radius: 6px; }}")

        overlay = QVBoxLayout(container)
        overlay.setContentsMargins(0, 0, 0, 0)
        overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay.setSpacing(2)

        icon_label = QLabel(container)
        icon_label.setPixmap(
            load_icon("app_tv", color="#FFFFFF").pixmap(QSize(36, 36))
        )
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        overlay.addWidget(icon_label)

        hint = QLabel("Sin preview disponible", container)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            "background: transparent; color: rgba(255,255,255,200); "
            "font-size: 10px; letter-spacing: 1px;"
        )
        overlay.addWidget(hint)
        self._placeholder_labels = (icon_label, hint)

        return container

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

    def set_preview(self, data: bytes | None) -> None:
        pixmap = QPixmap()
        if data:
            pixmap.loadFromData(data)
        self._preview.pixmap = pixmap
        for label in self._placeholder_labels:
            label.setVisible(pixmap.isNull())
        self._preview.update()
