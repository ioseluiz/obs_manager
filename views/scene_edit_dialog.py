import logging
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QSpinBox, QComboBox, QStackedWidget, QCheckBox,
                             QFormLayout, QPushButton, QWidget, QFileDialog,
                             QDialogButtonBox, QPlainTextEdit, QMessageBox,
                             QScrollArea)
from views.scene_view import CSS_PLACEHOLDER
from views.schedule_widget import ScheduleWidget
from views.scene_preview_widget import ScenePreviewWidget
from views.scene_preview_dialog import ScenePreviewDialog
from core.templates import get_template_names, get_template_defaults
from core.preview_worker import PreviewThread

log = logging.getLogger(__name__)


def _source_name_for(tipo, scene_name):
    """Convención del proyecto: file/image → _Contenido; url → _Web."""
    if not scene_name:
        return None
    return f"{scene_name}_Web" if tipo == "url" else f"{scene_name}_Contenido"


def empty_scene_defaults():
    """Defaults para modo agregar — coinciden con los defaults de la BD."""
    return {
        "id": None,
        "name": "",
        "duration": 20,
        "tipo": "file",
        "contenido": None,
        "ancho": 1920, "alto": 1080, "fps": 30,
        "reload_on_activate": False, "keep_session": True,
        "custom_css": None,
        "zoom_pct": 100, "pan_x": 0, "pan_y": 0,
        "refresh_interval_seg": 0,
        "video_loop": True, "video_restart_on_activate": True,
        "video_mute": False, "video_volume_pct": 100, "video_offset_seg": 0,
        "active_days": 127, "active_time_start": None, "active_time_end": None,
    }


