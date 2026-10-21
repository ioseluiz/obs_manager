"""Resuelve rutas de los assets del Autopilot v2.

Separado para que funcione tanto en desarrollo (archivos sueltos bajo
`obs_scripts/`) como en el .exe empaquetado por PyInstaller (archivos
dentro de `sys._MEIPASS` cuando el script se extrae a la carpeta temp
al arrancar).
"""
from __future__ import annotations

import sys
from pathlib import Path


LUA_V2_FILENAME = "autopilot_v2.lua"


def bundle_root() -> Path:
    """Raiz del bundle de datos de la app.

    - En .exe PyInstaller onefile: `sys._MEIPASS` (los datas de `.spec`
      se extraen ahi al arrancar). PyInstaller >=6.0 nos obliga a usarlo
      explicitamente — el fix v1.8.1 nacio por esto.
    - En desarrollo: la raiz del proyecto (padre de `core/`).
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent.parent


def autopilot_v2_lua_path() -> Path:
    """Ruta al `autopilot_v2.lua` embebido con la app."""
    return bundle_root() / "obs_scripts" / LUA_V2_FILENAME
