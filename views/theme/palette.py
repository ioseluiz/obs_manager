"""Paleta clara explicita + aplicacion del tema, independiente del SO.

Problema que resuelve: Qt 6 (>= 6.5) sigue el tema del sistema. Con Windows
en modo oscuro, el estilo Fusion arranca con una QPalette oscura y todo lo
que el QSS global no fija explicitamente (fondo de listas, color del texto
seleccionado, cabeceras de tabla, menus, tooltips) sale negro o ilegible:
los operadores veian la lista de canales negra y la fila seleccionada de la
playlist con texto oscuro sobre azul marino.

La app es "light theme" por diseno corporativo, asi que:

1. Pedimos a Qt el esquema claro (`styleHints().setColorScheme(Light)`,
   Qt >= 6.8) para que Fusion no derive la paleta del SO.
2. Fijamos una QPalette clara completa construida desde los tokens, para
   cualquier Qt que ignore el punto 1.
3. Aplicamos el QSS global (que ademas ya estiliza listas y selecciones).

Uso en main.py: `apply_light_theme(app)` justo despues de crear QApplication.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette

from .qss import LIGHT_THEME_QSS
from .tokens import COLORS

log = logging.getLogger(__name__)


def build_light_palette() -> QPalette:
    c = COLORS
    p = QPalette()
    R = QPalette.ColorRole
    roles = {
        R.Window: c["bg_app"],
        R.WindowText: c["text_primary"],
        R.Base: c["bg_input"],
        R.AlternateBase: c["bg_app"],
        R.Text: c["text_primary"],
        R.PlaceholderText: c["text_muted"],
        R.Button: c["bg_muted"],
        R.ButtonText: c["text_primary"],
        R.ToolTipBase: c["bg_panel"],
        R.ToolTipText: c["text_primary"],
        R.Highlight: c["accent_primary"],
        R.HighlightedText: c["text_inverse"],
        R.Link: c["accent_primary"],
        R.LinkVisited: c["accent_primary_pressed"],
        R.BrightText: c["text_inverse"],
        R.Light: "#FFFFFF",
        R.Midlight: c["bg_muted"],
        R.Mid: c["border_strong"],
        R.Dark: c["text_muted"],
        R.Shadow: c["text_primary"],
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    # Estado deshabilitado: gris legible, nunca negro.
    G = QPalette.ColorGroup.Disabled
    p.setColor(G, R.WindowText, QColor(c["text_muted"]))
    p.setColor(G, R.Text, QColor(c["text_muted"]))
    p.setColor(G, R.ButtonText, QColor(c["text_muted"]))
    p.setColor(G, R.HighlightedText, QColor(c["text_inverse"]))
    p.setColor(G, R.Highlight, QColor(c["border_strong"]))
    return p


def apply_light_theme(app) -> None:
    """Fuerza el tema claro corporativo en una QApplication ya creada."""
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
        try:
            hints.setColorScheme(Qt.ColorScheme.Light)
        except Exception as exc:  # Qt sin soporte en esta plataforma
            log.debug("setColorScheme(Light) no disponible: %s", exc)
    app.setStyle("Fusion")
    app.setPalette(build_light_palette())
    app.setStyleSheet(LIGHT_THEME_QSS)
