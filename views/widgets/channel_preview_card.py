"""Card compacta para 'Vista previa de canales' en la pestana Inicio.

Area de preview (color placeholder o pixmap si llega), chip 'En vivo'
cuando el canal esta transmitiendo, nombre canal + escena actual al pie.

Muestra la escena compuesta de cada canal recibida desde OBS.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QRect, QRectF
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
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
    """Area que muestra la captura del canal respetando su proporcion.

    - `heightForWidth` hace que el layout le de un rectangulo con la
      proporcion de la captura (16:9 por defecto; la del canvas de OBS
      cuando llega un pixmap), asi la imagen llena la caja sin franjas.
    - Si el layout aun asi entrega un rectangulo distinto, la imagen se
      centra en `_target_rect()` y el sobrante queda TRANSPARENTE (se ve
      el fondo de la tarjeta), nunca una franja negra.
    """

    CORNER_RADIUS = 6

    def __init__(self):
        super().__init__()
        self.pixmap = QPixmap()
        self._ratio = (16, 9)

    # --- proporcion -----------------------------------------------------

    def set_ratio(self, width: int, height: int) -> None:
        if width > 0 and height > 0 and (width, height) != self._ratio:
            self._ratio = (int(width), int(height))
            self.updateGeometry()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        rw, rh = self._ratio
        return max(1, round(width * rh / rw))

    def sizeHint(self) -> QSize:
        return QSize(320, self.heightForWidth(320))

    def _target_rect(self) -> QRect:
        """Rect centrado con la proporcion objetivo que cabe en el widget."""
        w, h = self.width(), self.height()
        rw, rh = self._ratio
        target_h = round(w * rh / rw)
        if target_h <= h:
            return QRect(0, (h - target_h) // 2, w, target_h)
        target_w = round(h * rw / rh)
        return QRect((w - target_w) // 2, 0, target_w, h)

    # --- pintado --------------------------------------------------------

    def paintEvent(self, event):
        if self.pixmap.isNull():
            # Placeholder: fondo navy del stylesheet + icono/leyenda overlay.
            super().paintEvent(event)
            return
        # Con captura NO pintamos el fondo del stylesheet ni rellenamos de
        # negro: solo la imagen, en su rect, con esquinas redondeadas.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = self._target_rect()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(target), self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.setClipPath(clip)
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
        # Expanding en ancho; en alto el layout consulta heightForWidth()
        # para mantener la proporcion de la captura.
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        container.setSizePolicy(policy)
        container.setObjectName("ChannelPreviewArea")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Dos estilos: placeholder (degradado navy) y con captura (fondo
        # transparente para que el sobrante muestre el fondo de la tarjeta).
        # Qt pinta el fondo del stylesheet antes de paintEvent, asi que la
        # unica forma fiable de quitarlo es cambiar el stylesheet.
        self._preview_css_placeholder = (
            f"#ChannelPreviewArea {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, "
            f"stop:0 {COLORS['brand_navy']}, stop:1 {COLORS['brand_navy_dark']}); border-radius: 6px; }}")
        self._preview_css_frame = "#ChannelPreviewArea { background: transparent; }"
        container.setStyleSheet(self._preview_css_placeholder)

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
        if not pixmap.isNull():
            # La caja adopta la proporcion real de la captura (la del canvas
            # de OBS), no una fija.
            self._preview.set_ratio(pixmap.width(), pixmap.height())
        # Con captura, fondo transparente (el sobrante fuera del rect de la
        # imagen muestra el fondo de la tarjeta, no una franja navy/negra);
        # sin captura, el degradado navy del placeholder. Solo se cambia el
        # stylesheet en las transiciones para no repolir cada segundo.
        css = self._preview_css_placeholder if pixmap.isNull() else self._preview_css_frame
        if self._preview.styleSheet() != css:
            self._preview.setStyleSheet(css)
        for label in self._placeholder_labels:
            label.setVisible(pixmap.isNull())
        self._preview.update()
