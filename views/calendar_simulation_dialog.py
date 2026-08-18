import calendar
import datetime
import re
import unicodedata

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

MONTH_NAMES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

# Slug sin tildes / mayúsculas, para buscar mes en el nombre de la escena.
_MONTH_SLUGS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def _strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def parse_month_year_from_scene_name(scene_name, fallback_year=None):
    """Extrae (year, month) del nombre de una escena tipo 'CUMPLEANOS DEL MES ABRIL 2026'.

    Devuelve (year, month) si detecta ambos, o (None, None) si no.
    """
    if not scene_name:
        return None, None
    slug = _strip_accents(scene_name).lower()
    month = None
    for name, num in _MONTH_SLUGS.items():
        if re.search(rf"\b{name}\b", slug):
            month = num
            break
    year = None
    m = re.search(r"\b(20\d{2})\b", slug)
    if m:
        year = int(m.group(1))
    elif month is not None and fallback_year is not None:
        year = fallback_year
    if month is None:
        return None, None
    return year, month


class CalendarSimulationDialog(QDialog):
    """Diálogo no-modal para simular el avance del indicador de día.

    El diálogo NO habla con OBS: solo capta parámetros y emite señales.
    El CalendarController es quien mueve el círculo y llama a set_progress()
    / set_finished() para reflejar el estado.
    """

    simulation_started = pyqtSignal(int, int, int, int)  # year, month, start_day, seconds_per_day
    simulation_stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Simulación del indicador de día")
        self.setModal(False)
        self.setMinimumWidth(360)

        today = datetime.date.today()

        form = QFormLayout()

        self.combo_month = QComboBox()
        for i, name in enumerate(MONTH_NAMES_ES, start=1):
            self.combo_month.addItem(name, userData=i)
        self.combo_month.setCurrentIndex(today.month - 1)

        self.spin_year = QSpinBox()
        self.spin_year.setRange(2020, 2099)
        self.spin_year.setValue(today.year)

        self.spin_start_day = QSpinBox()
        self.spin_start_day.setRange(1, 31)
        self.spin_start_day.setValue(1)

        self.spin_seconds = QSpinBox()
        self.spin_seconds.setRange(1, 60)
        self.spin_seconds.setValue(10)
        self.spin_seconds.setSuffix(" s")

        form.addRow("Mes:", self.combo_month)
        form.addRow("Año:", self.spin_year)
        form.addRow("Día inicial:", self.spin_start_day)
        form.addRow("Duración por día:", self.spin_seconds)

        self.lbl_info = QLabel()
        self.lbl_info.setStyleSheet("color: #495057; font-size: 11px;")
        self.lbl_info.setWordWrap(True)

        self.lbl_status = QLabel("Detenido")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(
            "padding: 6px; background-color: #212529; color: #F8F9FA;"
            " border-radius: 4px; font-family: Consolas, monospace;"
        )

        self.lbl_countdown = QLabel("Siguiente día en: —")
        self.lbl_countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_countdown.setStyleSheet("color: #495057; font-size: 12px;")

        self.progress_countdown = QProgressBar()
        self.progress_countdown.setRange(0, 1)  # se reajusta al iniciar
        self.progress_countdown.setValue(0)
        self.progress_countdown.setTextVisible(False)
        self.progress_countdown.setFixedHeight(8)

        self.btn_start = QPushButton("▶️ Iniciar")
        self.btn_start.setStyleSheet("background-color: #198754;")
        self.btn_stop = QPushButton("⏹ Detener")
        self.btn_stop.setStyleSheet("background-color: #DC3545;")
        self.btn_stop.setEnabled(False)

        actions = QHBoxLayout()
        actions.addWidget(self.btn_start)
        actions.addWidget(self.btn_stop)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.lbl_info)
        root.addWidget(self.lbl_status)
        root.addWidget(self.lbl_countdown)
        root.addWidget(self.progress_countdown)
        root.addLayout(actions)
        root.addWidget(close_box)

        self.combo_month.currentIndexChanged.connect(self._refresh_month_meta)
        self.spin_year.valueChanged.connect(self._refresh_month_meta)
        self.btn_start.clicked.connect(self._emit_start)
        self.btn_stop.clicked.connect(self._emit_stop)

        # Countdown al siguiente día. Se reinicia cada vez que el controlador
        # llama a set_progress() con un día nuevo.
        self._seconds_per_day = 0
        self._countdown_remaining = 0
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)

        self._refresh_month_meta()

    # ---- public API called by controller ----

    def prefill_from_scene_name(self, scene_name):
        """Si el nombre de la escena menciona un mes (y opcionalmente año),
        pre-selecciona ese mes/año en el diálogo. Silencioso si no matchea."""
        year, month = parse_month_year_from_scene_name(
            scene_name, fallback_year=datetime.date.today().year
        )
        if month is None:
            return
        self.combo_month.setCurrentIndex(month - 1)
        if year is not None:
            self.spin_year.setValue(year)
        # Reset día inicial a 1 al cambiar de mes.
        self.spin_start_day.setValue(1)
        # _refresh_month_meta se llama por los signals de los widgets.

    def set_progress(self, day, total_days, x, y):
        self.lbl_status.setText(
            f"Día {day} de {total_days} — (x={x}, y={y})"
        )
        # Cada nuevo día resetea el contador; el timer del diálogo tickea
        # independiente del timer del controlador — hay ~1s de tolerancia.
        is_last = (day >= total_days)
        if is_last:
            self._stop_countdown()
            self.lbl_countdown.setText("Último día del mes")
            self.progress_countdown.setRange(0, 1)
            self.progress_countdown.setValue(1)
        else:
            self._restart_countdown()

    def set_finished(self):
        self.lbl_status.setText("✅ Simulación completada")
        self._stop_countdown()
        self.lbl_countdown.setText("—")
        self.progress_countdown.setValue(0)
        self._set_running(False)

    def force_stop_state(self):
        """Llamado por el controlador cuando el usuario detiene desde afuera
        (o cuando falla el arranque)."""
        self._stop_countdown()
        self.lbl_countdown.setText("Siguiente día en: —")
        self.progress_countdown.setValue(0)
        self._set_running(False)
        if not self.lbl_status.text().startswith("✅"):
            self.lbl_status.setText("Detenido")

    # ---- countdown internals ----

    def _restart_countdown(self):
        self._countdown_remaining = max(1, int(self._seconds_per_day))
        self.progress_countdown.setRange(0, self._countdown_remaining)
        self.progress_countdown.setValue(self._countdown_remaining)
        self.lbl_countdown.setText(
            f"Siguiente día en: {self._countdown_remaining}s"
        )
        self._countdown_timer.start()

    def _stop_countdown(self):
        if self._countdown_timer.isActive():
            self._countdown_timer.stop()

    def _tick_countdown(self):
        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
            return
        self._countdown_remaining -= 1
        self.progress_countdown.setValue(self._countdown_remaining)
        if self._countdown_remaining <= 0:
            # Esperamos a que el controlador llame set_progress() con el
            # siguiente día — hasta entonces mostramos "cambiando…".
            self.lbl_countdown.setText("Cambiando de día…")
            self._countdown_timer.stop()
        else:
            self.lbl_countdown.setText(
                f"Siguiente día en: {self._countdown_remaining}s"
            )

    # ---- internals ----

    def _selected_month(self):
        return int(self.combo_month.currentData())

    def _month_days(self, year, month):
        return calendar.monthrange(year, month)[1]

    def _month_weeks(self, year, month):
        first_weekday, ndays = calendar.monthrange(year, month)
        start_col = (first_weekday + 1) % 7  # domingo=0
        return (start_col + ndays + 6) // 7

    def _refresh_month_meta(self):
        year = self.spin_year.value()
        month = self._selected_month()
        ndays = self._month_days(year, month)
        weeks = self._month_weeks(year, month)

        self.spin_start_day.setMaximum(ndays)
        if self.spin_start_day.value() > ndays:
            self.spin_start_day.setValue(ndays)

        self.lbl_info.setText(
            f"{MONTH_NAMES_ES[month-1]} {year} — {ndays} días, "
            f"{weeks} semanas (plantilla {weeks}w)"
        )

    def _set_running(self, running):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.combo_month.setEnabled(not running)
        self.spin_year.setEnabled(not running)
        self.spin_start_day.setEnabled(not running)
        self.spin_seconds.setEnabled(not running)

    def _emit_start(self):
        year = self.spin_year.value()
        month = self._selected_month()
        start_day = self.spin_start_day.value()
        seconds = self.spin_seconds.value()
        self._seconds_per_day = seconds
        self._set_running(True)
        self.lbl_status.setText("Iniciando...")
        self.lbl_countdown.setText(f"Siguiente día en: {seconds}s")
        self.progress_countdown.setRange(0, seconds)
        self.progress_countdown.setValue(seconds)
        self.simulation_started.emit(year, month, start_day, seconds)

    def _emit_stop(self):
        self.simulation_stopped.emit()

    def closeEvent(self, event):
        # Si estaba corriendo, avisar al controlador para que apague el timer.
        if self.btn_stop.isEnabled():
            self.simulation_stopped.emit()
        super().closeEvent(event)
