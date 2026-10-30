"""Shell principal del rediseno UI.

Layout:

    QMainWindow
    ├── central = QWidget
    │   └── QHBoxLayout
    │       ├── Sidebar (240px fijo, oscuro, items navegables)
    │       └── QVBoxLayout
    │           ├── AppHeader (72px fijo, blanco con logo + branding)
    │           └── QStackedWidget   ← paginas de contenido
    └── statusBar()                   ← logo + canvas + autopilot v2 + conn

El shell no conoce las paginas; las agrega el MainController via
`add_section(view, nombre, icon_name)`. Metodos conservados para que
el resto del codigo siga funcionando: `set_connection_ui`,
`set_reconnecting_ui`, `set_canvas_size`, `clear_canvas_size`,
`set_recording_ui`, `set_autopilot_v2_ui`. Atributos conservados:
`btn_settings`, `btn_connect`, `btn_export`, `btn_import` (ahora
en el AppHeader).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from views.theme import COLORS
from views.theme.icons import apply_icon
from views.widgets import AppHeader, Sidebar
from views.widgets.brand_image import BrandImage

_BASE = (
    Path(sys._MEIPASS)
    if getattr(sys, "frozen", False)
    else Path(__file__).parent.parent
)
_ICON_PATH = _BASE / "app_icon.ico"
_LOGO_PATH = _BASE / "assets" / "CP_hor_800px (1).png"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("OBS Automation Manager - INI")
        self.setWindowIcon(QIcon(str(_ICON_PATH)))
        # Min height 640px permite trabajar en laptops tipicos (1366x768 con
        # taskbar visible da ~700-720px de area util).
        self.setMinimumSize(1180, 680)

        # Tamano inicial adaptativo — 90% de la pantalla disponible, cap en
        # 1500x880. En el rediseno con sidebar + header fijo necesitamos
        # un poco mas de ancho minimo para que el contenido respire.
        self._compact_mode = False
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            target_w = max(1180, min(1500, int(avail.width() * 0.9)))
            target_h = max(680, min(880, int(avail.height() * 0.9)))
            self.resize(target_w, target_h)
            # Laptops de 14" suelen dar <=720px utiles. El flag lo consume
            # scene_view para compactar su propio toolbar interno.
            self._compact_mode = avail.height() <= 760

        # ----- Shell: sidebar + (header + stack) -----
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(self)
        root.addWidget(self.sidebar)

        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(0)

        self.header = AppHeader(self)
        content_col.addWidget(self.header)

        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet(
            f"QStackedWidget {{ background-color: {COLORS['bg_app']}; }}"
        )
        content_col.addWidget(self.stack, 1)

        root.addLayout(content_col, 1)

        # Alias de los botones del header para que el MainController los
        # conecte igual que antes.
        self.btn_settings = self.header.btn_settings
        self.btn_connect = self.header.btn_connect
        self.btn_export = self.header.btn_export
        self.btn_import = self.header.btn_import

        # Enlazar sidebar <-> stack.
        self.sidebar.section_selected.connect(self.set_active_section)

        # ----- Status bar (misma funcionalidad que antes) -----
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Listo")
        self._build_acp_credit()

        # lbl_record_timer y set_recording_ui eliminados en la
        # unificacion — el Canal Principal legacy ya no existe.
        self.lbl_canvas = QLabel("🖥 Canvas: — ")
        self.lbl_canvas.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-family: monospace;"
        )
        self.lbl_canvas.setToolTip(
            "Resolución del canvas de OBS (base_width × base_height)"
        )
        self.statusBar().addPermanentWidget(self.lbl_canvas)

        self.lbl_autopilot_v2 = QLabel("")
        self.lbl_autopilot_v2.setStyleSheet(
            f"color: {COLORS['text_muted']};"
        )
        self.lbl_autopilot_v2.setToolTip(
            "Estado del script Autopilot v2 residente en OBS. Mantiene la "
            "rotación de canales activa aunque la app se cierre."
        )
        self.lbl_autopilot_v2.setVisible(False)
        self.statusBar().addPermanentWidget(self.lbl_autopilot_v2)

        self.lbl_connection_status = QLabel("Desconectado ")
        self.lbl_connection_status.setStyleSheet(
            f"color: {COLORS['state_danger']}; font-weight: bold;"
        )
        self.statusBar().addPermanentWidget(self.lbl_connection_status)

    # ------------------------------------------------------------------
    # API publica: navegacion
    # ------------------------------------------------------------------

    def add_section(self, view: QWidget, name: str, icon_name: str) -> int:
        """Agrega una pagina de contenido al stack + un item al sidebar.

        `icon_name`: nombre canonico del helper icons (`inicio`,
        `calendario`, `escenas`, `contadores`, `produccion`, `logs`...).

        Devuelve el indice de la seccion (consistente entre sidebar y
        stack porque se agregan en el mismo orden).
        """
        idx = self.stack.addWidget(view)
        sidebar_idx = self.sidebar.add_section(name, icon_name)
        assert idx == sidebar_idx, "stack y sidebar divergieron"
        return idx

    def set_active_section(self, index: int) -> None:
        """Cambia la pagina visible + marca el item del sidebar."""
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            self.sidebar.set_active(index)

    # ------------------------------------------------------------------
    # Compat: `tabs` apunta al QStackedWidget para codigo que esperaba
    # un QTabWidget. Soporta solo el subset `addTab(view, name)` y
    # `currentChanged` que es lo que usaba el main_controller.
    # ------------------------------------------------------------------

    @property
    def tabs(self):
        return _StackTabsCompat(self)

    # ------------------------------------------------------------------
    # Status bar: logo ACP
    # ------------------------------------------------------------------

    def _build_acp_credit(self):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(6, 2, 8, 2)
        row.setSpacing(8)

        logo = BrandImage(_LOGO_PATH, 112, 22)

        credit = QLabel("División de Ingeniería - INI")
        credit.setStyleSheet(
            f"color: {COLORS['brand_navy']}; font-size: 11px; "
            "font-weight: 600; letter-spacing: 0.3px;"
        )
        credit.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )

        row.addWidget(logo)
        row.addWidget(credit)
        self.statusBar().insertPermanentWidget(0, container)

    # ------------------------------------------------------------------
    # Estados del boton de conexion
    # ------------------------------------------------------------------

    def _restyle_connect_button(self, text: str, tooltip: str) -> None:
        """Conservar el azul profundo en todos los estados de conexión."""
        self.btn_connect.setText(text)
        self.btn_connect.setToolTip(tooltip)
        self.btn_connect.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['toolbar_primary']}; "
            f"color: {COLORS['text_inverse']}; }}"
            f"QPushButton:hover {{ background-color: {COLORS['toolbar_hover']}; }}"
            f"QPushButton:pressed {{ background-color: {COLORS['toolbar_pressed']}; }}"
            f"QPushButton:disabled {{ background: {COLORS['bg_muted']}; color: {COLORS['text_muted']}; }}"
        )
        # Mantener icono blanco acorde al estado.
        apply_icon(self.btn_connect, "conectar", color="#FFFFFF")

    def set_connection_ui(self, connected: bool):
        """Cambia visualmente la UI dependiendo de si OBS esta conectado."""
        if connected:
            self._restyle_connect_button(
                " Conectado", "Conectado a OBS",
            )
            self.lbl_connection_status.setText("🟢 Conectado ")
            self.lbl_connection_status.setStyleSheet(
                f"color: {COLORS['state_success']}; font-weight: bold;"
            )
        else:
            self._restyle_connect_button(
                " Reconectar", "Reconectar a OBS",
            )
            self.lbl_connection_status.setText("🔴 Desconectado ")
            self.lbl_connection_status.setStyleSheet(
                f"color: {COLORS['state_danger']}; font-weight: bold;"
            )

    def set_reconnecting_ui(self, attempt: int):
        """Estado intermedio: el watchdog esta reintentando."""
        self._restyle_connect_button(
            " Reconectando…", f"Reconectando (intento {attempt})",
        )
        self.lbl_connection_status.setText(
            f"🟠 Reconectando (intento {attempt}) "
        )
        self.lbl_connection_status.setStyleSheet(
            f"color: {COLORS['state_warning']}; font-weight: bold;"
        )

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
                f"color: {COLORS['state_success']}; "
                "font-family: monospace; font-weight: bold;"
            )
        else:
            self.clear_canvas_size()

    def clear_canvas_size(self):
        self.lbl_canvas.setText("🖥 Canvas: — ")
        self.lbl_canvas.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-family: monospace;"
        )

    def set_autopilot_v2_ui(self, state: dict | None) -> None:
        """Actualiza el label de Autopilot v2 segun el state leido del Lua.

        `state`:
            None → script no detectado o no se pudo leer; oculta el label.
            dict con `mode` y `canales[]` → formatea segun standby/active.
        """
        if state is None:
            self.lbl_autopilot_v2.setVisible(False)
            return

        canales = state.get("canales") or []
        total = len(canales)
        mode = state.get("mode") or ""
        version = state.get("script_version") or "?"

        if mode == "active":
            activos = sum(
                1 for c in canales
                if int(c.get("seconds_remaining", 0) or 0) > 0
            )
            self.lbl_autopilot_v2.setText(
                f"🚀 Autopilot v{version} activo · {activos}/{total} rotando "
            )
            self.lbl_autopilot_v2.setStyleSheet(
                f"color: {COLORS['state_danger']}; font-weight: bold;"
            )
        else:
            self.lbl_autopilot_v2.setText(
                f"🎛 Autopilot v{version} listo · {total} canales "
            )
            self.lbl_autopilot_v2.setStyleSheet(
                f"color: {COLORS['state_success']}; font-weight: bold;"
            )
        self.lbl_autopilot_v2.setVisible(True)


class _StackTabsCompat:
    """Shim de compatibilidad para codigo que usa `main_window.tabs`.

    Expone solo lo que el main_controller actual necesita:
    `addTab(view, name)`. El icono se infiere del nombre via un mapa
    chico para no cambiar el main_controller en este commit. En fases
    siguientes el controller se migra a `add_section(view, name, icon)`.
    """

    _NAME_TO_ICON = {
        "Calendario de Cumpleaños": "calendario",
        "Biblioteca de Escenas": "escenas",
        "Contadores": "contadores",
        "Producción": "produccion",
        "Logs": "logs",
    }

    def __init__(self, window: MainWindow):
        self._window = window

    def addTab(self, view: QWidget, name: str) -> int:
        icon_name = self._NAME_TO_ICON.get(name, "informacion")
        return self._window.add_section(view, name, icon_name)
