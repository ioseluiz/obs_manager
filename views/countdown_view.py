from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
                             QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, 
                             QDateTimeEdit, QCheckBox, QGroupBox, QHeaderView)
from PyQt6.QtCore import QDateTime

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
        self.layout.addLayout(controls_layout)

        # --- TABLA DE CONTADORES ---
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "Evento", "Fecha Objetivo"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
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

        # Fuentes de Texto
        self.in_src_dias = QLineEdit("TXT_DIAS")
        self.in_src_horas = QLineEdit("TXT_HORAS")
        self.in_src_mins = QLineEdit("TXT_MINUTOS")
        self.in_src_secs = QLineEdit("TXT_SEGUNDOS")

        form_layout.addRow("Nombre del Evento:", self.in_nombre)
        form_layout.addRow("Fecha y Hora:", self.in_fecha)
        form_layout.addRow("", self.in_rep_anual)
        form_layout.addRow("Fuente OBS Días:", self.in_src_dias)
        form_layout.addRow("Fuente OBS Horas:", self.in_src_horas)
        form_layout.addRow("Fuente OBS Minutos:", self.in_src_mins)
        form_layout.addRow("Fuente OBS Segundos:", self.in_src_secs)

        form_group.setLayout(form_layout)
        self.layout.addWidget(form_group)

        # --- BOTONES CRUD ---
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Agregar Contador")
        self.btn_delete = QPushButton("Eliminar Seleccionado")
        self.btn_delete.setStyleSheet("background-color: #6C757D;")
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_delete)
        self.layout.addLayout(btn_layout)

    def populate_table(self, countdowns):
        self.table.setRowCount(0)
        for row, c in enumerate(countdowns):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(c["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(c["nombre"]))
            self.table.setItem(row, 2, QTableWidgetItem(c["fecha_objetivo"]))