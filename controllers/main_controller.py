from views.main_window import MainWindow
from views.settings_view import SettingsDialog
from views.scene_view import SceneView
from views.calendar_view import CalendarView
from views.logs_view import LogsView
from views.import_dialog import ImportPreviewDialog

from core import importexport

from models.obs_client import OBSClient
from models.settings_model import SettingsModel
from models.scene_model import SceneModel
from models.calendar_model import CalendarModel

from controllers.scene_controller import SceneController
from controllers.calendar_controller import CalendarController

from models.countdown_model import CountdownModel
from views.countdown_view import CountdownView
from controllers.countdown_controller import CountdownController

from core.workers import OBSConnectionWorker, OBSWatchdog

import logging
from datetime import datetime
from PyQt6.QtWidgets import QMessageBox, QDialog, QFileDialog

log = logging.getLogger(__name__)

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

        # 3.5 Pestaña de Logs
        self.logs_view = LogsView()
        self.main_window.tabs.addTab(self.logs_view, "Logs")

        # 4. Watchdog de conexión (arranca tras la primera conexión exitosa)
        self.watchdog = OBSWatchdog(self.obs_client, self.settings_model.get_settings)
        self.watchdog.connection_lost.connect(self._on_connection_lost)
        self.watchdog.connection_restored.connect(self._on_connection_restored)
        self.watchdog.reconnect_attempt.connect(self._on_reconnect_attempt)
        self.watchdog.start()

        # Estado para pausar/reanudar rotador ante caídas
        self._rotator_was_running = False

        self._connect_signals()

    def _connect_signals(self):
        self.main_window.btn_settings.clicked.connect(self.open_settings)
        self.main_window.btn_connect.clicked.connect(self.connect_to_obs)
        self.main_window.btn_export.clicked.connect(self.export_scenes)
        self.main_window.btn_import.clicked.connect(self.import_scenes)

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
        self.watchdog.mark_connected()
        log.info("Conexión inicial a OBS establecida.")

    def _on_connection_lost(self, message):
        log.warning("Caída de OBS detectada por watchdog: %s", message)
        self.main_window.statusBar().showMessage("Conexión con OBS perdida", 10000)
        self.main_window.set_connection_ui(False)
        # Pausar rotador si estaba activo (recordar para reanudar al restaurar)
        if self.scene_controller.timer.isActive() or self.scene_controller.is_paused:
            self._rotator_was_running = True
            self.scene_controller.timer.stop()
            self.scene_controller.refresh_timer.stop()
            log.info("Rotador detenido por caída de OBS.")

    def _on_reconnect_attempt(self, attempt):
        self.main_window.set_reconnecting_ui(attempt)

    def _on_connection_restored(self):
        log.info("Conexión con OBS restaurada.")
        self.main_window.statusBar().showMessage("Reconectado a OBS", 5000)
        self.main_window.set_connection_ui(True)
        # Reanudar rotador si estaba activo antes de la caída
        if self._rotator_was_running:
            self._rotator_was_running = False
            self.scene_controller.rotate_to_next_scene()
            log.info("Rotador reanudado tras reconexión.")

    def _on_connection_error(self, error_message):
        self.main_window.statusBar().showMessage("Error de conexión")
        self.main_window.btn_connect.setEnabled(True)
        # Revertimos la UI visual a desconectado
        self.main_window.set_connection_ui(False)
        QMessageBox.critical(self.main_window, "Error de Conexión", f"No se pudo conectar a OBS:\n{error_message}")

    def export_scenes(self):
        scenes = self.scene_model.get_all_scenes()
        if not scenes:
            QMessageBox.information(self.main_window, "Exportar",
                                    "No hay escenas para exportar.")
            return
        default_name = f"scenes_export_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self.main_window, "Exportar escenas a JSON", default_name,
            "Archivos JSON (*.json)"
        )
        if not path:
            return
        try:
            count = importexport.export_scenes_to_file(scenes, path, app_version="v1.0.0")
            QMessageBox.information(
                self.main_window, "Exportación exitosa",
                f"Se exportaron {count} escenas a:\n{path}\n\n"
                "Nota: el archivo puede contener URLs de dashboards internos. No lo compartas públicamente."
            )
        except Exception as e:
            log.error("Error exportando: %s", e)
            QMessageBox.critical(self.main_window, "Error", f"No se pudo exportar:\n{e}")

    def import_scenes(self):
        path, _ = QFileDialog.getOpenFileName(
            self.main_window, "Importar escenas desde JSON", "",
            "Archivos JSON (*.json)"
        )
        if not path:
            return
        try:
            scenes, metadata = importexport.import_scenes_from_file(path)
        except Exception as e:
            log.error("Error leyendo JSON: %s", e)
            QMessageBox.critical(self.main_window, "Error",
                                 f"No se pudo leer el archivo:\n{e}")
            return

        dialog = ImportPreviewDialog(scenes, metadata, self.main_window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        mode = dialog.get_mode()
        create_in_obs = dialog.create_in_obs()

        if create_in_obs and not self.obs_client.client:
            reply = QMessageBox.question(
                self.main_window, "OBS no conectado",
                "OBS no está conectado. ¿Continuar solo con la base de datos "
                "(las escenas no se crearán en OBS)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            create_in_obs = False

        if mode == ImportPreviewDialog.MODE_REPLACE:
            reply = QMessageBox.warning(
                self.main_window, "Confirmar reemplazo",
                f"Esto ELIMINARÁ todas las {len(self.scene_model.get_all_scenes())} escenas actuales "
                "y las reemplazará con las importadas. ¿Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            # Borrar todas las actuales (en OBS y BD)
            for s in self.scene_model.get_all_scenes():
                if create_in_obs and self.obs_client.client:
                    self.obs_client.delete_scene(s["name"])
                self.scene_model.delete_scene(s["id"])

        # Insertar las nuevas
        existing_names = {s["name"] for s in self.scene_model.get_all_scenes()}
        created = 0
        errors = []
        for src in scenes:
            new_name = importexport.unique_name(src["name"], existing_names)
            existing_names.add(new_name)
            # Crear en OBS si aplica
            if create_in_obs and self.obs_client.client:
                ok, msg = self._create_scene_in_obs(new_name, src)
                if not ok:
                    errors.append(f"'{new_name}': {msg}")
            # Insertar en BD
            self.scene_model.add_scene(
                new_name, src.get("duration", 20),
                tipo=src.get("tipo", "file"),
                contenido=src.get("contenido"),
                ancho=src.get("ancho", 1920),
                alto=src.get("alto", 1080),
                fps=src.get("fps", 30),
                reload_on_activate=src.get("reload_on_activate", False),
                keep_session=src.get("keep_session", True),
                custom_css=src.get("custom_css"),
                zoom_pct=src.get("zoom_pct", 100),
                pan_x=src.get("pan_x", 0),
                pan_y=src.get("pan_y", 0),
                refresh_interval_seg=src.get("refresh_interval_seg", 0),
                video_loop=src.get("video_loop", True),
                video_restart_on_activate=src.get("video_restart_on_activate", True),
                video_mute=src.get("video_mute", False),
                video_volume_pct=src.get("video_volume_pct", 100),
                video_offset_seg=src.get("video_offset_seg", 0),
                active_days=src.get("active_days", 127),
                active_time_start=src.get("active_time_start"),
                active_time_end=src.get("active_time_end"),
            )
            created += 1

        # Refrescar tabla del scene_controller
        self.scene_controller.refresh_table()

        msg = f"Se importaron {created} escenas."
        if errors:
            msg += f"\n\nAdvertencias:\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n… y {len(errors) - 10} más."
        QMessageBox.information(self.main_window, "Importación completada", msg)

    def _create_scene_in_obs(self, name, src):
        """Crea una escena en OBS a partir de un dict de import."""
        tipo = src.get("tipo", "file")
        contenido = src.get("contenido")
        if tipo == "url" and contenido:
            ok, msg = self.obs_client.create_web_scene(
                name, contenido,
                width=src.get("ancho", 1920),
                height=src.get("alto", 1080),
                fps=src.get("fps", 30),
                reload_on_activate=src.get("reload_on_activate", False),
                keep_session=src.get("keep_session", True),
                custom_css=src.get("custom_css"),
            )
        elif tipo == "file" and contenido:
            ok, msg = self.obs_client.create_scene_with_media(
                name, contenido,
                video_loop=src.get("video_loop", True),
                video_restart_on_activate=src.get("video_restart_on_activate", True),
                video_mute=src.get("video_mute", False),
                video_volume_pct=src.get("video_volume_pct", 100),
                video_offset_seg=src.get("video_offset_seg", 0),
            )
        else:
            # Sin contenido: solo crear la escena vacía
            try:
                self.obs_client.client.create_scene(name)
                return True, "OK"
            except Exception as e:
                return False, str(e)

        # Aplicar transform si difiere del default
        if ok and (src.get("zoom_pct", 100), src.get("pan_x", 0), src.get("pan_y", 0)) != (100, 0, 0):
            source_name = f"{name}_Web" if tipo == "url" else f"{name}_Contenido"
            self.obs_client.set_source_transform(
                name, source_name,
                src.get("zoom_pct", 100), src.get("pan_x", 0), src.get("pan_y", 0)
            )
        return ok, msg

    def show_main_window(self):
        self.main_window.show()
        self.connect_to_obs()

    def shutdown(self):
        """Detiene threads antes de cerrar la app."""
        try:
            self.watchdog.stop()
            self.watchdog.wait(2000)
        except Exception as e:
            log.warning("Error deteniendo watchdog: %s", e)