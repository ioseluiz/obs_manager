"""Serialización de escenas a JSON para backup y portabilidad entre máquinas."""

import json
import logging
from datetime import datetime

FORMAT_VERSION = "1.0"

# Campos exportables (todo lo que aparece en el modelo, excepto id y orden que se recomputan).
EXPORT_FIELDS = [
    "name", "duration", "tipo", "contenido",
    "ancho", "alto", "fps",
    "reload_on_activate", "keep_session", "custom_css",
    "zoom_pct", "pan_x", "pan_y",
    "refresh_interval_seg",
    "video_loop", "video_restart_on_activate",
    "video_mute", "video_volume_pct", "video_offset_seg",
    "active_days", "active_time_start", "active_time_end",
]

log = logging.getLogger(__name__)


def export_scenes_to_file(scenes, path, app_version="unknown"):
    """Serializa una lista de escenas (dicts como los devuelve SceneModel) a un JSON."""
    payload = {
        "format_version": FORMAT_VERSION,
        "app_version": app_version,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "scene_count": len(scenes),
        "scenes": [_scene_to_dict(s) for s in scenes],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    log.info("Export: %d escenas → %s", len(scenes), path)
    return len(scenes)


def import_scenes_from_file(path):
    """Lee un archivo JSON y devuelve la lista de escenas + metadata.

    Retorna (scenes, metadata). Lanza ValueError si el formato no es válido.
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict) or "scenes" not in payload:
        raise ValueError("El archivo no contiene el campo 'scenes'.")

    format_version = payload.get("format_version", "unknown")
    if format_version != FORMAT_VERSION:
        log.warning("Import: format_version distinto (%s vs %s). Intentando igual.",
                    format_version, FORMAT_VERSION)

    scenes_raw = payload["scenes"]
    if not isinstance(scenes_raw, list):
        raise ValueError("'scenes' debe ser una lista.")

    scenes = []
    for i, s in enumerate(scenes_raw):
        if not isinstance(s, dict) or "name" not in s or "duration" not in s:
            raise ValueError(f"Escena #{i} inválida: faltan campos obligatorios.")
        scenes.append(s)

    metadata = {
        "format_version": format_version,
        "app_version": payload.get("app_version"),
        "exported_at": payload.get("exported_at"),
        "scene_count": len(scenes),
    }
    log.info("Import: %d escenas leídas de %s", len(scenes), path)
    return scenes, metadata


def _scene_to_dict(scene):
    """Extrae solo los campos exportables de un scene dict del modelo."""
    return {k: scene.get(k) for k in EXPORT_FIELDS if k in scene}


CALENDAR_FORMAT_VERSION = "1.0"

# Claves de la calibración por plantilla que se serializan.
_CAL_PER_TEMPLATE_KEYS = (
    "x_start", "x_space", "y_start", "y_space", "scale", "dx_row0", "dy_row0",
)


def export_calendar_calibration_to_file(settings, path, app_version="unknown"):
    """Serializa la calibración del calendario (nombres, plantilla activa y los
    tres bloques 4w/5w/6w) a un archivo JSON portable.

    `settings` es el dict devuelto por SettingsModel.get_settings().
    """
    per_template = {}
    for key in ("4", "5", "6"):
        per_template[key] = {
            "x_start": int(settings[f"cal_x_start_{key}w"]),
            "x_space": int(settings[f"cal_x_space_{key}w"]),
            "y_start": int(settings[f"cal_y_start_{key}w"]),
            "y_space": int(settings[f"cal_y_space_{key}w"]),
            "scale": int(settings[f"cal_scale_{key}w"]),
            "dx_row0": int(settings.get(f"cal_dx_row0_{key}w", 0)),
            "dy_row0": int(settings.get(f"cal_dy_row0_{key}w", 0)),
        }

    payload = {
        "format_version": CALENDAR_FORMAT_VERSION,
        "type": "calendar_calibration",
        "app_version": app_version,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "scene": settings.get("cal_scene", ""),
        "source": settings.get("cal_source", ""),
        "template_weeks": str(settings.get("cal_template_weeks", "auto")),
        "per_template": per_template,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    log.info("Export calendario → %s", path)
    return payload


def import_calendar_calibration_from_file(path):
    """Lee un JSON de calibración del calendario y valida su estructura.

    Retorna un dict con las claves: scene, source, template_weeks, per_template,
    exported_at, app_version. Lanza ValueError si el formato no es válido.
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError("El archivo no es un JSON de calibración válido.")

    if payload.get("type") != "calendar_calibration":
        raise ValueError(
            "Este archivo no es una calibración de calendario. "
            "¿Quizás es un export de escenas? Usa el botón Importar del "
            "toolbar principal en ese caso."
        )

    fmt = payload.get("format_version", "unknown")
    if fmt != CALENDAR_FORMAT_VERSION:
        log.warning("Import calendario: format_version distinto (%s vs %s).",
                    fmt, CALENDAR_FORMAT_VERSION)

    per_template = payload.get("per_template")
    if not isinstance(per_template, dict):
        raise ValueError("Falta el bloque 'per_template'.")

    for key in ("4", "5", "6"):
        block = per_template.get(key)
        if not isinstance(block, dict):
            raise ValueError(f"Falta la plantilla '{key}w' en 'per_template'.")
        for field in _CAL_PER_TEMPLATE_KEYS:
            if field not in block:
                raise ValueError(
                    f"Plantilla '{key}w' incompleta: falta '{field}'."
                )
            # Validamos que sea numérico (int-castable).
            try:
                int(block[field])
            except (TypeError, ValueError):
                raise ValueError(
                    f"Plantilla '{key}w' tiene '{field}' no numérico."
                )

    template_weeks = str(payload.get("template_weeks", "auto")).lower()
    if template_weeks not in ("auto", "4", "5", "6"):
        template_weeks = "auto"

    log.info("Import calendario ← %s (exportado %s)",
             path, payload.get("exported_at", "?"))
    return {
        "scene": str(payload.get("scene", "")).strip(),
        "source": str(payload.get("source", "")).strip(),
        "template_weeks": template_weeks,
        "per_template": per_template,
        "exported_at": payload.get("exported_at"),
        "app_version": payload.get("app_version"),
    }


def unique_name(desired, existing_names):
    """Genera un nombre único agregando ' (importada)' si ya existe."""
    if desired not in existing_names:
        return desired
    candidate = f"{desired} (importada)"
    counter = 2
    while candidate in existing_names:
        candidate = f"{desired} (importada {counter})"
        counter += 1
    return candidate
