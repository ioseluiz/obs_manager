from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QHBoxLayout

class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de Conexión OBS")
        self.setFixedSize(350, 200)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.host_input = QLineEdit(current_settings.get("host"))
        self.port_input = QLineEdit(str(current_settings.get("port")))
        self.password_input = QLineEdit(current_settings.get("password"))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout.addRow("Host:", self.host_input)
        form_layout.addRow("Puerto:", self.port_input)
        form_layout.addRow("Contraseña:", self.password_input)
        
        layout.addLayout(form_layout)

        # Botones
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Guardar y Conectar")
        self.btn_cancel = QPushButton("Cancelar")
        
        # Estilo específico para cancelar para contrastar con el estilo global
        self.btn_cancel.setStyleSheet("background-color: #6C757D;") 

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

        # Conexiones internas de los botones
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self.accept)

    def get_inputs(self):
        return {
            "host": self.host_input.text(),
            "port": self.port_input.text(),
            "password": self.password_input.text()
        }