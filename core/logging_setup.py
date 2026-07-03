import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "OBS_Automation_Manager"
LOG_FILENAME = "app.log"
MAX_BYTES = 1_048_576  # 1 MB
BACKUP_COUNT = 5


def get_logs_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    logs_dir = Path(base) / APP_NAME / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_log_file_path() -> Path:
    return get_logs_dir() / LOG_FILENAME


def setup_logging(level=logging.INFO):
    """Configura root logger con RotatingFileHandler + console handler.

    Se ejecuta una sola vez al arrancar la app.
    """
    root = logging.getLogger()
    if getattr(root, "_obs_manager_configured", False):
        return
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        str(get_log_file_path()),
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    root._obs_manager_configured = True
