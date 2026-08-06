from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QDateTimeEdit, QCheckBox, QGroupBox, QHeaderView,
                             QComboBox, QDialog, QLabel, QListWidget,
                             QDialogButtonBox, QFontComboBox, QSpinBox,
                             QColorDialog, QSlider)
from PyQt6.QtCore import QDateTime, Qt, QTimer
from PyQt6.QtGui import QColor, QFont


def _make_editable_combo(default_text=""):
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    if default_text:
        combo.setEditText(default_text)
    return combo


def _fill_combo_preserving_text(combo, items):
    current = combo.currentText()
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(sorted(set(items or [])))
    combo.setEditText(current)
    combo.blockSignals(False)


def _qcolor_to_obs_bgr(qcolor):
    """Convierte QColor → int en formato 0xBBGGRR (el que consume text_gdiplus_v3)."""
    return (qcolor.blue() << 16) | (qcolor.green() << 8) | qcolor.red()


class ColorButton(QPushButton):
    """Botón que muestra su color de fondo y abre QColorDialog al pulsar."""

    def __init__(self, initial_qcolor, parent=None):
        super().__init__(parent)
        self._color = QColor(initial_qcolor)
        self.setFixedWidth(60)
        self.setFixedHeight(24)
        self._apply()
        self.clicked.connect(self._pick)

    def _apply(self):
        self.setStyleSheet(
            f"background-color: {self._color.name()}; border: 1px solid #666;"
        )
        self.setText("")

    def _pick(self):
        c = QColorDialog.getColor(self._color, self, "Seleccionar color")
        if c.isValid():
            self._color = c
            self._apply()

    def qcolor(self):
        return QColor(self._color)

    def obs_bgr_int(self):
        return _qcolor_to_obs_bgr(self._color)


