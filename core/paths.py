import os
from pathlib import Path

APP_NAME = "OBS_Automation_Manager"


def get_app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    app_dir = Path(base) / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir
