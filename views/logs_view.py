import os
import subprocess
from collections import deque

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QPlainTextEdit, QCheckBox)
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont

from core.logging_setup import get_log_file_path, get_logs_dir

MAX_LINES = 200
REFRESH_MS = 5000


class LogsView(QWidget):
    def __init__(self):
        super().__init__()
        self._log_path = get_log_file_path()
        self._logs_dir = get_logs_dir()

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.lbl_path = QLabel(f"Archivo: {self._log_path}")
        self.lbl_path.setStyleSheet("color: #6C757D;")
        top.addWidget(self.lbl_path, 1)

        self.chk_autorefresh = QCheckBox("Auto-refrescar cada 5s")
        self.chk_autorefresh.setChecked(True)
        self.chk_autorefresh.toggled.connect(self._toggle_autorefresh)
        top.addWidget(self.chk_autorefresh)

        self.btn_refresh = QPushButton("🔄 Refrescar")
        self.btn_refresh.clicked.connect(self.refresh_logs)
        top.addWidget(self.btn_refresh)

        self.btn_open_folder = QPushButton("📁 Abrir carpeta")
        self.btn_open_folder.clicked.connect(self._open_folder)
        top.addWidget(self.btn_open_folder)

        layout.addLayout(top)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.text.setFont(mono)
        layout.addWidget(self.text)

        self._timer = QTimer()
        self._timer.timeout.connect(self.refresh_logs)
        self._timer.start(REFRESH_MS)

        self.refresh_logs()

    def _toggle_autorefresh(self, enabled):
        if enabled:
            self._timer.start(REFRESH_MS)
        else:
            self._timer.stop()

    def refresh_logs(self):
        if not self._log_path.exists():
            self.text.setPlainText("(archivo de log aún no existe)")
            return
        try:
            with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
                # Últimas MAX_LINES líneas sin cargar el archivo entero en RAM
                tail = deque(f, maxlen=MAX_LINES)
            content = "".join(tail)
        except Exception as e:
            content = f"(no se pudo leer el archivo de log: {e})"
        # Preservar posición del scroll si el usuario estaba leyendo arriba
        scrollbar = self.text.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        self.text.setPlainText(content)
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _open_folder(self):
        path = str(self._logs_dir)
        try:
            os.startfile(path)  # Windows
        except AttributeError:
            subprocess.Popen(["xdg-open", path])
