from PyQt6.QtCore import Qt, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QPixmap, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSpinBox,
    QToolButton, QSizePolicy, QFrame,
)


class _PreviewCanvas(QFrame):
    """Superficie de dibujo del preview: pixmap + overlays.

    Aspect ratio 16:9 forzado. Overlays se dibujan en coordenadas de widget
    (no del pixmap original) para que se mantengan proporcionales al display.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setStyleSheet(
            "background-color: #0d0d0d; color: #E0E0E0;"
            " border: 1px solid #333;"
        )
        self.setMinimumSize(240, 135)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._pixmap = None
        self._placeholder = "Preview no disponible"

        # Toggles de overlays
        self.show_thirds = False
        self.show_safe = False

    def sizeHint(self):
        return QSize(400, 225)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return int(w * 9 / 16)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.update()

    def set_placeholder(self, text: str):
        self._placeholder = text
        self._pixmap = None
        self.update()

    def clear(self):
        self._pixmap = None
        self.update()

    def _target_rect(self):
        """Rect donde dibujamos el pixmap, respetando aspect 16:9 dentro del widget."""
        w = self.width()
        h = self.height()
        target_h = int(w * 9 / 16)
        if target_h <= h:
            return QRect(0, (h - target_h) // 2, w, target_h)
        target_w = int(h * 16 / 9)
        return QRect((w - target_w) // 2, 0, target_w, h)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self._target_rect()

        if self._pixmap and not self._pixmap.isNull():
            p.drawPixmap(r, self._pixmap)
        else:
            # Fondo oscuro + texto placeholder centrado
            p.fillRect(r, QColor(15, 15, 15))
            p.setPen(QColor(180, 180, 180))
            font = QFont()
            font.setPointSize(11)
            p.setFont(font)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._placeholder)

        # Marco del canvas (borde blanco fino que representa el edge de la escena OBS)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawRect(r)

        # Overlays
        if self.show_thirds and self._pixmap:
            self._draw_thirds(p, r)
        if self.show_safe and self._pixmap:
            self._draw_safe_zones(p, r)

    def _draw_thirds(self, p: QPainter, r: QRect):
        p.setPen(QPen(QColor(255, 255, 255, 130), 1, Qt.PenStyle.DashLine))
        for i in (1, 2):
            x = r.left() + int(r.width() * i / 3)
            y = r.top() + int(r.height() * i / 3)
            p.drawLine(x, r.top(), x, r.bottom())
            p.drawLine(r.left(), y, r.right(), y)

    def _draw_safe_zones(self, p: QPainter, r: QRect):
        # Action safe: 5% margen (rectángulo al 90%). Amarillo.
        margin_a = int(r.width() * 0.05), int(r.height() * 0.05)
        action = QRect(
            r.left() + margin_a[0], r.top() + margin_a[1],
            r.width() - 2 * margin_a[0], r.height() - 2 * margin_a[1],
        )
        p.setPen(QPen(QColor(255, 200, 0, 200), 1, Qt.PenStyle.DashLine))
        p.drawRect(action)

        # Title safe: 10% margen (rectángulo al 80%). Rojo suave.
        margin_t = int(r.width() * 0.10), int(r.height() * 0.10)
        title = QRect(
            r.left() + margin_t[0], r.top() + margin_t[1],
            r.width() - 2 * margin_t[0], r.height() - 2 * margin_t[1],
        )
        p.setPen(QPen(QColor(255, 80, 80, 200), 1, Qt.PenStyle.DashLine))
        p.drawRect(title)


class ScenePreviewWidget(QWidget):
    """Widget completo: canvas + toolbar de controles + label de cobertura.

    Signals:
        detach_requested: usuario pidió abrir el preview en ventana flotante.
        reattach_requested: usuario pidió cerrar la ventana flotante y volver.
        refresh_requested: usuario forzó refresh manual.
        fps_changed(int): usuario cambió los FPS.
    """

    detach_requested = pyqtSignal()
    reattach_requested = pyqtSignal()
    refresh_requested = pyqtSignal()
    fps_changed = pyqtSignal(int)

    def __init__(self, parent=None, canvas_w=1920, canvas_h=1080,
                 allow_detach=True):
        super().__init__(parent)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        self._detached = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(6)

        tb.addWidget(QLabel("FPS:"))
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 10)
        self.spin_fps.setValue(3)
        self.spin_fps.setMaximumWidth(60)
        self.spin_fps.setToolTip("Frames por segundo del polling (1-10)")
        self.spin_fps.valueChanged.connect(self.fps_changed.emit)
        tb.addWidget(self.spin_fps)

        tb.addSpacing(10)

        self.chk_thirds = QCheckBox("Tercios")
        self.chk_thirds.setToolTip("Regla de los tercios: divide el canvas en 9 secciones")
        self.chk_thirds.toggled.connect(self._on_thirds_toggled)
        tb.addWidget(self.chk_thirds)

        self.chk_safe = QCheckBox("Zonas seguras")
        self.chk_safe.setToolTip("Bordes broadcast: action safe (90%) y title safe (80%)")
        self.chk_safe.toggled.connect(self._on_safe_toggled)
        tb.addWidget(self.chk_safe)

        self.chk_coverage = QCheckBox("Cobertura")
        self.chk_coverage.setToolTip("Muestra qué % del canvas ocupa el source")
        self.chk_coverage.toggled.connect(self._on_coverage_toggled)
        tb.addWidget(self.chk_coverage)

        tb.addStretch()

        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("⟲")
        self.btn_refresh.setToolTip("Refrescar preview ahora")
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        tb.addWidget(self.btn_refresh)

        if allow_detach:
            self.btn_detach = QToolButton()
            self.btn_detach.setText("↗")
            self.btn_detach.setToolTip("Abrir preview en ventana flotante")
            self.btn_detach.clicked.connect(self._on_detach_clicked)
            tb.addWidget(self.btn_detach)
        else:
            self.btn_detach = None

        outer.addLayout(tb)

        # Canvas de preview
        self.canvas = _PreviewCanvas(self)
        outer.addWidget(self.canvas, 1)

        # Label de cobertura (oculto por defecto)
        self.coverage_label = QLabel("Cobertura H: — · V: — · Escala: —")
        self.coverage_label.setStyleSheet("color: #6C757D; font-family: monospace;")
        self.coverage_label.setVisible(False)
        outer.addWidget(self.coverage_label)

    def set_canvas_size(self, w, h):
        self._canvas_w = max(1, int(w))
        self._canvas_h = max(1, int(h))

    def set_pixmap(self, pixmap: QPixmap):
        self.canvas.set_pixmap(pixmap)

    def set_placeholder(self, text: str):
        self.canvas.set_placeholder(text)
        # Reset coverage cuando no hay preview real
        self.coverage_label.setText("Cobertura H: — · V: — · Escala: —")

    def update_coverage(self, transform: dict):
        """Recibe un dict de transform (scaleX/Y, sourceWidth/Height) y actualiza el label."""
        if not transform:
            return
        sw = float(transform.get("sourceWidth") or 0)
        sh = float(transform.get("sourceHeight") or 0)
        sx = float(transform.get("scaleX") or 1.0)
        sy = float(transform.get("scaleY") or 1.0)
        if sw <= 0 or sh <= 0 or self._canvas_w <= 0 or self._canvas_h <= 0:
            return
        rendered_w = sw * sx
        rendered_h = sh * sy
        cov_h = min(1.0, rendered_w / self._canvas_w) * 100
        cov_v = min(1.0, rendered_h / self._canvas_h) * 100
        avg_scale = (sx + sy) / 2.0 * 100
        self.coverage_label.setText(
            f"Cobertura H: {cov_h:.0f}% · V: {cov_v:.0f}% · Escala: {avg_scale:.0f}%"
        )

    def set_detached_state(self, detached: bool):
        """La ventana flotante llama aquí para que el widget muestre el botón
        adecuado (↗ para desenganchar vs ↙ para reenganchar)."""
        self._detached = detached
        if self.btn_detach:
            self.btn_detach.setText("↙" if detached else "↗")
            self.btn_detach.setToolTip(
                "Volver a integrar al diálogo" if detached
                else "Abrir preview en ventana flotante"
            )

    def current_fps(self):
        return self.spin_fps.value()

    def _on_thirds_toggled(self, checked):
        self.canvas.show_thirds = bool(checked)
        self.canvas.update()

    def _on_safe_toggled(self, checked):
        self.canvas.show_safe = bool(checked)
        self.canvas.update()

    def _on_coverage_toggled(self, checked):
        self.coverage_label.setVisible(bool(checked))

    def _on_detach_clicked(self):
        if self._detached:
            self.reattach_requested.emit()
        else:
            self.detach_requested.emit()
