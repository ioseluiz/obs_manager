import logging
import time
import threading
from PyQt6.QtCore import QThread, pyqtSignal

from core import obs_launcher

log = logging.getLogger(__name__)


class OBSConnectionWorker(QThread):
    # Señales para comunicar el resultado a la UI
    connection_success = pyqtSignal(str)
    connection_error = pyqtSignal(str)

    def __init__(self, obs_client, host, port, password, timeout=5.0):
        super().__init__()
        self.obs_client = obs_client
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout

    def run(self):
        success, message = self.obs_client.connect(
            self.host, self.port, self.password, timeout=self.timeout,
        )
        if success:
            self.connection_success.emit(message)
        else:
            self.connection_error.emit(message)


class OBSProbeWorker(QThread):
    """Prueba una conexión con parámetros ad-hoc sin tocar el cliente productivo.

    Se usa desde el diálogo de Ajustes para validar credenciales antes de guardar.
    Nunca dispara auto-launch ni afecta la sesión activa.
    """

    finished_probe = pyqtSignal(bool, str)

    def __init__(self, host, port, password, timeout=3.0):
        super().__init__()
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout

    def run(self):
        # Import perezoso para no colgar arranque si obsws_python explota.
        import obsws_python as obs
        from core.obs_errors import friendly_error
        try:
            client = obs.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password,
                timeout=self.timeout,
            )
            try:
                client.get_version()
            finally:
                try:
                    client.disconnect()
                except Exception:
                    pass
            self.finished_probe.emit(True, "Conexión exitosa")
        except Exception as e:
            self.finished_probe.emit(
                False,
                friendly_error(f"{type(e).__name__}: {e}", self.host, self.port),
            )


class OBSLauncherWorker(QThread):
    """Lanza OBS y espera a que el WebSocket responda.

    Flujo:
      1. Ejecuta obs_launcher.launch_obs(exe_path).
      2. Poll de conexión hasta `timeout_seconds` (1 intento por segundo).
      3. Emite finished(True, msg) si conecta, o finished(False, msg) si falla.
    """

    launching = pyqtSignal()
    waiting_websocket = pyqtSignal(int)  # nº de intento
    finished_launch = pyqtSignal(bool, str)

    def __init__(self, obs_client, exe_path, host, port, password,
                 timeout_seconds=30, connect_timeout=2.0):
        super().__init__()
        self.obs_client = obs_client
        self.exe_path = exe_path
        self.host = host
        self.port = port
        self.password = password
        self.timeout_seconds = timeout_seconds
        self.connect_timeout = connect_timeout

    def run(self):
        self.launching.emit()
        ok, msg = obs_launcher.launch_obs(self.exe_path)
        if not ok:
            self.finished_launch.emit(False, f"No se pudo lanzar OBS: {msg}")
            return

        for attempt in range(1, self.timeout_seconds + 1):
            self.waiting_websocket.emit(attempt)
            success, conn_msg = self.obs_client.connect(
                self.host, self.port, self.password, timeout=self.connect_timeout,
            )
            if success:
                self.finished_launch.emit(True, "Conectado tras auto-launch")
                return
            time.sleep(1)

        self.finished_launch.emit(
            False,
            "OBS se lanzó pero el WebSocket no respondió en "
            f"{self.timeout_seconds} segundos.\n"
            "Verifica que WebSocket esté habilitado en Herramientas → "
            "WebSocket Server Settings."
        )


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
        self._suspended = False
        self._reconnect_lock = threading.RLock()
        self._generation = 0

    def mark_connected(self):
        """La UI notifica al watchdog que la conexión inicial fue exitosa."""
        with self._reconnect_lock:
            self._generation += 1
            self._suspended = False
            self._connected_flag = True

    def suspend(self):
        """Una desconexión manual no debe disparar reconexión automática."""
        with self._reconnect_lock:
            self._generation += 1
            self._suspended = True
            self._connected_flag = False

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
                if self._suspended:
                    continue
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
        generation = self._generation
        while self._running:
            # Cancelar también intentos dormidos si hubo desconexión manual
            # seguida de una nueva conexión antes de terminar el backoff.
            with self._reconnect_lock:
                if self._suspended or generation != self._generation:
                    return
                attempt += 1
                self.reconnect_attempt.emit(attempt)
                log.info("Reconectando a OBS (intento %d, espera %ds)…", attempt, backoff)
                settings = self.get_settings()
                success, msg = self.obs_client.connect(
                    settings["host"], int(settings["port"]), settings["password"],
                    timeout=3.0,
                )
                if self._suspended:
                    self.obs_client.disconnect()
                    return
                if success:
                    log.info("Reconexión exitosa tras %d intento(s).", attempt)
                    self._connected_flag = True
                    self.connection_restored.emit()
                    return
                log.warning("Reconexión intento %d falló: %s", attempt, msg)
            time.sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff)
