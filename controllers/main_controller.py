from views.main_window import MainWindow
from views.settings_view import SettingsDialog
from views.scene_view import SceneView
from views.calendar_view import CalendarView

from models.obs_client import OBSClient
from models.settings_model import SettingsModel
from models.scene_model import SceneModel
from models.calendar_model import CalendarModel

from controllers.scene_controller import SceneController
from controllers.calendar_controller import CalendarController

from models.countdown_model import CountdownModel
from views.countdown_view import CountdownView
from controllers.countdown_controller import CountdownController

from core.workers import OBSConnectionWorker

from PyQt6.QtWidgets import QMessageBox, QDialog

class MainController:
    def __init__(self):
        self.obs_client = OBSClient()
        self.settings_model = SettingsModel()
        self.main_window = MainWindow()
        
        # 1. Iniciar Módulo de Calendario PRIMERO (porque SceneController lo va a necesitar)
        self.calendar_model = CalendarModel()
        current_settings = self.settings_model.get_settings()
        self.calendar_view = CalendarView(current_settings)
        self.calendar_controller = CalendarController(self.calendar_view, self.calendar_model, self.settings_model, self.obs_client)
        self.main_window.tabs.addTab(self.calendar_view, "Calendario de Cumpleaños")

        # 2. Iniciar Módulo de Escenas y pasarle el controlador del calendario y el de settings
        self.scene_model = SceneModel()
        self.scene_view = SceneView()
        self.scene_controller = SceneController(
            self.scene_view, 
            self.scene_model, 
            self.obs_client, 
            self.settings_model, 
            self.calendar_controller
        )
        self.main_window.tabs.addTab(self.scene_view, "Rotador de Escenas")


        # 3. Iniciar Módulo de Contadores
        self.countdown_model = CountdownModel()
        self.countdown_view = CountdownView()
        self.countdown_controller = CountdownController(self.countdown_view, self.countdown_model, self.obs_client)
        self.main_window.tabs.addTab(self.countdown_view, "Contadores")
        
        self._connect_signals()

    def _connect_signals(self):
        self.main_window.btn_settings.clicked.connect(self.open_settings)
        self.main_window.btn_connect.clicked.connect(self.connect_to_obs)

    def open_settings(self):
        current_settings = self.settings_model.get_settings()
        dialog = SettingsDialog(current_settings, self.main_window)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_settings = dialog.get_inputs()
            self.settings_model.save_settings(
                new_settings["host"], 
                new_settings["port"], 
                new_settings["password"]
            )
            self.connect_to_obs()

    def connect_to_obs(self):
        self.main_window.statusBar().showMessage("Conectando a OBS...")
        self.main_window.btn_connect.setEnabled(False) 
        
        settings = self.settings_model.get_settings()
        
        self.worker = OBSConnectionWorker(
            self.obs_client, 
            settings["host"], 
            int(settings["port"]), 
            settings["password"]
        )
        self.worker.connection_success.connect(self._on_connection_success)
        self.worker.connection_error.connect(self._on_connection_error)
        self.worker.start()

    def _on_connection_success(self, message):
        self.main_window.statusBar().showMessage("Conectado a OBS", 5000)
        self.main_window.btn_connect.setEnabled(True)
        # Llamamos a la función que diseñamos para actualizar toda la UI visual
        self.main_window.set_connection_ui(True)

    def _on_connection_error(self, error_message):
        self.main_window.statusBar().showMessage("Error de conexión")
        self.main_window.btn_connect.setEnabled(True)
        # Revertimos la UI visual a desconectado
        self.main_window.set_connection_ui(False)
        QMessageBox.critical(self.main_window, "Error de Conexión", f"No se pudo conectar a OBS:\n{error_message}")

    def show_main_window(self):
        self.main_window.show()
        self.connect_to_obs()