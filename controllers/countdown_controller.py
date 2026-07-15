from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox
import datetime
import logging

log = logging.getLogger(__name__)

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

    def _set_sync_ui(self, syncing):
        self.is_syncing = syncing
        if syncing:
            self.view.btn_toggle_sync.setText("⏹ Detener Sincronización")
            self.view.btn_toggle_sync.setStyleSheet("background-color: #DC3545;")
        else:
            self.view.btn_toggle_sync.setText("▶ Iniciar Sincronización")
            self.view.btn_toggle_sync.setStyleSheet("background-color: #198754;")

    def _stop_sync(self):
        self.timer.stop()
        self._set_sync_ui(False)

    def _required_source_names(self):
        """Nombres únicos y no vacíos de todos los text sources referenciados por los contadores."""
        names = set()
        for c in self.countdowns:
            for key in ("source_dias", "source_horas", "source_minutos", "source_segundos"):
                n = (c.get(key) or "").strip()
                if n:
                    names.add(n)
        return names

    def _preflight_check(self):
        """Verifica que todos los text sources referenciados existan en OBS.

        Devuelve True si todo OK. Si faltan, muestra dialog y devuelve False.
        Si no se pudo consultar OBS (list_input_names devolvió None), sigue
        adelante con un warning en log — no bloquea al usuario por un fallo
        transitorio del enum.
        """
        required = self._required_source_names()
        if not required:
            QMessageBox.warning(
                self.view, "Nada que sincronizar",
                "Ningún contador tiene fuentes OBS configuradas."
            )
            return False

        existing = self.obs_client.list_input_names()
        if existing is None:
            log.warning("Preflight: no se pudo enumerar inputs de OBS; se continúa sin validar.")
            return True

        missing = sorted(required - existing)
        if missing:
            QMessageBox.warning(
                self.view, "Fuentes faltantes en OBS",
                "Las siguientes fuentes de texto no existen en OBS:\n\n  • "
                + "\n  • ".join(missing)
                + "\n\nCréalas en OBS (Sources → +Text) con esos nombres exactos "
                "y vuelve a intentar."
            )
            return False
        return True

    def toggle_sync(self):
        if self.is_syncing:
            self._stop_sync()
            return

        if not self.obs_client.client:
            QMessageBox.warning(self.view, "Error", "Conecta OBS primero.")
            return

        if not self._preflight_check():
            return

        self.timer.start(1000)
        self._set_sync_ui(True)

    def process_countdowns(self):
        if not self.obs_client.client:
            log.warning("Sincronización de contadores detenida: OBS no está conectado.")
            self._stop_sync()
            return

        now = datetime.datetime.now()

        for c in self.countdowns:
            try:
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
            except Exception as e:
                log.error("Fallo procesando contador '%s': %s", c.get("nombre", "?"), e)