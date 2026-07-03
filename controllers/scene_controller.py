import logging
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QDialog
from datetime import datetime
from urllib.parse import urlparse
from views.scene_edit_dialog import SceneEditDialog
from views.schedule_widget import is_scene_active_now

log = logging.getLogger(__name__)

class SceneController:
    def __init__(self, view, model, obs_client, settings_model, calendar_controller):
        self.view = view
        self.model = model
        self.obs_client = obs_client
        self.settings_model = settings_model
        self.calendar_controller = calendar_controller
        
        self.scenes_list = []
        self.current_index = 0
        self.is_paused = False

        # NUEVAS VARIABLES PARA EL CONTEO REGRESIVO
        self.time_left = 0
        self.active_scene_name = ""
        
        self.timer = QTimer()
        # Ahora el timer llamará a la función de cuenta regresiva
        self.timer.timeout.connect(self.update_countdown)

        # Timer separado para auto-refresh de la escena web activa
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._auto_refresh_active_scene)
        self.active_refresh_source = None

        # Timer para reintentar cuando todas las escenas están fuera de ventana
        self.retry_timer = QTimer()
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self.rotate_to_next_scene)

        self._connect_signals()
        self.refresh_table()
        self.update_date_label() # Mostrar la fecha al abrir la app

    def _connect_signals(self):
        self.view.btn_add.clicked.connect(self.add_scene)
        self.view.btn_edit.clicked.connect(self.edit_scene)
        self.view.btn_duplicate.clicked.connect(self.duplicate_scene)
        self.view.btn_delete.clicked.connect(self.delete_scene)
        self.view.btn_move_up.clicked.connect(self.move_scene_up)
        self.view.btn_move_down.clicked.connect(self.move_scene_down)
        self.view.btn_start.clicked.connect(self.start_rotation)
        self.view.btn_stop.clicked.connect(self.stop_rotation)
        self.view.btn_pause.clicked.connect(self.toggle_pause)
        self.view.btn_prev.clicked.connect(self.skip_previous)
        self.view.btn_next.clicked.connect(self.skip_next)
        self.view.btn_browse.clicked.connect(self.browse_file)
        self.view.table.doubleClicked.connect(self._on_row_double_clicked)

        # Live tuning: al cambiar la selección de la tabla, cargar valores.
        self.view.table.itemSelectionChanged.connect(self._on_live_selection_changed)

        # Cada cambio de slider/spinbox empuja el transform a OBS de inmediato.
        for w in (self.view.live_zoom_slider, self.view.live_zoom_spin,
                  self.view.live_panx_slider, self.view.live_panx_spin,
                  self.view.live_pany_slider, self.view.live_pany_spin):
            w.valueChanged.connect(self._on_live_transform_changed)

        # Al soltar el slider, persistir en BD.
        for slider in (self.view.live_zoom_slider,
                       self.view.live_panx_slider,
                       self.view.live_pany_slider):
            slider.sliderReleased.connect(self._on_live_transform_released)
        # Spinbox: persistir al terminar edición manual (Enter o pierde foco).
        for spin in (self.view.live_zoom_spin,
                     self.view.live_panx_spin,
                     self.view.live_pany_spin):
            spin.editingFinished.connect(self._on_live_transform_released)

        self.view.btn_live_reset.clicked.connect(self._on_live_reset)

        # Estado del live tuning
        self.live_scene_id = None

    def duplicate_scene(self):
        scene_id = self.view.get_selected_scene_id()
        if not scene_id:
            QMessageBox.information(self.view, "Aviso", "Selecciona una escena para duplicar.")
            return
        src = self.model.get_scene(scene_id)
        if not src:
            return
        if not self.obs_client.client:
            QMessageBox.warning(self.view, "Error", "Conecta OBS primero.")
            return

        # Generar nombre único
        base = src["name"]
        new_name = f"{base} (copia)"
        counter = 2
        while self.model.scene_name_exists(new_name):
            new_name = f"{base} (copia {counter})"
            counter += 1

        # Crear escena en OBS con los mismos settings
        ok, msg = True, "OK"
        if src["tipo"] == "url" and src.get("contenido"):
            ok, msg = self.obs_client.create_web_scene(
                new_name, src["contenido"],
                width=src["ancho"], height=src["alto"], fps=src["fps"],
                reload_on_activate=src["reload_on_activate"],
                keep_session=src["keep_session"],
                custom_css=src.get("custom_css"),
            )
        elif src["tipo"] == "file" and src.get("contenido"):
            ok, msg = self.obs_client.create_scene_with_media(
                new_name, src["contenido"],
                video_loop=src["video_loop"],
                video_restart_on_activate=src["video_restart_on_activate"],
                video_mute=src["video_mute"],
                video_volume_pct=src["video_volume_pct"],
                video_offset_seg=src["video_offset_seg"],
            )
        else:
            try:
                self.obs_client.client.create_scene(new_name)
            except Exception as e:
                ok, msg = False, f"Error creando escena: {e}"

        if not ok:
            QMessageBox.critical(self.view, "Error de OBS", msg)
            return

        # Aplicar transform si difería del default
        if (src.get("zoom_pct", 100), src.get("pan_x", 0), src.get("pan_y", 0)) != (100, 0, 0):
            source_name = self._input_name_for(src["tipo"], new_name)
            self.obs_client.set_source_transform(
                new_name, source_name,
                src["zoom_pct"], src["pan_x"], src["pan_y"],
            )

        # Persistir en BD con todos los campos
        self.model.add_scene(
            new_name, src["duration"],
            tipo=src["tipo"], contenido=src.get("contenido"),
            ancho=src["ancho"], alto=src["alto"], fps=src["fps"],
            reload_on_activate=src["reload_on_activate"],
            keep_session=src["keep_session"],
            custom_css=src.get("custom_css"),
            zoom_pct=src["zoom_pct"], pan_x=src["pan_x"], pan_y=src["pan_y"],
            refresh_interval_seg=src.get("refresh_interval_seg", 0),
            video_loop=src["video_loop"],
            video_restart_on_activate=src["video_restart_on_activate"],
            video_mute=src["video_mute"],
            video_volume_pct=src["video_volume_pct"],
            video_offset_seg=src["video_offset_seg"],
            active_days=src.get("active_days", 127),
            active_time_start=src.get("active_time_start"),
            active_time_end=src.get("active_time_end"),
        )
        log.info("Escena duplicada: '%s' → '%s'", base, new_name)
        self.refresh_table()

    # --- LIVE TUNING (zoom + pan en vivo) ---
    def _on_live_selection_changed(self):
        scene_id = self.view.get_selected_scene_id()
        if not scene_id:
            self.live_scene_id = None
            self.view.clear_live_selection()
            return
        scene = None
        for sc in self.scenes_list:
            if sc["id"] == scene_id:
                scene = sc
                break
        if not scene:
            self.live_scene_id = None
            self.view.clear_live_selection()
            return
        self.live_scene_id = scene_id
        self.view.set_live_values(
            scene.get("zoom_pct", 100),
            scene.get("pan_x", 0),
            scene.get("pan_y", 0),
            target_label=f"Ajustando: {scene['name']}",
        )

    def _on_live_transform_changed(self):
        """Envía el transform actual a OBS. Se dispara con cada movimiento de slider/spinbox."""
        if not self.live_scene_id or not self.obs_client.client:
            return
        scene = None
        for sc in self.scenes_list:
            if sc["id"] == self.live_scene_id:
                scene = sc
                break
        if not scene:
            return
        zoom, px, py = self.view.get_live_values()
        source_name = self._input_name_for(scene["tipo"], scene["name"])
        self.obs_client.set_source_transform(scene["name"], source_name, zoom, px, py)

    def _on_live_transform_released(self):
        """Persiste el transform actual en BD. Se dispara al soltar slider o terminar edición spin."""
        if not self.live_scene_id:
            return
        zoom, px, py = self.view.get_live_values()
        self.model.update_scene_transform(self.live_scene_id, zoom, px, py)
        # Actualizar la copia in-memory
        for sc in self.scenes_list:
            if sc["id"] == self.live_scene_id:
                sc["zoom_pct"] = zoom
                sc["pan_x"] = px
                sc["pan_y"] = py
                break

    def _on_live_reset(self):
        if not self.live_scene_id:
            return
        self.view.set_live_values(100, 0, 0, target_label=self.view.lbl_live_target.text())
        self._on_live_transform_changed()
        self._on_live_transform_released()

    def move_scene_up(self):
        self._move_scene(-1)

    def move_scene_down(self):
        self._move_scene(1)

    def _move_scene(self, direction):
        scene_id = self.view.get_selected_scene_id()
        if not scene_id:
            QMessageBox.information(self.view, "Aviso", "Selecciona una escena de la tabla para moverla.")
            return
        moved = self.model.reorder_scene(scene_id, direction)
        if not moved:
            return  # ya estaba en el borde
        self.refresh_table()
        self.view.select_row_by_scene_id(scene_id)
        # Si el rotador está corriendo, resincronizar current_index para
        # que el próximo cambio caiga sobre la escena siguiente a la activa en el nuevo orden.
        if self.timer.isActive():
            self._resync_current_index()

    def _resync_current_index(self):
        """Ancla current_index a la posición siguiente a la escena activa."""
        if not self.scenes_list:
            self.current_index = 0
            return
        for i, sc in enumerate(self.scenes_list):
            if sc["name"] == self.active_scene_name:
                self.current_index = (i + 1) % len(self.scenes_list)
                return
        # Si la escena activa desapareció de la lista (borrada), acotar
        self.current_index = self.current_index % len(self.scenes_list)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self.view, "Seleccionar Archivo Multimedia", "",
            "Archivos Multimedia (*.mp4 *.mov *.mkv *.png *.jpg *.jpeg *.gif);;Todos los archivos (*)"
        )
        if file_path:
            self.view.input_file.setText(file_path)

    def refresh_table(self):
        self.scenes_list = self.model.get_all_scenes()
        self.view.populate_table(self.scenes_list)

    def add_scene(self):
        name = self.view.input_name.text().strip()
        duration = self.view.input_duration.value()
        tipo = self.view.get_current_type()
        tf = self.view.get_transform_options()
        sch = self.view.get_schedule_options()

        if not name:
            QMessageBox.warning(self.view, "Error", "El nombre de la escena no puede estar vacío.")
            return

        if tipo == "url":
            opts = self.view.get_web_options()
            url = opts["url"]
            if not self._is_valid_url(url):
                QMessageBox.warning(self.view, "Error", "URL inválida. Debe iniciar con http:// o https://")
                return
            if not self.obs_client.client:
                QMessageBox.warning(self.view, "Error", "Conecta OBS primero para poder crear la escena remota.")
                return
            success, msg = self.obs_client.create_web_scene(
                name, url,
                width=opts["ancho"], height=opts["alto"], fps=opts["fps"],
                reload_on_activate=opts["reload_on_activate"],
                keep_session=opts["keep_session"],
                custom_css=opts["custom_css"],
            )
            if not success:
                QMessageBox.critical(self.view, "Error de OBS", msg)
                return
            self._apply_transform_if_needed(name, "url", tf)
            self.model.add_scene(
                name, duration,
                tipo="url", contenido=url,
                ancho=opts["ancho"], alto=opts["alto"], fps=opts["fps"],
                reload_on_activate=opts["reload_on_activate"],
                keep_session=opts["keep_session"],
                custom_css=opts["custom_css"],
                zoom_pct=tf["zoom_pct"], pan_x=tf["pan_x"], pan_y=tf["pan_y"],
                refresh_interval_seg=opts["refresh_interval_seg"],
                active_days=sch["active_days"],
                active_time_start=sch["active_time_start"],
                active_time_end=sch["active_time_end"],
            )
        else:
            file_path = self.view.input_file.text().strip()
            vopts = self.view.get_video_options()
            if file_path:
                if not self.obs_client.client:
                    QMessageBox.warning(self.view, "Error", "Conecta OBS primero para poder crear la escena remota.")
                    return
                success, msg = self.obs_client.create_scene_with_media(
                    name, file_path,
                    video_loop=vopts["video_loop"],
                    video_restart_on_activate=vopts["video_restart_on_activate"],
                    video_mute=vopts["video_mute"],
                    video_volume_pct=vopts["video_volume_pct"],
                    video_offset_seg=vopts["video_offset_seg"],
                )
                if not success:
                    QMessageBox.critical(self.view, "Error de OBS", msg)
                    return
                self._apply_transform_if_needed(name, "file", tf)
            self.model.add_scene(
                name, duration, tipo="file", contenido=file_path or None,
                zoom_pct=tf["zoom_pct"], pan_x=tf["pan_x"], pan_y=tf["pan_y"],
                video_loop=vopts["video_loop"],
                video_restart_on_activate=vopts["video_restart_on_activate"],
                video_mute=vopts["video_mute"],
                video_volume_pct=vopts["video_volume_pct"],
                video_offset_seg=vopts["video_offset_seg"],
                active_days=sch["active_days"],
                active_time_start=sch["active_time_start"],
                active_time_end=sch["active_time_end"],
            )

        self.view.clear_inputs()
        self.refresh_table()

    def _apply_transform_if_needed(self, scene_name, tipo, tf):
        """Aplica set_source_transform solo si difiere del default (100/0/0)."""
        if tf["zoom_pct"] == 100 and tf["pan_x"] == 0 and tf["pan_y"] == 0:
            return
        source_name = self._input_name_for(tipo, scene_name)
        ok, msg = self.obs_client.set_source_transform(
            scene_name, source_name, tf["zoom_pct"], tf["pan_x"], tf["pan_y"]
        )
        if not ok:
            log.warning("Transform en escena '%s' falló: %s", scene_name, msg)

    def _is_valid_url(self, url):
        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except Exception:
            return False

    def _input_name_for(self, tipo, scene_name):
        return f"{scene_name}_Web" if tipo == "url" else f"{scene_name}_Contenido"

    def edit_scene(self):
        scene_id = self.view.get_selected_scene_id()
        if not scene_id:
            QMessageBox.information(self.view, "Aviso", "Selecciona una escena de la tabla para editar.")
            return

        old = self.model.get_scene(scene_id)
        if not old:
            QMessageBox.warning(self.view, "Error", "No se encontró la escena en la base de datos.")
            return

        dialog = SceneEditDialog(old, self.view, obs_client=self.obs_client)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new = dialog.get_values()

        # Validaciones
        if not new["name"]:
            QMessageBox.warning(self.view, "Error", "El nombre no puede estar vacío.")
            return
        if new["tipo"] == "url" and not self._is_valid_url(new["contenido"] or ""):
            QMessageBox.warning(self.view, "Error", "URL inválida. Debe iniciar con http:// o https://")
            return

        # Si hay cambios que requieren OBS y no está conectado, avisar
        obs_needed = self._changes_need_obs(old, new)
        if obs_needed and not self.obs_client.client:
            QMessageBox.warning(self.view, "Error", "Conecta OBS primero para aplicar los cambios remotos.")
            return

        if obs_needed:
            ok, msg = self._apply_obs_edits(old, new)
            if not ok:
                QMessageBox.critical(self.view, "Error de OBS", msg)
                return

        # Persistir en BD
        self.model.update_scene(
            scene_id=old["id"],
            name=new["name"],
            duration=new["duration"],
            tipo=new["tipo"],
            contenido=new["contenido"],
            ancho=new["ancho"],
            alto=new["alto"],
            fps=new["fps"],
            reload_on_activate=new["reload_on_activate"],
            keep_session=new["keep_session"],
            custom_css=new["custom_css"],
            zoom_pct=new["zoom_pct"],
            pan_x=new["pan_x"],
            pan_y=new["pan_y"],
            refresh_interval_seg=new.get("refresh_interval_seg", 0),
            video_loop=new.get("video_loop", True),
            video_restart_on_activate=new.get("video_restart_on_activate", True),
            video_mute=new.get("video_mute", False),
            video_volume_pct=new.get("video_volume_pct", 100),
            video_offset_seg=new.get("video_offset_seg", 0),
            active_days=new.get("active_days", 127),
            active_time_start=new.get("active_time_start"),
            active_time_end=new.get("active_time_end"),
        )
        self.refresh_table()

        # Reflejar en la escena activa sin esperar a la próxima rotación
        self._apply_hot_updates_to_active(old, new)

    def _apply_hot_updates_to_active(self, old, new):
        """Refleja cambios en la escena activa sin esperar a la próxima rotación.

        Aplica: duración (recomputa time_left preservando lo transcurrido),
        intervalo de auto-refresh, offset de video y nombre (state + highlight).
        """
        if not self.timer.isActive():
            return
        if old["name"] != self.active_scene_name:
            return  # la editada no es la que se está mostrando

        # Nombre: sincronizar variable de estado y highlight
        if old["name"] != new["name"]:
            self.active_scene_name = new["name"]
            self.view.highlight_active_scene(new["name"])

        # Duración: preservar lo transcurrido
        if old["duration"] != new["duration"]:
            elapsed = max(0, old["duration"] - self.time_left)
            remaining = new["duration"] - elapsed
            if remaining <= 0:
                # La nueva duración ya se agotó → rotar de inmediato
                self.timer.stop()
                self.rotate_to_next_scene()
                return
            self.time_left = remaining
            self.update_status_label()

        # Auto-refresh: reprogramar si cambió intervalo, o si cambió nombre (renueva source)
        if new["tipo"] == "url":
            old_interval = old.get("refresh_interval_seg") or 0
            new_interval = new.get("refresh_interval_seg") or 0
            if new_interval != old_interval or old["name"] != new["name"]:
                self.refresh_timer.stop()
                if new_interval > 0:
                    self.active_refresh_source = self._input_name_for("url", new["name"])
                    self.refresh_timer.start(new_interval * 1000)
                else:
                    self.active_refresh_source = None

        # Video offset: reseek si cambió
        if new["tipo"] == "file":
            old_offset = old.get("video_offset_seg") or 0
            new_offset = new.get("video_offset_seg") or 0
            if new_offset != old_offset and new_offset > 0 and self.obs_client.client:
                source_name = self._input_name_for("file", new["name"])
                self.obs_client.set_media_cursor(source_name, new_offset * 1000)

    def _changes_need_obs(self, old, new):
        """True si cualquier cambio requiere hablarle a OBS."""
        video_fields_changed = (
            old.get("video_loop", True) != new.get("video_loop", True)
            or old.get("video_restart_on_activate", True) != new.get("video_restart_on_activate", True)
            or old.get("video_mute", False) != new.get("video_mute", False)
            or old.get("video_volume_pct", 100) != new.get("video_volume_pct", 100)
            or old.get("video_offset_seg", 0) != new.get("video_offset_seg", 0)
        )
        return (
            old["name"] != new["name"]
            or old["tipo"] != new["tipo"]
            or (old.get("contenido") or "") != (new.get("contenido") or "")
            or old.get("zoom_pct", 100) != new.get("zoom_pct", 100)
            or old.get("pan_x", 0) != new.get("pan_x", 0)
            or old.get("pan_y", 0) != new.get("pan_y", 0)
            or (new["tipo"] == "url" and (
                old["ancho"] != new["ancho"]
                or old["alto"] != new["alto"]
                or old["fps"] != new["fps"]
                or old["reload_on_activate"] != new["reload_on_activate"]
                or old["keep_session"] != new["keep_session"]
                or (old.get("custom_css") or "") != (new.get("custom_css") or "")
            ))
            or (new["tipo"] == "file" and video_fields_changed)
        )

    def _apply_obs_edits(self, old, new):
        """Aplica cambios en OBS priorizando patch in-place.

        - Rename escena + input si cambia el nombre.
        - Type file<->url: remove_input + add_input nuevo (mantiene la escena).
        - Same type: set_input_settings con el delta (preserva sesión del navegador).
        """
        current_scene_name = old["name"]

        # 1) Rename escena + input (mantiene el navegador vivo)
        if old["name"] != new["name"]:
            ok, msg = self.obs_client.rename_scene(old["name"], new["name"])
            if not ok:
                return False, msg
            old_input = self._input_name_for(old["tipo"], old["name"])
            new_input_same_kind = self._input_name_for(old["tipo"], new["name"])
            ok, msg = self.obs_client.rename_input(old_input, new_input_same_kind)
            if not ok:
                # No abortamos: la escena ya se renombró; puede que el source no existiera
                log.warning("Rename input falló: %s", msg)
            current_scene_name = new["name"]

        # 2) Cambio de tipo → reemplazar input (fallback recreate del input)
        if old["tipo"] != new["tipo"]:
            old_input = self._input_name_for(old["tipo"], current_scene_name)
            new_input = self._input_name_for(new["tipo"], current_scene_name)
            self.obs_client.remove_input(old_input)
            if new["tipo"] == "url":
                ok, msg = self.obs_client.add_browser_input(
                    current_scene_name, new_input, new["contenido"],
                    new["ancho"], new["alto"], new["fps"],
                    new["reload_on_activate"], new["keep_session"],
                    custom_css=new["custom_css"],
                )
            else:
                if not new["contenido"]:
                    return False, "Debes indicar una ruta de archivo para el tipo Archivo local."
                ok, msg = self.obs_client.add_file_input(
                    current_scene_name, new_input, new["contenido"],
                    video_loop=new.get("video_loop", True),
                    video_restart_on_activate=new.get("video_restart_on_activate", True),
                    video_mute=new.get("video_mute", False),
                    video_volume_pct=new.get("video_volume_pct", 100),
                    video_offset_seg=new.get("video_offset_seg", 0),
                )
            return (ok, msg) if not ok else (True, "OK")

        # 3) Mismo tipo → patch in-place
        input_name = self._input_name_for(new["tipo"], current_scene_name)

        if new["tipo"] == "url":
            delta = {}
            if (old.get("contenido") or "") != (new.get("contenido") or ""):
                delta["url"] = new["contenido"]
            if old["ancho"] != new["ancho"]:
                delta["width"] = int(new["ancho"])
            if old["alto"] != new["alto"]:
                delta["height"] = int(new["alto"])
            if old["fps"] != new["fps"]:
                delta["fps"] = int(new["fps"])
            if old["reload_on_activate"] != new["reload_on_activate"]:
                delta["restart_when_active"] = bool(new["reload_on_activate"])
            if old["keep_session"] != new["keep_session"]:
                delta["shutdown"] = not bool(new["keep_session"])
            if (old.get("custom_css") or "") != (new.get("custom_css") or ""):
                delta["css"] = new.get("custom_css") or ""
            if delta:
                ok, msg = self.obs_client.patch_input_settings(input_name, delta)
                if not ok:
                    return False, msg
        else:  # file
            # Si cambia el archivo, la manera segura es recrear el input:
            # image_source y ffmpeg_source son kinds distintos y no se pueden mutar entre sí.
            if (old.get("contenido") or "") != (new.get("contenido") or ""):
                if not new["contenido"]:
                    return False, "Debes indicar una ruta de archivo para el tipo Archivo local."
                self.obs_client.remove_input(input_name)
                ok, msg = self.obs_client.add_file_input(
                    current_scene_name, input_name, new["contenido"],
                    video_loop=new.get("video_loop", True),
                    video_restart_on_activate=new.get("video_restart_on_activate", True),
                    video_mute=new.get("video_mute", False),
                    video_volume_pct=new.get("video_volume_pct", 100),
                    video_offset_seg=new.get("video_offset_seg", 0),
                )
                if not ok:
                    return False, msg
            else:
                # Mismo archivo, quizás cambiaron settings de video → patch in-place
                from models.obs_client import is_video_file
                if is_video_file(new.get("contenido") or ""):
                    settings_changed = (
                        old.get("video_loop", True) != new.get("video_loop", True)
                        or old.get("video_restart_on_activate", True) != new.get("video_restart_on_activate", True)
                        or old.get("video_offset_seg", 0) != new.get("video_offset_seg", 0)
                    )
                    if settings_changed:
                        ok, msg = self.obs_client.patch_video_settings(
                            input_name,
                            new.get("video_loop", True),
                            new.get("video_restart_on_activate", True),
                            new.get("video_offset_seg", 0),
                        )
                        if not ok:
                            return False, msg
                    audio_changed = (
                        old.get("video_mute", False) != new.get("video_mute", False)
                        or old.get("video_volume_pct", 100) != new.get("video_volume_pct", 100)
                    )
                    if audio_changed:
                        ok, msg = self.obs_client.set_input_audio(
                            input_name, new.get("video_mute", False), new.get("video_volume_pct", 100)
                        )
                        if not ok:
                            return False, msg

        # 4) Zoom / Pan — aplicar si cambió (patch in-place, no destruye nada)
        transform_changed = (
            old.get("zoom_pct", 100) != new.get("zoom_pct", 100)
            or old.get("pan_x", 0) != new.get("pan_x", 0)
            or old.get("pan_y", 0) != new.get("pan_y", 0)
        )
        if transform_changed:
            ok, msg = self.obs_client.set_source_transform(
                current_scene_name, input_name,
                new["zoom_pct"], new["pan_x"], new["pan_y"],
            )
            if not ok:
                return False, msg

        return True, "OK"

    def delete_scene(self):
        # 1. Obtener el ID de la fila seleccionada
        scene_id = self.view.get_selected_scene_id()
        if not scene_id:
            QMessageBox.information(self.view, "Aviso", "Selecciona una escena de la tabla para eliminar.")
            return

        # 2. Buscar el nombre de la escena usando ese ID
        scene_name = None
        for scene in self.scenes_list:
            if scene["id"] == scene_id:
                scene_name = scene["name"]
                break

        # 3. Pedir confirmación al usuario (¡Por seguridad!)
        reply = QMessageBox.question(
            self.view, 
            'Eliminar Escena', 
            f"¿Estás seguro de que deseas eliminar la escena '{scene_name}'?\n\nEsto la borrará del rotador y también desaparecerá de OBS.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        # 4. Si el usuario dice que sí, procedemos a la eliminación doble
        if reply == QMessageBox.StandardButton.Yes:
            
            # A) Intentar eliminar de OBS primero (si estamos conectados)
            if self.obs_client.client and scene_name:
                success, msg = self.obs_client.delete_scene(scene_name)
                # Si falla (por ejemplo, alguien ya la borró a mano en OBS), solo mostramos un aviso
                if not success:
                    log.warning("Delete scene OBS: %s", msg)
            
            # B) Eliminar de nuestra base de datos (SQLite) y refrescar la tabla
            self.model.delete_scene(scene_id)
            self.refresh_table()

    # --- NUEVAS FUNCIONES DE TIEMPO Y FECHA ---

    def update_date_label(self):
        """Obtiene la fecha actual de la computadora y la formatea en español."""
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        
        now = datetime.now()
        # Formato: Lunes, 11 de Mayo de 2026
        date_str = f"{dias[now.weekday()]}, {now.day} de {meses[now.month-1]} de {now.year}"
        self.view.lbl_date.setText(date_str)

    def start_rotation(self):
        if not self.scenes_list:
            QMessageBox.warning(self.view, "Error", "No hay escenas en la lista.")
            return
        if not self.obs_client.client:
            QMessageBox.warning(self.view, "Error", "Conecta OBS primero.")
            return

        self.current_index = 0
        self.is_paused = False
        self.view.set_rotator_state("running")

        self.rotate_to_next_scene()

    def stop_rotation(self):
        self.timer.stop()
        self.refresh_timer.stop()
        self.retry_timer.stop()
        self.active_refresh_source = None
        self.is_paused = False
        self.view.set_rotator_state("stopped")
        self.view.lbl_status.setText("Estado: Detenido")
        self.view.lbl_status.setStyleSheet("font-weight: bold; color: #DC3545;")
        self.view.highlight_active_scene(None)

    def toggle_pause(self):
        if not self.view.btn_pause.isEnabled():
            return
        if self.is_paused:
            self._resume_rotation()
        else:
            self._pause_rotation()

    def _pause_rotation(self):
        """Congela el countdown sin rotar. La escena activa sigue en pantalla."""
        self.timer.stop()
        self.refresh_timer.stop()
        self.retry_timer.stop()
        self.is_paused = True
        self.view.set_rotator_state("paused")
        self.view.lbl_status.setText(
            f"⏸ Pausado en: {self.active_scene_name}  ({self.time_left} seg restantes)"
        )
        self.view.lbl_status.setStyleSheet("font-weight: bold; color: #FD7E14;")
        log.info("Rotador pausado en '%s' (%ds restantes)",
                 self.active_scene_name, self.time_left)

    def _resume_rotation(self):
        """Reanuda el countdown desde donde quedó."""
        self.is_paused = False
        self.view.set_rotator_state("running")
        self.timer.start(1000)
        # Restaurar refresh_timer si la escena activa lo requería
        for sc in self.scenes_list:
            if sc["name"] == self.active_scene_name:
                interval = sc.get("refresh_interval_seg") or 0
                if sc.get("tipo") == "url" and interval > 0:
                    self.active_refresh_source = self._input_name_for("url", sc["name"])
                    self.refresh_timer.start(interval * 1000)
                break
        self.update_status_label()
        log.info("Rotador reanudado en '%s'", self.active_scene_name)

    def skip_next(self):
        if not self.timer.isActive() and not self.is_paused:
            return
        self.timer.stop()
        self.refresh_timer.stop()
        self.is_paused = False
        self.view.set_rotator_state("running")
        log.info("Skip → siguiente")
        self.rotate_to_next_scene()

    def skip_previous(self):
        if not self.timer.isActive() and not self.is_paused:
            return
        self.timer.stop()
        self.refresh_timer.stop()
        self.is_paused = False
        self.view.set_rotator_state("running")
        # current_index apunta a la SIGUIENTE. Restar 2 nos deja en la anterior.
        if self.scenes_list:
            self.current_index = (self.current_index - 2) % len(self.scenes_list)
        log.info("Skip → anterior")
        self.rotate_to_next_scene()

    def goto_scene(self, scene_id):
        """Salta directamente a una escena. Arranca el rotador si estaba detenido."""
        if not scene_id:
            return
        if not self.obs_client.client:
            QMessageBox.warning(self.view, "Error", "Conecta OBS primero.")
            return
        idx = None
        for i, s in enumerate(self.scenes_list):
            if s["id"] == scene_id:
                idx = i
                break
        if idx is None:
            return
        self.current_index = idx
        self.timer.stop()
        self.refresh_timer.stop()
        self.is_paused = False
        self.view.set_rotator_state("running")
        log.info("Goto → '%s'", self.scenes_list[idx]["name"])
        self.rotate_to_next_scene()

    def _on_row_double_clicked(self, index):
        scene_id = self.view.get_selected_scene_id()
        self.goto_scene(scene_id)

    def _pick_next_active_scene(self):
        """Escoge la próxima escena activa según programación, avanzando current_index.

        Recorre hasta len(scenes_list) intentando encontrar una activa. Si ninguna
        aplica devuelve None (current_index queda sin cambios efectivos).
        """
        n = len(self.scenes_list)
        if n == 0:
            return None
        now = datetime.now()
        for _ in range(n):
            candidate = self.scenes_list[self.current_index]
            if is_scene_active_now(candidate, now):
                # Avanzar el índice para la próxima rotación
                self.current_index = (self.current_index + 1) % n
                return candidate
            self.current_index = (self.current_index + 1) % n
        return None

    def rotate_to_next_scene(self):
        self.update_date_label() # Refresca la fecha cada vez que cambia una escena

        # Detener refresh de la escena anterior
        self.refresh_timer.stop()
        self.active_refresh_source = None
        self.retry_timer.stop()

        # Buscar la próxima escena que esté en ventana (día + horario)
        scene = self._pick_next_active_scene()
        if scene is None:
            # Nada activo en este momento → esperar y reintentar
            self.view.lbl_status.setText("⏳ Sin escenas activas en la ventana actual. Reintentando en 60s…")
            self.view.lbl_status.setStyleSheet("font-weight: bold; color: #FD7E14;")
            self.view.highlight_active_scene(None)
            log.info("Ninguna escena activa en la ventana actual. Reintentando en 60s.")
            self.retry_timer.start(60000)
            return

        self.active_scene_name = scene["name"]

        cal_scene_name = self.settings_model.get_settings().get("cal_scene")
        if scene["name"] == cal_scene_name:
            self.calendar_controller.move_circle_to_today(show_messages=False)

        success = self.obs_client.change_scene(scene["name"])

        if success:
            self.time_left = scene["duration"]
            self.update_status_label()
            self.view.highlight_active_scene(scene["name"])
            log.info("Rotar → '%s' (dur %ds, tipo %s)",
                     scene["name"], scene["duration"], scene.get("tipo", "?"))

            # Auto-refresh: solo si es escena URL con intervalo definido
            interval = scene.get("refresh_interval_seg") or 0
            if scene.get("tipo") == "url" and interval > 0:
                self.active_refresh_source = self._input_name_for("url", scene["name"])
                self.refresh_timer.start(interval * 1000)

            # Video con offset: seek al segundo indicado (bypass del restart natural)
            offset = scene.get("video_offset_seg") or 0
            if scene.get("tipo") == "file" and offset > 0:
                self.obs_client.set_media_cursor(
                    self._input_name_for("file", scene["name"]), offset * 1000
                )
            
            # Ahora el timer "hace tick" cada 1000 ms (1 segundo)
            self.timer.start(1000)
            # current_index ya fue avanzado por _pick_next_active_scene
        else:
            self.stop_rotation()
            QMessageBox.critical(self.view, "Error", f"No se pudo cambiar a '{scene['name']}'.")

    def update_countdown(self):
        """Esta función se ejecuta automáticamente cada 1 segundo."""
        self.time_left -= 1
        
        if self.time_left <= 0:
            self.timer.stop()
            self.rotate_to_next_scene() # ¡Tiempo agotado! Salta a la siguiente escena.
        else:
            self.update_status_label() # Actualiza el texto en pantalla

    def update_status_label(self):
        """Dibuja el estado y el reloj de arena en la interfaz."""
        self.view.lbl_status.setText(f"Mostrando: {self.active_scene_name}  ( ⏳ {self.time_left} seg )")
        self.view.lbl_status.setStyleSheet("font-weight: bold; color: #0D6EFD;")

    def _auto_refresh_active_scene(self):
        """Fuerza F5 sobre el browser_source activo. Preserva sesión/cookies."""
        if not self.active_refresh_source:
            return
        ok, msg = self.obs_client.refresh_browser_source(self.active_refresh_source)
        if not ok:
            log.warning("Auto-refresh falló: %s", msg)