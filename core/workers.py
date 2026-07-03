import logging
import time
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)


class OBSConnectionWorker(QThread):
    # Señales para comunicar el resultado a la UI
    connection_success = pyqtSignal(str)
    connection_error = pyqtSignal(str)

    def __init__(self, obs_client, host, port, password):
        super().__init__()
        self.obs_client = obs_client
        self.host = host
        self.port = port
        self.password = password

    def run(self):
        success, message = self.obs_client.connect(self.host, self.port, self.password)
        if success:
            self.connection_success.emit(message)
        else:
            self.connection_error.emit(message)


class OBSWatchdog(QThread):
    """Vigila la conexión con OBS.

    Cada `ping_interval` segundos hace una llamada ligera. Si detecta caída
    emite `connection_lost`, entra en modo reconexión con backoff exponencial
    (1, 2, 4, 8… hasta `max_backoff` segundos) y emite `connection_restored`
    cuando vuelve a responder.
    """

    connection_lost = pyqtSignal(str)
    connection_restored = pyqtSignal()
    reconnect_attempt = pyqtSignal(int)  # nº de intento

    def __init__(self, obs_client, settings_getter, ping_interval=10, max_backoff=60):
        super().__init__()
        self.obs_client = obs_client
        self.get_settings = settings_getter
        self.ping_interval = ping_interval
        self.max_backoff = max_backoff
        self._running = True
        self._connected_flag = False

    def mark_connected(self):
        """La UI notifica al watchdog que la conexión inicial fue exitosa."""
        self._connected_flag = True

    def stop(self):
        self._running = False

    def run(self):
        log.info("Watchdog OBS iniciado (ping %ds)", self.ping_interval)
        while self._running:
            time.sleep(self.ping_interval)
            if not self._running:
                break
            if not self._connected_flag:
                continue  # aún no ha habido primera conexión exitosa
            if not self._ping_ok():
                log.warning("Watchdog detectó caída de OBS. Iniciando reconexión.")
                self.connection_lost.emit("Se perdió la conexión con OBS")
                self._connected_flag = False
                self._reconnect_loop()

    def _ping_ok(self):
        """Ping ligero. False si detectamos caída."""
        if not self.obs_client.client:
            return False
        try:
            self.obs_client.client.get_version()
            return True
        except Exception as e:
            log.debug("Ping falló: %s", e)
            return False

    def _reconnect_loop(self):
        backoff = 1
        attempt = 0
        while self._running:
            attempt += 1
            self.reconnect_attempt.emit(attempt)
            log.info("Reconectando a OBS (intento %d, espera %ds)…", attempt, backoff)
            settings = self.get_settings()
            success, msg = self.obs_client.connect(
                settings["host"], int(settings["port"]), settings["password"]
            )
            if success:
                log.info("Reconexión exitosa tras %d intento(s).", attempt)
                self._connected_flag = True
                self.connection_restored.emit()
                return
            log.warning("Reconexión intento %d falló: %s", attempt, msg)
            time.sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff)
