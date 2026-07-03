import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from views.styles import LIGHT_THEME_QSS
from controllers.main_controller import MainController
from core.database import init_db  # <-- Importamos el inicializador de la BD
from core.logging_setup import setup_logging

# sys._MEIPASS existe cuando PyInstaller empaqueta la app como --onefile
BASE_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent

def main():
    # 0. Configurar logging antes de nada para capturar init de BD, errores tempranos, etc.
    setup_logging()
    logging.info("=== OBS_Automation_Manager arrancando ===")

    # 1. Crear la base de datos y las tablas ANTES de iniciar cualquier controlador
    init_db()

    # 2. Levantar la aplicación de PyQt
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(BASE_DIR / "app_icon.ico")))

    # Forzamos el estilo Fusion como base neutra para luego sobreescribirlo
    app.setStyle("Fusion")

    # Aplicamos el QSS global (fuerza Light Theme)
    app.setStyleSheet(LIGHT_THEME_QSS)

    # 3. Inicializamos la arquitectura MVC
    # Ahora el MainController y sus sub-controladores encontrarán las tablas creadas
    controller = MainController()
    controller.show_main_window()
    app.aboutToQuit.connect(controller.shutdown)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()