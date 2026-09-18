"""Resolución de paths del script Autopilot empaquetado.

En desarrollo (correr `python main.py`), el `autopilot.lua` vive en
`obs_scripts/autopilot.lua` relativo a la raíz del proyecto.

En instalación (correr `OBS_Automation_Manager.exe` desde el .exe generado
por PyInstaller + Inno Setup), el `autopilot.lua` vive junto al .exe en la
carpeta `obs_scripts/` dentro del onedir bundle. PyInstaller lo empaqueta
como data — ver `OBS_Automation_Manager.spec`.

Este módulo aisla la lógica de dónde encontrar el archivo para que el
wizard del PR AUT-3 no tenga que decidirlo.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _is_frozen() -> bool:
    """True si estamos corriendo dentro de un bundle PyInstaller."""
    return getattr(sys, "frozen", False)


def bundle_root() -> Path:
    """Raíz de recursos disponible en runtime.

    - En dev: raíz del repo (donde vive `main.py`).
    - En instalación: carpeta que contiene el .exe (por ejemplo
      `%LOCALAPPDATA%\\Programs\\OBS_Automation_Manager\\`).

    Usar esta base para localizar archivos data empaquetados con
    PyInstaller vía `Analysis(datas=[('obs_scripts', 'obs_scripts')])`.
    """
    if _is_frozen():
        return Path(sys.executable).parent.resolve()
    # dev: `core/autopilot_paths.py` está en `<repo>/core/`, subir 1 nivel
    return Path(__file__).resolve().parent.parent


def autopilot_lua_path() -> Path:
    """Ruta al `autopilot.lua` empaquetado.

    Raises:
        FileNotFoundError: si el archivo no existe (bug del bundle o dev
        sin el repo completo).
    """
    candidate = bundle_root() / "obs_scripts" / "autopilot.lua"
    if not candidate.exists():
        raise FileNotFoundError(
            f"No se encontró autopilot.lua en {candidate}. "
            f"En desarrollo: correr desde la raíz del repo. "
            f"En instalación: verificar que el instalador empaquete obs_scripts/."
        )
    return candidate


def autopilot_lua_bytes() -> bytes:
    """Contenido crudo del script — útil para copiar a otras ubicaciones."""
    return autopilot_lua_path().read_bytes()


def default_downloads_dir() -> Path:
    """Devuelve la carpeta Descargas del usuario en Windows.

    Fallback a Documentos si por alguna razón no existe.
    """
    if sys.platform == "win32":
        # USERPROFILE es siempre confiable en Windows
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            candidate = Path(userprofile) / "Downloads"
            if candidate.exists():
                return candidate
            candidate = Path(userprofile) / "Documents"
            if candidate.exists():
                return candidate
    return Path.home()
