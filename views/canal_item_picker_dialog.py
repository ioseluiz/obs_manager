"""Diálogo para elegir una escena del rotador como item de canal."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QSpinBox, QVBoxLayout,
)


class CanalItemPickerDialog(QDialog):
    """Elige una `secuencia` (escena del rotador) para agregar como item de canal.

    Devuelve (secuencia_id, duracion_override_seg_o_None).
    """

    def __init__(self, secuencias: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar item al canal")
        self.setMinimumSize(420, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Seleccione una escena del Rotador para incluirla en el canal:"
        ))

        self._list = QListWidget()
        for s in secuencias:
            item = QListWidgetItem(f"{s['name']}   ·   {s['duration']}s")
            item.setData(0x0100, int(s["id"]))  # UserRole
            item.setData(0x0101, int(s["duration"]))  # UserRole+1: default duration
            self._list.addItem(item)
        layout.addWidget(self._list, 1)

        # Duracion override
        row = QHBoxLayout()
        row.addWidget(QLabel("Duración override (segundos, 0 = usar la de la escena):"))
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(0, 3600)
        self.spin_duration.setValue(0)
        row.addWidget(self.spin_duration)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        if self._list.currentItem() is None:
            QMessageBox.warning(self, "Validación", "Seleccione una escena primero.")
            return
        self.accept()

    def get_selection(self) -> tuple[int, int | None]:
        """Retorna (secuencia_id, duracion_override_seg_o_None)."""
        item = self._list.currentItem()
        secuencia_id = int(item.data(0x0100))
        duration_override = self.spin_duration.value()
        return secuencia_id, (duration_override if duration_override > 0 else None)
