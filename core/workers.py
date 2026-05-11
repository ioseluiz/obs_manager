from PyQt6.QtCore import QThread, pyqtSignal

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
        # Esta función se ejecuta en un hilo separado
        success, message = self.obs_client.connect(self.host, self.port, self.password)
        if success:
            self.connection_success.emit(message)
        else:
            self.connection_error.emit(message)