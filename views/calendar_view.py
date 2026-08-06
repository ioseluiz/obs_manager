from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QSpinBox, QPushButton, QLineEdit, QGroupBox,
                             QHBoxLayout, QLabel)


class CalendarView(QWidget):
    def __init__(self, current_settings):
        super().__init__()
        self.layout = QVBoxLayout(self)

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
        bg_layout.addWidget(self.input_bg_file)
        bg_layout.addWidget(self.btn_browse_bg)

        circle_layout = QHBoxLayout()
        self.input_circle_file = QLineEdit()
        self.input_circle_file.setPlaceholderText("Selecciona el PNG del globo/círculo...")
        self.btn_browse_circle = QPushButton("📁")
        circle_layout.addWidget(self.input_circle_file)
        circle_layout.addWidget(self.btn_browse_circle)

        self.btn_build_scene = QPushButton("🛠 Construir Escena en OBS")
        self.btn_build_scene.setStyleSheet("background-color: #198754;")

        build_layout.addRow("Nombre de la Escena:", self.input_scene_name)
        build_layout.addRow("Nombre del Marcador:", self.input_source_name)
        build_layout.addRow("Imagen de Fondo:", bg_layout)
        build_layout.addRow("Imagen del Marcador:", circle_layout)
        build_layout.addRow("", self.btn_build_scene)

        build_group.setLayout(build_layout)
        self.layout.addWidget(build_group)

        # --- PANEL 2: CALIBRACIÓN MATEMÁTICA ---
        # Ahora dividida en Común (X + escala) + Plantilla 5 semanas + Plantilla 6 semanas.

        common_group = QGroupBox("2. Calibración común (columnas X + escala)")
        common_layout = QFormLayout()

        # Los spinboxes X_START y X_SPACE ahora comparten defaults del Lua original.
        self.spin_x_start = self._create_spinbox(3000, current_settings.get("cal_x_start", 180))
        self.spin_x_space = self._create_spinbox(500, current_settings.get("cal_x_space", 190))

        self.spin_scale = QSpinBox()
        self.spin_scale.setRange(1, 500)
        self.spin_scale.setValue(current_settings.get("cal_scale", 100))
        self.spin_scale.setSuffix(" %")

        common_layout.addRow("Posición X (Domingo Sem 1):", self.spin_x_start)
        common_layout.addRow("Espaciado Horizontal (ΔX):", self.spin_x_space)
        common_layout.addRow("Tamaño del Círculo (Escala):", self.spin_scale)

        common_group.setLayout(common_layout)
        self.layout.addWidget(common_group)

        # Plantilla 5 semanas (celdas grandes)
        cal5_group = QGroupBox("3. Plantilla 5 semanas (celdas grandes)")
        cal5_layout = QFormLayout()
        self.spin_y_start_5w = self._create_spinbox(3000, current_settings.get("cal_y_start_5w", 165))
        self.spin_y_space_5w = self._create_spinbox(500, current_settings.get("cal_y_space_5w", 185))
        cal5_layout.addRow("Posición Y (Domingo Sem 1) — 5 sem:", self.spin_y_start_5w)
        cal5_layout.addRow("Espaciado Vertical (ΔY) — 5 sem:", self.spin_y_space_5w)
        cal5_group.setLayout(cal5_layout)
        self.layout.addWidget(cal5_group)

        # Plantilla 6 semanas (celdas comprimidas)
        cal6_group = QGroupBox("4. Plantilla 6 semanas (celdas comprimidas)")
        cal6_layout = QFormLayout()
        self.spin_y_start_6w = self._create_spinbox(3000, current_settings.get("cal_y_start_6w", 155))
        self.spin_y_space_6w = self._create_spinbox(500, current_settings.get("cal_y_space_6w", 155))
        cal6_layout.addRow("Posición Y (Domingo Sem 1) — 6 sem:", self.spin_y_start_6w)
        cal6_layout.addRow("Espaciado Vertical (ΔY) — 6 sem:", self.spin_y_space_6w)
        cal6_group.setLayout(cal6_layout)
        self.layout.addWidget(cal6_group)

        hint = QLabel(
            "La calibración correcta se aplica automáticamente según cuántas "
            "semanas tenga el mes actual."
        )
        hint.setStyleSheet("color: #6C757D; font-size: 11px;")
        hint.setWordWrap(True)
        self.layout.addWidget(hint)

        # --- BOTONES DE ACCIÓN ---
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Guardar Calibración")
        self.btn_save.setStyleSheet("background-color: #6C757D;")
        self.btn_test = QPushButton("🎯 Mover Círculo a HOY")

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_test)

        self.layout.addLayout(btn_layout)
        self.layout.addStretch()

    def _create_spinbox(self, max_val, default_val):
        spin = QSpinBox()
        spin.setRange(-1000, max_val)
        spin.setValue(int(default_val))
        spin.setSuffix(" px")
        return spin
