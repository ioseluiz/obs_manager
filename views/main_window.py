import sys
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTabWidget, QToolBar, QStatusBar, QPushButton,
                             QLabel, QApplication)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap

_BASE = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent.parent
_ICON_PATH = _BASE / "app_icon.ico"
_LOGO_PATH = _BASE / "assets" / "CP_hor_800px (1).png"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # --- CONFIGURACIÓN DE LA VENTANA ---
        self.setWindowTitle("OBS Automation Manager - INI")
        self.setWindowIcon(QIcon(str(_ICON_PATH)))
        # Min height 640px permite trabajar en laptops típicos (1366x768 con
        # taskbar visible da ~700-720px de área útil).
        self.setMinimumSize(1100, 640)

        # Tamaño inicial adaptativo — 90% de la pantalla disponible, cap en
        # 1500×880. Esto evita que la ventana arranque al mínimo y comprima
        # los botones verticalmente en pantallas grandes.
        # También detectamos pantallas bajas (<720px útiles) para modo compacto.
        self._compact_mode = False
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            target_w = max(1100, min(1500, int(avail.width() * 0.9)))
            target_h = max(640, min(880, int(avail.height() * 0.9)))
            self.resize(target_w, target_h)
            # Laptops de 14" (768px o 1080px @ 125%) suelen dar ≤720px útiles.
            self._compact_mode = avail.height() <= 760

        # --- WIDGET CENTRAL Y LAYOUT ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # --- CONTENEDOR DE PESTAÑAS (TABS) ---
        # Aquí es donde el MainController insertará SceneView, CalendarView y CountdownView
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True) # Le da un aspecto más moderno en Windows
        self.tabs.setMovable(True)
        self.main_layout.addWidget(self.tabs)

        # --- TOOLBAR (BARRA DE HERRAMIENTAS) ---
        self.toolbar = QToolBar("Barra Principal")
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # En modo compacto (pantallas ≤760px), los textos largos consumen ancho
        # innecesario en el toolbar. Reducimos a un símbolo + tooltip descriptivo.
        # `_text_full` / `_text_compact` se guardan como atributos para permitir
        # cambiar el estado del botón (p.ej. Conectar → Conectado) sin perder
        # el texto compacto.
        compact = self._compact_mode

        # Botón de Ajustes
        self.btn_settings = QPushButton("⚙" if compact else " ⚙ Ajustes")
        self.btn_settings.setToolTip("Ajustes")
        self.toolbar.addWidget(self.btn_settings)

        self.toolbar.addSeparator()

        # Botón de Conexión OBS
        self.btn_connect = QPushButton("🔌" if compact else " 🔌 Conectar OBS")
        self.btn_connect.setToolTip("Conectar a OBS")
        self.btn_connect.setStyleSheet("background-color: #0D6EFD; color: white;")
        self.toolbar.addWidget(self.btn_connect)

        self.toolbar.addSeparator()

        # Export / Import de escenas
        self.btn_export = QPushButton("📤" if compact else " 📤 Exportar")
        self.btn_export.setToolTip("Exportar todas las escenas a un archivo JSON")
        self.toolbar.addWidget(self.btn_export)

        self.btn_import = QPushButton("📥" if compact else " 📥 Importar")
        self.btn_import.setToolTip("Importar escenas desde un archivo JSON")
        self.toolbar.addWidget(self.btn_import)

        self.toolbar.addSeparator()

        # Botón de Transmisión (toggle) — dispara StartRecord/StopRecord de OBS,
        # que en la config Custom Output FFmpeg + URL UDP transmite sin generar archivo.
        self.btn_record = QPushButton("🔴" if compact else " 🔴 Transmitir")
        self.btn_record.setToolTip("Iniciar salida en OBS (Custom Output FFmpeg → UDP)")
        self.btn_record.setEnabled(False)  # Se habilita al conectar
        self._record_style_idle = "background-color: #6C757D; color: white;"
        self._record_style_active = "background-color: #DC3545; color: white;"
        self.btn_record.setStyleSheet(self._record_style_idle)
        self.toolbar.addWidget(self.btn_record)

        # --- BARRA DE ESTADO (STATUS BAR) ---
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Listo")

        # Logo ACP + crédito (al inicio del área de permanent widgets, para que
        # queden al mismo nivel horizontal que Canvas / Conexión y no los tape
        # ningún mensaje temporal). El logo es blanco sobre transparente, así
        # que el contenedor lleva fondo oscuro para dar contraste.
        self._build_acp_credit()

        # Timer de grabación (permanent widget, oculto por defecto)
        self.lbl_record_timer = QLabel("")
        self.lbl_record_timer.setStyleSheet("color: #DC3545; font-weight: bold;")
        self.lbl_record_timer.setVisible(False)
        self.statusBar().addPermanentWidget(self.lbl_record_timer)

        # Canvas de OBS (resolución del base_width × base_height).
        # Va en el status bar porque (a) es info de estado — su lugar natural,
        # (b) es siempre visible sin competir con botones por espacio horizontal.
        self.lbl_canvas = QLabel("🖥 Canvas: — ")
        self.lbl_canvas.setStyleSheet("color: #6C757D; font-family: monospace;")
        self.lbl_canvas.setToolTip("Resolución del canvas de OBS (base_width × base_height)")
        self.statusBar().addPermanentWidget(self.lbl_canvas)

        # Label para indicar el estado de la conexión en la barra de estado
        self.lbl_connection_status = QLabel("Desconectado ")
        self.lbl_connection_status.setStyleSheet("color: #DC3545; font-weight: bold;")
        self.statusBar().addPermanentWidget(self.lbl_connection_status)

    def _build_acp_credit(self):
        # Logo a color sobre transparente — sin fondo propio, hereda el color
        # de la ventana para integrarse con la UI.
        container = QWidget()

        row = QHBoxLayout(container)
        row.setContentsMargins(6, 2, 8, 2)
        row.setSpacing(8)

        logo = QLabel()
        pix = QPixmap(str(_LOGO_PATH))
        if not pix.isNull():
            # Status bar típica ~22px; escalamos el logo a 20px de alto.
            logo.setPixmap(pix.scaledToHeight(
                20, Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText("ACP")
            logo.setStyleSheet("color: #0D3B66; font-weight: bold;")
        logo.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Texto en azul marino igual al del logo — contrasta con el gris claro
        # de la ventana y arma con el resto de la paleta (Conectar #0D6EFD).
        credit = QLabel("División de Ingeniería - INI")
        credit.setStyleSheet(
            "color: #0D3B66; font-size: 11px; font-weight: 600; "
            "letter-spacing: 0.3px;"
        )
        credit.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        row.addWidget(logo)
        row.addWidget(credit)

        # insertPermanentWidget(0, ...) → queda a la izquierda del grupo de
        # widgets permanentes (Canvas / Conexión), al mismo nivel horizontal.
        self.statusBar().insertPermanentWidget(0, container)

    def set_connection_ui(self, connected: bool):
        """Cambia visualmente la UI dependiendo de si OBS está conectado o no."""
        compact = self._compact_mode
        if connected:
            self.btn_connect.setText("✔" if compact else " ✔ Conectado")
            self.btn_connect.setToolTip("Conectado a OBS")
            self.btn_connect.setStyleSheet("background-color: #198754; color: white;")
            self.lbl_connection_status.setText("🟢 Conectado ")
            self.lbl_connection_status.setStyleSheet("color: #198754; font-weight: bold;")
            self.btn_record.setEnabled(True)
        else:
            self.btn_connect.setText("🔌" if compact else " 🔌 Reconectar")
            self.btn_connect.setToolTip("Reconectar a OBS")
            self.btn_connect.setStyleSheet("background-color: #0D6EFD; color: white;")
            self.lbl_connection_status.setText("🔴 Desconectado ")
            self.lbl_connection_status.setStyleSheet("color: #DC3545; font-weight: bold;")
            self.btn_record.setEnabled(False)

    def set_reconnecting_ui(self, attempt: int):
        """Estado intermedio: el watchdog está reintentando."""
        compact = self._compact_mode
        self.btn_connect.setText("🔁" if compact else " 🔁 Reconectando…")
        self.btn_connect.setToolTip(f"Reconectando (intento {attempt})")
        self.btn_connect.setStyleSheet("background-color: #FD7E14; color: white;")
        self.lbl_connection_status.setText(f"🟠 Reconectando (intento {attempt}) ")
        self.lbl_connection_status.setStyleSheet("color: #FD7E14; font-weight: bold;")
        self.btn_record.setEnabled(False)

    def set_canvas_size(self, width, height):
        """Actualiza el label del canvas de OBS en el status bar."""
        try:
            w = int(width) if width else 0
            h = int(height) if height else 0
        except (TypeError, ValueError):
            w = h = 0
        if w > 0 and h > 0:
            self.lbl_canvas.setText(f"🖥 Canvas: {w}×{h} ")
            self.lbl_canvas.setStyleSheet(
                "color: #198754; font-family: monospace; font-weight: bold;"
            )
        else:
            self.clear_canvas_size()

    def clear_canvas_size(self):
        self.lbl_canvas.setText("🖥 Canvas: — ")
        self.lbl_canvas.setStyleSheet("color: #6C757D; font-family: monospace;")

    def set_recording_ui(self, active: bool, timecode: str = "00:00:00"):
        """Actualiza el estado visual del botón de transmisión y el timer."""
        compact = self._compact_mode
        if active:
            self.btn_record.setText("⏹" if compact else " ⏹ Detener")
            self.btn_record.setToolTip("Detener salida en OBS")
            self.btn_record.setStyleSheet(self._record_style_active)
            self.lbl_record_timer.setText(f"🔴 EN VIVO {timecode} ")
            self.lbl_record_timer.setVisible(True)
        else:
            self.btn_record.setText("🔴" if compact else " 🔴 Transmitir")
            self.btn_record.setToolTip("Iniciar salida en OBS (Custom Output FFmpeg → UDP)")
            self.btn_record.setStyleSheet(self._record_style_idle)
            self.lbl_record_timer.setVisible(False)
            self.lbl_record_timer.setText("")