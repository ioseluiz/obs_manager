from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QListWidget, QRadioButton, QButtonGroup,
                             QDialogButtonBox, QCheckBox)
from PyQt6.QtCore import Qt


class ImportPreviewDialog(QDialog):
    """Muestra el contenido del JSON y deja elegir modo de import."""

    MODE_APPEND = "append"
    MODE_REPLACE = "replace"

    def __init__(self, scenes, metadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vista previa de importación")
        self.setMinimumSize(560, 420)
        self._scenes = scenes

        layout = QVBoxLayout(self)

        # Metadata
        meta_str = (
            f"Archivo: {metadata.get('scene_count', len(scenes))} escenas · "
            f"Formato: {metadata.get('format_version', 'desconocido')} · "
            f"Exportado: {metadata.get('exported_at', '?')}"
        )
        meta_lbl = QLabel(meta_str)
        meta_lbl.setStyleSheet("color: #6C757D;")
        meta_lbl.setWordWrap(True)
        layout.addWidget(meta_lbl)

        # Lista de escenas
        layout.addWidget(QLabel("Escenas incluidas:"))
        self.list_widget = QListWidget()
        for s in scenes:
            tipo_icon = "🌐" if s.get("tipo") == "url" else "📁"
            dur = s.get("duration", "?")
            contenido = s.get("contenido") or "(sin contenido)"
            if len(str(contenido)) > 60:
                contenido = str(contenido)[:57] + "..."
            self.list_widget.addItem(f"{tipo_icon}  {s['name']}  —  {dur}s  —  {contenido}")
        layout.addWidget(self.list_widget)

        # Modo
        layout.addWidget(QLabel("Modo de importación:"))
        self.radio_append = QRadioButton("➕ Añadir al final de la lista actual (renombra si hay conflictos)")
        self.radio_append.setChecked(True)
        self.radio_replace = QRadioButton("♻ Reemplazar todas las escenas actuales (BORRA las existentes)")
        self.radio_replace.setStyleSheet("color: #DC3545;")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_append)
        self.mode_group.addButton(self.radio_replace)
        layout.addWidget(self.radio_append)
        layout.addWidget(self.radio_replace)

        self.chk_create_in_obs = QCheckBox("Crear escenas también en OBS (requiere OBS conectado)")
        self.chk_create_in_obs.setChecked(True)
        layout.addWidget(self.chk_create_in_obs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Importar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_mode(self):
        return self.MODE_REPLACE if self.radio_replace.isChecked() else self.MODE_APPEND

    def create_in_obs(self):
        return self.chk_create_in_obs.isChecked()

    def get_scenes(self):
        return self._scenes
