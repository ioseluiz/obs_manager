from views.main_window import MainWindow
from views.settings_view import SettingsDialog
from views.scene_view import SceneView
from views.calendar_view import CalendarView
from views.logs_view import LogsView
from views.import_dialog import ImportPreviewDialog

from core import importexport, obs_launcher

from models.obs_client import OBSClient
from models.settings_model import SettingsModel
from models.scene_model import SceneModel
from models.calendar_model import CalendarModel

from controllers.scene_controller import SceneController
from controllers.calendar_controller import CalendarController

from models.countdown_model import CountdownModel
from views.countdown_view import CountdownView
from controllers.countdown_controller import CountdownController

from core.workers import OBSConnectionWorker, OBSWatchdog, OBSLauncherWorker

import logging
import os
import subprocess
import sys
from datetime import datetime
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QDialog, QFileDialog

log = logging.getLogger(__name__)

class MainController:
    def __init__(self):
        self.obs_client = OBSClient()
        self.settings_model = SettingsModel()
        self.main_window = MainWindow()
        
        # 1. Iniciar Módulo de Calendario PRIMERO (porque SceneController lo va a necesitar)
        self.scene_model = SceneModel()  # se necesita antes para pasarlo al CalendarController
        self.calendar_model = CalendarModel()
        current_settings = self.settings_model.get_settings()
        self.calendar_view = CalendarView(current_settings)
        self.calendar_controller = CalendarController(
            self.calendar_view, self.calendar_model, self.settings_model, self.obs_client,
            scene_model=self.scene_model,
        )
        self.main_window.tabs.addTab(self.calendar_view, "Calendario de Cumpleaños")

        # 2. Iniciar Módulo de Escenas y pasarle el controlador del calendario y el de settings
        self.scene_view = SceneView()
        self.scene_controller = SceneController(
            self.scene_view,
            self.scene_model,
            self.obs_client,
            self.settings_model,
            self.calendar_controller
        )
        self.main_window.tabs.addTab(self.scene_view, "Rotador de Escenas")

        # Enlazar callback: cuando el calendario construye una escena, refrescar la tabla del rotador.
        self.calendar_controller.on_scene_created = self.scene_controller.refresh_table


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

        # Estado de grabación (in-memory, no persiste entre sesiones)
        self._recording_enabled = False
        self._is_recording = False
        self._record_timer = QTimer()
        self._record_timer.setInterval(1000)
        self._record_timer.timeout.connect(self._poll_recording_status)

        self._connect_signals()

    def _connect_signals(self):
        self.main_window.btn_settings.clicked.connect(self.open_settings)
        self.main_window.btn_connect.clicked.connect(self.connect_to_obs)
        self.main_window.btn_export.clicked.connect(self.export_scenes)
        self.main_window.btn_import.clicked.connect(self.import_scenes)
        self.main_window.btn_record.clicked.connect(self.toggle_recording)

    def open_settings(self):
        current_settings = self.settings_model.get_settings()
        dialog = SettingsDialog(
            current_settings, self.main_window,
            recording_enabled=self._recording_enabled,
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_settings = dialog.get_inputs()
            self.settings_model.save_settings(
                new_settings["host"],
                new_settings["port"],
                new_settings["password"]
            )
            self.settings_model.save_launch_settings(
                new_settings["obs_exe_path"],
                new_settings["obs_autolaunch"]
            )
            self._apply_recording_enabled(new_settings["recording_enabled"])
            self.connect_to_obs()

    def _apply_recording_enabled(self, enabled):
        if enabled == self._recording_enabled:
            return
        # Si se apaga mientras grabamos, detenemos limpiamente (muestra el dialog con el path).
        if not enabled and self._is_recording:
            log.info("Grabación deshabilitada desde Ajustes; deteniendo grabación en curso.")
            self.toggle_recording()
        self._recording_enabled = enabled
        self.main_window.set_recording_enabled(enabled)

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
        # Sincronizar estado de grabación con OBS (por si ya estaba grabando)
        self._sync_recording_state()

    def _sync_recording_state(self):
        # Mientras la grabación esté deshabilitada, la app no controla ni refleja
        # el estado de OBS. El usuario debe activarla en Ajustes.
        if not self._recording_enabled:
            return
        status = self.obs_client.get_recording_status()
        if status and status["active"]:
            self._is_recording = True
            self.main_window.set_recording_ui(True, status["timecode"][:8])
            if not self._record_timer.isActive():
                self._record_timer.start()
        else:
            self._is_recording = False
            self.main_window.set_recording_ui(False)
            self._record_timer.stop()

    def _on_connection_lost(self, message):
        log.warning("Caída de OBS detectada por watchdog: %s", message)
        self.main_window.statusBar().showMessage("Conexión con OBS perdida", 10000)
        self.main_window.set_connection_ui(False)
        # Detener el polling del timer local; el estado real se re-sincroniza al reconectar.
        self._record_timer.stop()
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
        # Re-sincronizar estado de grabación (OBS puede haber seguido grabando)
        self._sync_recording_state()
        # Reanudar rotador si estaba activo antes de la caída
        if self._rotator_was_running:
            self._rotator_was_running = False
            self.scene_controller.rotate_to_next_scene()
            log.info("Rotador reanudado tras reconexión.")

    def _on_connection_error(self, error_message):
        settings = self.settings_model.get_settings()
        # Si el usuario activó auto-launch y OBS no está corriendo, intentamos abrirlo.
        if (sys.platform == "win32"
                and settings.get("obs_autolaunch", True)
                and not obs_launcher.is_obs_running()):
            exe_path = settings.get("obs_exe_path") or obs_launcher.find_obs_executable()
            if exe_path:
                self._start_autolaunch(exe_path, settings)
                return
            log.warning("Auto-launch activo pero no se encontró obs64.exe.")

        self._show_connection_error(error_message)

    def _show_connection_error(self, error_message):
        self.main_window.statusBar().showMessage("Error de conexión")
        self.main_window.btn_connect.setEnabled(True)
        self.main_window.set_connection_ui(False)
        QMessageBox.critical(
            self.main_window, "Error de Conexión",
            f"No se pudo conectar a OBS:\n{error_message}"
        )

    def _start_autolaunch(self, exe_path, settings):
        log.info("Iniciando auto-launch de OBS desde: %s", exe_path)
        self.launcher_worker = OBSLauncherWorker(
            self.obs_client, exe_path,
            settings["host"], int(settings["port"]), settings["password"]
        )
        self.launcher_worker.launching.connect(self._on_launch_starting)
        self.launcher_worker.waiting_websocket.connect(self._on_launch_waiting)
        self.launcher_worker.finished_launch.connect(self._on_launch_finished)
        self.launcher_worker.start()

    def _on_launch_starting(self):
        self.main_window.statusBar().showMessage("Iniciando OBS Studio…")

    def _on_launch_waiting(self, attempt):
        self.main_window.statusBar().showMessage(
            f"Esperando OBS WebSocket ({attempt}/30)…"
        )

    def _on_launch_finished(self, success, message):
        if success:
            self._on_connection_success(message)
        else:
            self._show_connection_error(message)

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

    # --- GRABACIÓN ---
    def toggle_recording(self):
        if not self.obs_client.client:
            QMessageBox.warning(self.main_window, "Sin conexión",
                                "Conecta a OBS antes de grabar.")
            return

        if self._is_recording:
            ok, msg = self.obs_client.stop_recording()
            if not ok:
                QMessageBox.critical(self.main_window, "Error al detener grabación", msg)
                return
            self._is_recording = False
            self._record_timer.stop()
            self.main_window.set_recording_ui(False)
            self.main_window.statusBar().showMessage("Grabación detenida", 5000)
            log.info("Grabación detenida. Archivo: %s", msg or "(sin path)")
            if msg:
                self._show_recording_saved_dialog(msg)
        else:
            ok, msg = self.obs_client.start_recording()
            if not ok:
                QMessageBox.critical(self.main_window, "Error al iniciar grabación", msg)
                return
            self._is_recording = True
            self.main_window.set_recording_ui(True, "00:00:00")
            self._record_timer.start()
            self.main_window.statusBar().showMessage("Grabación iniciada", 5000)
            log.info("Grabación iniciada.")

    def _poll_recording_status(self):
        status = self.obs_client.get_recording_status()
        if status is None:
            # OBS no responde; el watchdog se encarga. Paramos el polling local.
            self._record_timer.stop()
            return
        if not status["active"]:
            # OBS detuvo la grabación por otro medio (UI de OBS, hotkey, error…).
            self._is_recording = False
            self._record_timer.stop()
            self.main_window.set_recording_ui(False)
            return
        self.main_window.set_recording_ui(True, status["timecode"][:8])

    def _show_recording_saved_dialog(self, path):
        box = QMessageBox(self.main_window)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Grabación guardada")
        box.setText(f"Grabación guardada en:\n{path}")
        btn_open = box.addButton("Abrir carpeta", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is btn_open:
            self._open_in_explorer(path)

    def _open_in_explorer(self, path):
        if sys.platform != "win32":
            return
        try:
            subprocess.Popen(["explorer", f"/select,{path}"])
        except Exception as e:
            log.warning("No se pudo abrir el explorador con /select: %s", e)
            try:
                os.startfile(os.path.dirname(path))
            except Exception as e2:
                log.error("Fallback os.startfile también falló: %s", e2)

    def show_main_window(self):
        self.main_window.show()
        self.connect_to_obs()

    def shutdown(self):
        """Detiene threads antes de cerrar la app."""
        try:
            self._record_timer.stop()
        except Exception as e:
            log.warning("Error deteniendo record_timer: %s", e)
        try:
            self.watchdog.stop()
            self.watchdog.wait(2000)
        except Exception as e:
            log.warning("Error deteniendo watchdog: %s", e)