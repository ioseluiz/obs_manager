"""Diálogo para crear o editar un canal multi-salida."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSpinBox, QVBoxLayout,
)


ENCODERS = ("x264", "qsv", "nvenc", "amf")


class CanalEditDialog(QDialog):
    """Modal para crear/editar un `canal`.

    Uso::

        # Crear:
        dlg = CanalEditDialog(parent=..., existing_names={"OtroCanal"})
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()   # dict listo para CanalModel.add_canal

        # Editar:
        dlg = CanalEditDialog(parent=..., canal=canal_dict,
                              existing_names={n for n in ... if n != canal["nombre"]})
        ...

    `existing_names` es el conjunto de nombres ocupados (excepto el propio
    canal si se está editando) para validar unicidad antes de aceptar.
    """

    def __init__(self, parent=None, canal: dict | None = None,
                 existing_names: set[str] | None = None):
        super().__init__(parent)
        self._existing_names = existing_names or set()
        self._is_edit = canal is not None
        self.setWindowTitle("Editar Canal" if self._is_edit else "Nuevo Canal")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setContentsMargins(10, 10, 10, 10)

        self.ed_nombre = QLineEdit()
        self.ed_nombre.setPlaceholderText("Ej.: Piso3-Lobby")
        form.addRow("Nombre / escena OBS:", self.ed_nombre)

        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText("udp://192.168.1.100:9998")
        form.addRow("URL de destino:", self.ed_url)

        self.cmb_encoder = QComboBox()
        for e in ENCODERS:
            self.cmb_encoder.addItem(e)
        form.addRow("Encoder:", self.cmb_encoder)

        self.spin_bitrate = QSpinBox()
        self.spin_bitrate.setRange(500, 50000)
        self.spin_bitrate.setSingleStep(500)
        self.spin_bitrate.setSuffix(" kbps")
        self.spin_bitrate.setValue(2500)
        form.addRow("Bitrate:", self.spin_bitrate)

        self.chk_habilitado = QCheckBox("Habilitado (arranca la transmisión al aplicar)")
        self.chk_habilitado.setChecked(True)
        form.addRow("", self.chk_habilitado)

        self.ed_descripcion = QLineEdit()
        self.ed_descripcion.setPlaceholderText("Opcional")
        form.addRow("Descripción:", self.ed_descripcion)

        layout.addLayout(form)

        # Hint sobre unicidad
        hint = QLabel(
            "El nombre debe ser único — se usa como nombre de la escena "
            "contenedora en OBS."
        )
        hint.setStyleSheet("color: #6C757D; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Botones
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Prefill si es edición
        if canal:
            self.ed_nombre.setText(canal.get("nombre", ""))
            self.ed_url.setText(canal.get("url_destino", ""))
            enc = canal.get("encoder", "x264")
            if enc in ENCODERS:
                self.cmb_encoder.setCurrentText(enc)
            self.spin_bitrate.setValue(int(canal.get("bitrate_kbps", 2500)))
            self.chk_habilitado.setChecked(bool(canal.get("habilitado", True)))
            self.ed_descripcion.setText(canal.get("descripcion") or "")

    def _on_accept(self):
        nombre = self.ed_nombre.text().strip()
        url = self.ed_url.text().strip()

        if not nombre:
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio.")
            return
        if not url:
            QMessageBox.warning(self, "Validación", "La URL de destino es obligatoria.")
            return
        if not url.startswith(("udp://", "rtmp://", "rtmps://", "srt://")):
            QMessageBox.warning(
                self, "Validación",
                "La URL debe empezar con udp://, rtmp://, rtmps:// o srt://.",
            )
            return
        if nombre in self._existing_names:
            QMessageBox.warning(
                self, "Validación",
                f"Ya existe un canal con el nombre '{nombre}'.",
            )
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "nombre": self.ed_nombre.text().strip(),
            "url_destino": self.ed_url.text().strip(),
            "encoder": self.cmb_encoder.currentText(),
            "bitrate_kbps": int(self.spin_bitrate.value()),
            "habilitado": self.chk_habilitado.isChecked(),
            "descripcion": self.ed_descripcion.text().strip() or None,
        }
