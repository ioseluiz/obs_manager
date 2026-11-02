"""Layout helpers: keep existing controls accessible as the window narrows."""
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout, QSizePolicy, QSpacerItem


def arrange_grid(layout, widgets, columns):
    while layout.count():
        layout.takeAt(0)
    # Reset stretches left by a previous, wider arrangement.
    for column in range(layout.columnCount()):
        layout.setColumnStretch(column, 0)
    for index, widget in enumerate(widgets):
        layout.addWidget(widget, index // columns, index % columns)
    for column in range(columns):
        layout.setColumnStretch(column, 1)


class FlowLayout(QLayout):
    """A toolbar that wraps whole controls without shortening their labels."""
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self._stretches = {}
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def addWidget(self, widget, stretch=0, alignment=Qt.AlignmentFlag(0)):
        super().addWidget(widget)
        self._stretches[widget] = stretch
        if alignment:
            self._items[-1].setAlignment(alignment)

    def addLayout(self, layout, stretch=0):
        self.addChildLayout(layout)
        self.addItem(layout)

    def addSpacing(self, size):
        self.addItem(QSpacerItem(size, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))

    def addStretch(self, stretch=0):
        self.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation.Horizontal

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._place(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._place(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            if item.widget() is None or not item.widget().isHidden():
                size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _place(self, rect, measure):
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line_height = area.x(), area.y(), 0
        gap = self.spacing()
        visible = [item for item in self._items if item.widget() is None or not item.widget().isHidden()]
        for index, item in enumerate(visible):
            hint = item.sizeHint()
            width = min(hint.width(), max(0, area.width()))
            remaining = sum(i.sizeHint().width() + gap for i in visible[index + 1:])
            if self._stretches.get(item.widget(), 0) and area.width() >= hint.width() + remaining:
                width = min(item.maximumSize().width(), max(width, area.right() + 1 - x - remaining))
            if item.spacerItem() and hint.width() == 0:
                width = max(0, area.right() + 1 - x - remaining)
            height = item.heightForWidth(width) if item.hasHeightForWidth() else hint.height()
            if x > area.x() and x + width > area.right() + 1:
                x, y, line_height = area.x(), y + line_height + gap, 0
            if not measure:
                item.setGeometry(QRect(QPoint(x, y), QSize(width, max(0, height))))
            x += width + gap
            line_height = max(line_height, height)
        return y - rect.y() + line_height + margins.bottom()
