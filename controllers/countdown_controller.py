from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox
import datetime

class CountdownController:
    def __init__(self, view, model, obs_client):
        self.view = view
        self.model = model
        self.obs_client = obs_client
        
        self.countdowns = []
        self.is_syncing = False
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.process_countdowns)

        self._connect_signals()
        self.refresh_table()

    def _connect_signals(self):
        self.view.btn_add.clicked.connect(self.add_countdown)
        self.view.btn_delete.clicked.connect(self.delete_countdown)
        self.view.btn_toggle_sync.clicked.connect(self.toggle_sync)

    def refresh_table(self):
        self.countdowns = self.model.get_all_countdowns()
        self.view.populate_table(self.countdowns)

    def add_countdown(self):
        data = {
            "nombre": self.view.in_nombre.text().strip(),
            # ISO format para guardarlo seguro en SQLite
            "fecha_objetivo": self.view.in_fecha.dateTime().toPyDateTime().isoformat(),
            "source_dias": self.view.in_src_dias.text().strip(),
            "source_horas": self.view.in_src_horas.text().strip(),
            "source_minutos": self.view.in_src_mins.text().strip(),
            "source_segundos": self.view.in_src_secs.text().strip(),
            "repetir_anual": self.view.in_rep_anual.isChecked()
        }
        
        if not data["nombre"]:
            QMessageBox.warning(self.view, "Error", "El nombre es requerido.")
            return

        self.model.add_countdown(data)
        self.view.in_nombre.clear()
        self.refresh_table()

    def delete_countdown(self):
        selected_items = self.view.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            c_id = int(self.view.table.item(row, 0).text())
            self.model.delete_countdown(c_id)
            self.refresh_table()

    def toggle_sync(self):
        if not self.obs_client.client:
            QMessageBox.warning(self.view, "Error", "Conecta OBS primero.")
            return

        if self.is_syncing:
            self.timer.stop()
            self.is_syncing = False
            self.view.btn_toggle_sync.setText("▶ Iniciar Sincronización")
            self.view.btn_toggle_sync.setStyleSheet("background-color: #198754;")
        else:
            self.timer.start(1000) # Ejecutar cada 1 segundo
            self.is_syncing = True
            self.view.btn_toggle_sync.setText("⏹ Detener Sincronización")
            self.view.btn_toggle_sync.setStyleSheet("background-color: #DC3545;")

    def process_countdowns(self):
        if not self.obs_client.client:
            self.toggle_sync()
            return

        now = datetime.datetime.now()

        for c in self.countdowns:
            target = datetime.datetime.fromisoformat(c["fecha_objetivo"])
            
            # Lógica de repetición anual (Como el script Lua original)
            if now > target:
                if c["repetir_anual"]:
                    # Le sumamos un año a la fecha objetivo temporalmente para el cálculo
                    target = target.replace(year=now.year)
                    if now > target:
                        target = target.replace(year=now.year + 1)
                    diff = target - now
                else:
                    diff = datetime.timedelta(0) # Se queda en cero
            else:
                diff = target - now

            # Extracción de tiempo
            dias = diff.days
            horas, remainder = divmod(diff.seconds, 3600)
            minutos, segundos = divmod(remainder, 60)

            # Enviar por WebSocket a OBS formateando con ceros a la izquierda (ej: 09)
            if c["source_dias"]: self.obs_client.set_text_source_text(c["source_dias"], f"{dias:02d}")
            if c["source_horas"]: self.obs_client.set_text_source_text(c["source_horas"], f"{horas:02d}")
            if c["source_minutos"]: self.obs_client.set_text_source_text(c["source_minutos"], f"{minutos:02d}")
            if c["source_segundos"]: self.obs_client.set_text_source_text(c["source_segundos"], f"{segundos:02d}")