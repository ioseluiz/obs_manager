import logging
from PyQt6.QtCore import (QObject, QThread, QTimer, pyqtSignal, pyqtSlot,
                          QMetaObject, Qt, Q_ARG)
from PyQt6.QtGui import QPixmap

log = logging.getLogger(__name__)


class ScenePreviewWorker(QObject):
    """Polling worker que toma screenshots de una escena de OBS a N FPS y emite
    QPixmap listos para pintar.

    Vive en su propio QThread (dedicado al preview) para no bloquear la UI
    con requests WebSocket que pueden tardar 30-100ms. Read-only: no afecta
    la rotación ni el output live de OBS.

    Thread-safety: los slots públicos (start/stop/set_fps/set_target) deben
    invocarse vía QMetaObject.invokeMethod desde otros threads — usa el
    wrapper PreviewThread abajo.
    """

    frame_ready = pyqtSignal(QPixmap)
    transform_updated = pyqtSignal(dict)
    error = pyqtSignal(str)

    # Cada cuántos ticks refrescamos el transform (mucho más lento que el frame)
    _TRANSFORM_EVERY_N_TICKS = 3

    def __init__(self, obs_client, scene_name, source_name=None,
                 fps=3, snap_width=960, snap_height=540):
        super().__init__()
        self._obs = obs_client
        self._scene = scene_name
        self._source = source_name
        self._fps = max(1, min(15, int(fps)))
        self._snap_w = snap_width
        self._snap_h = snap_height
        self._tick_count = 0
        self._timer = None  # QTimer se crea en start() dentro del thread destino

    @pyqtSlot()
    def start(self):
        """Crea e inicia el timer. Se ejecuta EN el thread del worker vía
        QThread.started signal (Queued por default)."""
        if self._timer is None:
            # El QTimer se crea sin parent para vivir en el thread actual (worker)
            self._timer = QTimer()
            self._timer.timeout.connect(self._tick)
        self._timer.start(int(1000 / self._fps))
        log.debug("PreviewWorker iniciado @ %d FPS para escena '%s'",
                  self._fps, self._scene)

    @pyqtSlot()
    def stop(self):
        """Detiene el timer. Debe ejecutarse EN el thread del worker — usar
        BlockingQueuedConnection desde otros threads."""
        if self._timer is not None:
            self._timer.stop()

    @pyqtSlot(int)
    def set_fps(self, fps):
        self._fps = max(1, min(15, int(fps)))
        if self._timer and self._timer.isActive():
            self._timer.setInterval(int(1000 / self._fps))

    @pyqtSlot(str, str)
    def set_target(self, scene_name, source_name):
        """Cambio de escena/source en caliente (útil en modo flotante)."""
        self._scene = scene_name
        self._source = source_name or None
        self._tick_count = 0  # fuerza refresh de transform en el próximo tick

    def _tick(self):
        # Guard-all: cualquier excepción en el thread del worker es silenciosa
        # (sys.excepthook solo aplica al main thread). Un raise aquí abortaría
        # el worker y podría afectar la limpieza del QThread.
        try:
            self._do_tick()
        except Exception as e:
            log.debug("PreviewWorker _tick error: %s", e)

    def _do_tick(self):
        if not self._scene:
            return
        # Screenshot de la escena completa (compuesto con transforms aplicados).
        # OBSClient.get_scene_screenshot_bytes ya serializa con lock.
        data = self._obs.get_scene_screenshot_bytes(
            self._scene, self._snap_w, self._snap_h, "jpg", 75
        )
        if data:
            pix = QPixmap()
            if pix.loadFromData(data):
                self.frame_ready.emit(pix)

        # Transform del source (menos frecuente — no cambia en cada frame)
        self._tick_count += 1
        if self._source and (self._tick_count % self._TRANSFORM_EVERY_N_TICKS == 0):
            tf = self._obs.get_scene_item_transform(self._scene, self._source)
            if tf:
                self.transform_updated.emit(tf)


class PreviewThread:
    """Manager que empaqueta un QThread + ScenePreviewWorker y expone start/stop
    limpios y thread-safe. Simplifica el uso desde views/dialogs.

    Uso típico:
        pt = PreviewThread(obs_client, "MI_ESCENA", "MI_ESCENA_Contenido")
        pt.worker.frame_ready.connect(preview_widget.set_pixmap)
        pt.worker.transform_updated.connect(preview_widget.update_coverage)
        pt.start()
        ...
        pt.stop()  # al cerrar el diálogo
    """

    def __init__(self, obs_client, scene_name, source_name=None, fps=3):
        self.thread = QThread()
        self.worker = ScenePreviewWorker(obs_client, scene_name, source_name, fps)
        self.worker.moveToThread(self.thread)
        # Al arrancar el thread, invocamos worker.start() dentro de ese thread
        self.thread.started.connect(self.worker.start)
        # Cleanup limpio: cuando el thread termina, borra el worker.
        # No agregamos thread.finished → thread.deleteLater porque el
        # wrapper todavía puede tener referencia y borrarlo dos veces crashea.
        self.thread.finished.connect(self.worker.deleteLater)
        self._stopped = False

    def start(self):
        if not self.thread.isRunning() and not self._stopped:
            self.thread.start()

    def stop(self):
        """Detiene el worker y espera a que el thread termine. Idempotente y
        seguro llamar desde cualquier thread. Usa BlockingQueuedConnection
        para asegurar que el QTimer se apague EN el thread del worker antes
        de emitir quit()."""
        if self._stopped:
            return
        self._stopped = True
        try:
            if self.thread.isRunning():
                # Detener timer en el thread del worker (blocking → sincrónico)
                try:
                    QMetaObject.invokeMethod(
                        self.worker, "stop",
                        Qt.ConnectionType.BlockingQueuedConnection
                    )
                except Exception as e:
                    log.debug("invokeMethod stop falló: %s", e)
                self.thread.quit()
                if not self.thread.wait(3000):
                    log.warning("PreviewThread no terminó en 3s; forzando terminate")
                    self.thread.terminate()
                    self.thread.wait(1000)
        except Exception as e:
            log.debug("PreviewThread.stop error: %s", e)

    def set_target(self, scene_name, source_name):
        """Delegado thread-safe: el slot vive en el worker (otro thread), Qt lo
        despacha con QueuedConnection automáticamente."""
        if self._stopped or not self.thread.isRunning():
            return
        QMetaObject.invokeMethod(
            self.worker, "set_target", Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, scene_name or ""),
            Q_ARG(str, source_name or ""),
        )

    def set_fps(self, fps):
        if self._stopped or not self.thread.isRunning():
            return
        QMetaObject.invokeMethod(
            self.worker, "set_fps", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, int(fps)),
        )

    def __del__(self):
        """Fail-safe: si el objeto se destruye sin stop explícito, intentamos
        pararlo. No podemos usar invokeMethod aquí porque el objeto ya está
        muriendo; hacemos best-effort."""
        try:
            if not self._stopped and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(500)
        except Exception:
            pass
