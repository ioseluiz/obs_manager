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
    - En instalación PyInstaller: `sys._MEIPASS` — la carpeta donde
      PyInstaller extrae/agrupa los `datas`. En modo onedir (PyInstaller
      >= 6.0) esto es `<exe_dir>/_internal/`. En modo onefile es un
      directorio temporal que se limpia al salir.

    Usar esta base para localizar archivos data empaquetados con
    PyInstaller vía `Analysis(datas=[('obs_scripts', 'obs_scripts')])`.
    """
    if _is_frozen():
        # sys._MEIPASS es SIEMPRE la raíz de los datas empaquetados.
        # En builds previos usaba `Path(sys.executable).parent` que sólo
        # funcionaba con versiones viejas de PyInstaller (< 6.0) que
        # ponían los datas junto al .exe. Desde 6.0 quedan en _internal/,
        # y sin este fallback autopilot.lua daba FileNotFoundError.
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        # Fallback defensivo — nunca debería ejecutarse en un frozen bundle
        # bien formado, pero cubre casos edge donde _MEIPASS no está set.
        return Path(sys.executable).parent.resolve()
    # dev: `core/autopilot_paths.py` está en `<repo>/core/`, subir 1 nivel
    return Path(__file__).resolve().parent.parent


def autopilot_lua_path() -> Path:
    """Ruta al `autopilot.lua` empaquetado.

    Busca en múltiples ubicaciones para cubrir variantes de PyInstaller:
    - `<bundle_root>/obs_scripts/autopilot.lua` — ubicación estándar.
    - `<exe_dir>/_internal/obs_scripts/autopilot.lua` — onedir moderno.
    - `<exe_dir>/obs_scripts/autopilot.lua` — onedir viejo.

    Raises:
        FileNotFoundError: si el archivo no existe en ninguna variante.
    """
    candidates = [bundle_root() / "obs_scripts" / "autopilot.lua"]

    if _is_frozen():
        exe_dir = Path(sys.executable).parent.resolve()
        candidates.extend([
            exe_dir / "_internal" / "obs_scripts" / "autopilot.lua",
            exe_dir / "obs_scripts" / "autopilot.lua",
        ])

    for candidate in candidates:
        if candidate.exists():
            log.debug("autopilot.lua encontrado en %s", candidate)
            return candidate

    tried = "\n  - ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"No se encontró autopilot.lua en ninguna ubicación conocida. "
        f"Ubicaciones intentadas:\n  - {tried}"
    )


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
