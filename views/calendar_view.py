from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, 
                             QSpinBox, QPushButton, QLineEdit, QGroupBox, QHBoxLayout, QLabel)

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
        grid_group = QGroupBox("2. Calibración Matemática de la Cuadrícula")
        grid_layout = QFormLayout()

        self.spin_x_start = self._create_spinbox(3000, current_settings.get("cal_x_start", 270))
        self.spin_y_start = self._create_spinbox(3000, current_settings.get("cal_y_start", 157))
        self.spin_x_space = self._create_spinbox(500, current_settings.get("cal_x_space", 159))
        self.spin_y_space = self._create_spinbox(500, current_settings.get("cal_y_space", 148))

        self.spin_scale = QSpinBox()
        self.spin_scale.setRange(1, 500) # Permite desde 1% hasta 500%
        self.spin_scale.setValue(current_settings.get("cal_scale", 100))
        self.spin_scale.setSuffix(" %")

        grid_layout.addRow("Posición X (Domingo Sem 1):", self.spin_x_start)
        grid_layout.addRow("Posición Y (Domingo Sem 1):", self.spin_y_start)
        grid_layout.addRow("Espaciado Horizontal (ΔX):", self.spin_x_space)
        grid_layout.addRow("Espaciado Vertical (ΔY):", self.spin_y_space)
        grid_layout.addRow("Tamaño del Círculo (Escala):", self.spin_scale)
        
        grid_group.setLayout(grid_layout)
        self.layout.addWidget(grid_group)

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