"""Helper centralizado para cargar iconos corporativos.

Reemplaza los emojis Unicode que la UI actual usa como texto en
botones (▶ ⏸ ⚙ 📤 📥 ➕ ✏ 🗑 🔌 ...) por los PNG corporativos ya
provistos en `assets/icono_*.png`.

Uso tipico:

    from views.theme.icons import apply_icon

    self.btn_save = QPushButton("Guardar")
    apply_icon(self.btn_save, "agregar")

    # Si el texto trae el emoji prefijado, usar scrub_emoji_prefix:
    self.btn_play = QPushButton(" ▶  Play")
    apply_icon(self.btn_play, "play")  # el texto queda " Play"

Para iconos de reproduccion que no tienen asset corporativo
(prev/next/stop), uso `QStyle.StandardPixmap` como fallback nativo
coherente con el sistema operativo.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QPushButton, QStyle


# ---------------------------------------------------------------------------
# Resolucion de rutas (con fallback a sys._MEIPASS para PyInstaller)
# ---------------------------------------------------------------------------

def _assets_dir() -> Path:
    """Directorio `assets/` del bundle. Funciona en dev y en .exe."""
    import sys
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "assets"
    return Path(__file__).resolve().parent.parent.parent / "assets"


# ---------------------------------------------------------------------------
# Nombres canonicos de iconos disponibles en assets/icono_*.png
# ---------------------------------------------------------------------------

ICON_NAMES = {
    "actualizacion_sincro",
    "actualizar",
    "agregar",
    "ajustes_deslizadores",
    "app_tv",
    "bajar",
    "buque",
    "calendario",
    "calendario_fecha",
    "carpeta",
    "check_conexion",
    "conectar",
    "configuracion",
    "contadores",
    "documento",
    "editar",
    "eliminar",
    "escenas",
    "imagen_vista_previa",
    "informacion",
    "inicio",
    "logs",
    "monitor_canvas",
    "ordenar",
    "pausa",
    "play",
    "produccion",
    "prohibido_desconectado",
    "restablecer",
    "subir",
}


# Mapeo de emojis Unicode usados en la UI actual a nombre canonico.
# Lo que no tiene asset corporativo mapea a None → el helper usa un
# QStyle.StandardPixmap como fallback.
EMOJI_TO_ICON = {
    "▶": "play",
    "⏸": "pausa",
    "⏮": None,  # prev → QStyle.SP_MediaSkipBackward
    "⏭": None,  # next → QStyle.SP_MediaSkipForward
    "⏹": None,  # stop → QStyle.SP_MediaStop
    "⚙": "configuracion",
    "🔌": "conectar",
    "📤": "subir",
    "📥": "bajar",
    "➕": "agregar",
    "✏": "editar",
    "🗑": "eliminar",
    "🔄": "actualizar",
    "📁": "carpeta",
    "ℹ": "informacion",
    "📄": "documento",
    "🏠": "inicio",
    "📅": "calendario",
    "🖥": "monitor_canvas",
    "🚢": "buque",
    "🎬": "produccion",
}

_EMOJI_FALLBACK = {
    "⏮": QStyle.StandardPixmap.SP_MediaSkipBackward,
    "⏭": QStyle.StandardPixmap.SP_MediaSkipForward,
    "⏹": QStyle.StandardPixmap.SP_MediaStop,
}


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

@lru_cache(maxsize=256)
def _load_pixmap(name: str) -> QPixmap:
    """Carga el PNG original de `assets/icono_<name>.png`. Cacheado."""
    path = _assets_dir() / f"icono_{name}.png"
    pix = QPixmap(str(path))
    if pix.isNull():
        # No tirar — el helper que llama ya loguea; devolvemos un
        # pixmap vacio 1x1 transparente para no romper.
        empty = QPixmap(1, 1)
        empty.fill(Qt.GlobalColor.transparent)
        return empty
    return pix


def _tint(pix: QPixmap, color: str) -> QPixmap:
    """Tinta un pixmap preservando su canal alfa (QPainter SourceIn)."""
    tinted = QPixmap(pix.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pix)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color))
    painter.end()
    return tinted


def icon(name: str, color: str | None = None) -> QIcon:
    """Devuelve el QIcon corporativo para `name`.

    `color`: hex opcional para tintar el icono (p. ej. "#FFFFFF" para
    el sidebar oscuro). Si None, usa el PNG original.
    """
    if name not in ICON_NAMES:
        return QIcon()
    pix = _load_pixmap(name)
    if color:
        pix = _tint(pix, color)
    return QIcon(pix)


def standard_icon(pm: QStyle.StandardPixmap) -> QIcon:
    """Devuelve un QIcon desde QStyle.StandardPixmap — fallback para
    glifos que no tienen asset corporativo (prev/next/stop media)."""
    app = QApplication.instance()
    if app is None:
        return QIcon()
    return app.style().standardIcon(pm)


# Regex de emojis conocidos para quitarlos de un texto de boton.
# Se incluye el espaciado circundante (uno o varios espacios).
_EMOJI_CHARS = "".join(re.escape(c) for c in EMOJI_TO_ICON.keys())
_EMOJI_RE = re.compile(rf"\s*[{_EMOJI_CHARS}]\s*")


def scrub_emoji_prefix(text: str) -> str:
    """Remueve el emoji del comienzo (y cualquier espacio alrededor) de
    un texto de boton. Deja intactos emojis en medio del texto.

    Ejemplos:
      " ▶  Play"            → "Play"
      "📤 Exportar"         → "Exportar"
      "🗑 Eliminar Selec."  → "Eliminar Selec."
      "No emoji aqui"       → "No emoji aqui"
    """
    stripped = text.lstrip()
    match = _EMOJI_RE.match(stripped)
    if match:
        return stripped[match.end():].strip()
    return text


def apply_icon(
    button: QPushButton,
    name_or_emoji: str,
    color: str | None = None,
    size: int = 18,
    scrub_text: bool = True,
) -> None:
    """Aplica un icono al boton y, opcionalmente, limpia el emoji
    del texto para evitar duplicar glifos.

    `name_or_emoji`: puede ser un nombre canonico (`"play"`) o el
    propio emoji usado en el texto (`"▶"`), que se resuelve via
    `EMOJI_TO_ICON`. Si es un emoji sin mapeo pero con fallback
    nativo (p. ej. `"⏮"`), usa `QStyle.StandardPixmap`.
    """
    resolved_name: str | None = None
    fallback_pm: QStyle.StandardPixmap | None = None

    if name_or_emoji in ICON_NAMES:
        resolved_name = name_or_emoji
    elif name_or_emoji in EMOJI_TO_ICON:
        mapped = EMOJI_TO_ICON[name_or_emoji]
        if mapped is not None:
            resolved_name = mapped
        else:
            fallback_pm = _EMOJI_FALLBACK.get(name_or_emoji)
    else:
        fallback_pm = _EMOJI_FALLBACK.get(name_or_emoji)

    if resolved_name is not None:
        button.setIcon(icon(resolved_name, color=color))
    elif fallback_pm is not None:
        button.setIcon(standard_icon(fallback_pm))
    else:
        return  # Nada que aplicar; dejamos el texto como esta.

    button.setIconSize(QSize(size, size))

    if scrub_text:
        new_text = scrub_emoji_prefix(button.text())
        if new_text != button.text():
            button.setText(new_text)
