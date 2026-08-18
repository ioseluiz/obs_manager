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
        # Cada imagen del calendario tiene su propia geometría (celdas y
        # márgenes) — no solo el número de filas. Por eso TODOS los parámetros
        # de calibración (X_START, ΔX, Y_START, ΔY, escala) se guardan por
        # plantilla 4w/5w/6w. Al cambiar entre imágenes cada una recuerda
        # sus valores.
        #
        # Fallbacks: si el .env aún tiene las llaves globales legacy
        # (CAL_X_START, CAL_X_SPACE, CAL_SCALE), se usan como valor inicial
        # para las tres plantillas — preserva calibraciones previas.
        legacy_x_start = os.getenv("CAL_X_START")
        legacy_x_space = os.getenv("CAL_X_SPACE")
        legacy_scale = os.getenv("CAL_SCALE")

        def _int(key, fallback_env, default):
            val = os.getenv(key)
            if val is not None:
                return int(val)
            if fallback_env is not None:
                return int(fallback_env)
            return default

        return {
            "host": os.getenv("OBS_HOST", "localhost"),
            "port": os.getenv("OBS_PORT", "4455"),
            "password": os.getenv("OBS_PASSWORD", ""),
            "obs_exe_path": os.getenv("OBS_EXE_PATH", ""),
            "obs_autolaunch": os.getenv("OBS_AUTOLAUNCH", "true").strip().lower() == "true",
            "cal_scene": os.getenv("CAL_SCENE_NAME", "CUMPLEANOS DEL MES"),
            "cal_source": os.getenv("CAL_SOURCE_NAME", "CIRCULO"),
            # Plantilla activa: "auto" | "4" | "5" | "6".
            "cal_template_weeks": os.getenv("CAL_TEMPLATE_WEEKS", "auto"),
            # --- Plantilla 4 semanas (extrapolado; sin medición real) ---
            "cal_x_start_4w": _int("CAL_X_START_4W", legacy_x_start, 298),
            "cal_x_space_4w": _int("CAL_X_SPACE_4W", legacy_x_space, 191),
            "cal_y_start_4w": int(os.getenv("CAL_Y_START_4W", 200)),
            "cal_y_space_4w": int(os.getenv("CAL_Y_SPACE_4W", 220)),
            "cal_scale_4w": _int("CAL_SCALE_4W", legacy_scale, 100),
            "cal_dx_row0_4w": int(os.getenv("CAL_DX_ROW0_4W", 0)),
            "cal_dy_row0_4w": int(os.getenv("CAL_DY_ROW0_4W", 0)),
            # --- Plantilla 5 semanas (medido sobre ABRIL 2026, 1920x1080) ---
            # Celda 179x167, paso 191x182. Y_START aproximado.
            "cal_x_start_5w": _int("CAL_X_START_5W", legacy_x_start, 298),
            "cal_x_space_5w": _int("CAL_X_SPACE_5W", legacy_x_space, 191),
            "cal_y_start_5w": int(os.getenv("CAL_Y_START_5W", 200)),
            "cal_y_space_5w": int(os.getenv("CAL_Y_SPACE_5W", 182)),
            "cal_scale_5w": _int("CAL_SCALE_5W", legacy_scale, 100),
            "cal_dx_row0_5w": int(os.getenv("CAL_DX_ROW0_5W", 0)),
            "cal_dy_row0_5w": int(os.getenv("CAL_DY_ROW0_5W", 0)),
            # --- Plantilla 6 semanas ---
            # Mismo layout horizontal que 5w (calendarios Autoridad tienen columnas
            # idénticas independientemente del mes). ΔY compresado a 152 para
            # meter 6 filas en la misma área vertical que 5w:
            #   5w: 4×182 + 167 = 895 px de grid
            #   6w: 5×152 + 139 ≈ 899 px (cell_h ~5/6 de la de 5w)
            "cal_x_start_6w": _int("CAL_X_START_6W", legacy_x_start, 298),
            "cal_x_space_6w": _int("CAL_X_SPACE_6W", legacy_x_space, 191),
            "cal_y_start_6w": int(os.getenv("CAL_Y_START_6W", 155)),
            "cal_y_space_6w": int(os.getenv("CAL_Y_SPACE_6W", 152)),
            "cal_scale_6w": _int("CAL_SCALE_6W", legacy_scale, 100),
            "cal_dx_row0_6w": int(os.getenv("CAL_DX_ROW0_6W", 0)),
            "cal_dy_row0_6w": int(os.getenv("CAL_DY_ROW0_6W", 0)),
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

    def save_calendar_settings(self, scene, source, template_weeks, per_template):
        """Guarda la calibración del calendario en el .env.

        `per_template` es un dict con la forma:
            {"4": {"x_start": .., "x_space": .., "y_start": .., "y_space": ..,
                   "scale": ..},
             "5": {...}, "6": {...}}
        """
        updates = {
            "CAL_SCENE_NAME": scene,
            "CAL_SOURCE_NAME": source,
            "CAL_TEMPLATE_WEEKS": str(template_weeks),
        }
        for key in ("4", "5", "6"):
            block = per_template[key]
            updates[f"CAL_X_START_{key}W"] = str(block["x_start"])
            updates[f"CAL_X_SPACE_{key}W"] = str(block["x_space"])
            updates[f"CAL_Y_START_{key}W"] = str(block["y_start"])
            updates[f"CAL_Y_SPACE_{key}W"] = str(block["y_space"])
            updates[f"CAL_SCALE_{key}W"] = str(block["scale"])
            updates[f"CAL_DX_ROW0_{key}W"] = str(block.get("dx_row0", 0))
            updates[f"CAL_DY_ROW0_{key}W"] = str(block.get("dy_row0", 0))
        self._update_env_file(updates)