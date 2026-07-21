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
        self.setMinimumSize(1200, 750)

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

        self.toolbar.addSeparator()

        # Export / Import de escenas
        self.btn_export = QPushButton(" 📤 Exportar")
        self.btn_export.setToolTip("Exportar todas las escenas a un archivo JSON")
        self.toolbar.addWidget(self.btn_export)

        self.btn_import = QPushButton(" 📥 Importar")
        self.btn_import.setToolTip("Importar escenas desde un archivo JSON")
        self.toolbar.addWidget(self.btn_import)

        self.toolbar.addSeparator()

        # Botón de Transmisión (toggle) — dispara StartRecord/StopRecord de OBS,
        # que en la config Custom Output FFmpeg + URL UDP transmite sin generar archivo.
        self.btn_record = QPushButton(" 🔴 Transmitir")
        self.btn_record.setToolTip("Iniciar salida en OBS (Custom Output FFmpeg → UDP)")
        self.btn_record.setEnabled(False)  # Se habilita al conectar
        self._record_style_idle = "background-color: #6C757D; color: white;"
        self._record_style_active = "background-color: #DC3545; color: white;"
        self.btn_record.setStyleSheet(self._record_style_idle)
        self.toolbar.addWidget(self.btn_record)

        # --- BARRA DE ESTADO (STATUS BAR) ---
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Listo")

        # Timer de grabación (permanent widget, oculto por defecto)
        self.lbl_record_timer = QLabel("")
        self.lbl_record_timer.setStyleSheet("color: #DC3545; font-weight: bold;")
        self.lbl_record_timer.setVisible(False)
        self.statusBar().addPermanentWidget(self.lbl_record_timer)

        # Label para indicar el estado de la conexión en la barra de estado
        self.lbl_connection_status = QLabel("Desconectado ")
        self.lbl_connection_status.setStyleSheet("color: #DC3545; font-weight: bold;")
        self.statusBar().addPermanentWidget(self.lbl_connection_status)

    def set_connection_ui(self, connected: bool):
        """Cambia visualmente la UI dependiendo de si OBS está conectado o no."""
        if connected:
            self.btn_connect.setText(" ✔ Conectado")
            self.btn_connect.setStyleSheet("background-color: #198754; color: white;")
            self.lbl_connection_status.setText("🟢 Conectado ")
            self.lbl_connection_status.setStyleSheet("color: #198754; font-weight: bold;")
            self.btn_record.setEnabled(True)
        else:
            self.btn_connect.setText(" 🔌 Reconectar")
            self.btn_connect.setStyleSheet("background-color: #0D6EFD; color: white;")
            self.lbl_connection_status.setText("🔴 Desconectado ")
            self.lbl_connection_status.setStyleSheet("color: #DC3545; font-weight: bold;")
            self.btn_record.setEnabled(False)

    def set_reconnecting_ui(self, attempt: int):
        """Estado intermedio: el watchdog está reintentando."""
        self.btn_connect.setText(" 🔁 Reconectando…")
        self.btn_connect.setStyleSheet("background-color: #FD7E14; color: white;")
        self.lbl_connection_status.setText(f"🟠 Reconectando (intento {attempt}) ")
        self.lbl_connection_status.setStyleSheet("color: #FD7E14; font-weight: bold;")
        self.btn_record.setEnabled(False)

    def set_recording_ui(self, active: bool, timecode: str = "00:00:00"):
        """Actualiza el estado visual del botón de transmisión y el timer."""
        if active:
            self.btn_record.setText(" ⏹ Detener")
            self.btn_record.setToolTip("Detener salida en OBS")
            self.btn_record.setStyleSheet(self._record_style_active)
            self.lbl_record_timer.setText(f"🔴 EN VIVO {timecode} ")
            self.lbl_record_timer.setVisible(True)
        else:
            self.btn_record.setText(" 🔴 Transmitir")
            self.btn_record.setToolTip("Iniciar salida en OBS (Custom Output FFmpeg → UDP)")
            self.btn_record.setStyleSheet(self._record_style_idle)
            self.lbl_record_timer.setVisible(False)
            self.lbl_record_timer.setText("")