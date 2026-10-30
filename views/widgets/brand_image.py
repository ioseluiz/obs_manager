"""Paint original artwork at the display's resolution, including HiDPI."""
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QWidget


class BrandImage(QWidget):
    def __init__(self, path: Path, width: int, height: int, parent=None):
        super().__init__(parent)
        self._source = QPixmap(str(path))
        self.setFixedSize(width, height)
        self.setAccessibleName(path.stem)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        if self._source.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = self._source.size().scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF((self.width() - size.width()) / 2,
                        (self.height() - size.height()) / 2,
                        size.width(), size.height())
        painter.drawPixmap(target, self._source, QRectF(self._source.rect()))
