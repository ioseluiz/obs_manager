import sys
from PyQt6.QtWidgets import QApplication
from views.styles import LIGHT_THEME_QSS
from controllers.main_controller import MainController
from core.database import init_db  # <-- Importamos el inicializador de la BD

def main():
    # 1. Crear la base de datos y las tablas ANTES de iniciar cualquier controlador
    init_db()

    # 2. Levantar la aplicación de PyQt
    app = QApplication(sys.argv)
    
    # Forzamos el estilo Fusion como base neutra para luego sobreescribirlo
    app.setStyle("Fusion")
    
    # Aplicamos el QSS global (fuerza Light Theme)
    app.setStyleSheet(LIGHT_THEME_QSS)

    # 3. Inicializamos la arquitectura MVC
    # Ahora el MainController y sus sub-controladores encontrarán las tablas creadas
    controller = MainController()
    controller.show_main_window()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()