class CountdownView(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # --- CONTROLES SUPERIORES ---
        controls_layout = QHBoxLayout()
        self.btn_toggle_sync = QPushButton("▶ Iniciar Sincronización")
        self.btn_toggle_sync.setStyleSheet("background-color: #198754;")
        controls_layout.addWidget(self.btn_toggle_sync)
        controls_layout.addStretch()
        self.btn_refresh_sources = QPushButton("↻ Refrescar de OBS")
        self.btn_refresh_sources.setToolTip(
            "Lee escenas y text sources actuales de OBS para poblar los "
            "combos del formulario."
        )
        controls_layout.addWidget(self.btn_refresh_sources)
        self.layout.addLayout(controls_layout)

        # --- TABLA DE CONTADORES ---
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Evento", "Fecha Objetivo", "Escena"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.hideColumn(0)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.layout.addWidget(self.table)

        # --- FORMULARIO PARA AGREGAR ---
        form_group = QGroupBox("Nuevo Contador")
        form_layout = QFormLayout()

        self.in_nombre = QLineEdit()
        self.in_fecha = QDateTimeEdit(QDateTime.currentDateTime())
        self.in_fecha.setCalendarPopup(True)
        self.in_rep_anual = QCheckBox("Reiniciar anualmente si la fecha ya pasó")

        # Escena OBS a la que pertenece el contador
        self.in_escena = _make_editable_combo()
        self.in_escena.setToolTip(
            "Escena OBS donde viven los text sources de este contador. "
            "Se usa para crear las fuentes faltantes en el sitio correcto."
        )

        # Fuentes de Texto — combos editables (auto-completa con text sources
        # reales de OBS, permite tipear un nombre nuevo).
        self.in_src_dias = _make_editable_combo("TXT_DIAS")
        self.in_src_horas = _make_editable_combo("TXT_HORAS")
        self.in_src_mins = _make_editable_combo("TXT_MINUTOS")
        self.in_src_secs = _make_editable_combo("TXT_SEGUNDOS")

        form_layout.addRow("Nombre del Evento:", self.in_nombre)
        form_layout.addRow("Fecha y Hora:", self.in_fecha)
        form_layout.addRow("", self.in_rep_anual)
        form_layout.addRow("Escena OBS:", self.in_escena)
        form_layout.addRow("Fuente OBS Días:", self.in_src_dias)
        form_layout.addRow("Fuente OBS Horas:", self.in_src_horas)
        form_layout.addRow("Fuente OBS Minutos:", self.in_src_mins)
        form_layout.addRow("Fuente OBS Segundos:", self.in_src_secs)

        form_group.setLayout(form_layout)
        self.layout.addWidget(form_group)

        # --- BOTONES CRUD ---
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Agregar Contador")
        self.btn_edit = QPushButton("Editar Seleccionado")
        self.btn_position = QPushButton("Ajustar Posición")
        self.btn_delete = QPushButton("Eliminar Seleccionado")
        self.btn_delete.setStyleSheet("background-color: #6C757D;")

        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_edit)
        btn_row.addWidget(self.btn_position)
        btn_row.addWidget(self.btn_delete)
        self.layout.addLayout(btn_row)

    def populate_table(self, countdowns):
        self.table.setRowCount(0)
        for row, c in enumerate(countdowns):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(c["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(c["nombre"]))
            self.table.setItem(row, 2, QTableWidgetItem(c["fecha_objetivo"]))
            self.table.setItem(row, 3, QTableWidgetItem(c.get("escena") or ""))

    def set_source_choices(self, names):
        for combo in (self.in_src_dias, self.in_src_horas,
                      self.in_src_mins, self.in_src_secs):
            _fill_combo_preserving_text(combo, names)

    def set_scene_choices(self, names):
        _fill_combo_preserving_text(self.in_escena, names)


class MissingSourcesDialog(QDialog):
    """Lista fuentes faltantes con su escena destino y estilo por defecto."""

    _HALIGN = [("Izquierda", "left"), ("Centro", "center"), ("Derecha", "right")]
    _VALIGN = [("Arriba", "top"), ("Centro", "center"), ("Abajo", "bottom")]
    _STYLE = ["Regular", "Bold", "Italic", "Bold Italic"]

    def __init__(self, source_scene_map, scene_names, parent=None):
        """source_scene_map: dict {source_name: default_scene_or_empty}."""
        super().__init__(parent)
        self.setWindowTitle("Fuentes faltantes en OBS")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Las siguientes fuentes de texto no existen en OBS. "
            "Elige la escena destino para cada una:"
        ))

        # --- Asignación por fuente ---
        assign_group = QGroupBox("Fuentes → Escena")
        assign_form = QFormLayout(assign_group)
        self._row_combos = {}
        for src in sorted(source_scene_map.keys()):
            combo = _make_editable_combo()
            combo.addItems(scene_names or [])
            default = (source_scene_map.get(src) or "").strip()
            if default:
                combo.setEditText(default)
            self._row_combos[src] = combo
            assign_form.addRow(f"{src}:", combo)
        layout.addWidget(assign_group)

        # --- Estilo por defecto ---
        style_group = QGroupBox("Estilo por defecto")
        style_form = QFormLayout(style_group)

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont("Arial"))
        style_form.addRow("Fuente:", self.font_combo)

        self.spin_size = QSpinBox()
        self.spin_size.setRange(8, 500)
        self.spin_size.setValue(96)
        style_form.addRow("Tamaño (pt):", self.spin_size)

        self.combo_style = QComboBox()
        self.combo_style.addItems(self._STYLE)
        self.combo_style.setCurrentText("Bold")
        style_form.addRow("Estilo:", self.combo_style)

        self.color_btn = ColorButton(QColor("white"))
        style_form.addRow("Color texto:", self.color_btn)

        self.check_outline = QCheckBox("Con contorno")
        self.check_outline.setChecked(True)
        style_form.addRow("", self.check_outline)

        self.outline_color_btn = ColorButton(QColor("black"))
        style_form.addRow("Color contorno:", self.outline_color_btn)

        self.spin_outline_size = QSpinBox()
        self.spin_outline_size.setRange(1, 40)
        self.spin_outline_size.setValue(4)
        style_form.addRow("Grosor contorno:", self.spin_outline_size)

        self.combo_halign = QComboBox()
        for label, key in self._HALIGN:
            self.combo_halign.addItem(label, key)
        self.combo_halign.setCurrentIndex(1)
        style_form.addRow("Alineación H:", self.combo_halign)

        self.combo_valign = QComboBox()
        for label, key in self._VALIGN:
            self.combo_valign.addItem(label, key)
        self.combo_valign.setCurrentIndex(1)
        style_form.addRow("Alineación V:", self.combo_valign)

        self.check_outline.toggled.connect(self._on_outline_toggled)
        self._on_outline_toggled(self.check_outline.isChecked())

        layout.addWidget(style_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.create_btn = buttons.addButton(
            "Crear en OBS", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.create_btn.setEnabled(bool(scene_names))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_outline_toggled(self, on):
        self.outline_color_btn.setEnabled(on)
        self.spin_outline_size.setEnabled(on)

    def get_assignments(self):
        """Devuelve dict {source_name: scene_name} con lo elegido por el usuario."""
        return {src: combo.currentText().strip()
                for src, combo in self._row_combos.items()}

    def get_style(self):
        style_str = self.combo_style.currentText()
        flags = 0
        if "Bold" in style_str:
            flags |= 1
        if "Italic" in style_str:
            flags |= 2

        return {
            "font": {
                "face": self.font_combo.currentFont().family(),
                "size": int(self.spin_size.value()),
                "style": style_str,
                "flags": flags,
            },
            "color": self.color_btn.obs_bgr_int(),
            "outline": bool(self.check_outline.isChecked()),
            "outline_color": self.outline_color_btn.obs_bgr_int(),
            "outline_size": int(self.spin_outline_size.value()),
            "outline_opacity": 100,
            "align": self.combo_halign.currentData(),
            "valign": self.combo_valign.currentData(),
        }


class CountdownEditDialog(QDialog):
    """Diálogo modal para editar un contador existente."""

    def __init__(self, countdown, scene_names, source_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Contador")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.in_nombre = QLineEdit(countdown.get("nombre", ""))

        self.in_fecha = QDateTimeEdit()
        self.in_fecha.setCalendarPopup(True)
        fecha_iso = countdown.get("fecha_objetivo") or ""
        qdt = QDateTime.fromString(fecha_iso, Qt.DateFormat.ISODate)
        self.in_fecha.setDateTime(qdt if qdt.isValid() else QDateTime.currentDateTime())

        self.in_rep_anual = QCheckBox("Reiniciar anualmente si la fecha ya pasó")
        self.in_rep_anual.setChecked(bool(countdown.get("repetir_anual")))

        self.in_escena = _make_editable_combo()
        self.in_escena.addItems(sorted(set(scene_names or [])))
        self.in_escena.setEditText(countdown.get("escena") or "")

        src_defaults = [
            ("source_dias", "in_src_dias"),
            ("source_horas", "in_src_horas"),
            ("source_minutos", "in_src_mins"),
            ("source_segundos", "in_src_secs"),
        ]
        source_names_sorted = sorted(set(source_names or []))
        for key, attr in src_defaults:
            combo = _make_editable_combo()
            combo.addItems(source_names_sorted)
            combo.setEditText(countdown.get(key) or "")
            setattr(self, attr, combo)

        form.addRow("Nombre del Evento:", self.in_nombre)
        form.addRow("Fecha y Hora:", self.in_fecha)
        form.addRow("", self.in_rep_anual)
        form.addRow("Escena OBS:", self.in_escena)
        form.addRow("Fuente OBS Días:", self.in_src_dias)
        form.addRow("Fuente OBS Horas:", self.in_src_horas)
        form.addRow("Fuente OBS Minutos:", self.in_src_mins)
        form.addRow("Fuente OBS Segundos:", self.in_src_secs)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return {
            "nombre": self.in_nombre.text().strip(),
            "fecha_objetivo": self.in_fecha.dateTime().toPyDateTime().isoformat(),
            "source_dias": self.in_src_dias.currentText().strip(),
            "source_horas": self.in_src_horas.currentText().strip(),
            "source_minutos": self.in_src_mins.currentText().strip(),
            "source_segundos": self.in_src_secs.currentText().strip(),
            "repetir_anual": self.in_rep_anual.isChecked(),
            "escena": self.in_escena.currentText().strip(),
        }


class CountdownLayoutDialog(QDialog):
    """Ajusta posición, ancho y tamaño de la fila del contador con vista en vivo."""

    _DEBOUNCE_MS = 60

    def __init__(self, countdown, obs_client, parent=None):
        super().__init__(parent)
        self.countdown = countdown
        self.obs_client = obs_client
        self._sources_ordered = [
            (countdown.get("source_dias") or "").strip(),
            (countdown.get("source_horas") or "").strip(),
            (countdown.get("source_minutos") or "").strip(),
            (countdown.get("source_segundos") or "").strip(),
        ]
        self._scene = (countdown.get("escena") or "").strip()

        self._original = {
            "pos_x_pct": int(countdown.get("pos_x_pct") or 50),
            "pos_y_pct": int(countdown.get("pos_y_pct") or 50),
            "spread_pct": int(countdown.get("spread_pct") or 100),
            "scale_pct": int(countdown.get("scale_pct") or 100),
        }

        self.setWindowTitle(f"Ajustar posición: {countdown.get('nombre', '')}")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Los cambios se aplican en OBS en vivo. Cancela para revertir."
        ))

        form = QFormLayout()
        self.slider_x, wx = self._slider_row(0, 100, self._original["pos_x_pct"])
        form.addRow("Posición X (%):", wx)
        self.slider_y, wy = self._slider_row(0, 100, self._original["pos_y_pct"])
        form.addRow("Posición Y (%):", wy)
        self.slider_spread, ws = self._slider_row(10, 200, self._original["spread_pct"])
        form.addRow("Ancho de fila (%):", ws)
        self.slider_scale, wsc = self._slider_row(10, 500, self._original["scale_pct"])
        form.addRow("Tamaño (%):", wsc)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self._on_cancel)
        layout.addWidget(buttons)

        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(self._DEBOUNCE_MS)
        self._apply_timer.timeout.connect(self._apply_to_obs)

        for slider in (self.slider_x, self.slider_y,
                       self.slider_spread, self.slider_scale):
            slider.valueChanged.connect(lambda _v: self._apply_timer.start())

        # Aplicar el estado inicial una vez, por si OBS no tuviera la posición
        # persistida (ej. sources movidos manualmente en OBS).
        self._apply_to_obs()

    def _slider_row(self, mn, mx, val):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(mn, mx)
        slider.setValue(val)
        spin = QSpinBox()
        spin.setRange(mn, mx)
        spin.setValue(val)
        spin.setFixedWidth(70)
        # Sincronizar slider ↔ spinbox sin loop
        def _from_slider(v):
            if spin.value() != v:
                spin.setValue(v)
        def _from_spin(v):
            if slider.value() != v:
                slider.setValue(v)
        slider.valueChanged.connect(_from_slider)
        spin.valueChanged.connect(_from_spin)

        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(slider, 1)
        h.addWidget(spin)
        return slider, container

    def _apply_to_obs(self):
        if not self._scene:
            return
        self.obs_client.position_countdown_sources(
            self._scene, self._sources_ordered,
            x_pct=self.slider_x.value(),
            y_pct=self.slider_y.value(),
            spread_pct=self.slider_spread.value(),
            scale_pct=self.slider_scale.value(),
        )

    def _on_cancel(self):
        # Revertir valores en OBS
        self.slider_x.setValue(self._original["pos_x_pct"])
        self.slider_y.setValue(self._original["pos_y_pct"])
        self.slider_spread.setValue(self._original["spread_pct"])
        self.slider_scale.setValue(self._original["scale_pct"])
        # Aplicar directo (sin debounce) para que quede antes de cerrar
        self._apply_to_obs()
        self.reject()

    def get_values(self):
        return {
            "pos_x_pct": self.slider_x.value(),
            "pos_y_pct": self.slider_y.value(),
            "spread_pct": self.slider_spread.value(),
            "scale_pct": self.slider_scale.value(),
        }
