"""Diálogo mínimo para editar el override de duración de un canal_item."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox,
    QVBoxLayout,
)


class CanalItemEditDialog(QDialog):
    """Editar la `duracion_override_seg` de un canal_item.

    Devuelve el nuevo valor (int en segundos) o `None` si el usuario elige
    "sin override" (usar la duración de la secuencia). Devuelve
    `DialogCode.Rejected` si se cancela sin cambios.
    """

    def __init__(self, secuencia_nombre: str, secuencia_duration_seg: int,
                 current_override: int | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar duración del item")
        self.setMinimumWidth(360)
        self._secuencia_duration = secuencia_duration_seg

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            f"Escena: <b>{secuencia_nombre}</b><br>"
            f"Duración base: {secuencia_duration_seg} s"
        ))

        form = QFormLayout()
        self.chk_use_default = QCheckBox("Usar la duración de la escena")
        self.spin_override = QSpinBox()
        self.spin_override.setRange(1, 3600)
        self.spin_override.setSuffix(" s")

        if current_override is None:
            self.chk_use_default.setChecked(True)
            self.spin_override.setValue(secuencia_duration_seg)
        else:
            self.chk_use_default.setChecked(False)
            self.spin_override.setValue(int(current_override))

        form.addRow("", self.chk_use_default)
        form.addRow("Override (segundos):", self.spin_override)
        layout.addLayout(form)

        # Deshabilitar el spinbox cuando "usar default" está marcado
        self.chk_use_default.toggled.connect(
            lambda checked: self.spin_override.setDisabled(checked)
        )
        self.spin_override.setDisabled(self.chk_use_default.isChecked())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_override(self) -> int | None:
        """Devuelve el override elegido, o None si se optó por default."""
        if self.chk_use_default.isChecked():
            return None
        return int(self.spin_override.value())
