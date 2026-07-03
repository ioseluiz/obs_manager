from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QSpinBox, QComboBox, QStackedWidget, QCheckBox,
                             QFormLayout, QPushButton, QWidget, QFileDialog,
                             QDialogButtonBox, QPlainTextEdit, QMessageBox)
from views.scene_view import CSS_PLACEHOLDER
from views.schedule_widget import ScheduleWidget


class SceneEditDialog(QDialog):
    def __init__(self, scene, parent=None, obs_client=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar escena — {scene['name']}")
        self.setMinimumWidth(520)
        self._scene = scene
        self._obs_client = obs_client

        layout = QVBoxLayout(self)

        info = QLabel("Recomendación: detén el rotador antes de editar la escena activa.")
        info.setStyleSheet("color: #6C757D; font-style: italic;")
        layout.addWidget(info)

        form = QFormLayout()

        self.input_name = QLineEdit(scene["name"])
        form.addRow("Nombre (OBS):", self.input_name)

        self.combo_type = QComboBox()
        self.combo_type.addItem("Archivo local", "file")
        self.combo_type.addItem("URL / Dashboard", "url")
        idx = 1 if scene.get("tipo") == "url" else 0
        self.combo_type.setCurrentIndex(idx)
        form.addRow("Tipo:", self.combo_type)

        self.input_duration = QSpinBox()
        self.input_duration.setRange(1, 3600)
        self.input_duration.setValue(scene["duration"])
        form.addRow("Duración (seg):", self.input_duration)

        layout.addLayout(form)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_file_panel(scene))
        self.stack.addWidget(self._build_web_panel(scene))
        self.stack.setCurrentIndex(idx)
        layout.addWidget(self.stack)
        self.combo_type.currentIndexChanged.connect(self.stack.setCurrentIndex)

        # Programación
        layout.addWidget(QLabel("Programación:"))
        self.schedule_widget = ScheduleWidget(
            days_mask=scene.get("active_days") if scene.get("active_days") is not None else 127,
            time_start=scene.get("active_time_start"),
            time_end=scene.get("active_time_end"),
        )
        layout.addWidget(self.schedule_widget)

        # Zoom + pan (universal)
        transform_row = QHBoxLayout()
        self.input_zoom = QSpinBox()
        self.input_zoom.setRange(10, 500)
        self.input_zoom.setValue(scene.get("zoom_pct") or 100)
        self.input_zoom.setSuffix(" %")

        self.input_pan_x = QSpinBox()
        self.input_pan_x.setRange(-4000, 4000)
        self.input_pan_x.setValue(scene.get("pan_x") or 0)
        self.input_pan_x.setSuffix(" px")

        self.input_pan_y = QSpinBox()
        self.input_pan_y.setRange(-4000, 4000)
        self.input_pan_y.setValue(scene.get("pan_y") or 0)
        self.input_pan_y.setSuffix(" px")

        transform_row.addWidget(QLabel("Zoom:"))
        transform_row.addWidget(self.input_zoom)
        transform_row.addSpacing(12)
        transform_row.addWidget(QLabel("Pan X:"))
        transform_row.addWidget(self.input_pan_x)
        transform_row.addSpacing(12)
        transform_row.addWidget(QLabel("Pan Y:"))
        transform_row.addWidget(self.input_pan_y)
        transform_row.addStretch()
        layout.addLayout(transform_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_file_panel(self, scene):
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        row.addWidget(QLabel("Archivo:"))
        self.input_file = QLineEdit(scene.get("contenido") or "" if scene.get("tipo") != "url" else "")
        self.input_file.setPlaceholderText("Ruta al archivo (.mp4, .png, .jpg...)")
        row.addWidget(self.input_file, 1)
        btn = QPushButton("📁 Buscar")
        btn.clicked.connect(self._pick_file)
        row.addWidget(btn)
        outer.addLayout(row)

        video_note = QLabel("Opciones de video (ignoradas en imágenes):")
        video_note.setStyleSheet("color: #6C757D; font-style: italic;")
        outer.addWidget(video_note)

        row1 = QHBoxLayout()
        self.chk_video_loop = QCheckBox("Repetir en bucle")
        self.chk_video_loop.setChecked(bool(scene.get("video_loop", True)))
        self.chk_video_restart = QCheckBox("Reiniciar al entrar")
        self.chk_video_restart.setChecked(bool(scene.get("video_restart_on_activate", True)))
        row1.addWidget(self.chk_video_loop)
        row1.addWidget(self.chk_video_restart)
        row1.addStretch()
        outer.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_video_mute = QCheckBox("Silenciar")
        self.chk_video_mute.setChecked(bool(scene.get("video_mute", False)))
        row2.addWidget(self.chk_video_mute)
        row2.addWidget(QLabel("Volumen:"))
        self.input_video_volume = QSpinBox()
        self.input_video_volume.setRange(0, 100)
        self.input_video_volume.setValue(int(scene.get("video_volume_pct") or 100))
        self.input_video_volume.setSuffix(" %")
        row2.addWidget(self.input_video_volume)
        row2.addSpacing(12)
        row2.addWidget(QLabel("Comenzar desde:"))
        self.input_video_offset = QSpinBox()
        self.input_video_offset.setRange(0, 36000)
        self.input_video_offset.setValue(int(scene.get("video_offset_seg") or 0))
        self.input_video_offset.setSuffix(" seg")
        row2.addWidget(self.input_video_offset)
        row2.addStretch()
        outer.addLayout(row2)

        detect_row = QHBoxLayout()
        self.btn_detect_duration = QPushButton("🎬 Detectar duración del video")
        self.btn_detect_duration.setStyleSheet("background-color: #6C757D;")
        self.btn_detect_duration.clicked.connect(self._detect_video_duration)
        detect_row.addWidget(self.btn_detect_duration)
        detect_row.addStretch()
        outer.addLayout(detect_row)

        return panel

    def _detect_video_duration(self):
        """Consulta a OBS la duración del video y ajusta el spinbox de duración de escena."""
        if not self._obs_client or not self._obs_client.client:
            QMessageBox.warning(self, "Aviso", "OBS no está conectado.")
            return
        source_name = f"{self._scene['name']}_Contenido"
        duration_ms = self._obs_client.get_video_duration_ms(source_name)
        if not duration_ms:
            QMessageBox.warning(self, "Aviso",
                                "No se pudo detectar la duración. Verifica que la escena exista en OBS "
                                "y que el archivo sea un video reproducible.")
            return
        offset = self.input_video_offset.value()
        remaining_sec = max(1, (duration_ms // 1000) - offset)
        self.input_duration.setValue(remaining_sec)
        QMessageBox.information(self, "Duración detectada",
                                f"Duración del video: {duration_ms // 1000} seg.\n"
                                f"Escena ajustada a {remaining_sec} seg (video - offset).")

    def _build_web_panel(self, scene):
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("URL:"))
        self.input_url = QLineEdit(scene.get("contenido") or "" if scene.get("tipo") == "url" else "")
        self.input_url.setPlaceholderText("https://...")
        url_row.addWidget(self.input_url, 1)
        outer.addLayout(url_row)

        opts_row = QHBoxLayout()
        form = QFormLayout()

        self.input_width = QSpinBox()
        self.input_width.setRange(100, 4000)
        self.input_width.setValue(scene.get("ancho") or 1920)
        self.input_width.setSuffix(" px")

        self.input_height = QSpinBox()
        self.input_height.setRange(100, 4000)
        self.input_height.setValue(scene.get("alto") or 1080)
        self.input_height.setSuffix(" px")

        self.input_fps = QSpinBox()
        self.input_fps.setRange(1, 60)
        self.input_fps.setValue(scene.get("fps") or 30)
        self.input_fps.setSuffix(" fps")

        form.addRow("Ancho:", self.input_width)
        form.addRow("Alto:", self.input_height)
        form.addRow("FPS:", self.input_fps)
        opts_row.addLayout(form)

        checks = QVBoxLayout()
        self.chk_reload = QCheckBox("Recargar al entrar a la escena")
        self.chk_reload.setChecked(bool(scene.get("reload_on_activate")))
        self.chk_keep_session = QCheckBox("Mantener sesión activa (no cerrar navegador)")
        self.chk_keep_session.setChecked(bool(scene.get("keep_session", True)))
        checks.addWidget(self.chk_reload)
        checks.addWidget(self.chk_keep_session)
        checks.addStretch()
        opts_row.addLayout(checks)

        outer.addLayout(opts_row)

        refresh_row = QHBoxLayout()
        current_refresh = scene.get("refresh_interval_seg") or 0
        self.chk_auto_refresh = QCheckBox("Auto-refresh cada")
        self.chk_auto_refresh.setChecked(current_refresh > 0)
        self.input_refresh_interval = QSpinBox()
        self.input_refresh_interval.setRange(5, 3600)
        self.input_refresh_interval.setValue(current_refresh if current_refresh > 0 else 60)
        self.input_refresh_interval.setSuffix(" seg")
        self.input_refresh_interval.setEnabled(current_refresh > 0)
        self.chk_auto_refresh.toggled.connect(self.input_refresh_interval.setEnabled)
        refresh_row.addWidget(self.chk_auto_refresh)
        refresh_row.addWidget(self.input_refresh_interval)
        refresh_row.addStretch()
        outer.addLayout(refresh_row)

        css_label = QLabel("CSS opcional (inyectado en la página):")
        css_label.setStyleSheet("color: #6C757D;")
        outer.addWidget(css_label)
        self.input_css = QPlainTextEdit()
        self.input_css.setPlaceholderText(CSS_PLACEHOLDER)
        self.input_css.setFixedHeight(90)
        if scene.get("custom_css"):
            self.input_css.setPlainText(scene["custom_css"])
        outer.addWidget(self.input_css)

        return panel

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Archivo Multimedia", "",
            "Archivos Multimedia (*.mp4 *.mov *.mkv *.png *.jpg *.jpeg *.gif);;Todos los archivos (*)"
        )
        if path:
            self.input_file.setText(path)

    def get_values(self):
        tipo = self.combo_type.currentData()
        css_text = self.input_css.toPlainText().strip()
        return {
            "id": self._scene["id"],
            "name": self.input_name.text().strip(),
            "duration": self.input_duration.value(),
            "tipo": tipo,
            "contenido": (self.input_url.text().strip() if tipo == "url"
                          else self.input_file.text().strip() or None),
            "ancho": self.input_width.value(),
            "alto": self.input_height.value(),
            "fps": self.input_fps.value(),
            "reload_on_activate": self.chk_reload.isChecked(),
            "keep_session": self.chk_keep_session.isChecked(),
            "custom_css": css_text or None,
            "zoom_pct": self.input_zoom.value(),
            "pan_x": self.input_pan_x.value(),
            "pan_y": self.input_pan_y.value(),
            "refresh_interval_seg": (
                self.input_refresh_interval.value() if self.chk_auto_refresh.isChecked() else 0
            ),
            "video_loop": self.chk_video_loop.isChecked(),
            "video_restart_on_activate": self.chk_video_restart.isChecked(),
            "video_mute": self.chk_video_mute.isChecked(),
            "video_volume_pct": self.input_video_volume.value(),
            "video_offset_seg": self.input_video_offset.value(),
            **self.schedule_widget.get_values(),
        }
