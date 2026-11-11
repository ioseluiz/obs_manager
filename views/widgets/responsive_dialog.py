"""Keep existing dialog forms scrollable inside the available screen."""
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from views.widgets.wheel_guard import guard_wheel_in


class ResponsiveDialog(QDialog):
    def showEvent(self, event):
        if not getattr(self, '_responsive_ready', False):
            self._responsive_ready = True
            # Todo dialogo responsive queda protegido contra cambios de valor
            # por rueda del mouse sin foco (spinboxes, combos, sliders).
            guard_wheel_in(self)
            requested = self.size()
            original = self.layout()
            if original is not None:
                buttons = []
                for index in reversed(range(original.count())):
                    widget = original.itemAt(index).widget()
                    if isinstance(widget, QDialogButtonBox):
                        original.takeAt(index)
                        buttons.insert(0, widget)
                content = QWidget()
                content.setLayout(original)
                for form in content.findChildren(QFormLayout):
                    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
                for label in content.findChildren(QLabel):
                    if label.pixmap().isNull():
                        label.setWordWrap(True)
                outer = QVBoxLayout(self)
                outer.setContentsMargins(0, 0, 0, 0)
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.Shape.NoFrame)
                scroll.setWidget(content)
                outer.addWidget(scroll, 1)
                for button_box in buttons:
                    outer.addWidget(button_box)
                self.setMinimumSize(360, 240)
                screen = self.screen()
                if screen is not None:
                    available = screen.availableGeometry().adjusted(16, 16, -16, -16)
                    self.resize(min(requested.width(), available.width()),
                                min(requested.height(), available.height()))
        super().showEvent(event)
