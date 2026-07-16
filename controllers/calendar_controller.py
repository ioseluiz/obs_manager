import logging
from PyQt6.QtWidgets import QMessageBox, QFileDialog

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

        self._connect_signals()

    def _connect_signals(self):
        self.view.btn_save.clicked.connect(self.save_settings)
        self.view.btn_test.clicked.connect(lambda: self.move_circle_to_today(show_messages=True))

        # Nuevas conexiones
        self.view.btn_browse_bg.clicked.connect(self.browse_bg)
        self.view.btn_browse_circle.clicked.connect(self.browse_circle)
        self.view.btn_build_scene.clicked.connect(self.build_scene)

        # Live tuning: cada cambio en los spins mueve el marcador en OBS al vuelo;
        # al terminar la edición (Enter o perder foco) se persiste en .env.
        spin_widgets = (
            self.view.spin_x_start, self.view.spin_y_start,
            self.view.spin_x_space, self.view.spin_y_space,
            self.view.spin_scale,
        )
        for w in spin_widgets:
            w.valueChanged.connect(self._apply_live_calibration)
            w.editingFinished.connect(self._persist_live_calibration)
        # Los nombres de escena/marcador solo persisten al terminar edición.
        self.view.input_scene_name.editingFinished.connect(self._persist_live_calibration)
        self.view.input_source_name.editingFinished.connect(self._persist_live_calibration)

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
        x_space = self.view.spin_x_space.value() # Usamos el ΔX de la calibración

        if not all([scene_name, circle_name, bg_path, circle_path]):
            QMessageBox.warning(self.view, "Faltan datos", "Selecciona todos los archivos.")
            return

        success, msg = self.obs_client.build_calendar_scene(
            scene_name, bg_path, circle_path, circle_name, x_space
        )

        if success:
            # Una vez construido con auto-escala, movemos a la posición de hoy
            self.move_circle_to_today(show_messages=False)
            # Registrar la escena en la BD del rotador para que aparezca en la lista
            self._persist_calendar_scene(scene_name)
            if self.on_scene_created:
                self.on_scene_created()
            QMessageBox.information(self.view, "Éxito", "Calendario configurado automáticamente.")
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
            self.view.input_scene_name.text(),
            self.view.input_source_name.text(),
            self.view.spin_x_start.value(),
            self.view.spin_y_start.value(),
            self.view.spin_x_space.value(),
            self.view.spin_y_space.value(),
            self.view.spin_scale.value()
        )
        QMessageBox.information(self.view, "Éxito", "Calibración del calendario guardada en .env")

    def move_circle_to_today(self, show_messages=False):
        if not self.obs_client.client:
            if show_messages: QMessageBox.warning(self.view, "Error", "Conecta OBS primero.")
            return False

        # 1. Leer configuración
        settings = self.settings_model.get_settings()
        x_start = settings["cal_x_start"]
        y_start = settings["cal_y_start"]
        x_space = settings["cal_x_space"]
        y_space = settings["cal_y_space"]
        scene_name = settings["cal_scene"]
        source_name = settings["cal_source"]

        # 2. Calcular coordenadas matemáticas
        x, y = self.model.calculate_position(x_start, y_start, x_space, y_space)

        # 3. Enviar comando a OBS (incluyendo la escala)
        success = self.obs_client.move_scene_item(
            scene_name, source_name, x, y, scale_pct=settings["cal_scale"]
        )

        if show_messages:
            if success:
                QMessageBox.information(self.view, "Actualizado", f"Círculo movido a X: {x}, Y: {y} y escalado a {settings['cal_scale']}%")
            else:
                QMessageBox.critical(self.view, "Error", "No se pudo mover/escalar el círculo.")

        return success

    def _apply_live_calibration(self):
        """Recalcula la posición del día de hoy con los valores actuales de los
        spins y actualiza el marcador en OBS. Silencioso: no muestra mensajes."""
        if not self.obs_client.client:
            return
        scene_name = self.view.input_scene_name.text().strip()
        source_name = self.view.input_source_name.text().strip()
        if not scene_name or not source_name:
            return
        x_start = self.view.spin_x_start.value()
        y_start = self.view.spin_y_start.value()
        x_space = self.view.spin_x_space.value()
        y_space = self.view.spin_y_space.value()
        scale_pct = self.view.spin_scale.value()
        x, y = self.model.calculate_position(x_start, y_start, x_space, y_space)
        self.obs_client.move_scene_item(scene_name, source_name, x, y, scale_pct=scale_pct)

    def _persist_live_calibration(self):
        """Guarda los valores actuales de la calibración en .env. Silencioso."""
        self.settings_model.save_calendar_settings(
            self.view.input_scene_name.text().strip(),
            self.view.input_source_name.text().strip(),
            self.view.spin_x_start.value(),
            self.view.spin_y_start.value(),
            self.view.spin_x_space.value(),
            self.view.spin_y_space.value(),
            self.view.spin_scale.value(),
        )