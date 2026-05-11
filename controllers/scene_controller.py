from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QFileDialog
from datetime import datetime

class SceneController:
    def __init__(self, view, model, obs_client, settings_model, calendar_controller):
        self.view = view
        self.model = model
        self.obs_client = obs_client
        self.settings_model = settings_model
        self.calendar_controller = calendar_controller
        
        self.scenes_list = []
        self.current_index = 0
        
        # NUEVAS VARIABLES PARA EL CONTEO REGRESIVO
        self.time_left = 0
        self.active_scene_name = ""
        
        self.timer = QTimer()
        # Ahora el timer llamará a la función de cuenta regresiva
        self.timer.timeout.connect(self.update_countdown)

        self._connect_signals()
        self.refresh_table()
        self.update_date_label() # Mostrar la fecha al abrir la app

    def _connect_signals(self):
        self.view.btn_add.clicked.connect(self.add_scene)
        self.view.btn_delete.clicked.connect(self.delete_scene)
        self.view.btn_start.clicked.connect(self.start_rotation)
        self.view.btn_stop.clicked.connect(self.stop_rotation)
        self.view.btn_browse.clicked.connect(self.browse_file)

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
        file_path = self.view.input_file.text().strip()
        
        if not name:
            QMessageBox.warning(self.view, "Error", "El nombre de la escena no puede estar vacío.")
            return

        if file_path:
            if not self.obs_client.client:
                QMessageBox.warning(self.view, "Error", "Conecta OBS primero para poder crear la escena remota.")
                return
            success, msg = self.obs_client.create_scene_with_media(name, file_path)
            if not success:
                QMessageBox.critical(self.view, "Error de OBS", msg)
                return

        self.model.add_scene(name, duration)
        self.view.input_name.clear()
        self.view.input_file.clear()
        self.refresh_table()

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
                    print(f"Aviso OBS: {msg}") 
            
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
        self.view.btn_start.setEnabled(False)
        self.view.btn_stop.setEnabled(True)
        
        self.rotate_to_next_scene()

    def stop_rotation(self):
        self.timer.stop()
        self.view.btn_start.setEnabled(True)
        self.view.btn_stop.setEnabled(False)
        self.view.lbl_status.setText("Estado: Detenido")
        self.view.lbl_status.setStyleSheet("font-weight: bold; color: #DC3545;")

    def rotate_to_next_scene(self):
        self.update_date_label() # Refresca la fecha cada vez que cambia una escena
        
        scene = self.scenes_list[self.current_index]
        self.active_scene_name = scene["name"]
        
        cal_scene_name = self.settings_model.get_settings().get("cal_scene")
        if scene["name"] == cal_scene_name:
            self.calendar_controller.move_circle_to_today(show_messages=False)
        
        success = self.obs_client.change_scene(scene["name"])
        
        if success:
            self.time_left = scene["duration"]
            self.update_status_label()
            
            # Ahora el timer "hace tick" cada 1000 ms (1 segundo)
            self.timer.start(1000) 
            self.current_index = (self.current_index + 1) % len(self.scenes_list)
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