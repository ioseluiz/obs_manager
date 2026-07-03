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
