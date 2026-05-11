from PyQt6.QtWidgets import QMessageBox, QFileDialog

class CalendarController:
    def __init__(self, view, model, settings_model, obs_client):
        self.view = view
        self.model = model
        self.settings_model = settings_model
        self.obs_client = obs_client

        self._connect_signals()

    def _connect_signals(self):
        self.view.btn_save.clicked.connect(self.save_settings)
        self.view.btn_test.clicked.connect(lambda: self.move_circle_to_today(show_messages=True))
        
        # Nuevas conexiones
        self.view.btn_browse_bg.clicked.connect(self.browse_bg)
        self.view.btn_browse_circle.clicked.connect(self.browse_circle)
        self.view.btn_build_scene.clicked.connect(self.build_scene)

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
            QMessageBox.information(self.view, "Éxito", "Calendario configurado automáticamente.")
        else:
            QMessageBox.critical(self.view, "Error", msg)

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
        
        # Convertimos el porcentaje (ej. 50%) a decimal (ej. 0.5) para OBS
        scale_decimal = settings["cal_scale"] / 100.0 

        # 2. Calcular coordenadas matemáticas
        x, y = self.model.calculate_position(x_start, y_start, x_space, y_space)

        # 3. Enviar comando a OBS (ahora con la escala incluida)
        success = self.obs_client.move_scene_item(scene_name, source_name, x, y)

        if show_messages:
            if success:
                QMessageBox.information(self.view, "Actualizado", f"Círculo movido a X: {x}, Y: {y} y escalado a {settings['cal_scale']}%")
            else:
                QMessageBox.critical(self.view, "Error", "No se pudo mover/escalar el círculo.")
                
        return success