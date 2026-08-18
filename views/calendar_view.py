from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QSpinBox, QPushButton, QLineEdit, QGroupBox,
                             QHBoxLayout, QLabel, QScrollArea, QFrame,
                             QComboBox)


class CalendarView(QWidget):
    def __init__(self, current_settings):
        super().__init__()

        # El layout raíz de la vista contiene un QScrollArea que envuelve todo.
        # Esto permite trabajar cómodamente en laptops de 14" donde el
        # contenido combinado (4 groupboxes) excede la altura útil (~540px).
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)
        self.layout = QVBoxLayout(inner)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(8)

        # --- PANEL 1: CONSTRUCTOR AUTOMÁTICO EN OBS ---
        build_group = QGroupBox("1. Constructor Automático de Escena")
        build_layout = QFormLayout()

        self.input_scene_name = QLineEdit(current_settings.get("cal_scene", "CUMPLEANOS DEL MES"))
        self.input_source_name = QLineEdit(current_settings.get("cal_source", "CIRCULO"))

        # Selectores de archivo
        bg_layout = QHBoxLayout()
        self.input_bg_file = QLineEdit()
        self.input_bg_file.setPlaceholderText("Selecciona la imagen del mes...")
        self.btn_browse_bg = QPushButton("📁")
        self.btn_browse_bg.setMaximumWidth(40)
        bg_layout.addWidget(self.input_bg_file)
        bg_layout.addWidget(self.btn_browse_bg)

        circle_layout = QHBoxLayout()
        self.input_circle_file = QLineEdit()
        self.input_circle_file.setPlaceholderText("Selecciona el PNG del globo/círculo...")
        self.btn_browse_circle = QPushButton("📁")
        self.btn_browse_circle.setMaximumWidth(40)
        circle_layout.addWidget(self.input_circle_file)
        circle_layout.addWidget(self.btn_browse_circle)

        self.spin_build_start_day = QSpinBox()
        self.spin_build_start_day.setRange(1, 31)
        self.spin_build_start_day.setValue(1)
        self.spin_build_start_day.setSuffix(" (día del mes)")
        self.spin_build_start_day.setToolTip(
            "Día inicial donde se colocará el círculo al construir la escena. "
            "Al iniciar la rotación se moverá automáticamente al día de hoy."
        )

        self.btn_build_scene = QPushButton("🛠 Construir Escena en OBS")
        self.btn_build_scene.setStyleSheet("background-color: #198754;")

        build_layout.addRow("Nombre de la Escena:", self.input_scene_name)
        build_layout.addRow("Nombre del Marcador:", self.input_source_name)
        build_layout.addRow("Imagen de Fondo:", bg_layout)
        build_layout.addRow("Imagen del Marcador:", circle_layout)
        build_layout.addRow("Día inicial (opcional):", self.spin_build_start_day)
        build_layout.addRow("", self.btn_build_scene)

        build_group.setLayout(build_layout)
        self.layout.addWidget(build_group)

        # --- PANEL 2: SELECTOR DE PLANTILLA ACTIVA ---
        common_group = QGroupBox("2. Plantilla activa")
        common_layout = QFormLayout()

        self.combo_template_weeks = QComboBox()
        self.combo_template_weeks.addItem("Auto (según el mes)", userData="auto")
        self.combo_template_weeks.addItem("4 semanas", userData="4")
        self.combo_template_weeks.addItem("5 semanas", userData="5")
        self.combo_template_weeks.addItem("6 semanas", userData="6")
        self.combo_template_weeks.setToolTip(
            "Elige la plantilla según cuántas filas tenga la imagen del calendario "
            "cargada como fondo. Auto detecta 4/5/6 semanas del mes actual."
        )
        current_tpl = str(current_settings.get("cal_template_weeks", "auto")).lower()
        idx = self.combo_template_weeks.findData(current_tpl)
        self.combo_template_weeks.setCurrentIndex(idx if idx >= 0 else 0)

        common_layout.addRow("Semanas de la imagen:", self.combo_template_weeks)

        common_group.setLayout(common_layout)
        self.layout.addWidget(common_group)

        # --- PANELES 3, 4 y 5 lado a lado: plantillas 4 / 5 / 6 semanas ---
        # Cada panel guarda TODA la calibración de esa plantilla (X, Y, escala).
        # Así al cambiar entre imágenes con distinta geometría cada una recuerda
        # sus valores y no hay que reconfigurar.
        templates_row = QHBoxLayout()
        templates_row.setSpacing(8)

        self._template_groups = {}
        for key, title, tooltip in (
            ("4", "3. Plantilla 4 semanas",
             "Aplicada cuando la imagen del calendario ocupa 4 filas (celdas muy grandes)"),
            ("5", "4. Plantilla 5 semanas",
             "Aplicada cuando la imagen del calendario ocupa 5 filas (celdas grandes)"),
            ("6", "5. Plantilla 6 semanas",
             "Aplicada cuando la imagen del calendario ocupa 6 filas (celdas comprimidas)"),
        ):
            group = QGroupBox(title)
            group.setToolTip(tooltip)
            form = QFormLayout()

            spin_x_start = self._create_spinbox(
                3000, current_settings.get(f"cal_x_start_{key}w", 298))
            spin_x_space = self._create_spinbox(
                500, current_settings.get(f"cal_x_space_{key}w", 191))
            spin_y_start = self._create_spinbox(
                3000, current_settings.get(f"cal_y_start_{key}w", 200))
            spin_y_space = self._create_spinbox(
                500, current_settings.get(f"cal_y_space_{key}w", 182))
            spin_scale = QSpinBox()
            spin_scale.setRange(1, 500)
            spin_scale.setValue(current_settings.get(f"cal_scale_{key}w", 100))
            spin_scale.setSuffix(" %")

            # Compensaciones para fila 0 (primera semana parcial). Se aplican
            # SOLO cuando el día cae en fila 0 — útil cuando la imagen dibuja
            # esa fila desplazada del slot uniforme.
            spin_dx_row0 = self._create_spinbox(
                500, current_settings.get(f"cal_dx_row0_{key}w", 0))
            spin_dy_row0 = self._create_spinbox(
                500, current_settings.get(f"cal_dy_row0_{key}w", 0))
            for s in (spin_dx_row0, spin_dy_row0):
                s.setMinimum(-500)
                s.setToolTip(
                    "Compensación en píxeles aplicada SOLO a los días de la "
                    "primera semana parcial (fila 0). Déjalo en 0 si tu imagen "
                    "tiene fila 0 alineada con el resto del grid."
                )

            setattr(self, f"spin_x_start_{key}w", spin_x_start)
            setattr(self, f"spin_x_space_{key}w", spin_x_space)
            setattr(self, f"spin_y_start_{key}w", spin_y_start)
            setattr(self, f"spin_y_space_{key}w", spin_y_space)
            setattr(self, f"spin_scale_{key}w", spin_scale)
            setattr(self, f"spin_dx_row0_{key}w", spin_dx_row0)
            setattr(self, f"spin_dy_row0_{key}w", spin_dy_row0)

            form.addRow("Posición X (Domingo Sem 1):", spin_x_start)
            form.addRow("Espaciado Horizontal ΔX:", spin_x_space)
            form.addRow("Posición Y (Sem 1):", spin_y_start)
            form.addRow("Espaciado Vertical ΔY:", spin_y_space)
            form.addRow("Escala del marcador:", spin_scale)
            form.addRow("Comp. X fila 0:", spin_dx_row0)
            form.addRow("Comp. Y fila 0:", spin_dy_row0)

            group.setLayout(form)
            templates_row.addWidget(group)
            self._template_groups[key] = group

        self.layout.addLayout(templates_row)

        self.lbl_active_template = QLabel()
        self.lbl_active_template.setStyleSheet("color: #6C757D; font-size: 11px;")
        self.lbl_active_template.setWordWrap(True)
        self.layout.addWidget(self.lbl_active_template)

        # --- FILA "LEER DEL MARCADOR EN OBS" ---
        # Arrastras el marcador en OBS, aquí indicas a qué día corresponde y
        # a qué campo aplicar. La app lee la transform y recalcula.
        read_row = QHBoxLayout()
        read_row.setSpacing(6)
        read_row.addWidget(QLabel("Referencia día:"))

        self.spin_read_ref_day = QSpinBox()
        self.spin_read_ref_day.setRange(1, 31)
        self.spin_read_ref_day.setValue(1)
        self.spin_read_ref_day.setMaximumWidth(60)
        read_row.addWidget(self.spin_read_ref_day)

        read_row.addWidget(QLabel("Aplicar a:"))
        self.combo_read_target = QComboBox()
        self.combo_read_target.addItem("X/Y de la plantilla activa", userData="grid")
        self.combo_read_target.addItem("Compensación fila 0", userData="row0")
        self.combo_read_target.setToolTip(
            "\"X/Y de la plantilla\" recalcula X_START y Y_START (afecta todos los días).\n"
            "\"Compensación fila 0\" solo ajusta el desfase de la primera semana parcial."
        )
        read_row.addWidget(self.combo_read_target)

        self.btn_read_obs = QPushButton("📥 Leer del marcador OBS")
        self.btn_read_obs.setStyleSheet("background-color: #6610F2;")
        self.btn_read_obs.setToolTip(
            "Lee la posición y escala actuales del marcador en OBS y las convierte "
            "en valores de calibración para el día indicado."
        )
        read_row.addWidget(self.btn_read_obs)
        read_row.addStretch()

        self.layout.addLayout(read_row)

        # --- BOTONES DE ACCIÓN ---
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Guardar Calibración")
        self.btn_save.setStyleSheet("background-color: #6C757D;")
        self.btn_test = QPushButton("🎯 Mover Círculo a HOY")
        self.btn_simulate = QPushButton("🎬 Iniciar Simulación...")
        self.btn_simulate.setStyleSheet("background-color: #0D6EFD;")

        # Export/Import de la calibración a JSON — para poder llevar la
        # configuración del calendario a otra máquina o hacer respaldo.
        # Etiqueta explícita para diferenciar del Exportar/Importar del
        # toolbar principal (que maneja escenas).
        self.btn_export_cal = QPushButton("📤 Exportar Settings Calendario")
        self.btn_export_cal.setToolTip(
            "Guarda la calibración del calendario (nombres, plantilla activa "
            "y los tres bloques 4/5/6 semanas) en un archivo JSON portable. "
            "No confundir con «Exportar» del toolbar principal, que exporta "
            "escenas."
        )
        self.btn_import_cal = QPushButton("📥 Importar Settings Calendario")
        self.btn_import_cal.setToolTip(
            "Restaura la calibración del calendario desde un archivo JSON "
            "exportado previamente. No confundir con «Importar» del toolbar "
            "principal, que importa escenas."
        )

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_test)
        btn_layout.addWidget(self.btn_simulate)
        btn_layout.addWidget(self.btn_export_cal)
        btn_layout.addWidget(self.btn_import_cal)

        self.layout.addLayout(btn_layout)
        self.layout.addStretch()

    def _create_spinbox(self, max_val, default_val):
        spin = QSpinBox()
        spin.setRange(-1000, max_val)
        spin.setValue(int(default_val))
        spin.setSuffix(" px")
        return spin
