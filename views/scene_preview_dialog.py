from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDialogButtonBox,
)

from views.scene_preview_widget import ScenePreviewWidget
from core.preview_worker import PreviewThread


class ScenePreviewDialog(QDialog):
    """Ventana flotante non-modal para preview de escena.

    Similar al preview integrado en SceneEditDialog, pero:
    - Vive independiente (puede quedar abierta mientras editas otra escena).
    - Incluye un QComboBox para saltar entre escenas sin cerrar.
    - Gestiona su propio PreviewThread (no comparte con el diálogo padre).

    Emite `closed_by_user` cuando el usuario la cierra desde la X o botón,
    para que el padre pueda reintegrar el preview.
    """

    closed_by_user = pyqtSignal()

    def __init__(self, obs_client, scene_name, source_name,
                 canvas_w=1920, canvas_h=1080,
                 available_scenes=None, fps=3,
                 show_thirds=False, show_safe=False, show_coverage=False,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Preview — {scene_name}")
        self.setModal(False)
        # Ventana propia con botón de cerrar/minimizar/maximizar
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.resize(720, 480)

        self._obs = obs_client
        self._scene = scene_name
        self._source = source_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Selector de escena (solo si se pasa una lista)
        if available_scenes:
            row = QHBoxLayout()
            row.addWidget(QLabel("Escena:"))
            self.combo_scene = QComboBox()
            for s in available_scenes:
                # s puede ser un str o (name, source_name)
                if isinstance(s, tuple):
                    self.combo_scene.addItem(s[0], s)
                else:
                    self.combo_scene.addItem(s, s)
            # Preseleccionar la escena inicial
            idx = self.combo_scene.findText(scene_name)
            if idx >= 0:
                self.combo_scene.setCurrentIndex(idx)
            self.combo_scene.currentIndexChanged.connect(self._on_scene_changed)
            row.addWidget(self.combo_scene, 1)
            layout.addLayout(row)
        else:
            self.combo_scene = None

        # Preview widget (con botón detach mostrando ↙ para reintegrar)
        self.preview = ScenePreviewWidget(
            self, canvas_w=canvas_w, canvas_h=canvas_h, allow_detach=True
        )
        self.preview.set_detached_state(True)
        self.preview.spin_fps.setValue(fps)
        self.preview.chk_thirds.setChecked(show_thirds)
        self.preview.chk_safe.setChecked(show_safe)
        self.preview.chk_coverage.setChecked(show_coverage)
        self.preview.reattach_requested.connect(self._on_reattach_clicked)
        self.preview.refresh_requested.connect(self._on_refresh_clicked)
        self.preview.fps_changed.connect(self._on_fps_changed)
        layout.addWidget(self.preview, 1)

        # Botón de cierre estándar
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.close)
        btns.accepted.connect(self.close)
        # StandardButton.Close usa la señal rejected
        layout.addWidget(btns)

        # Thread de preview
        self._preview_thread = PreviewThread(
            obs_client, scene_name, source_name, fps=fps
        )
        self._preview_thread.worker.frame_ready.connect(self.preview.set_pixmap)
        self._preview_thread.worker.transform_updated.connect(self.preview.update_coverage)
        self._preview_thread.start()

    def _on_scene_changed(self, idx):
        if idx < 0 or not self.combo_scene:
            return
        data = self.combo_scene.itemData(idx)
        if isinstance(data, tuple):
            new_scene, new_source = data[0], data[1]
        else:
            new_scene = data
            # Heurística: inferimos el source por convención de nombres.
            # Si el llamador quiere ser preciso, debe pasar tuplas.
            new_source = None
        self._scene = new_scene
        self._source = new_source
        self.setWindowTitle(f"Preview — {new_scene}")
        self.preview.set_placeholder("Cambiando escena…")
        self._preview_thread.set_target(new_scene, new_source or "")

    def _on_reattach_clicked(self):
        # El usuario quiere volver al modo integrado
        self.close()

    def _on_refresh_clicked(self):
        # Bump manual: como el timer está corriendo, no hace falta lógica extra.
        # Podríamos forzar un tick invocando el slot, pero es innecesario.
        pass

    def _on_fps_changed(self, fps):
        self._preview_thread.set_fps(fps)

    def closeEvent(self, event):
        try:
            self._preview_thread.stop()
        finally:
            self.closed_by_user.emit()
            super().closeEvent(event)

    def current_state(self):
        """Devuelve el estado actual para que el padre lo replique al reintegrar."""
        return {
            "fps": self.preview.spin_fps.value(),
            "show_thirds": self.preview.chk_thirds.isChecked(),
            "show_safe": self.preview.chk_safe.isChecked(),
            "show_coverage": self.preview.chk_coverage.isChecked(),
            "scene_name": self._scene,
            "source_name": self._source,
        }
