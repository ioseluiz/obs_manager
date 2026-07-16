from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
                             QTimeEdit, QLabel)
from PyQt6.QtCore import QTime

DAY_LABELS = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do"]
ALL_DAYS_MASK = 127


class ScheduleWidget(QWidget):
    """Bloque de programación reutilizable: días de la semana + ventana horaria opcional.

    Bitmask de días: bit 0=Lu, bit 1=Ma, ..., bit 6=Do. 127 = todos.
    Horario en formato "HH:MM" o None para sin restricción.
    Soporta ventanas que cruzan la medianoche (start > end).
    """

    def __init__(self, days_mask=ALL_DAYS_MASK, time_start=None, time_end=None):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        days_row = QHBoxLayout()
        days_row.addWidget(QLabel("Días activos:"))
        self._day_checks = []
        for i, name in enumerate(DAY_LABELS):
            chk = QCheckBox(name)
            chk.setChecked(bool(days_mask & (1 << i)))
            days_row.addWidget(chk)
            self._day_checks.append(chk)
        days_row.addStretch()
        outer.addLayout(days_row)

        time_row = QHBoxLayout()
        self.chk_time_window = QCheckBox("Solo entre horas:")
        self.time_start = QTimeEdit()
        self.time_start.setDisplayFormat("HH:mm")
        self.time_end = QTimeEdit()
        self.time_end.setDisplayFormat("HH:mm")

        has_window = bool(time_start and time_end)
        self.chk_time_window.setChecked(has_window)
        if has_window:
            self.time_start.setTime(QTime.fromString(time_start, "HH:mm"))
            self.time_end.setTime(QTime.fromString(time_end, "HH:mm"))
        else:
            self.time_start.setTime(QTime(8, 0))
            self.time_end.setTime(QTime(18, 0))
        self.time_start.setEnabled(has_window)
        self.time_end.setEnabled(has_window)
        self.chk_time_window.toggled.connect(self.time_start.setEnabled)
        self.chk_time_window.toggled.connect(self.time_end.setEnabled)

        time_row.addWidget(self.chk_time_window)
        time_row.addWidget(self.time_start)
        time_row.addWidget(QLabel("a"))
        time_row.addWidget(self.time_end)
        time_row.addStretch()
        outer.addLayout(time_row)

    def get_values(self):
        mask = 0
        for i, chk in enumerate(self._day_checks):
            if chk.isChecked():
                mask |= (1 << i)
        if self.chk_time_window.isChecked():
            ts = self.time_start.time().toString("HH:mm")
            te = self.time_end.time().toString("HH:mm")
        else:
            ts, te = None, None
        return {"active_days": mask, "active_time_start": ts, "active_time_end": te}


def format_schedule_summary(active_days, time_start, time_end):
    """Devuelve un resumen conciso para mostrar en la tabla.

    Ejemplos: 'Siempre', 'L-V', 'S-D 08:00-14:00', 'LMV 09:00-11:30'
    """
    days_mask = active_days if active_days is not None else ALL_DAYS_MASK
    is_all_days = days_mask == ALL_DAYS_MASK
    no_time = not time_start or not time_end
    if is_all_days and no_time:
        return "Siempre"

    # Compactar días. Usar L,M,X,J,V,S,D estilo español para menos ancho.
    short = ["L", "M", "X", "J", "V", "S", "D"]
    active = [short[i] for i in range(7) if days_mask & (1 << i)]
    days_str = "".join(active) if active else "—"

    # Rangos comunes
    if days_str == "LMXJV":
        days_str = "L-V"
    elif days_str == "LMXJVSD":
        days_str = "Todos"
    elif days_str == "SD":
        days_str = "S-D"

    if no_time:
        return days_str
    return f"{days_str} {time_start}-{time_end}"


def is_scene_active_now(scene, now):
    """Evalúa si una escena debe estar activa en el instante `now` (datetime).

    Bitmask: bit 0 = Lunes (weekday()==0), ..., bit 6 = Domingo.
    Ventana horaria: soporta cruzar medianoche (start > end).
    """
    mask = scene.get("active_days")
    if mask is None:
        mask = ALL_DAYS_MASK
    if not (mask & (1 << now.weekday())):
        return False

    ts = scene.get("active_time_start")
    te = scene.get("active_time_end")
    if not ts or not te:
        return True

    def _parse(s):
        h, m = s.split(":")
        return int(h) * 60 + int(m)

    try:
        start = _parse(ts)
        end = _parse(te)
    except Exception:
        return True

    now_min = now.hour * 60 + now.minute
    if start <= end:
        return start <= now_min <= end
    # Ventana cruza medianoche
    return now_min >= start or now_min <= end
