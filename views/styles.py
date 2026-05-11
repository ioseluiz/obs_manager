# Paleta de colores: Blanco puro, gris claro para fondos, azul moderno para acentos.
LIGHT_THEME_QSS = """
    /* Fondo principal y texto general */
    QWidget {
        background-color: #F8F9FA;
        color: #212529;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 14px;
    }

    /* Paneles genéricos */
    QFrame {
        background-color: #FFFFFF;
        border: 1px solid #DEE2E6;
        border-radius: 6px;
    }

    /* Solución para el recorte de los encabezados de QGroupBox */
    QGroupBox {
        background-color: #FFFFFF;
        border: 1px solid #DEE2E6;
        border-radius: 6px;
        margin-top: 25px; /* Reserva espacio en la parte superior para el título */
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        left: 10px; /* Un ligero sangrado desde el borde izquierdo */
        top: 0px;
        color: #0D6EFD; /* Azul moderno para destacar las secciones */
        font-weight: bold;
    }

    /* Botones principales */
    QPushButton {
        background-color: #0D6EFD; 
        color: #FFFFFF;
        border: none;
        border-radius: 4px;
        padding: 8px 16px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #0B5ED7;
    }
    QPushButton:pressed {
        background-color: #0A58CA;
    }

    /* Entradas de texto y tablas */
    QLineEdit, QSpinBox, QDateTimeEdit, QTableWidget {
        background-color: #FFFFFF;
        color: #212529;
        border: 1px solid #CED4DA;
        border-radius: 4px;
        padding: 4px;
    }
    QLineEdit:focus, QSpinBox:focus, QDateTimeEdit:focus {
        border: 1px solid #86B7FE;
    }
    
    /* Pestañas */
    QTabWidget::pane {
        border: 1px solid #DEE2E6;
        background-color: #FFFFFF;
    }
    QTabBar::tab {
        background-color: #E9ECEF;
        color: #495057;
        padding: 8px 12px;
        border: 1px solid #DEE2E6;
        border-bottom-color: transparent;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }
    QTabBar::tab:selected {
        background-color: #FFFFFF;
        color: #0D6EFD;
        font-weight: bold;
    }
"""