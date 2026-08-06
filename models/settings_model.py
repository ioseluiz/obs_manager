import os
import sys
import shutil
import logging
from pathlib import Path
from dotenv import load_dotenv
from core.paths import get_app_data_dir


def _default_env_path() -> str:
    return str(get_app_data_dir() / ".env")


def _migrate_legacy_env(target_path: str) -> None:
    """Si existe un .env legacy junto al CWD o al ejecutable frozen y no existe
    aún en la ubicación nueva de %LOCALAPPDATA%, moverlo una sola vez.
    """
    if os.path.exists(target_path):
        return

    candidates = [Path.cwd() / ".env"]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / ".env")

    for legacy in candidates:
        try:
            if legacy.is_file() and legacy.resolve() != Path(target_path).resolve():
                shutil.move(str(legacy), target_path)
                logging.info("Migrado .env legacy de %s a %s", legacy, target_path)
                return
        except Exception as e:
            logging.warning("No se pudo migrar .env desde %s: %s", legacy, e)


class SettingsModel:
    def __init__(self, env_path=None):
        self.env_path = env_path or _default_env_path()
        _migrate_legacy_env(self.env_path)
        if not os.path.exists(self.env_path):
            with open(self.env_path, 'w', encoding='utf-8') as f:
                f.write("OBS_HOST=localhost\nOBS_PORT=4455\nOBS_PASSWORD=\n")
        load_dotenv(self.env_path)

    def get_settings(self):
        return {
            "host": os.getenv("OBS_HOST", "localhost"),
            "port": os.getenv("OBS_PORT", "4455"),
            "password": os.getenv("OBS_PASSWORD", ""),
            "obs_exe_path": os.getenv("OBS_EXE_PATH", ""),
            "obs_autolaunch": os.getenv("OBS_AUTOLAUNCH", "true").strip().lower() == "true",
            "cal_scene": os.getenv("CAL_SCENE_NAME", "CUMPLEANOS DEL MES"),
            "cal_source": os.getenv("CAL_SOURCE_NAME", "CIRCULO"),
            # Coordenadas comunes X y escala.
            # Valores medidos sobre la plantilla AGOSTO 2026 (canvas 1920x1080):
            # Domingo (col 0) = 348, Lunes (col 1) = 510  →  ΔX = 162.
            "cal_x_start": int(os.getenv("CAL_X_START", 348)),
            "cal_x_space": int(os.getenv("CAL_X_SPACE", 162)),
            "cal_scale": int(os.getenv("CAL_SCALE", 100)),
            # Calibración para plantillas de <=5 semanas (celdas grandes).
            # Estimado: mismo y_start que 6W; y_space mayor para llenar el área.
            "cal_y_start_5w": int(os.getenv("CAL_Y_START_5W", 159)),
            "cal_y_space_5w": int(os.getenv("CAL_Y_SPACE_5W", 185)),
            # Calibración para plantillas de 6 semanas (celdas comprimidas).
            # Valores medidos sobre AGOSTO 2026: fila 1 = y=159, fila 2 = y=307.
            "cal_y_start_6w": int(os.getenv("CAL_Y_START_6W", 159)),
            "cal_y_space_6w": int(os.getenv("CAL_Y_SPACE_6W", 148)),
        }

    def _update_env_file(self, updates):
        """
        Función auxiliar que lee el archivo, actualiza múltiples valores en memoria 
        y lo guarda UNA sola vez para evitar que OneDrive bloquee el archivo.
        """
        if os.path.exists(self.env_path):
            with open(self.env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        else:
            lines = []

        new_lines = []
        keys_updated = set()

        for line in lines:
            updated = False
            for key, val in updates.items():
                if line.startswith(f"{key}="):
                    new_lines.append(f"{key}={val}\n")
                    keys_updated.add(key)
                    updated = True
                    break
            if not updated:
                new_lines.append(line)

        # Si hay alguna llave nueva que no estaba en el archivo, se agrega al final
        for key, val in updates.items():
            if key not in keys_updated:
                new_lines.append(f"{key}={val}\n")

        # Sobreescribir el archivo de un solo golpe
        with open(self.env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
            
        load_dotenv(self.env_path, override=True)

    def save_settings(self, host, port, password):
        self._update_env_file({
            "OBS_HOST": host,
            "OBS_PORT": str(port),
            "OBS_PASSWORD": password
        })

    def save_launch_settings(self, exe_path, autolaunch):
        self._update_env_file({
            "OBS_EXE_PATH": exe_path or "",
            "OBS_AUTOLAUNCH": "true" if autolaunch else "false"
        })

    def save_calendar_settings(self, scene, source, x_start, x_space,
                               y_start_5w, y_space_5w,
                               y_start_6w, y_space_6w, scale):
        self._update_env_file({
            "CAL_SCENE_NAME": scene,
            "CAL_SOURCE_NAME": source,
            "CAL_X_START": str(x_start),
            "CAL_X_SPACE": str(x_space),
            "CAL_Y_START_5W": str(y_start_5w),
            "CAL_Y_SPACE_5W": str(y_space_5w),
            "CAL_Y_START_6W": str(y_start_6w),
            "CAL_Y_SPACE_6W": str(y_space_6w),
            "CAL_SCALE": str(scale),
        })