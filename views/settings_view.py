from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QPushButton, QHBoxLayout, QCheckBox, QLabel,
                             QFileDialog, QMessageBox, QGroupBox)

from core import obs_launcher


class SettingsDialog(QDialog):
    # Emitida cuando el user hace click en "Instalar Autopilot" (AUT-3).
    # El controller la escucha y lanza el wizard con el OBSClient real.
    install_autopilot_requested = pyqtSignal()

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de Conexión OBS")
        self.setFixedSize(480, 460)

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

        # --- Autopilot (AUT-3) ---
        autopilot_group = QGroupBox("Autopilot — rotación 24/7")
        autopilot_layout = QVBoxLayout(autopilot_group)

        self.lbl_autopilot_status = QLabel(
            "Instalá el Autopilot en OBS para que la rotación siga "
            "funcionando aunque la app se cierre o la laptop se apague."
        )
        self.lbl_autopilot_status.setWordWrap(True)
        self.lbl_autopilot_status.setStyleSheet("color: #495057;")
        autopilot_layout.addWidget(self.lbl_autopilot_status)

        ap_row = QHBoxLayout()
        ap_row.addStretch(1)
        self.btn_install_autopilot = QPushButton("🚀 Instalar Autopilot en OBS")
        self.btn_install_autopilot.setToolTip(
            "Abre un asistente paso a paso para instalar el Autopilot "
            "en el servidor de OBS. Solo hay que hacerlo una vez."
        )
        ap_row.addWidget(self.btn_install_autopilot)
        autopilot_layout.addLayout(ap_row)

        layout.addWidget(autopilot_group)

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
        self.btn_install_autopilot.clicked.connect(
            self.install_autopilot_requested.emit
        )

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

    def set_autopilot_status(self, installed: bool, version: str | None = None) -> None:
        """Actualiza el label de estado del Autopilot en el dialog.

        installed: True si el script está detectado en OBS.
        version: número de versión reportado por el script (opcional).
        """
        if installed:
            v = f" (v{version})" if version else ""
            self.lbl_autopilot_status.setText(
                f"✓ Autopilot instalado y corriendo en OBS{v}.\n"
                "La rotación de escenas seguirá funcionando aunque cierres "
                "esta app."
            )
            self.lbl_autopilot_status.setStyleSheet("color: #198754;")
            self.btn_install_autopilot.setText("↻ Reinstalar / actualizar")
        else:
            self.lbl_autopilot_status.setText(
                "⚠ Autopilot no detectado. Sin él, si cerrás la app o "
                "apagás la laptop, la rotación se congela.\n"
                "Instalalo una sola vez con el asistente."
            )
            self.lbl_autopilot_status.setStyleSheet("color: #FD7E14;")
            self.btn_install_autopilot.setText("🚀 Instalar Autopilot en OBS")

    def get_inputs(self):
        return {
            "host": self.host_input.text(),
            "port": self.port_input.text(),
            "password": self.password_input.text(),
            "obs_exe_path": self.obs_exe_input.text().strip(),
            "obs_autolaunch": self.chk_autolaunch.isChecked(),
        }
