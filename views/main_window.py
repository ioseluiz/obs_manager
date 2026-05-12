import sys
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QTabWidget,
                             QToolBar, QStatusBar, QPushButton, QLabel)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

_BASE = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent.parent
_ICON_PATH = _BASE / "app_icon.ico"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # --- CONFIGURACIÓN DE LA VENTANA ---
        self.setWindowTitle("OBS Automation Manager - INI")
        self.setWindowIcon(QIcon(str(_ICON_PATH)))
        self.setMinimumSize(900, 700)

        # --- WIDGET CENTRAL Y LAYOUT ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # --- CONTENEDOR DE PESTAÑAS (TABS) ---
        # Aquí es donde el MainController insertará SceneView, CalendarView y CountdownView
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True) # Le da un aspecto más moderno en Windows
        self.tabs.setMovable(True)
        self.main_layout.addWidget(self.tabs)

        # --- TOOLBAR (BARRA DE HERRAMIENTAS) ---
        self.toolbar = QToolBar("Barra Principal")
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # Botón de Ajustes
        self.btn_settings = QPushButton(" ⚙ Ajustes")
        self.toolbar.addWidget(self.btn_settings)
        
        self.toolbar.addSeparator()

        # Botón de Conexión OBS
        self.btn_connect = QPushButton(" 🔌 Conectar OBS")
        # Estilo inicial de conexión
        self.btn_connect.setStyleSheet("background-color: #0D6EFD; color: white;")
        self.toolbar.addWidget(self.btn_connect)

        # --- BARRA DE ESTADO (STATUS BAR) ---
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Listo")

        # Label para indicar el estado de la conexión en la barra de estado
        self.lbl_connection_status = QLabel("Desconectado ")
        self.lbl_connection_status.setStyleSheet("color: #DC3545; font-weight: bold;")
        self.statusBar().addPermanentWidget(self.lbl_connection_status)

    def set_connection_ui(self, connected: bool):
        """Cambia visualmente la UI dependiendo de si OBS está conectado o no."""
        if connected:
            self.btn_connect.setText(" ✔ Conectado")
            self.btn_connect.setStyleSheet("background-color: #198754; color: white;")
            self.lbl_connection_status.setText("Conectado ")
            self.lbl_connection_status.setStyleSheet("color: #198754; font-weight: bold;")
        else:
            self.btn_connect.setText(" 🔌 Reconectar")
            self.btn_connect.setStyleSheet("background-color: #0D6EFD; color: white;")
            self.lbl_connection_status.setText("Desconectado ")
            self.lbl_connection_status.setStyleSheet("color: #DC3545; font-weight: bold;")