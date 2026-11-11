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


def find_running_obs_executable():
    """Ruta completa del obs64.exe que esta corriendo ahora mismo, o None.

    Es la mejor fuente cuando la app esta conectada a un OBS local: cubre
    el OBS portable (que no esta en el registro ni en Program Files) sin
    que el usuario tenga que configurar OBS_EXE_PATH. Usa la API Win32
    (Toolhelp + QueryFullProcessImageName), sin subprocesos.
    """
    if not _IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes as wt

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
        k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.OpenProcess.restype = wt.HANDLE
        k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
        k32.CloseHandle.argtypes = [wt.HANDLE]

        TH32CS_SNAPPROCESS = 0x00000002
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        INVALID_HANDLE_VALUE = wt.HANDLE(-1).value

        snapshot = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == INVALID_HANDLE_VALUE or not snapshot:
            return None
        pids = []
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            ok = k32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                if entry.szExeFile.lower() == "obs64.exe":
                    pids.append(entry.th32ProcessID)
                ok = k32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snapshot)

        for pid in pids:
            handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                continue
            try:
                buf = ctypes.create_unicode_buffer(32768)
                size = wt.DWORD(len(buf))
                if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) and buf.value:
                    return buf.value
            finally:
                k32.CloseHandle(handle)
    except Exception as e:
        log.debug("No se pudo obtener la ruta del obs64.exe en ejecución: %s", e)
    return None


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
