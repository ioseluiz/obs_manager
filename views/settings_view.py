from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QPushButton, QHBoxLayout, QCheckBox, QLabel,
                             QFileDialog, QMessageBox, QGroupBox)

from core import obs_launcher


class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None, recording_enabled=False):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de Conexión OBS")
        self.setFixedSize(480, 440)

        layout = QVBoxLayout(self)

        # --- Conexión WebSocket ---
        conn_group = QGroupBox("Conexión WebSocket")
        form_layout = QFormLayout(conn_group)

        self.host_input = QLineEdit(current_settings.get("host", ""))
        self.port_input = QLineEdit(str(current_settings.get("port", "")))
        self.password_input = QLineEdit(current_settings.get("password", ""))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout.addRow("Host:", self.host_input)
        form_layout.addRow("Puerto:", self.port_input)
        form_layout.addRow("Contraseña:", self.password_input)
        layout.addWidget(conn_group)

        # --- Lanzamiento automático de OBS ---
        launch_group = QGroupBox("Lanzamiento automático")
        launch_layout = QVBoxLayout(launch_group)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Ruta obs64.exe:"))
        self.obs_exe_input = QLineEdit(current_settings.get("obs_exe_path", ""))
        self.obs_exe_input.setPlaceholderText("Vacío = autodetectar en runtime")
        path_row.addWidget(self.obs_exe_input, 1)
        launch_layout.addLayout(path_row)

        btn_row = QHBoxLayout()
        self.btn_detect = QPushButton("Autodetectar")
        self.btn_browse = QPushButton("Examinar…")
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_detect)
        btn_row.addWidget(self.btn_browse)
        launch_layout.addLayout(btn_row)

        self.chk_autolaunch = QCheckBox(
            "Abrir OBS automáticamente si no está corriendo"
        )
        self.chk_autolaunch.setChecked(bool(current_settings.get("obs_autolaunch", True)))
        launch_layout.addWidget(self.chk_autolaunch)

        layout.addWidget(launch_group)

        # --- Grabación (opt-in, sin persistencia) ---
        rec_group = QGroupBox("Grabación")
        rec_layout = QVBoxLayout(rec_group)
        self.chk_recording = QCheckBox("Habilitar grabación a archivo")
        self.chk_recording.setChecked(bool(recording_enabled))
        rec_layout.addWidget(self.chk_recording)
        rec_hint = QLabel(
            "Se restablece al abrir la app. La grabación se hace en el disco "
            "configurado en OBS."
        )
        rec_hint.setStyleSheet("color: #6C757D; font-size: 11px;")
        rec_hint.setWordWrap(True)
        rec_layout.addWidget(rec_hint)
        layout.addWidget(rec_group)

        # --- Botones inferiores ---
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Guardar y Conectar")
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setStyleSheet("background-color: #6C757D;")
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

        # Conexiones
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self.accept)
        self.btn_detect.clicked.connect(self._on_detect)
        self.btn_browse.clicked.connect(self._on_browse)

    def _on_detect(self):
        path = obs_launcher.find_obs_executable()
        if path:
            self.obs_exe_input.setText(path)
        else:
            QMessageBox.information(
                self, "Autodetección",
                "No se encontró OBS Studio automáticamente.\n"
                "Usa 'Examinar…' para seleccionar obs64.exe manualmente."
            )

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona obs64.exe", "",
            "Ejecutable OBS (obs64.exe);;Todos los archivos (*.*)"
        )
        if path:
            self.obs_exe_input.setText(path)

    def get_inputs(self):
        return {
            "host": self.host_input.text(),
            "port": self.port_input.text(),
            "password": self.password_input.text(),
            "obs_exe_path": self.obs_exe_input.text().strip(),
            "obs_autolaunch": self.chk_autolaunch.isChecked(),
            "recording_enabled": self.chk_recording.isChecked(),
        }
