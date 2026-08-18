import calendar
import datetime
import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QFileDialog

from core import importexport
from views.calendar_simulation_dialog import CalendarSimulationDialog

log = logging.getLogger(__name__)


class CalendarController:
    def __init__(self, view, model, settings_model, obs_client,
                 scene_model=None, on_scene_created=None):
        self.view = view
        self.model = model
        self.settings_model = settings_model
        self.obs_client = obs_client
        self.scene_model = scene_model
        self.on_scene_created = on_scene_created

        self._sim_timer = None
        self._sim_state = None
        self._sim_dialog = None

        self._connect_signals()

    def _connect_signals(self):
        self.view.btn_save.clicked.connect(self.save_settings)
        self.view.btn_test.clicked.connect(lambda: self.move_circle_to_today(show_messages=True))
        self.view.btn_simulate.clicked.connect(self.open_simulation_dialog)
        self.view.btn_read_obs.clicked.connect(self.read_position_from_obs)
        self.view.btn_export_cal.clicked.connect(self.export_calibration)
        self.view.btn_import_cal.clicked.connect(self.import_calibration)

        # Nuevas conexiones
        self.view.btn_browse_bg.clicked.connect(self.browse_bg)
        self.view.btn_browse_circle.clicked.connect(self.browse_circle)
        self.view.btn_build_scene.clicked.connect(self.build_scene)

        # Live tuning: cada cambio en los spins mueve el marcador en OBS al vuelo;
        # al terminar la edición (Enter o perder foco) se persiste en .env.
        # Todos los spins per-plantilla (4w/5w/6w) se conectan: al editar uno
        # que NO es la plantilla activa no afecta la posición del círculo, pero
        # sí se persiste — así el usuario puede pre-calibrar plantillas.
        for key in ("4", "5", "6"):
            for name in ("spin_x_start", "spin_x_space",
                         "spin_y_start", "spin_y_space", "spin_scale",
                         "spin_dx_row0", "spin_dy_row0"):
                w = getattr(self.view, f"{name}_{key}w")
                w.valueChanged.connect(self._apply_live_calibration)
                w.editingFinished.connect(self._persist_live_calibration)
        # Cambiar la plantilla activa recoloca el marcador y persiste inmediatamente.
        self.view.combo_template_weeks.currentIndexChanged.connect(self._on_template_changed)
        # Los nombres de escena/marcador solo persisten al terminar edición.
        self.view.input_scene_name.editingFinished.connect(self._persist_live_calibration)
        self.view.input_source_name.editingFinished.connect(self._persist_live_calibration)

        # Etiqueta inicial de plantilla activa.
        self._refresh_active_template_label()

    def browse_bg(self):
        file_path, _ = QFileDialog.getOpenFileName(self.view, "Seleccionar Fondo", "", "Imágenes (*.png *.jpg *.jpeg)")
        if file_path: self.view.input_bg_file.setText(file_path)

    def browse_circle(self):
        file_path, _ = QFileDialog.getOpenFileName(self.view, "Seleccionar Marcador", "", "Imágenes (*.png *.jpg)")
        if file_path: self.view.input_circle_file.setText(file_path)

    def build_scene(self):
        scene_name = self.view.input_scene_name.text().strip()
        circle_name = self.view.input_source_name.text().strip()
        bg_path = self.view.input_bg_file.text().strip()
        circle_path = self.view.input_circle_file.text().strip()
        # ΔX de la plantilla activa (build_calendar_scene ya no lo usa para
        # nada crítico — se pasa por retrocompatibilidad).
        active_key = self._resolve_template_key(
            self._selected_template_key_from_view()
        )
        x_space = getattr(self.view, f"spin_x_space_{active_key}w").value()

        if not all([scene_name, circle_name, bg_path, circle_path]):
            QMessageBox.warning(self.view, "Faltan datos", "Selecciona todos los archivos.")
            return

        success, msg, auto_scale_pct = self.obs_client.build_calendar_scene(
            scene_name, bg_path, circle_path, circle_name, x_space
        )

        if success:
            # El marcador se insertó a tamaño nativo (100%). Resetear el spin
            # de escala de la plantilla activa a 100% y persistir para que
            # futuras llamadas a move_scene_item no apliquen una escala vieja.
            if auto_scale_pct is not None and auto_scale_pct > 0:
                spin_scale = getattr(self.view, f"spin_scale_{active_key}w")
                spin_scale.blockSignals(True)
                spin_scale.setValue(auto_scale_pct)
                spin_scale.blockSignals(False)
                self._persist_live_calibration()
                log.info(
                    "Escena construida — cal_scale_%sw reseteado a %d%%",
                    active_key, auto_scale_pct,
                )

            # Colocamos el marcador en el "día inicial" indicado por el usuario
            # (default 1). Al iniciar la rotación de escenas, el flujo normal
            # llamará a move_circle_to_today() sin target_date y se moverá al
            # día real automáticamente.
            start_day = self.view.spin_build_start_day.value()
            today = datetime.date.today()
            last_day = calendar.monthrange(today.year, today.month)[1]
            start_day = max(1, min(start_day, last_day))
            target_date = datetime.date(today.year, today.month, start_day)
            self.move_circle_to_today(show_messages=False, target_date=target_date)
            log.info("Círculo colocado en día inicial %d (%s)", start_day, target_date.isoformat())

            # Registrar la escena en la BD del rotador para que aparezca en la lista
            self._persist_calendar_scene(scene_name)
            if self.on_scene_created:
                self.on_scene_created()
            QMessageBox.information(
                self.view, "Éxito",
                f"Calendario configurado. Círculo colocado en el día {start_day} "
                "a escala 100% (tamaño nativo del PNG).\n"
                "Ajusta la escala del panel de la plantilla activa si el "
                "marcador es más grande o más chico que la celda.\n"
                "Al iniciar la rotación se moverá automáticamente al día de hoy."
            )
        else:
            QMessageBox.critical(self.view, "Error", msg)

    def _persist_calendar_scene(self, scene_name):
        """Inserta o actualiza la escena de calendario en la BD del rotador.

        Se guarda como tipo='file' sin contenido: la escena ya vive en OBS con
        sus propios sources (fondo + marcador); la BD sólo la trackea para
        aparecer en la lista del rotador.
        """
        if self.scene_model is None:
            log.warning("scene_model no inyectado — no se registró '%s' en el rotador.", scene_name)
            return
        try:
            existing = self.scene_model.get_scene_by_name(scene_name)
            if existing:
                self.scene_model.update_scene(
                    scene_id=existing["id"],
                    name=scene_name,
                    duration=existing["duration"],
                    tipo="file",
                    contenido=None,
                    ancho=existing["ancho"],
                    alto=existing["alto"],
                    fps=existing["fps"],
                    reload_on_activate=existing["reload_on_activate"],
                    keep_session=existing["keep_session"],
                    custom_css=existing.get("custom_css"),
                    zoom_pct=existing.get("zoom_pct", 100),
                    pan_x=existing.get("pan_x", 0),
                    pan_y=existing.get("pan_y", 0),
                    refresh_interval_seg=existing.get("refresh_interval_seg", 0),
                    video_loop=existing.get("video_loop", True),
                    video_restart_on_activate=existing.get("video_restart_on_activate", True),
                    video_mute=existing.get("video_mute", False),
                    video_volume_pct=existing.get("video_volume_pct", 100),
                    video_offset_seg=existing.get("video_offset_seg", 0),
                    active_days=existing.get("active_days", 127),
                    active_time_start=existing.get("active_time_start"),
                    active_time_end=existing.get("active_time_end"),
                )
                log.info("Escena de calendario actualizada en BD: '%s'", scene_name)
            else:
                self.scene_model.add_scene(scene_name, 20, tipo="file", contenido=None)
                log.info("Escena de calendario añadida a BD: '%s' (20s)", scene_name)
        except Exception as e:
            log.error("Fallo persistiendo escena de calendario '%s': %s", scene_name, e)

    def save_settings(self):
        self.settings_model.save_calendar_settings(
            scene=self.view.input_scene_name.text(),
            source=self.view.input_source_name.text(),
            template_weeks=self._selected_template_key_from_view(),
            per_template=self._collect_all_templates_from_view(),
        )
        QMessageBox.information(self.view, "Éxito", "Calibración del calendario guardada en .env")

    def export_calibration(self):
        """Exporta la calibración actual del calendario a un archivo JSON.

        Persiste primero los valores de los spinboxes al .env para que el
        archivo refleje lo que el usuario ve en pantalla (no una versión
        vieja del .env si aún no había pulsado Guardar).
        """
        self._persist_live_calibration()

        default_name = (
            f"calendario_calibracion_"
            f"{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            self.view, "Exportar calibración del calendario",
            default_name, "JSON (*.json)"
        )
        if not path:
            return
        try:
            settings = self.settings_model.get_settings()
            importexport.export_calendar_calibration_to_file(
                settings, path, app_version="v1.0.0"
            )
            QMessageBox.information(
                self.view, "Exportación exitosa",
                f"Calibración guardada en:\n{path}\n\n"
                "Puedes copiar este archivo a otra máquina y usar Importar "
                "para restaurar la configuración del calendario."
            )
        except Exception as e:
            log.error("Error exportando calibración: %s", e)
            QMessageBox.critical(
                self.view, "Error",
                f"No se pudo exportar la calibración:\n{e}"
            )

    def import_calibration(self):
        """Restaura la calibración del calendario desde un archivo JSON."""
        path, _ = QFileDialog.getOpenFileName(
            self.view, "Importar calibración del calendario", "",
            "JSON (*.json);;Todos los archivos (*)"
        )
        if not path:
            return
        try:
            data = importexport.import_calendar_calibration_from_file(path)
        except Exception as e:
            log.error("Error importando calibración: %s", e)
            QMessageBox.critical(
                self.view, "Error",
                f"No se pudo leer el archivo:\n{e}"
            )
            return

        exported_at = data.get("exported_at") or "fecha desconocida"
        confirm = QMessageBox.question(
            self.view, "Confirmar importación",
            f"Se reemplazará la calibración actual del calendario con la "
            f"del archivo (exportado el {exported_at}).\n\n"
            f"Escena: {data['scene'] or '(vacío)'}\n"
            f"Marcador: {data['source'] or '(vacío)'}\n"
            f"Plantilla activa: {data['template_weeks']}\n\n"
            "¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Persistir en .env primero — así get_settings() en refresh_view()
        # lee valores frescos y no depende del orden de los setValue de abajo.
        self.settings_model.save_calendar_settings(
            scene=data["scene"],
            source=data["source"],
            template_weeks=data["template_weeks"],
            per_template=data["per_template"],
        )

        # Reflejar en la UI sin disparar valueChanged (evitaría un ping-pong
        # con OBS por cada spin, y volvería a persistir uno por uno).
        self.view.input_scene_name.setText(data["scene"])
        self.view.input_source_name.setText(data["source"])
        idx = self.view.combo_template_weeks.findData(data["template_weeks"])
        if idx >= 0:
            self.view.combo_template_weeks.blockSignals(True)
            self.view.combo_template_weeks.setCurrentIndex(idx)
            self.view.combo_template_weeks.blockSignals(False)
        for key, block in data["per_template"].items():
            self._set_spin_silent(f"spin_x_start_{key}w", int(block["x_start"]))
            self._set_spin_silent(f"spin_x_space_{key}w", int(block["x_space"]))
            self._set_spin_silent(f"spin_y_start_{key}w", int(block["y_start"]))
            self._set_spin_silent(f"spin_y_space_{key}w", int(block["y_space"]))
            self._set_spin_silent(f"spin_scale_{key}w", int(block["scale"]))
            self._set_spin_silent(f"spin_dx_row0_{key}w", int(block.get("dx_row0", 0)))
            self._set_spin_silent(f"spin_dy_row0_{key}w", int(block.get("dy_row0", 0)))

        self._refresh_active_template_label()
        # Si OBS está conectado, aplicar la calibración importada al marcador.
        self._apply_live_calibration()

        log.info("Calibración importada desde %s", path)
        QMessageBox.information(
            self.view, "Importación completada",
            "La calibración del calendario se restauró correctamente."
        )

    # --- Selección de plantilla (4/5/6) según elección del usuario o auto ---
    def _selected_template_key_from_view(self):
        """Devuelve el valor del combobox como string: "auto"|"4"|"5"|"6"."""
        data = self.view.combo_template_weeks.currentData()
        return str(data) if data is not None else "auto"

    def _resolve_template_key(self, preference, target_date=None):
        """Resuelve la plantilla activa a "4", "5" o "6".

        `preference` viene del combobox ("auto"|"4"|"5"|"6") o de settings.
        Si es explícita se respeta; si es "auto", se deriva del número de
        filas que ocupa el mes en `target_date` (o el mes actual).
        """
        pref = str(preference).lower()
        if pref in ("4", "5", "6"):
            return pref
        weeks = self.model.weeks_in_month(target_date=target_date)
        if weeks <= 4:
            return "4"
        if weeks == 5:
            return "5"
        return "6"

    def _collect_template_from_view(self, key):
        """Devuelve el dict de calibración para la plantilla `key` leído de los spins."""
        return {
            "x_start": getattr(self.view, f"spin_x_start_{key}w").value(),
            "x_space": getattr(self.view, f"spin_x_space_{key}w").value(),
            "y_start": getattr(self.view, f"spin_y_start_{key}w").value(),
            "y_space": getattr(self.view, f"spin_y_space_{key}w").value(),
            "scale": getattr(self.view, f"spin_scale_{key}w").value(),
            "dx_row0": getattr(self.view, f"spin_dx_row0_{key}w").value(),
            "dy_row0": getattr(self.view, f"spin_dy_row0_{key}w").value(),
        }

    def _collect_all_templates_from_view(self):
        return {k: self._collect_template_from_view(k) for k in ("4", "5", "6")}

    def _active_calibration_from_settings(self, settings, target_date=None):
        """Devuelve la calibración completa
        (x_start, x_space, y_start, y_space, scale, dx_row0, dy_row0)
        de la plantilla activa según el combobox/settings."""
        key = self._resolve_template_key(
            settings.get("cal_template_weeks", "auto"), target_date
        )
        return (
            settings[f"cal_x_start_{key}w"],
            settings[f"cal_x_space_{key}w"],
            settings[f"cal_y_start_{key}w"],
            settings[f"cal_y_space_{key}w"],
            settings[f"cal_scale_{key}w"],
            settings.get(f"cal_dx_row0_{key}w", 0),
            settings.get(f"cal_dy_row0_{key}w", 0),
        )

    def _active_calibration_from_view(self, target_date=None):
        """Igual que la anterior, pero leyendo los spinboxes (para live tuning)."""
        key = self._resolve_template_key(
            self._selected_template_key_from_view(), target_date
        )
        block = self._collect_template_from_view(key)
        return (
            block["x_start"], block["x_space"],
            block["y_start"], block["y_space"],
            block["scale"],
            block["dx_row0"], block["dy_row0"],
        )

    def _refresh_active_template_label(self, target_date=None):
        """Actualiza la etiqueta "Actualmente activa: N semanas" bajo los paneles."""
        pref = self._selected_template_key_from_view()
        key = self._resolve_template_key(pref, target_date)
        origin = "según selección" if pref != "auto" else "auto según el mes"
        self.view.lbl_active_template.setText(
            f"Plantilla activa: {key} semanas ({origin}). "
            f"Los valores de calibración vienen del panel «Plantilla {key} semanas»."
        )

    def _on_template_changed(self):
        """Al cambiar la plantilla: refrescar etiqueta, recolocar el círculo y persistir."""
        self._refresh_active_template_label()
        self._apply_live_calibration()
        self._persist_live_calibration()

    def move_circle_to_today(self, show_messages=False, target_date=None):
        """Mueve el círculo al día indicado. Si `target_date` es None, usa hoy.

        La rotación de escenas siempre llama sin `target_date` para posicionar
        en la fecha real; `build_scene` lo usa para colocar el círculo en el
        día inicial elegido por el usuario durante la configuración.
        """
        if not self.obs_client.client:
            if show_messages: QMessageBox.warning(self.view, "Error", "Conecta OBS primero.")
            return False

        # 1. Leer configuración de la plantilla activa (per-plantilla completa).
        settings = self.settings_model.get_settings()
        x_start, x_space, y_start, y_space, scale_pct, dx_row0, dy_row0 = \
            self._active_calibration_from_settings(settings, target_date)
        scene_name = settings["cal_scene"]
        source_name = settings["cal_source"]

        # 2. Calcular coordenadas matemáticas
        x, y = self.model.calculate_position(
            x_start, y_start, x_space, y_space,
            target_date=target_date,
            dx_row0=dx_row0, dy_row0=dy_row0,
        )

        # 3. Enviar comando a OBS (incluyendo la escala)
        success = self.obs_client.move_scene_item(
            scene_name, source_name, x, y, scale_pct=scale_pct
        )

        if show_messages:
            if success:
                weeks = self.model.weeks_in_month(target_date=target_date)
                QMessageBox.information(
                    self.view, "Actualizado",
                    f"Círculo movido a X: {x}, Y: {y} y escalado a {scale_pct}%\n"
                    f"(calibración de {weeks} semanas)"
                )
            else:
                QMessageBox.critical(self.view, "Error", "No se pudo mover/escalar el círculo.")

        return success

    def read_position_from_obs(self):
        """Lee la posición actual del marcador en OBS y actualiza los spinboxes
        de la plantilla activa asumiendo que esa posición corresponde al
        "día de referencia" indicado en la vista.

        Modos:
        - "grid": recalcula X_START y Y_START (afecta todas las filas).
        - "row0": recalcula compensación fila 0 (solo aplicable si el día de
          referencia cae en fila 0).
        """
        if not self.obs_client.client:
            QMessageBox.warning(self.view, "Leer de OBS", "Conecta OBS primero.")
            return

        scene_name = self.view.input_scene_name.text().strip()
        source_name = self.view.input_source_name.text().strip()
        if not scene_name or not source_name:
            QMessageBox.warning(
                self.view, "Leer de OBS",
                "Configura los nombres de escena y marcador antes de leer.",
            )
            return

        tf = self.obs_client.get_scene_item_transform(scene_name, source_name)
        if tf is None:
            QMessageBox.critical(
                self.view, "Leer de OBS",
                f"No se pudo obtener la transform de «{source_name}» "
                f"en la escena «{scene_name}». ¿Existen en OBS?",
            )
            return

        obs_x = float(tf.get("positionX", 0))
        obs_y = float(tf.get("positionY", 0))
        scale_x = float(tf.get("scaleX", 1.0))
        scale_pct = max(1, min(500, int(round(scale_x * 100))))

        # Reconstruir el día de referencia con mes/año actuales.
        ref_day = self.view.spin_read_ref_day.value()
        today = datetime.date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        ref_day = max(1, min(ref_day, last_day))
        target_date = datetime.date(today.year, today.month, ref_day)

        # Calcular col y fila del día de referencia.
        first_weekday, _ = calendar.monthrange(target_date.year, target_date.month)
        start_col = (first_weekday + 1) % 7
        col = (start_col + (ref_day - 1)) % 7
        row = (start_col + (ref_day - 1)) // 7

        # Plantilla activa y valores actuales.
        active_key = self._resolve_template_key(
            self._selected_template_key_from_view(), target_date
        )
        current = self._collect_template_from_view(active_key)
        x_space = current["x_space"]
        y_space = current["y_space"]
        dx_row0 = current["dx_row0"]
        dy_row0 = current["dy_row0"]

        mode = self.view.combo_read_target.currentData()

        if mode == "row0":
            if row != 0:
                QMessageBox.warning(
                    self.view, "Leer de OBS",
                    f"El día {ref_day} está en la fila {row}. Para actualizar "
                    "«Comp. fila 0» elige un día que caiga en la fila 0 "
                    "(primera semana parcial).",
                )
                return
            # dx_row0 se define tal que:
            #   obs_x = X_START + col*ΔX + dx_row0
            new_dx = int(round(obs_x - current["x_start"] - col * x_space))
            new_dy = int(round(obs_y - current["y_start"]))  # row=0, sin ΔY
            self._set_spin_silent(f"spin_dx_row0_{active_key}w", new_dx)
            self._set_spin_silent(f"spin_dy_row0_{active_key}w", new_dy)
            summary = (
                f"Comp. X fila 0 = {new_dx} px\n"
                f"Comp. Y fila 0 = {new_dy} px\n"
                f"(escala no se toca en modo fila 0)"
            )
        else:
            # Modo "grid": recalcular X_START y Y_START asumiendo ΔX/ΔY correctos.
            # obs_x = X_START + col*ΔX + (dx_row0 si row==0)
            # obs_y = Y_START + row*ΔY + (dy_row0 si row==0)
            row0_dx = dx_row0 if row == 0 else 0
            row0_dy = dy_row0 if row == 0 else 0
            new_x_start = int(round(obs_x - col * x_space - row0_dx))
            new_y_start = int(round(obs_y - row * y_space - row0_dy))
            self._set_spin_silent(f"spin_x_start_{active_key}w", new_x_start)
            self._set_spin_silent(f"spin_y_start_{active_key}w", new_y_start)
            self._set_spin_silent(f"spin_scale_{active_key}w", scale_pct)
            summary = (
                f"X_START = {new_x_start} px\n"
                f"Y_START = {new_y_start} px\n"
                f"Escala = {scale_pct}%\n"
                f"(usando ΔX={x_space}, ΔY={y_space} de la plantilla {active_key}w)"
            )

        # Persistir todo (ya que setValue con blockSignals no dispara editingFinished).
        self._persist_live_calibration()

        log.info(
            "Leído de OBS: pos=(%.1f, %.1f) scale=%d%% → día %d (col=%d, row=%d, modo=%s)",
            obs_x, obs_y, scale_pct, ref_day, col, row, mode,
        )
        QMessageBox.information(
            self.view, "Leído de OBS",
            f"Marcador en OBS: ({obs_x:.0f}, {obs_y:.0f}), escala {scale_pct}%.\n"
            f"Día {ref_day} → col {col}, fila {row}. Plantilla activa: {active_key} semanas.\n\n"
            f"Actualizado:\n{summary}",
        )

    def _set_spin_silent(self, attr_name, value):
        """setValue sin disparar valueChanged (evita ping-pong con OBS)."""
        spin = getattr(self.view, attr_name)
        spin.blockSignals(True)
        spin.setValue(int(value))
        spin.blockSignals(False)

    def _apply_live_calibration(self):
        """Recalcula la posición del día de hoy con los valores actuales de los
        spins y actualiza el marcador en OBS. Silencioso: no muestra mensajes."""
        if not self.obs_client.client:
            return
        scene_name = self.view.input_scene_name.text().strip()
        source_name = self.view.input_source_name.text().strip()
        if not scene_name or not source_name:
            return
        x_start, x_space, y_start, y_space, scale_pct, dx_row0, dy_row0 = \
            self._active_calibration_from_view()
        x, y = self.model.calculate_position(
            x_start, y_start, x_space, y_space,
            dx_row0=dx_row0, dy_row0=dy_row0,
        )
        self.obs_client.move_scene_item(scene_name, source_name, x, y, scale_pct=scale_pct)

    def _persist_live_calibration(self):
        """Guarda los valores actuales de la calibración en .env. Silencioso."""
        self.settings_model.save_calendar_settings(
            scene=self.view.input_scene_name.text().strip(),
            source=self.view.input_source_name.text().strip(),
            template_weeks=self._selected_template_key_from_view(),
            per_template=self._collect_all_templates_from_view(),
        )

    # --- Simulación día por día (herramienta de verificación) ---
    def open_simulation_dialog(self):
        if self._sim_dialog is None:
            self._sim_dialog = CalendarSimulationDialog(parent=self.view)
            self._sim_dialog.simulation_started.connect(self._start_simulation)
            self._sim_dialog.simulation_stopped.connect(
                lambda: self._stop_simulation(restore_today=True, user_initiated=True)
            )
        # Pre-llenar mes/año desde el nombre de la escena (ej. "CUMPLEANOS DEL
        # MES ABRIL 2026" → Abril 2026). Evita que el usuario simule agosto
        # sobre una imagen de abril, que fue el bug reportado el 2026-08-18.
        scene_name = self.view.input_scene_name.text().strip()
        if scene_name:
            self._sim_dialog.prefill_from_scene_name(scene_name)
        self._sim_dialog.show()
        self._sim_dialog.raise_()
        self._sim_dialog.activateWindow()

    def _start_simulation(self, year, month, start_day, seconds_per_day):
        if not self.obs_client.client:
            QMessageBox.warning(self.view, "Simulación", "Conecta OBS primero.")
            if self._sim_dialog:
                self._sim_dialog.force_stop_state()
            return

        scene_name = self.view.input_scene_name.text().strip()
        source_name = self.view.input_source_name.text().strip()
        if not scene_name or not source_name:
            QMessageBox.warning(
                self.view, "Simulación",
                "Configura los nombres de escena y marcador antes de simular."
            )
            if self._sim_dialog:
                self._sim_dialog.force_stop_state()
            return

        last_day = calendar.monthrange(year, month)[1]
        self._sim_state = {
            "year": year,
            "month": month,
            "day": max(1, min(start_day, last_day)),
            "last_day": last_day,
            "seconds_per_day": seconds_per_day,
        }

        if self._sim_timer is None:
            self._sim_timer = QTimer(self.view)
            self._sim_timer.timeout.connect(self._advance_simulation)
        self._sim_timer.setInterval(seconds_per_day * 1000)

        log.info(
            "Iniciando simulación de calendario: %04d-%02d desde día %d, %ds/día",
            year, month, self._sim_state["day"], seconds_per_day,
        )
        # Mostrar el primer día inmediatamente y arrancar el timer para el siguiente.
        self._render_simulation_day()
        self._sim_timer.start()

    def _advance_simulation(self):
        if self._sim_state is None:
            return
        state = self._sim_state
        if state["day"] >= state["last_day"]:
            log.info("Simulación completada en %04d-%02d", state["year"], state["month"])
            self._stop_simulation(restore_today=True, user_initiated=False)
            if self._sim_dialog:
                self._sim_dialog.set_finished()
            return
        state["day"] += 1
        self._render_simulation_day()

    def _render_simulation_day(self):
        state = self._sim_state
        target_date = datetime.date(state["year"], state["month"], state["day"])

        # Leer calibración en vivo desde los spinboxes (permite live-tuning
        # mientras la simulación corre). La plantilla se resuelve honrando el
        # combobox: si el usuario eligió "5 semanas", todos los días simulados
        # usan la plantilla 5w aunque el mes real tenga 4 o 6.
        x_start, x_space, y_start, y_space, scale_pct, dx_row0, dy_row0 = \
            self._active_calibration_from_view(target_date=target_date)
        scene_name = self.view.input_scene_name.text().strip()
        source_name = self.view.input_source_name.text().strip()

        x, y = self.model.calculate_position(
            x_start, y_start, x_space, y_space,
            target_date=target_date,
            dx_row0=dx_row0, dy_row0=dy_row0,
        )
        self.obs_client.move_scene_item(scene_name, source_name, x, y, scale_pct=scale_pct)

        if self._sim_dialog:
            self._sim_dialog.set_progress(state["day"], state["last_day"], x, y)

    def _stop_simulation(self, restore_today=True, user_initiated=False):
        if self._sim_timer is not None and self._sim_timer.isActive():
            self._sim_timer.stop()
        was_running = self._sim_state is not None
        self._sim_state = None

        if user_initiated and self._sim_dialog:
            self._sim_dialog.force_stop_state()

        if was_running and restore_today and self.obs_client.client:
            try:
                self.move_circle_to_today(show_messages=False)
            except Exception as e:
                log.warning("No se pudo restaurar el círculo al día de hoy: %s", e)