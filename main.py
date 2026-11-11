import sys
import logging
import traceback
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon
from views.theme import apply_light_theme
from controllers.main_controller import MainController
from core.database import init_db  # <-- Importamos el inicializador de la BD
from core.logging_setup import setup_logging
from core.version import APP_VERSION

# sys._MEIPASS existe cuando PyInstaller empaqueta la app como --onefile
BASE_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent


def _install_excepthook():
    """Captura excepciones no manejadas para que la app no se cierre en silencio.

    En PyQt6, una excepción no controlada dentro de un slot (p. ej. un QTimer)
    termina el proceso por defecto. Este hook la loguea y muestra un diálogo.
    """
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.error("Excepción no controlada:\n%s", tb_text)
        try:
            QMessageBox.critical(
                None,
                "Error inesperado",
                f"Se produjo un error no controlado:\n\n{exc_type.__name__}: {exc_value}\n\n"
                "Revisa el archivo de logs para más detalle.",
            )
        except Exception:
            pass

    sys.excepthook = _hook


def main():
    # 0. Configurar logging antes de nada para capturar init de BD, errores tempranos, etc.
    setup_logging()
    _install_excepthook()
    logging.info("=== OBS_Automation_Manager arrancando ===")

    # 1. Crear la base de datos y las tablas ANTES de iniciar cualquier controlador
    init_db()

    # 2. Levantar la aplicación de PyQt
    app = QApplication(sys.argv)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(str(BASE_DIR / "app_icon.ico")))

    # Tema claro corporativo: estilo Fusion + QPalette clara explicita + QSS.
    # Sin la paleta explicita, Qt 6 adoptaba la paleta oscura de Windows en
    # modo oscuro y las listas / selecciones salian negras o ilegibles.
    apply_light_theme(app)

    # 3. Inicializamos la arquitectura MVC
    # Ahora el MainController y sus sub-controladores encontrarán las tablas creadas
    controller = MainController()
    controller.show_main_window()
    app.aboutToQuit.connect(controller.shutdown)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
