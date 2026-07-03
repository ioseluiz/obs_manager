from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QLineEdit, QSpinBox,
                             QLabel, QHeaderView, QGroupBox, QGridLayout,
                             QComboBox, QStackedWidget, QCheckBox, QFormLayout,
                             QPlainTextEdit, QSlider)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from views.schedule_widget import ScheduleWidget, format_schedule_summary

ACTIVE_ROW_BG = QColor("#CCE5FF")  # azul claro, alta legibilidad sobre texto oscuro

CSS_PLACEHOLDER = (
    "/* CSS opcional inyectado en la página (dashboards, etc.) */\n"
    "body { background: transparent; margin: 0; overflow: hidden; }\n"
    "::-webkit-scrollbar { display: none; }"
)

class SceneView(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self._active_scene_name = None

        # --- PANEL SUPERIOR: Controles de Reproducción ---
        controls_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ Iniciar Rotador")
        self.btn_start.setStyleSheet("background-color: #198754;")

        self.btn_prev = QPushButton("⏮")
        self.btn_prev.setToolTip("Escena anterior (cancela el countdown actual)")
        self.btn_prev.setStyleSheet("background-color: #6C757D;")
        self.btn_prev.setMaximumWidth(50)
        self.btn_prev.setEnabled(False)

        self.btn_pause = QPushButton("⏸ Pausar")
        self.btn_pause.setToolTip("Congelar el countdown en la escena actual")
        self.btn_pause.setStyleSheet("background-color: #FD7E14;")
        self.btn_pause.setEnabled(False)

        self.btn_next = QPushButton("⏭")
        self.btn_next.setToolTip("Escena siguiente (cancela el countdown actual)")
        self.btn_next.setStyleSheet("background-color: #6C757D;")
        self.btn_next.setMaximumWidth(50)
        self.btn_next.setEnabled(False)

        self.btn_stop = QPushButton("⏹ Detener Rotador")
        self.btn_stop.setStyleSheet("background-color: #DC3545;")
        self.btn_stop.setEnabled(False)

        self.lbl_status = QLabel("Estado: Detenido")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #6C757D;")

        self.lbl_date = QLabel("Fecha...")
        self.lbl_date.setStyleSheet("font-weight: bold; color: #495057; font-size: 15px;")
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        controls_layout.addWidget(self.btn_start)
        controls_layout.addWidget(self.btn_prev)
        controls_layout.addWidget(self.btn_pause)
        controls_layout.addWidget(self.btn_next)
        controls_layout.addWidget(self.btn_stop)
        controls_layout.addWidget(self.lbl_status)
        controls_layout.addStretch()
        controls_layout.addWidget(self.lbl_date)

        self.layout.addLayout(controls_layout)

        # --- TABLA DE ESCENAS ---
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Nombre de Escena en OBS", "Tipo", "Contenido", "Duración (s)", "Programación"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.hideColumn(0)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Stretch=1 → la tabla absorbe todo el espacio vertical libre
        self.layout.addWidget(self.table, 1)

        # --- PANEL AJUSTE EN VIVO ---
        self.layout.addWidget(self._build_live_panel(), 0)

        # --- PANEL INFERIOR: Agregar / Eliminar ---
        add_group = QGroupBox("Agregar Nueva Escena a la Rotación")
        grid_layout = QGridLayout()

        # Fila 0: Nombre
        grid_layout.addWidget(QLabel("Nombre (OBS):"), 0, 0)
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Ej: FIESTAS PATRIAS")
        grid_layout.addWidget(self.input_name, 0, 1, 1, 2)

        # Fila 1: Tipo de contenido
        grid_layout.addWidget(QLabel("Tipo:"), 1, 0)
        self.combo_type = QComboBox()
        self.combo_type.addItem("Archivo local", "file")
        self.combo_type.addItem("URL / Dashboard", "url")
        grid_layout.addWidget(self.combo_type, 1, 1, 1, 2)

        # Fila 2: Stack con paneles según tipo
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_file_panel())
        self.stack.addWidget(self._build_web_panel())
        grid_layout.addWidget(self.stack, 2, 0, 1, 3)

        # Fila 3: Zoom + Pan (universal — aplica a cualquier tipo)
        grid_layout.addWidget(QLabel("Ajuste visual:"), 3, 0)
        zoom_row = QHBoxLayout()

        self.input_zoom = QSpinBox()
        self.input_zoom.setRange(10, 500)
        self.input_zoom.setValue(100)
        self.input_zoom.setSuffix(" %")
        self.input_zoom.setToolTip("Zoom del source: 100% tamaño nativo, >100% amplía.")

        self.input_pan_x = QSpinBox()
        self.input_pan_x.setRange(-4000, 4000)
        self.input_pan_x.setValue(0)
        self.input_pan_x.setSuffix(" px")
        self.input_pan_x.setToolTip("Desplazamiento horizontal desde el centro del canvas.")

        self.input_pan_y = QSpinBox()
        self.input_pan_y.setRange(-4000, 4000)
        self.input_pan_y.setValue(0)
        self.input_pan_y.setSuffix(" px")
        self.input_pan_y.setToolTip("Desplazamiento vertical desde el centro del canvas.")

        zoom_row.addWidget(QLabel("Zoom:"))
        zoom_row.addWidget(self.input_zoom)
        zoom_row.addSpacing(12)
        zoom_row.addWidget(QLabel("Pan X:"))
        zoom_row.addWidget(self.input_pan_x)
        zoom_row.addSpacing(12)
        zoom_row.addWidget(QLabel("Pan Y:"))
        zoom_row.addWidget(self.input_pan_y)
        zoom_row.addStretch()
        grid_layout.addLayout(zoom_row, 3, 1, 1, 2)

        # Fila 4: Programación (días + horario)
        grid_layout.addWidget(QLabel("Programación:"), 4, 0)
        self.schedule_widget = ScheduleWidget()
        grid_layout.addWidget(self.schedule_widget, 4, 1, 1, 2)

        # Fila 5: Duración + botones
        grid_layout.addWidget(QLabel("Tiempo (seg):"), 5, 0)
        self.input_duration = QSpinBox()
        self.input_duration.setRange(1, 3600)
        self.input_duration.setValue(20)
        grid_layout.addWidget(self.input_duration, 5, 1)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Agregar Escena")
        self.btn_edit = QPushButton("✏ Editar Seleccionada")
        self.btn_edit.setStyleSheet("background-color: #0D6EFD;")
        self.btn_duplicate = QPushButton("📋 Duplicar")
        self.btn_duplicate.setToolTip("Clonar la escena seleccionada con todos sus ajustes")
        self.btn_duplicate.setStyleSheet("background-color: #6F42C1;")
        self.btn_move_up = QPushButton("▲  Subir")
        self.btn_move_up.setToolTip("Mover escena seleccionada hacia arriba en el orden")
        self.btn_move_up.setStyleSheet("background-color: #6C757D; font-weight: bold;")
        self.btn_move_down = QPushButton("▼  Bajar")
        self.btn_move_down.setToolTip("Mover escena seleccionada hacia abajo en el orden")
        self.btn_move_down.setStyleSheet("background-color: #6C757D; font-weight: bold;")
        self.btn_delete = QPushButton("Eliminar Seleccionada")
        self.btn_delete.setStyleSheet("background-color: #DC3545;")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_duplicate)
        btn_layout.addWidget(self.btn_move_up)
        btn_layout.addWidget(self.btn_move_down)
        btn_layout.addWidget(self.btn_delete)

        grid_layout.addLayout(btn_layout, 5, 2)
        add_group.setLayout(grid_layout)
        self.layout.addWidget(add_group)

        self.combo_type.currentIndexChanged.connect(self.stack.setCurrentIndex)

    def _build_live_panel(self):
        """Panel de zoom/pan en vivo. Actúa sobre la escena seleccionada en la tabla."""
        group = QGroupBox("Ajuste en vivo (selecciona una escena y arrastra los sliders)")
        group.setMaximumHeight(160)
        outer = QVBoxLayout()
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(2)

        self.live_zoom_slider, self.live_zoom_spin = self._make_live_row(
            outer, "Zoom:", 10, 500, 100, " %"
        )
        self.live_panx_slider, self.live_panx_spin = self._make_live_row(
            outer, "Pan X:", -2000, 2000, 0, " px"
        )
        self.live_pany_slider, self.live_pany_spin = self._make_live_row(
            outer, "Pan Y:", -2000, 2000, 0, " px"
        )

        bottom = QHBoxLayout()
        self.lbl_live_target = QLabel("Sin escena seleccionada")
        self.lbl_live_target.setStyleSheet("color: #6C757D; font-style: italic;")
        bottom.addWidget(self.lbl_live_target, 1)
        self.btn_live_reset = QPushButton("🔄 Reset")
        self.btn_live_reset.setToolTip("Restaurar zoom 100% y pan 0,0")
        self.btn_live_reset.setStyleSheet("background-color: #6C757D;")
        bottom.addWidget(self.btn_live_reset)
        outer.addLayout(bottom)

        group.setLayout(outer)
        self._live_widgets = [
            self.live_zoom_slider, self.live_zoom_spin,
            self.live_panx_slider, self.live_panx_spin,
            self.live_pany_slider, self.live_pany_spin,
        ]
        self._set_live_enabled(False)

        # Linkear slider ↔ spinbox
        self._link_slider_spin(self.live_zoom_slider, self.live_zoom_spin)
        self._link_slider_spin(self.live_panx_slider, self.live_panx_spin)
        self._link_slider_spin(self.live_pany_slider, self.live_pany_spin)

        return group

    def _make_live_row(self, parent_layout, label, mn, mx, default, suffix):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(50)
        row.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(mn, mx)
        slider.setValue(default)
        row.addWidget(slider, 1)
        spin = QSpinBox()
        spin.setRange(mn, mx)
        spin.setValue(default)
        spin.setSuffix(suffix)
        spin.setMinimumWidth(90)
        row.addWidget(spin)
        parent_layout.addLayout(row)
        return slider, spin

    def _link_slider_spin(self, slider, spin):
        """Mantiene slider y spinbox sincronizados. Emite ambas señales normalmente."""
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)

    def _set_live_enabled(self, enabled):
        for w in self._live_widgets:
            w.setEnabled(enabled)
        self.btn_live_reset.setEnabled(enabled)

    def set_live_values(self, zoom_pct, pan_x, pan_y, target_label=None):
        """Carga valores en el panel sin disparar señales (para selección de fila)."""
        for w in self._live_widgets:
            w.blockSignals(True)
        self.live_zoom_slider.setValue(int(zoom_pct))
        self.live_zoom_spin.setValue(int(zoom_pct))
        self.live_panx_slider.setValue(int(pan_x))
        self.live_panx_spin.setValue(int(pan_x))
        self.live_pany_slider.setValue(int(pan_y))
        self.live_pany_spin.setValue(int(pan_y))
        for w in self._live_widgets:
            w.blockSignals(False)
        if target_label is not None:
            self.lbl_live_target.setText(target_label)
        self._set_live_enabled(target_label is not None)

    def clear_live_selection(self):
        self.lbl_live_target.setText("Sin escena seleccionada")
        self._set_live_enabled(False)

    def get_live_values(self):
        return (
            self.live_zoom_spin.value(),
            self.live_panx_spin.value(),
            self.live_pany_spin.value(),
        )

    def _build_file_panel(self):
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        row.addWidget(QLabel("Multimedia:"))
        self.input_file = QLineEdit()
        self.input_file.setPlaceholderText("Ruta al archivo (.mp4, .png, .jpg...)")
        row.addWidget(self.input_file, 1)
        self.btn_browse = QPushButton("📁 Buscar")
        self.btn_browse.setStyleSheet("background-color: #6C757D;")
        row.addWidget(self.btn_browse)
        outer.addLayout(row)

        # Opciones de video (ignoradas para imágenes)
        video_note = QLabel("Opciones de video (ignoradas en imágenes):")
        video_note.setStyleSheet("color: #6C757D; font-style: italic;")
        outer.addWidget(video_note)

        row1 = QHBoxLayout()
        self.chk_video_loop = QCheckBox("Repetir en bucle")
        self.chk_video_loop.setChecked(True)
        self.chk_video_restart = QCheckBox("Reiniciar al entrar")
        self.chk_video_restart.setChecked(True)
        row1.addWidget(self.chk_video_loop)
        row1.addWidget(self.chk_video_restart)
        row1.addStretch()
        outer.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_video_mute = QCheckBox("Silenciar")
        row2.addWidget(self.chk_video_mute)
        row2.addWidget(QLabel("Volumen:"))
        self.input_video_volume = QSpinBox()
        self.input_video_volume.setRange(0, 100)
        self.input_video_volume.setValue(100)
        self.input_video_volume.setSuffix(" %")
        row2.addWidget(self.input_video_volume)
        row2.addSpacing(12)
        row2.addWidget(QLabel("Comenzar desde:"))
        self.input_video_offset = QSpinBox()
        self.input_video_offset.setRange(0, 36000)
        self.input_video_offset.setValue(0)
        self.input_video_offset.setSuffix(" seg")
        row2.addWidget(self.input_video_offset)
        row2.addStretch()
        outer.addLayout(row2)

        return panel

    def _build_web_panel(self):
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("URL:"))
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("https://app.powerbi.com/... o https://ejemplo.com/dashboard")
        url_row.addWidget(self.input_url, 1)
        outer.addLayout(url_row)

        opts_row = QHBoxLayout()

        self.input_width = QSpinBox()
        self.input_width.setRange(100, 4000)
        self.input_width.setValue(1920)
        self.input_width.setSuffix(" px")

        self.input_height = QSpinBox()
        self.input_height.setRange(100, 4000)
        self.input_height.setValue(1080)
        self.input_height.setSuffix(" px")

        self.input_fps = QSpinBox()
        self.input_fps.setRange(1, 60)
        self.input_fps.setValue(30)
        self.input_fps.setSuffix(" fps")

        form = QFormLayout()
        form.addRow("Ancho:", self.input_width)
        form.addRow("Alto:", self.input_height)
        form.addRow("FPS:", self.input_fps)
        opts_row.addLayout(form)

        checks = QVBoxLayout()
        self.chk_reload = QCheckBox("Recargar al entrar a la escena")
        self.chk_reload.setChecked(False)
        self.chk_reload.setToolTip("Fuerza recarga de la página cada vez que se activa la escena.\n"
                                   "Desmárcalo para dashboards con sesión (Power BI, etc.).")

        self.chk_keep_session = QCheckBox("Mantener sesión activa (no cerrar navegador)")
        self.chk_keep_session.setChecked(True)
        self.chk_keep_session.setToolTip("Deja el navegador de OBS vivo en segundo plano para preservar la sesión\n"
                                         "de dashboards con login. Solo persiste mientras OBS siga abierto.")

        checks.addWidget(self.chk_reload)
        checks.addWidget(self.chk_keep_session)
        checks.addStretch()
        opts_row.addLayout(checks)

        outer.addLayout(opts_row)

        refresh_row = QHBoxLayout()
        self.chk_auto_refresh = QCheckBox("Auto-refresh cada")
        self.chk_auto_refresh.setToolTip("Recarga la página (F5) periódicamente mientras la escena esté activa.\n"
                                         "Preserva cookies y sesión.")
        self.input_refresh_interval = QSpinBox()
        self.input_refresh_interval.setRange(5, 3600)
        self.input_refresh_interval.setValue(60)
        self.input_refresh_interval.setSuffix(" seg")
        self.input_refresh_interval.setEnabled(False)
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
        self.input_css.setFixedHeight(80)
        outer.addWidget(self.input_css)

        return panel

    def get_current_type(self):
        return self.combo_type.currentData()

    def get_transform_options(self):
        return {
            "zoom_pct": self.input_zoom.value(),
            "pan_x": self.input_pan_x.value(),
            "pan_y": self.input_pan_y.value(),
        }

    def get_video_options(self):
        return {
            "video_loop": self.chk_video_loop.isChecked(),
            "video_restart_on_activate": self.chk_video_restart.isChecked(),
            "video_mute": self.chk_video_mute.isChecked(),
            "video_volume_pct": self.input_video_volume.value(),
            "video_offset_seg": self.input_video_offset.value(),
        }

    def get_schedule_options(self):
        return self.schedule_widget.get_values()

    def get_web_options(self):
        css_text = self.input_css.toPlainText().strip()
        return {
            "url": self.input_url.text().strip(),
            "ancho": self.input_width.value(),
            "alto": self.input_height.value(),
            "fps": self.input_fps.value(),
            "reload_on_activate": self.chk_reload.isChecked(),
            "keep_session": self.chk_keep_session.isChecked(),
            "custom_css": css_text or None,
            "refresh_interval_seg": (
                self.input_refresh_interval.value() if self.chk_auto_refresh.isChecked() else 0
            ),
        }

    def clear_inputs(self):
        self.input_name.clear()
        self.input_file.clear()
        self.input_url.clear()
        self.input_css.clear()
        self.input_zoom.setValue(100)
        self.input_pan_x.setValue(0)
        self.input_pan_y.setValue(0)
        self.chk_auto_refresh.setChecked(False)
        self.input_refresh_interval.setValue(60)
        self.chk_video_loop.setChecked(True)
        self.chk_video_restart.setChecked(True)
        self.chk_video_mute.setChecked(False)
        self.input_video_volume.setValue(100)
        self.input_video_offset.setValue(0)

    def populate_table(self, scenes):
        self.table.setRowCount(0)
        for row, scene in enumerate(scenes):
            self.table.insertRow(row)
            tipo_label = "🌐 URL" if scene.get("tipo") == "url" else "📁 Archivo"
            contenido = scene.get("contenido") or ""
            schedule_label = format_schedule_summary(
                scene.get("active_days"),
                scene.get("active_time_start"),
                scene.get("active_time_end"),
            )
            self.table.setItem(row, 0, QTableWidgetItem(str(scene["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(scene["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(tipo_label))
            self.table.setItem(row, 3, QTableWidgetItem(contenido))
            self.table.setItem(row, 4, QTableWidgetItem(str(scene["duration"])))
            self.table.setItem(row, 5, QTableWidgetItem(schedule_label))
        self._apply_active_highlight()

    def highlight_active_scene(self, scene_name):
        """Marca la fila cuya escena está reproduciéndose. None = ninguna."""
        self._active_scene_name = scene_name
        self._apply_active_highlight()

    def _apply_active_highlight(self):
        default_brush = QBrush()
        active_brush = QBrush(ACTIVE_ROW_BG)
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            if not name_item:
                continue
            is_active = (self._active_scene_name is not None
                         and name_item.text() == self._active_scene_name)
            brush = active_brush if is_active else default_brush
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(brush)

    def set_rotator_state(self, state):
        """state: 'stopped', 'running', 'paused'"""
        if state == "stopped":
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_pause.setText("⏸ Pausar")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.btn_stop.setEnabled(False)
        elif state == "running":
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("⏸ Pausar")
            self.btn_prev.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_stop.setEnabled(True)
        elif state == "paused":
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("▶ Reanudar")
            self.btn_prev.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_stop.setEnabled(True)

    def get_selected_scene_id(self):
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            return int(self.table.item(row, 0).text())
        return None

    def select_row_by_scene_id(self, scene_id):
        """Selecciona la fila cuyo ID coincida (usado tras reorder)."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and int(item.text()) == scene_id:
                self.table.selectRow(row)
                return