class SceneEditDialog(QDialog):
    def __init__(self, scene=None, parent=None, obs_client=None, is_new=False):
        super().__init__(parent)
        self.is_new = is_new
        if scene is None or is_new:
            scene = scene or empty_scene_defaults()
        self.setWindowTitle("Agregar Nueva Escena" if is_new
                            else f"Editar escena — {scene['name']}")
        self.setMinimumWidth(720)
        # Alto máximo sensato: 90% del alto de pantalla; el QScrollArea manejará overflow
        self.resize(720, 620)
        self._scene = scene
        self._obs_client = obs_client

        # Estado del preview
        self._preview_thread = None
        self._floating_preview = None
        self._original_transform = (
            scene.get("zoom_pct") or 100,
            scene.get("pan_x") or 0,
            scene.get("pan_y") or 0,
        )
        self._transform_dirty = False
        # Debounce timer para los sliders de zoom/pan (se dispara al soltar)
        self._transform_debounce = QTimer(self)
        self._transform_debounce.setSingleShot(True)
        self._transform_debounce.setInterval(150)
        self._transform_debounce.timeout.connect(self._apply_live_transform)

        # Layout raíz: transform_row fijo arriba + scroll con contenido +
        # botones OK/Cancel fijos abajo. Los sliders de zoom/pan quedan
        # SIEMPRE visibles junto al preview, sin depender del scroll.
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # --- Zoom + pan (universal) — FIJO arriba del scroll ---
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
        root.addLayout(transform_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        if is_new:
            info = QLabel("Completa los campos y presiona Aceptar para crear la escena en OBS + BD.")
        else:
            info = QLabel("Recomendación: detén el rotador antes de editar la escena activa.")
        info.setStyleSheet("color: #6C757D; font-style: italic;")
        layout.addWidget(info)

        # --- PREVIEW ---
        # Solo en modo edición (escenas nuevas aún no existen en OBS).
        self._preview_widget = None
        if not is_new and obs_client is not None:
            canvas_w = getattr(obs_client, "canvas_width", 1920) or 1920
            canvas_h = getattr(obs_client, "canvas_height", 1080) or 1080
            self._preview_widget = ScenePreviewWidget(
                self, canvas_w=canvas_w, canvas_h=canvas_h, allow_detach=True
            )
            # Compacto por defecto (16:9 a ~240px alto): usable en laptops sin
            # bloquear el resto del formulario. En modo flotante crece libre.
            self._preview_widget.setMaximumHeight(260)
            self._preview_widget.detach_requested.connect(self._on_detach_preview)
            self._preview_widget.reattach_requested.connect(self._on_reattach_preview)
            self._preview_widget.refresh_requested.connect(self._on_refresh_preview)
            self._preview_widget.fps_changed.connect(self._on_fps_changed)
            layout.addWidget(self._preview_widget)

            # Placeholder que se muestra cuando el preview está en ventana flotante
            self._detached_placeholder = QLabel(
                "Preview en ventana flotante. Ciérrala o presiona ↙ para reintegrar."
            )
            self._detached_placeholder.setStyleSheet(
                "color: #6C757D; font-style: italic; padding: 12px; "
                "border: 1px dashed #999;"
            )
            self._detached_placeholder.setVisible(False)
            layout.addWidget(self._detached_placeholder)

        form = QFormLayout()

        # Template combo solo en modo agregar
        if is_new:
            self.combo_template = QComboBox()
            for name in get_template_names():
                self.combo_template.addItem(name)
            self.combo_template.currentTextChanged.connect(self._on_template_changed)
            self.combo_template.setToolTip("Preset con valores típicos. Podés seguir editando después.")
            form.addRow("Template:", self.combo_template)
        else:
            self.combo_template = None

        self.input_name = QLineEdit(scene.get("name", ""))
        self.input_name.setPlaceholderText("Ej: DASHBOARD_VENTAS")
        form.addRow("Nombre (OBS):", self.input_name)

        self.combo_type = QComboBox()
        self.combo_type.addItem("Archivo local", "file")
        self.combo_type.addItem("URL / Dashboard", "url")
        idx = 1 if scene.get("tipo") == "url" else 0
        self.combo_type.setCurrentIndex(idx)
        form.addRow("Tipo:", self.combo_type)

        self.input_duration = QSpinBox()
        self.input_duration.setRange(1, 3600)
        self.input_duration.setValue(scene.get("duration", 20))
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

        # Wiring de sliders → transform en vivo (solo si hay preview activo).
        # Cada cambio arma el debounce; cuando el usuario deja de tocar 150ms,
        # se aplica set_source_transform una sola vez. El preview lo verá en el
        # próximo tick de polling (~330ms a 3 FPS).
        if not is_new and obs_client is not None:
            self.input_zoom.valueChanged.connect(self._schedule_transform)
            self.input_pan_x.valueChanged.connect(self._schedule_transform)
            self.input_pan_y.valueChanged.connect(self._schedule_transform)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        # Botones fuera del scroll area → siempre visibles al pie del diálogo
        root.addWidget(buttons)

    def _build_file_panel(self, scene):
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        row = QHBoxLayout()
        row.addWidget(QLabel("Archivo:"))
        self.input_file = QLineEdit(scene.get("contenido") or "" if scene.get("tipo") != "url" else "")
        self.input_file.setPlaceholderText("Ruta al archivo (.mp4, .png, .jpg...)")
        row.addWidget(self.input_file, 1)
        btn = QPushButton("📁 Buscar")
        btn.clicked.connect(self._pick_file)
        row.addWidget(btn)
        outer.addLayout(row)

        # Opciones de video — todo en una sola línea + botón detectar
        video_row = QHBoxLayout()
        video_lbl = QLabel("Video:")
        video_lbl.setStyleSheet("color: #6C757D;")
        video_lbl.setToolTip("Opciones ignoradas si el archivo es una imagen")
        video_row.addWidget(video_lbl)

        self.chk_video_loop = QCheckBox("Loop")
        self.chk_video_loop.setChecked(bool(scene.get("video_loop", True)))
        self.chk_video_loop.setToolTip("Repetir en bucle")
        video_row.addWidget(self.chk_video_loop)

        self.chk_video_restart = QCheckBox("Restart")
        self.chk_video_restart.setChecked(bool(scene.get("video_restart_on_activate", True)))
        self.chk_video_restart.setToolTip("Reiniciar al entrar a la escena")
        video_row.addWidget(self.chk_video_restart)

        self.chk_video_mute = QCheckBox("Mute")
        self.chk_video_mute.setChecked(bool(scene.get("video_mute", False)))
        self.chk_video_mute.setToolTip("Silenciar")
        video_row.addWidget(self.chk_video_mute)

        video_row.addSpacing(8)
        video_row.addWidget(QLabel("Vol:"))
        self.input_video_volume = QSpinBox()
        self.input_video_volume.setRange(0, 100)
        self.input_video_volume.setValue(int(scene.get("video_volume_pct") or 100))
        self.input_video_volume.setSuffix(" %")
        self.input_video_volume.setMaximumWidth(80)
        video_row.addWidget(self.input_video_volume)

        video_row.addSpacing(8)
        off_lbl = QLabel("Inicio:")
        off_lbl.setToolTip("Comenzar reproducción desde este segundo")
        video_row.addWidget(off_lbl)
        self.input_video_offset = QSpinBox()
        self.input_video_offset.setRange(0, 36000)
        self.input_video_offset.setValue(int(scene.get("video_offset_seg") or 0))
        self.input_video_offset.setSuffix(" s")
        self.input_video_offset.setMaximumWidth(90)
        video_row.addWidget(self.input_video_offset)

        video_row.addStretch()
        self.btn_detect_duration = QPushButton("🎬 Detectar duración")
        self.btn_detect_duration.setStyleSheet("background-color: #6C757D;")
        self.btn_detect_duration.clicked.connect(self._detect_video_duration)
        video_row.addWidget(self.btn_detect_duration)

        outer.addLayout(video_row)

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
        self.input_css.setFixedHeight(70)
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

    def _on_template_changed(self, template_name):
        defaults = get_template_defaults(template_name)
        if not defaults:
            return
        if "tipo" in defaults:
            idx = 1 if defaults["tipo"] == "url" else 0
            self.combo_type.setCurrentIndex(idx)
            self.stack.setCurrentIndex(idx)
        if "duration" in defaults:
            self.input_duration.setValue(int(defaults["duration"]))
        if "ancho" in defaults:
            self.input_width.setValue(int(defaults["ancho"]))
        if "alto" in defaults:
            self.input_height.setValue(int(defaults["alto"]))
        if "fps" in defaults:
            self.input_fps.setValue(int(defaults["fps"]))
        if "reload_on_activate" in defaults:
            self.chk_reload.setChecked(bool(defaults["reload_on_activate"]))
        if "keep_session" in defaults:
            self.chk_keep_session.setChecked(bool(defaults["keep_session"]))
        if "custom_css" in defaults:
            self.input_css.setPlainText(defaults["custom_css"] or "")
        if "refresh_interval_seg" in defaults:
            interval = int(defaults["refresh_interval_seg"] or 0)
            self.chk_auto_refresh.setChecked(interval > 0)
            if interval > 0:
                self.input_refresh_interval.setValue(interval)
        if "video_loop" in defaults:
            self.chk_video_loop.setChecked(bool(defaults["video_loop"]))
        if "video_restart_on_activate" in defaults:
            self.chk_video_restart.setChecked(bool(defaults["video_restart_on_activate"]))
        if "video_mute" in defaults:
            self.chk_video_mute.setChecked(bool(defaults["video_mute"]))
        if "video_volume_pct" in defaults:
            self.input_video_volume.setValue(int(defaults["video_volume_pct"]))
        if "video_offset_seg" in defaults:
            self.input_video_offset.setValue(int(defaults["video_offset_seg"]))

    # --------- CICLO DE VIDA DEL PREVIEW ---------

    def _current_source_name(self):
        """Source name basado en el scene original (no cambia al editar el nombre
        dentro del diálogo — el source en OBS aún tiene el nombre viejo)."""
        tipo = self._scene.get("tipo", "file")
        return _source_name_for(tipo, self._scene.get("name"))

    def _start_preview_thread(self):
        if self._preview_thread is not None:
            return
        scene_name = self._scene.get("name")
        source_name = self._current_source_name()
        if not scene_name or not self._obs_client:
            return
        self._preview_thread = PreviewThread(
            self._obs_client, scene_name, source_name,
            fps=self._preview_widget.current_fps() if self._preview_widget else 3,
        )
        self._preview_thread.worker.frame_ready.connect(self._preview_widget.set_pixmap)
        self._preview_thread.worker.transform_updated.connect(self._preview_widget.update_coverage)
        self._preview_thread.start()

    def _stop_preview_thread(self):
        if self._preview_thread is None:
            return
        try:
            self._preview_thread.stop()
        except Exception as e:
            log.debug("Error deteniendo preview thread: %s", e)
        self._preview_thread = None

    def showEvent(self, event):
        super().showEvent(event)
        if self._preview_widget is not None and self._preview_thread is None:
            # Refrescar tamaño de canvas por si cambió (OBS puede haberse
            # reconectado con settings distintos entre aperturas del diálogo).
            if self._obs_client:
                cw = getattr(self._obs_client, "canvas_width", 1920) or 1920
                ch = getattr(self._obs_client, "canvas_height", 1080) or 1080
                self._preview_widget.set_canvas_size(cw, ch)
            self._preview_widget.set_placeholder("Cargando preview…")
            self._start_preview_thread()

    def closeEvent(self, event):
        self._stop_preview_thread()
        if self._floating_preview is not None:
            try:
                self._floating_preview.close()
            except Exception:
                pass
            self._floating_preview = None
        super().closeEvent(event)

    def reject(self):
        # Al cancelar, si tocamos el transform en vivo, revertir al original en OBS
        if self._transform_dirty and self._obs_client and not self.is_new:
            z0, px0, py0 = self._original_transform
            source_name = self._current_source_name()
            try:
                self._obs_client.set_source_transform(
                    self._scene.get("name"), source_name, z0, px0, py0
                )
            except Exception as e:
                log.warning("No se pudo revertir transform tras Cancel: %s", e)
        super().reject()

    # --------- LIVE TRANSFORM ---------

    def _schedule_transform(self, _value=None):
        # Marcamos dirty y armamos el debounce
        self._transform_dirty = True
        self._transform_debounce.start()

    def _apply_live_transform(self):
        if not self._obs_client or self.is_new:
            return
        source_name = self._current_source_name()
        if not source_name:
            return
        try:
            self._obs_client.set_source_transform(
                self._scene.get("name"), source_name,
                self.input_zoom.value(),
                self.input_pan_x.value(),
                self.input_pan_y.value(),
            )
        except Exception as e:
            log.debug("Live transform falló: %s", e)

    # --------- FLOATING PREVIEW ---------

    def _on_detach_preview(self):
        """Abrir el preview en ventana flotante."""
        if not self._preview_widget or self._floating_preview is not None:
            return
        # Snapshot del estado actual para replicarlo en la floating
        state = {
            "fps": self._preview_widget.spin_fps.value(),
            "show_thirds": self._preview_widget.chk_thirds.isChecked(),
            "show_safe": self._preview_widget.chk_safe.isChecked(),
            "show_coverage": self._preview_widget.chk_coverage.isChecked(),
        }
        # Detener el preview del diálogo para no duplicar carga
        self._stop_preview_thread()
        self._preview_widget.setVisible(False)
        self._detached_placeholder.setVisible(True)

        cw = getattr(self._obs_client, "canvas_width", 1920) or 1920
        ch = getattr(self._obs_client, "canvas_height", 1080) or 1080
        self._floating_preview = ScenePreviewDialog(
            self._obs_client,
            self._scene.get("name"),
            self._current_source_name(),
            canvas_w=cw, canvas_h=ch,
            available_scenes=None,  # scene switcher solo si se pasa lista
            fps=state["fps"],
            show_thirds=state["show_thirds"],
            show_safe=state["show_safe"],
            show_coverage=state["show_coverage"],
            parent=self,
        )
        self._floating_preview.closed_by_user.connect(self._on_floating_closed)
        self._floating_preview.show()

    def _on_reattach_preview(self):
        """Botón ↙ presionado dentro del widget (poco probable en este flujo)."""
        if self._floating_preview:
            self._floating_preview.close()

    def _on_floating_closed(self):
        # Recuperar estado del floating (por si el usuario cambió FPS/overlays)
        if self._floating_preview:
            state = self._floating_preview.current_state()
            self._preview_widget.spin_fps.setValue(state["fps"])
            self._preview_widget.chk_thirds.setChecked(state["show_thirds"])
            self._preview_widget.chk_safe.setChecked(state["show_safe"])
            self._preview_widget.chk_coverage.setChecked(state["show_coverage"])
            self._floating_preview = None

        self._detached_placeholder.setVisible(False)
        self._preview_widget.setVisible(True)
        self._preview_widget.set_placeholder("Reanudando preview…")
        self._start_preview_thread()

    def _on_refresh_preview(self):
        """El polling ya está corriendo — el próximo tick trae el frame nuevo.
        Este slot existe por si en el futuro añadimos un force-refresh manual."""
        pass

    def _on_fps_changed(self, fps):
        if self._preview_thread:
            self._preview_thread.set_fps(fps)

    def get_values(self):
        tipo = self.combo_type.currentData()
        css_text = self.input_css.toPlainText().strip()
        return {
            "id": self._scene.get("id"),
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
