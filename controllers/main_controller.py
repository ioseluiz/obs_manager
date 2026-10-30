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

from models.canal_model import CanalModel
from views.produccion_view import ProduccionView
from controllers.canal_controller import CanalController

from core.autopilot_client import AutopilotClientV2
from core.legacy_migrator import migrate_legacy_to_canal, needs_migration
from controllers.autopilot_v2_controller import AutopilotV2Controller
from controllers.home_controller import HomeController
from views.autopilot_install_v2_dialog import AutopilotInstallV2Dialog
from views.home_view import HomeView
from views.legacy_migration_dialog import LegacyMigrationDialog

from core.workers import OBSConnectionWorker, OBSWatchdog, OBSLauncherWorker, OBSProbeWorker


_LOCAL_HOSTS = ("", "localhost", "127.0.0.1", "::1", "[::1]")


def _is_local_host(host: str) -> bool:
    return (host or "").strip().lower() in _LOCAL_HOSTS

import logging
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
        
        # 0. Pestana Inicio (Fase 3 UI redesign) — va primera en el sidebar.
        # La view se agrega aqui; el controller se instancia al final del
        # __init__ cuando ya existen todos los modelos y controllers que
        # alimentan sus KPIs.
        self.home_view = HomeView()
        self.main_window.add_section(self.home_view, "Inicio", "inicio")

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

        # 2. Iniciar Módulo de Escenas (SceneView vive ahora en la pestaña
        # "Biblioteca de Escenas" en modo compacto: sin controles de
        # reproducción, esos ahora viven en Producción / Canal Principal).
        self.scene_view = SceneView(compact_mode=True)
        self.scene_controller = SceneController(
            self.scene_view,
            self.scene_model,
            self.obs_client,
            self.settings_model,
            self.calendar_controller
        )
        self.main_window.tabs.addTab(self.scene_view, "Biblioteca de Escenas")

        # Enlazar callback: cuando el calendario construye una escena, refrescar la tabla del rotador.
        self.calendar_controller.on_scene_created = self.scene_controller.refresh_table


        # 3. Iniciar Módulo de Contadores
        self.countdown_model = CountdownModel()
        self.countdown_view = CountdownView()
        self.countdown_controller = CountdownController(self.countdown_view, self.countdown_model, self.obs_client)
        self.main_window.tabs.addTab(self.countdown_view, "Contadores")

        # 3.4 Módulo de Canales Multi-Salida + Producción (Fase 1 + Fase R)
        # La pestaña "Producción" une Canal Principal (rotador legacy) con
        # los canales regulares en una sidebar con panel de detalle.
        self.canal_model = CanalModel()
        self.canal_controller = CanalController(
            self.canal_model, self.scene_model, self.obs_client,
            calendar_controller=self.calendar_controller,
        )
        self.produccion_view = ProduccionView(
            self.canal_model, self.scene_model, self.canal_controller,
        )
        self.main_window.tabs.addTab(self.produccion_view, "Producción")

        # 3.6 Autopilot v2 (Fases C + D del port): mantiene la rotacion
        # de los canales multi-salida activa + la rotacion del Canal
        # Principal legacy (program_global) aunque la app se cierre.
        # Requiere que el usuario haya instalado `autopilot_v2.lua` en
        # OBS; si no esta, el controller se queda inactivo sin romper
        # nada.
        self.autopilot_v2_client = AutopilotClientV2(self.obs_client)
        self.autopilot_v2 = AutopilotV2Controller(
            self.autopilot_v2_client,
            self.canal_controller,
            scene_controller=self.scene_controller,
        )
        # Timer de 3s para refrescar el label de status bar del Autopilot v2.
        self._autopilot_v2_status_timer = QTimer()
        self._autopilot_v2_status_timer.setInterval(3000)
        self._autopilot_v2_status_timer.timeout.connect(
            self._refresh_autopilot_v2_status)

        # 3.5 Pestaña de Logs
        self.logs_view = LogsView()
        self.main_window.tabs.addTab(self.logs_view, "Logs")

        # 4. Watchdog de conexión (arranca tras la primera conexión exitosa)
        self.watchdog = OBSWatchdog(self.obs_client, self.settings_model.get_settings)
        self.watchdog.connection_lost.connect(self._on_connection_lost)
        self.watchdog.connection_restored.connect(self._on_connection_restored)
        self.watchdog.reconnect_attempt.connect(self._on_reconnect_attempt)
        self.watchdog.start()

        # Estado de recording / rotador legacy del Canal Principal:
        # eliminado como parte de la unificacion. Toda la transmision
        # vive ahora en los canales multi-salida via Source Record.

        # Fase 3 UI redesign: controller de la pestana Inicio. Se instancia
        # aqui porque ya existen todos los modelos + canal_controller que
        # alimentan sus KPIs y previews. Las acciones rapidas se encadenan
        # a los handlers existentes del MainController.
        self.home_controller = HomeController(
            self.home_view,
            canal_model=self.canal_model,
            scene_model=self.scene_model,
            obs_client=self.obs_client,
            settings_model=self.settings_model,
            canal_controller=self.canal_controller,
        )
        self.home_view.action_new_canal.connect(
            lambda: self.main_window.set_active_section(4)
        )
        self.home_view.action_connect_obs.connect(self.connect_to_obs)
        self.home_view.action_import.connect(self.import_scenes)
        self.home_view.action_open_schedule.connect(
            lambda: self.main_window.set_active_section(1)
        )
        self.home_view.action_open_settings.connect(self.open_settings)
        self._manually_disconnected = False
        self.home_view.action_disconnect_obs.connect(self.disconnect_from_obs)

        self._connect_signals()

    def _connect_signals(self):
        self.main_window.btn_settings.clicked.connect(self.open_settings)
        self.main_window.btn_connect.clicked.connect(self.connect_to_obs)
        self.main_window.btn_export.clicked.connect(self.export_scenes)
        self.main_window.btn_import.clicked.connect(self.import_scenes)
        # El botón Transmitir global fue removido en R-4 — su callback ahora
        # llega por el panel de Canal Principal via el argumento
        # on_transmit_principal_toggle de ProduccionView.

    def open_settings(self):
        current_settings = self.settings_model.get_settings()
        dialog = SettingsDialog(current_settings, self.main_window)
        dialog.test_connection_requested.connect(
            lambda params, d=dialog: self._probe_connection(params, d)
        )
        # Fase 2e: mostrar estado de calibración en el diálogo + wire el botón
        # de re-calibrar. Requiere conexión activa a OBS para el fingerprint.
        try:
            self._populate_settings_calibration(dialog)
        except Exception as e:
            log.debug("No se pudo poblar estado de calibración: %s", e)
        dialog.recalibrate_requested.connect(
            lambda d=dialog: self._on_recalibrate_requested(d)
        )
        dialog.install_autopilot_v2_requested.connect(
            lambda d=dialog: self._on_install_autopilot_v2_requested(d)
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
            self.connect_to_obs()

    def _probe_connection(self, params: dict, dialog):
        """Prueba credenciales/host sin tocar la conexión productiva ni auto-launch."""
        try:
            port = int(params.get("port") or 0)
        except (TypeError, ValueError):
            dialog.set_test_result(False, "Puerto inválido.")
            return
        host = (params.get("host") or "").strip()
        if not host:
            dialog.set_test_result(False, "Host / IP vacío.")
            return
        dialog.set_test_pending()
        worker = OBSProbeWorker(host, port, params.get("password") or "", timeout=3.0)
        worker.finished_probe.connect(dialog.set_test_result)
        # Retener referencia en el diálogo para que el GC no mate el thread
        dialog._probe_worker = worker
        worker.start()

    def connect_to_obs(self):
        worker = getattr(self, "worker", None)
        if worker is not None and worker.isRunning():
            return
        self.watchdog.suspend()
        self._manually_disconnected = False
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

    def disconnect_from_obs(self):
        self._manually_disconnected = True
        self.watchdog.suspend()
        # Entregar el control al Lua antes de cerrar la sesión cliente.
        try:
            self.autopilot_v2.stop(publish_handoff=True)
        except Exception as exc:
            log.warning("No se pudo publicar el handoff al desconectar: %s", exc)
        self.canal_controller.shutdown_keeping_filters()
        self._stop_lag_watchdog()
        self._autopilot_v2_status_timer.stop()
        self.obs_client.disconnect()
        self.main_window.set_connection_ui(False)
        self.main_window.clear_canvas_size()
        self.main_window.set_autopilot_v2_ui(None)
        self.main_window.statusBar().showMessage("Desconectado de OBS", 5000)
        self.home_controller.refresh()

    def _on_connection_success(self, message):
        if self._manually_disconnected:
            self.obs_client.disconnect()
            self.main_window.btn_connect.setEnabled(True)
            return
        self.main_window.statusBar().showMessage("Conectado a OBS", 5000)
        self.main_window.btn_connect.setEnabled(True)
        # Llamamos a la función que diseñamos para actualizar toda la UI visual
        self.main_window.set_connection_ui(True)
        self.main_window.set_canvas_size(
            self.obs_client.canvas_width, self.obs_client.canvas_height
        )
        self.watchdog.mark_connected()
        self.home_controller.refresh()
        log.info("Conexión inicial a OBS establecida.")
        # Poblar combos del módulo de contadores con las escenas / text sources de OBS
        self.countdown_controller.refresh_from_obs()
        # Auto-aplicar canales habilitados a OBS (Fase 1e)
        self._auto_apply_canales()
        # Fase 2 unificacion: ofrecer migrar secuencias legacy a un canal
        # regular. Non-blocking — si el user omite, se re-ofrece en el
        # proximo connect; si marca "no volver a preguntar", nunca mas.
        self._maybe_offer_legacy_migration()
        # Arrancar watchdog de encoding_lag (Fase 2f)
        self._start_lag_watchdog()
        # Fase E del port: si el Lua Autopilot v2 estuvo rotando mientras
        # la app estaba cerrada, leer su estado y restaurar los rotadores
        # locales (active_index + remaining) antes de retomar control.
        try:
            self._sync_from_autopilot_v2()
        except Exception as e:
            log.warning("Sync bidireccional Autopilot v2 fallo en connect: %s", e)
        # Arrancar Autopilot v2 (Fase C del port). Idempotente: si el
        # script Lua no esta instalado se queda inactivo. Debe ir despues
        # del sync para que el primer publish lleve los handoffs
        # restaurados (y el Lua vuelva a standby con la foto correcta).
        try:
            self.autopilot_v2.start()
        except Exception as e:
            log.warning("Autopilot v2 no arranco en connect: %s", e)
        # Arrancar refresh del label del Autopilot v2 en el status bar.
        self._refresh_autopilot_v2_status()
        self._autopilot_v2_status_timer.start()

    def _on_connection_lost(self, message):
        if self._manually_disconnected:
            return
        log.warning("Caída de OBS detectada por watchdog: %s", message)
        self.main_window.statusBar().showMessage("Conexión con OBS perdida", 10000)
        self.main_window.set_connection_ui(False)
        self.main_window.clear_canvas_size()
        # Detener el watchdog de lag (Fase 2f) — sin OBS no hay stats.
        self._stop_lag_watchdog()
        # Detener Autopilot v2 (Fase C del port) — sin OBS no se puede
        # publicar. El script Lua del lado del servidor hara su propio
        # timeout de heartbeat (30s) y tomara control.
        try:
            self.autopilot_v2.stop()
        except Exception as e:
            log.debug("Autopilot v2 stop en caida fallo: %s", e)
        # Pausar el refresh del label de status bar — ya no hay OBS que leer.
        self._autopilot_v2_status_timer.stop()
        self.main_window.set_autopilot_v2_ui(None)

    def _on_reconnect_attempt(self, attempt):
        if self._manually_disconnected:
            return
        self.main_window.set_reconnecting_ui(attempt)

    def _on_connection_restored(self):
        if self._manually_disconnected:
            return
        self.home_controller.refresh()
        log.info("Conexión con OBS restaurada.")
        self.main_window.statusBar().showMessage("Reconectado a OBS", 5000)
        self.main_window.set_connection_ui(True)
        self.main_window.set_canvas_size(
            self.obs_client.canvas_width, self.obs_client.canvas_height
        )
        # Refrescar combos del módulo de contadores
        self.countdown_controller.refresh_from_obs()
        # Re-aplicar canales habilitados — OBS pudo haber reiniciado y
        # perdido las escenas contenedoras (Fase 1e).
        self._auto_apply_canales()
        # Reiniciar watchdog de encoding_lag (Fase 2f) tras reconexión.
        self._start_lag_watchdog()
        # Fase E del port: sync bidireccional con el Lua Autopilot v2.
        # Si durante la caida de OBS el Lua estuvo rotando por su cuenta
        # (mode=active), restaurar active_index + remaining en los
        # rotadores locales antes de retomar control.
        try:
            self._sync_from_autopilot_v2()
        except Exception as e:
            log.warning("Sync bidireccional Autopilot v2 fallo en reconexion: %s", e)
        # Re-arrancar Autopilot v2 (Fase C del port). El start() es
        # idempotente y re-detecta si el script Lua esta instalado.
        try:
            self.autopilot_v2.start()
        except Exception as e:
            log.warning("Autopilot v2 no arranco en reconexion: %s", e)
        # Reanudar refresh del label de status bar.
        self._refresh_autopilot_v2_status()
        if not self._autopilot_v2_status_timer.isActive():
            self._autopilot_v2_status_timer.start()

    def _refresh_autopilot_v2_status(self):
        """Fase F del port: lee el state del Lua y lo pinta en la status
        bar. Silencioso ante fallos — una desconexion momentanea no debe
        tirar el refresh."""
        try:
            if not self.autopilot_v2_client.is_installed():
                self.main_window.set_autopilot_v2_ui(None)
                return
            state = self.autopilot_v2_client.read_state()
        except Exception as e:
            log.debug("Refresh Autopilot v2 status fallo: %s", e)
            self.main_window.set_autopilot_v2_ui(None)
            return
        self.main_window.set_autopilot_v2_ui(state)

    def _sync_from_autopilot_v2(self):
        """Fase E del port de Autopilot v2.

        Lee el estado publicado por el Lua residente en OBS
        (`__autopilot_state_v2__`). Si el script estaba en mode=active
        (porque la app estuvo cerrada o perdio OBS), significa que el
        Lua tomo control de los rotadores. Al reconectar, restauramos
        en los rotadores locales la foto exacta — active_index +
        remaining — asi la UI no muestra un salto y el proximo tick
        continua desde donde el Lua dejo.

        Si el Lua estaba en standby (la app NO perdio heartbeat) o si
        el script no esta instalado, no hay nada que sincronizar.
        """
        if not self.autopilot_v2_client.is_installed():
            return
        state = self.autopilot_v2_client.read_state()
        if state is None:
            return
        if state.get("mode") != "active":
            return

        synced = 0
        for entry in state.get("canales") or []:
            try:
                canal_id = int(entry.get("canal_id", -999999))
                remaining = int(entry.get("seconds_remaining", 0) or 0)
                if remaining <= 0:
                    continue
                # Canal Principal legacy (canal_id=-1) fue eliminado — hoy
                # todos los canales son multi-salida.
                if canal_id < 0:
                    continue
                active_si = int(entry.get("active_scene_item_id", 0) or 0)
                if active_si > 0 and self.canal_controller.sync_from_handoff(
                        canal_id, active_si, remaining):
                    synced += 1
            except Exception as e:
                log.debug("sync entry Autopilot v2 fallo: %s", e)

        if synced:
            log.info(
                "Autopilot v2: %d rotador(es) sincronizados desde el Lua activo",
                synced,
            )

    def _maybe_offer_legacy_migration(self):
        """Fase 2 de la unificacion.

        Si hay secuencias en la Biblioteca y el flag
        LEGACY_MIGRATION_DONE no esta marcado, ofrece al user crear un
        canal regular que agrupe esas secuencias como items. El dialog
        tiene 3 salidas:

        - Convertir: ejecuta migrate_legacy_to_canal con la seleccion
          del user y marca el flag.
        - Omitir por ahora: cierra sin marcar — vuelve a aparecer en
          el proximo connect.
        - No volver a preguntar: marca el flag sin crear canal.

        Nunca interrumpe el flujo de connect — ante cualquier excepcion
        la migracion se omite silenciosamente.
        """
        try:
            if not needs_migration(self.scene_model, self.settings_model):
                return
            scenes = self.scene_model.get_all_scenes() or []
            dialog = LegacyMigrationDialog(scenes, parent=self.main_window)
            dialog.exec()
            decision = dialog.decision
            if decision == LegacyMigrationDialog.DO_NEVER:
                self.settings_model.set_flag("LEGACY_MIGRATION_DONE", "true")
                log.info("Legacy migration: user eligio 'no volver a preguntar'")
                return
            if decision != LegacyMigrationDialog.DO_CONVERT:
                # DO_SKIP: no se marca flag, se re-ofrece la proxima vez.
                return
            ok, canal_id, msg = migrate_legacy_to_canal(
                canal_model=self.canal_model,
                scene_model=self.scene_model,
                canal_controller=self.canal_controller,
                canal_name=dialog.canal_name,
                udp_url=dialog.udp_url,
                secuencia_ids=dialog.selected_ids,
            )
            if ok:
                self.settings_model.set_flag("LEGACY_MIGRATION_DONE", "true")
                log.info("Legacy migration: %s", msg)
                if hasattr(self, "produccion_view") and self.produccion_view is not None:
                    self.produccion_view.refresh()
                QMessageBox.information(
                    self.main_window, "Migración completada", msg,
                )
            else:
                log.warning("Legacy migration fallo: %s", msg)
                QMessageBox.warning(
                    self.main_window, "Migración incompleta",
                    f"{msg}\n\nEl flag no se marco — se te volvera a "
                    "preguntar en el proximo arranque.",
                )
        except Exception as e:
            log.warning("Legacy migration excepcion: %s", e)

    def _auto_apply_canales(self):
        """Aplica en OBS los canales habilitados del modelo (Fase 1e).

        Después del apply, corre la validación de capacidad (Fase 2d):
        si los canales configurados exceden la calibración persistida del
        equipo, muestra un dialog informativo. Nunca auto-degrada — regla
        firme de Fase 2.
        """
        try:
            results = self.canal_controller.apply_all_habilitados()
        except Exception as e:
            log.warning("Auto-apply de canales falló: %s", e)
            return
        if results:
            ok = sum(1 for r in results if r["ok"])
            log.info("Canales auto-aplicados a OBS: %d/%d.", ok, len(results))
            if hasattr(self, "produccion_view") and self.produccion_view is not None:
                self.produccion_view.refresh()
        self._validate_capacity_and_maybe_warn()

    def _validate_capacity_and_maybe_warn(self):
        """Compara canales habilitados vs calibración persistida (Fase 2d).

        Si hay overloaded, abre un dialog non-bloqueante. Ejecutable
        una sola vez por conexión — el flag `_capacity_warned_this_session`
        evita spammear cada reconexión.
        """
        if getattr(self, "_capacity_warned_this_session", False):
            return
        try:
            from core.capacity_repo import CapacityRepo, detect_fingerprint
            from core.capacity_validator import validate_capacity
        except Exception as e:
            log.debug("Fase 2 no disponible: %s", e)
            return

        try:
            # Fingerprint requiere obs_major — leemos del cliente si podemos
            obs_major = 30
            try:
                ver = self.obs_client._raw_client().get_version()
                obs_ver_str = getattr(ver, "obs_version", "") or ""
                if obs_ver_str:
                    obs_major = int(obs_ver_str.split(".", 1)[0])
            except Exception:
                pass
            fp = detect_fingerprint(obs_major=obs_major)
            repo = CapacityRepo()
            entry = repo.get(fp)
            canales = self.canal_model.get_all_canales()
            result = validate_capacity(canales, entry)
        except Exception as e:
            log.warning("Validación de capacidad falló: %s", e)
            return

        if result.ok:
            log.info("Capacity check OK: %s", result.reason)
            # Fase 2e: si no hay calibración aún, invitar a calibrar.
            # Non-bloqueante, una vez por sesión.
            if entry is None:
                self._maybe_invite_first_calibration()
            return

        # Overloaded — mostrar dialog
        log.warning("Capacity check overloaded: %s", result.reason)
        self._capacity_warned_this_session = True
        try:
            from views.capacity_validation_dialog import CapacityValidationDialog
            dlg = CapacityValidationDialog(
                result, parent=self.main_window,
                on_go_to_produccion=self._focus_produccion_tab,
            )
            dlg.exec()
        except Exception as e:
            log.warning("No se pudo mostrar CapacityValidationDialog: %s", e)

    def _focus_produccion_tab(self):
        """Trae al frente la pestaña Producción — callback del dialog 2d."""
        if not hasattr(self, "main_window") or self.main_window is None:
            return
        tabs = getattr(self.main_window, "tabs", None)
        if tabs is None:
            return
        for i in range(tabs.count()):
            if "Producción" in tabs.tabText(i):
                tabs.setCurrentIndex(i)
                return

    # ------------------------------------------------------------------
    # Fase 2e — settings de calibración + primer-run
    # ------------------------------------------------------------------

    def _current_fingerprint(self):
        """Devuelve el Fingerprint del equipo actual, o None si no se puede."""
        try:
            from core.capacity_repo import detect_fingerprint
            obs_major = 30
            try:
                ver = self.obs_client._raw_client().get_version()
                obs_ver_str = getattr(ver, "obs_version", "") or ""
                if obs_ver_str:
                    obs_major = int(obs_ver_str.split(".", 1)[0])
            except Exception:
                pass
            return detect_fingerprint(obs_major=obs_major)
        except Exception as e:
            log.debug("No se pudo obtener fingerprint: %s", e)
            return None

    def _populate_settings_calibration(self, dialog):
        """Carga el estado actual de calibración en el SettingsDialog."""
        from core.capacity_repo import CapacityRepo
        fp = self._current_fingerprint()
        if fp is None:
            return
        entry = CapacityRepo().get(fp)
        dialog.set_calibration_status(entry)

    def _on_install_autopilot_v2_requested(self, settings_dialog):
        """Handler del boton 'Instalar / Verificar Autopilot v2' en
        Settings. Abre el AutopilotInstallV2Dialog con el cliente actual.

        No requiere OBS conectado: el export al disco funciona offline;
        la verificacion si requiere conexion y el propio dialogo avisa
        si no la hay.
        """
        dialog = AutopilotInstallV2Dialog(
            self.autopilot_v2_client, parent=settings_dialog,
        )
        dialog.exec()
        # Refrescar el label de status bar por si el usuario acabo de
        # cargar el script o verifica estado nuevo.
        self._refresh_autopilot_v2_status()

    def _on_recalibrate_requested(self, settings_dialog):
        """Handler del botón 'Re-calibrar' en Settings.

        Lanza el CalibrationDialog. Al terminar, refresca el label del
        SettingsDialog con la nueva calibración.
        """
        if not self.obs_client.client:
            QMessageBox.warning(
                settings_dialog, "Re-calibrar",
                "Conectate a OBS primero — la calibración necesita "
                "crear escenas y filtros en OBS.",
            )
            return
        self._launch_calibration_dialog(parent=settings_dialog,
                                        on_finish=lambda: self._populate_settings_calibration(settings_dialog))

    def _launch_calibration_dialog(self, parent=None, on_finish=None,
                                    encoders=None):
        """Instancia y muestra el CalibrationDialog con dependencies armadas.

        encoders: lista de shortnames a calibrar; por defecto los conocidos
            del plugin Source Record.
        on_finish: callback opcional al cerrar el dialog.
        """
        try:
            from core.calibration_engine import CalibrationEngine
            from core.calibration_facade import RealObsFacade
            from core.capacity_repo import CapacityRepo
            from views.calibration_dialog import CalibrationDialog
        except Exception as e:
            log.warning("No se pudo cargar módulos de Fase 2: %s", e)
            return
        fp = self._current_fingerprint()
        if fp is None:
            QMessageBox.warning(
                parent or self.main_window, "Calibración",
                "No se pudo detectar el equipo. Verifique la conexión a OBS.",
            )
            return
        facade = RealObsFacade(self.obs_client)
        engine = CalibrationEngine(facade=facade)
        repo = CapacityRepo()
        encoders = encoders or ["x264", "qsv", "nvenc", "amf"]
        dlg = CalibrationDialog(
            engine, encoders=encoders, fingerprint=fp,
            capacity_repo=repo, parent=parent or self.main_window,
        )
        dlg.exec()
        if on_finish is not None:
            try:
                on_finish()
            except Exception:
                pass

    def _maybe_invite_first_calibration(self):
        """Si no hay calibración para el equipo actual, invita a hacerla.

        Non-bloqueante. Se dispara UNA vez por sesión (flag).
        """
        if getattr(self, "_first_cal_invited_this_session", False):
            return
        try:
            from core.capacity_repo import CapacityRepo
            fp = self._current_fingerprint()
            if fp is None:
                return
            entry = CapacityRepo().get(fp)
            if entry is not None:
                return  # Ya calibrado
        except Exception as e:
            log.debug("Skip invitación calibración: %s", e)
            return
        self._first_cal_invited_this_session = True
        answer = QMessageBox.question(
            self.main_window,
            "Calibración recomendada",
            "Este equipo aún no fue calibrado. Sin calibración, la app "
            "no puede validar si los canales que configures excederán "
            "la capacidad del encoder.\n\n"
            "La calibración toma ~60 segundos por encoder y crea una "
            "escena baseline temporal en OBS.\n\n"
            "¿Calibrar ahora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._launch_calibration_dialog()

    # ------------------------------------------------------------------
    # Fase 2f — watchdog de encoding_lag runtime
    # ------------------------------------------------------------------

    def _start_lag_watchdog(self):
        """Arranca el watchdog de encoding_lag si aún no está corriendo.

        Requiere conexión OBS activa — el stats_provider llama a
        get_stats() vía el facade.
        """
        try:
            from core.encoding_lag_watchdog import EncodingLagWatchdog
            from core.calibration_facade import RealObsFacade
        except Exception as e:
            log.debug("Fase 2f no disponible: %s", e)
            return
        # Reciclar instancia si ya existe: la creamos una sola vez y
        # sólo la arrancamos/detenemos. Así el cooldown se preserva
        # entre reconexiones.
        if not hasattr(self, "_lag_watchdog") or self._lag_watchdog is None:
            facade = RealObsFacade(self.obs_client)
            self._lag_watchdog = EncodingLagWatchdog(
                stats_provider=facade.get_output_frame_stats,
                parent=self.main_window,
            )
            self._lag_watchdog.lag_alert.connect(self._on_lag_alert)
        if not self._lag_watchdog.is_running():
            self._lag_watchdog.start()

    def _stop_lag_watchdog(self):
        """Detiene el watchdog si estaba corriendo."""
        wd = getattr(self, "_lag_watchdog", None)
        if wd is not None and wd.is_running():
            wd.stop()

    def _on_lag_alert(self, pct: int):
        """Handler del signal lag_alert: muestra advertencia non-modal."""
        log.warning("Watchdog: encoding lag alto sostenido %d%%", pct)
        try:
            self.main_window.statusBar().showMessage(
                f"⚠ Encoding lag {pct}% — considere bajar bitrate o "
                f"deshabilitar algún canal", 15000,
            )
        except Exception:
            pass

    def _on_connection_error(self, error_message):
        settings = self.settings_model.get_settings()
        host = settings.get("host", "")
        port = settings.get("port", "4455")
        # Auto-launch de OBS local sólo tiene sentido si el host apunta a esta misma máquina.
        # Con host remoto, lanzar un OBS local es contraproducente: crea una ventana OBS
        # inservible y espera 30s antes de mostrar el error real de red.
        if (sys.platform == "win32"
                and _is_local_host(host)
                and settings.get("obs_autolaunch", True)
                and not obs_launcher.is_obs_running()):
            exe_path = settings.get("obs_exe_path") or obs_launcher.find_obs_executable()
            if exe_path:
                self._start_autolaunch(exe_path, settings)
                return
            log.warning("Auto-launch activo pero no se encontró obs64.exe.")

        self._show_connection_error(error_message, host=host, port=port)

    def _show_connection_error(self, error_message, host: str = "", port: str = "4455"):
        from core.obs_errors import friendly_error
        self.main_window.statusBar().showMessage("Error de conexión")
        self.main_window.btn_connect.setEnabled(True)
        self.main_window.set_connection_ui(False)
        friendly = friendly_error(error_message, host, port)
        QMessageBox.critical(self.main_window, "Error de Conexión", friendly)

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

    # --- TRANSMISIÓN ---
    # Start/StopRecord global del Canal Principal legacy fue eliminado
    # como parte de la unificacion. Hoy la transmision vive en cada
    # canal multi-salida via OutputAdapter.enable() (filtro udp_out
    # Source Record). El toggle "Transmitir" por canal esta en
    # CanalDetailView, enlazado a CanalController.set_habilitado.

    def show_main_window(self):
        self.main_window.show()
        self.connect_to_obs()

    def shutdown(self):
        """Detiene threads antes de cerrar la app.

        Regla firme para canales (Fase 1e): NO se deshabilitan filters ni
        se remueven escenas — las pantallas remotas siguen recibiendo el
        último frame del canal aunque la app se cierre.
        """
        self.home_controller.stop()
        try:
            self.watchdog.stop()
            self.watchdog.wait(2000)
        except Exception as e:
            log.warning("Error deteniendo watchdog: %s", e)
        try:
            self._stop_lag_watchdog()
        except Exception as e:
            log.warning("Error deteniendo lag watchdog: %s", e)
        # Detener refresh del label de Autopilot v2 (Fase F).
        try:
            self._autopilot_v2_status_timer.stop()
        except Exception as e:
            log.debug("Stop autopilot v2 status timer fallo: %s", e)
        # Publicar handoff final al Lua v2 ANTES de parar el canal_controller
        # — asi el script retoma la rotacion con el active_index y
        # seconds_remaining que la app estaba manejando (Fase C).
        try:
            self.autopilot_v2.stop(publish_handoff=True)
        except Exception as e:
            log.warning("Error en shutdown de Autopilot v2: %s", e)
        try:
            self.canal_controller.shutdown_keeping_filters()
        except Exception as e:
            log.warning("Error en shutdown de canal_controller: %s", e)
