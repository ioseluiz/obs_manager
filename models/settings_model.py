import os
from dotenv import load_dotenv

class SettingsModel:
    def __init__(self, env_path=".env"):
        self.env_path = env_path
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
            "cal_x_start": int(os.getenv("CAL_X_START", 270)),
            "cal_y_start": int(os.getenv("CAL_Y_START", 157)),
            "cal_x_space": int(os.getenv("CAL_X_SPACE", 159)),
            "cal_y_space": int(os.getenv("CAL_Y_SPACE", 148)),
            "cal_scale": int(os.getenv("CAL_SCALE", 100))
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

    def save_calendar_settings(self, scene, source, x_start, y_start, x_space, y_space, scale):
        self._update_env_file({
            "CAL_SCENE_NAME": scene,
            "CAL_SOURCE_NAME": source,
            "CAL_X_START": str(x_start),
            "CAL_Y_START": str(y_start),
            "CAL_X_SPACE": str(x_space),
            "CAL_Y_SPACE": str(y_space),
            "CAL_SCALE": str(scale)
        })