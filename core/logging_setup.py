import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "OBS_Automation_Manager"
LOG_FILENAME = "app.log"
MAX_BYTES = 1_048_576  # 1 MB
BACKUP_COUNT = 5

_secrets = set()
_SECRET_FIELD = re.compile(
    r'''(?i)((?:["']?(?:password|passwd|obs_password|token|secret|authorization)["']?)\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)'''
)


def register_secret(value):
    if value:
        _secrets.add(str(value))


def redact_secrets(text):
    text = _SECRET_FIELD.sub(lambda m: m.group(1) + "[OCULTO]", str(text))
    for secret in sorted(tuple(_secrets), key=len, reverse=True):
        text = text.replace(secret, "[OCULTO]")
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact_secrets(super().format(record))


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

    from dotenv import dotenv_values
    from core.paths import get_app_data_dir
    for key, value in dotenv_values(get_app_data_dir() / '.env').items():
        if any(part in key.upper() for part in ('PASSWORD', 'PASSWD', 'TOKEN', 'SECRET')):
            register_secret(value)

    # Redact also historical logs so the Logs view and shared files are safe.
    for path in get_logs_dir().glob("app.log*"):
        if path.is_file():
            try:
                original = path.read_text(encoding="utf-8", errors="replace")
                cleaned = redact_secrets(original)
                if cleaned != original:
                    path.write_text(cleaned, encoding="utf-8")
            except OSError:
                pass

    fmt = RedactingFormatter(
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

    # obsws_python.reqs emite un ERROR con traceback cada vez que un request
    # devuelve un status != 100 (p.ej. GetSourceScreenshot 702 "Failed to render
    # screenshot" cuando el media source aún no tiene primera frame). Nuestros
    # wrappers en OBSClient ya capturan la excepción y hacen fallback/log DEBUG.
    # Silenciar la librería a WARNING evita duplicar el ruido en el log.
    logging.getLogger("obsws_python.reqs").setLevel(logging.WARNING)

    root._obs_manager_configured = True
