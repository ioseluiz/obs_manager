from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QLineEdit, QSpinBox, 
                             QLabel, QHeaderView, QGroupBox, QGridLayout)
from PyQt6.QtCore import Qt

class SceneView(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # --- PANEL SUPERIOR: Controles de Reproducción ---
        controls_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ Iniciar Rotador")
        self.btn_start.setStyleSheet("background-color: #198754;") 
        
        self.btn_stop = QPushButton("⏹ Detener Rotador")
        self.btn_stop.setStyleSheet("background-color: #DC3545;") 
        self.btn_stop.setEnabled(False)

        self.lbl_status = QLabel("Estado: Detenido")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #6C757D;")

        self.lbl_date = QLabel("Fecha...")
        self.lbl_date.setStyleSheet("font-weight: bold; color: #495057; font-size: 15px;")
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        controls_layout.addWidget(self.btn_start)
        controls_layout.addWidget(self.btn_stop)
        controls_layout.addWidget(self.lbl_status)
        controls_layout.addStretch()
        controls_layout.addWidget(self.lbl_date)
        
        self.layout.addLayout(controls_layout)

        # --- TABLA DE ESCENAS ---
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "Nombre de Escena en OBS", "Duración (Segundos)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.hideColumn(0) 
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.layout.addWidget(self.table)

        # --- PANEL INFERIOR: Agregar / Eliminar ---
        add_group = QGroupBox("Agregar Nueva Escena a la Rotación")
        grid_layout = QGridLayout()

        # Fila 1: Nombre
        grid_layout.addWidget(QLabel("Nombre (OBS):"), 0, 0)
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Ej: FIESTAS PATRIAS")
        grid_layout.addWidget(self.input_name, 0, 1, 1, 2)

        # Fila 2: Archivo Multimedia (Opcional)
        grid_layout.addWidget(QLabel("Multimedia:"), 1, 0)
        self.input_file = QLineEdit()
        self.input_file.setPlaceholderText("Selecciona archivo o pega una URL (http://...)")
        self.input_file.setReadOnly(False) # AHORA ES FALSE para que el usuario pueda pegar links
        grid_layout.addWidget(self.input_file, 1, 1)
        
        self.btn_browse = QPushButton("📁 Buscar")
        self.btn_browse.setStyleSheet("background-color: #6C757D;")
        grid_layout.addWidget(self.btn_browse, 1, 2)

        # Fila 3: Tiempo y Botones
        grid_layout.addWidget(QLabel("Tiempo (seg):"), 2, 0)
        self.input_duration = QSpinBox()
        self.input_duration.setRange(1, 3600)
        self.input_duration.setValue(20)
        grid_layout.addWidget(self.input_duration, 2, 1)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Agregar Escena")
        self.btn_delete = QPushButton("Eliminar Seleccionada")
        self.btn_delete.setStyleSheet("background-color: #DC3545;")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_delete)
        
        grid_layout.addLayout(btn_layout, 2, 2)
        add_group.setLayout(grid_layout)
        self.layout.addWidget(add_group)

    def populate_table(self, scenes):
        self.table.setRowCount(0)
        for row, scene in enumerate(scenes):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(scene["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(scene["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(str(scene["duration"])))

    def get_selected_scene_id(self):
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            return int(self.table.item(row, 0).text())
        return None