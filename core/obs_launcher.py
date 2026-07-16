"""Utilidades para detectar y lanzar OBS Studio en Windows.

Todas las funciones son no-ops seguros fuera de Windows para que la app
siga siendo importable en entornos de desarrollo (Linux/macOS).
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

# Rutas típicas de instalación de OBS Studio en Windows
_COMMON_PATHS = [
    r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe",
]

# Flags de creación de proceso para desapegar OBS del proceso padre.
# Si nuestra app se cierra, OBS sigue corriendo.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def find_obs_executable():
    """Localiza obs64.exe. Devuelve la ruta absoluta o None si no la encuentra.

    Estrategia:
      1. Registro de Windows (HKLM\\SOFTWARE\\OBS Studio).
      2. Rutas comunes en Program Files.
    """
    if not _IS_WINDOWS:
        return None

    # 1. Registro
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\OBS Studio") as key:
                    install_path, _ = winreg.QueryValueEx(key, None)
                    candidate = Path(install_path) / "bin" / "64bit" / "obs64.exe"
                    if candidate.is_file():
                        return str(candidate)
            except OSError:
                continue
    except Exception as e:
        log.debug("Lectura de registro para OBS falló: %s", e)

    # 2. Rutas comunes
    for path in _COMMON_PATHS:
        if os.path.isfile(path):
            return path

    return None


def is_obs_running():
    """Devuelve True si hay al menos un proceso obs64.exe corriendo."""
    if not _IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return "obs64.exe" in result.stdout.lower()
    except Exception as e:
        log.debug("tasklist falló al buscar obs64.exe: %s", e)
        return False


def launch_obs(exe_path):
    """Lanza OBS de forma desapegada. Devuelve (ok, mensaje).

    OBS se ejecuta con cwd = directorio del ejecutable, requerido para que
    encuentre sus plugins y datos. Los creationflags evitan que OBS se cierre
    cuando nuestra app termine.
    """
    if not _IS_WINDOWS:
        return False, "Auto-launch de OBS solo está disponible en Windows."
    if not exe_path or not os.path.isfile(exe_path):
        return False, f"No se encontró el ejecutable de OBS: {exe_path}"

    try:
        subprocess.Popen(
            [exe_path],
            cwd=os.path.dirname(exe_path),
            creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        log.info("OBS lanzado desde: %s", exe_path)
        return True, "OK"
    except Exception as e:
        log.error("Fallo al lanzar OBS: %s", e)
        return False, str(e)
