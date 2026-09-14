from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QPushButton, QHBoxLayout, QCheckBox, QLabel,
                             QFileDialog, QMessageBox, QGroupBox)

from core import obs_launcher


class SettingsDialog(QDialog):
    # Emitida al pulsar "Probar conexión". El controller la usa para lanzar
    # un OBSProbeWorker con un cliente desechable (no toca la sesión activa).
    test_connection_requested = pyqtSignal(dict)
    # Emitida al pulsar "Re-calibrar este equipo" (Fase 2e).
    recalibrate_requested = pyqtSignal()

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de Conexión OBS")
        self.setFixedSize(520, 560)

        layout = QVBoxLayout(self)

        # --- Conexión WebSocket ---
        conn_group = QGroupBox("Conexión WebSocket")
        conn_layout = QVBoxLayout(conn_group)
        form_layout = QFormLayout()

        self.host_input = QLineEdit(current_settings.get("host", ""))
        self.host_input.setPlaceholderText(
            "localhost o IP del equipo con OBS (ej. 192.168.1.42)"
        )
        self.port_input = QLineEdit(str(current_settings.get("port", "")))
        self.password_input = QLineEdit(current_settings.get("password", ""))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout.addRow("Host / IP:", self.host_input)
        form_layout.addRow("Puerto:", self.port_input)
        form_layout.addRow("Contraseña:", self.password_input)
        conn_layout.addLayout(form_layout)

        # Botón Probar Conexión + label de estado
        probe_row = QHBoxLayout()
        self.btn_test = QPushButton("Probar conexión")
        self.lbl_test_status = QLabel("")
        self.lbl_test_status.setWordWrap(True)
        probe_row.addWidget(self.btn_test)
        probe_row.addWidget(self.lbl_test_status, 1)
        conn_layout.addLayout(probe_row)

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

        # --- Calibración de capacidad (Fase 2e) ---
        cal_group = QGroupBox("Calibración de capacidad (Fase 2)")
        cal_layout = QVBoxLayout(cal_group)

        self.lbl_cal_status = QLabel("Sin datos de calibración.")
        self.lbl_cal_status.setWordWrap(True)
        self.lbl_cal_status.setStyleSheet("color: #495057;")
        cal_layout.addWidget(self.lbl_cal_status)

        cal_row = QHBoxLayout()
        cal_row.addStretch(1)
        self.btn_recalibrate = QPushButton("🔬 Re-calibrar este equipo")
        self.btn_recalibrate.setToolTip(
            "Corre la calibración automática: mide cuántos canales UDP "
            "simultáneos aguanta cada encoder en este equipo. "
            "Toma ~60 segundos por encoder."
        )
        cal_row.addWidget(self.btn_recalibrate)
        cal_layout.addLayout(cal_row)

        layout.addWidget(cal_group)

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
        self.btn_test.clicked.connect(self._on_test_clicked)
        self.btn_recalibrate.clicked.connect(self.recalibrate_requested.emit)

    def _on_test_clicked(self):
        self.test_connection_requested.emit({
            "host": self.host_input.text().strip(),
            "port": self.port_input.text().strip(),
            "password": self.password_input.text(),
        })

    def set_test_pending(self):
        """Estado 'Probando…' mientras el probe worker corre."""
        self.btn_test.setEnabled(False)
        self.lbl_test_status.setStyleSheet("color: #6C757D;")
        self.lbl_test_status.setText("Probando…")

    def set_test_result(self, success: bool, message: str):
        """Slot que recibe el resultado del OBSProbeWorker."""
        self.btn_test.setEnabled(True)
        if success:
            self.lbl_test_status.setStyleSheet("color: #198754; font-weight: bold;")
            self.lbl_test_status.setText(f"✓ {message}")
        else:
            self.lbl_test_status.setStyleSheet("color: #DC3545;")
            self.lbl_test_status.setText(f"✗ {message}")

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

    def set_calibration_status(self, entry) -> None:
        """Actualiza el label de calibración con la info del CapacityEntry.

        entry: CapacityEntry para el fingerprint actual, o None si no hay.
        """
        if entry is None:
            self.lbl_cal_status.setStyleSheet("color: #FD7E14;")
            self.lbl_cal_status.setText(
                "⚠ Este equipo aún no fue calibrado. Se recomienda "
                "calibrar antes de configurar canales multi-salida."
            )
            return
        if not entry.encoders:
            self.lbl_cal_status.setStyleSheet("color: #FD7E14;")
            self.lbl_cal_status.setText(
                f"⚠ Calibración presente pero sin encoders medidos "
                f"({entry.notes or 'sin detalle'})."
            )
            return
        # Formato: "Última: 2026-09-14 · x264=2, qsv=3"
        fecha = entry.calibrated_at[:10] if entry.calibrated_at else "?"
        encs = ", ".join(f"{k}={v}" for k, v in sorted(entry.encoders.items()))
        note_suffix = f"  ({entry.notes})" if entry.notes else ""
        self.lbl_cal_status.setStyleSheet("color: #198754;")
        self.lbl_cal_status.setText(
            f"✓ Calibrado el {fecha} · Capacidad (1080p30): {encs}{note_suffix}"
        )

    def get_inputs(self):
        return {
            "host": self.host_input.text(),
            "port": self.port_input.text(),
            "password": self.password_input.text(),
            "obs_exe_path": self.obs_exe_input.text().strip(),
            "obs_autolaunch": self.chk_autolaunch.isChecked(),
        }
