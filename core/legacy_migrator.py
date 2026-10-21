"""Migracion del rotador legacy (Canal Principal) a un canal regular.

Antes de la unificacion, el "Canal Principal" era un rotador especial
que cambiaba el Program global de OBS via SetCurrentProgramScene y
transmitia con StartRecord + Custom Output FFmpeg (configurado
manualmente en OBS Settings → Output). Las escenas que rotaba vivian
en la tabla `secuencias` y se gestionaban en la "Biblioteca de Escenas".

Con la unificacion, todo pasa a canales con filtro Source Record por
canal. Este migrador toma las secuencias existentes y las agrupa en
un canal nuevo "Canal Legacy" con filtro udp_out apuntando a una URL
UDP configurable. Las secuencias no se tocan — se mantienen como pool
reusable.

El flujo tipico:

    from core.legacy_migrator import migrate_legacy_to_canal, needs_migration

    if needs_migration(scene_model, settings_model):
        ok, canal_id, msg = migrate_legacy_to_canal(
            canal_model, scene_model, canal_controller,
            canal_name="Canal Legacy",
            udp_url="udp://127.0.0.1:9001",
        )
        if ok:
            settings_model.set_flag("LEGACY_MIGRATION_DONE", "true")

Es idempotente a nivel de secuencias (no las duplica), pero NO es
idempotente a nivel de canal — llamar dos veces crea dos canales
nuevos con los mismos items. El flag LEGACY_MIGRATION_DONE evita eso.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def needs_migration(scene_model, settings_model) -> bool:
    """True si corresponde ofrecer el wizard de migracion.

    Criterios:
    - Hay secuencias en la Biblioteca (`scene_model.get_all_scenes()`
      no vacio).
    - El flag `LEGACY_MIGRATION_DONE` no esta marcado como "true" en
      el .env.

    Nota: no verifica si ya existe un "Canal Legacy" — eso lo hace el
    flag. Si el user quiere re-migrar (ej. tras borrar el canal
    legacy), tiene que limpiar el flag manualmente.
    """
    try:
        scenes = scene_model.get_all_scenes() or []
    except Exception as e:
        log.debug("needs_migration: get_all_scenes fallo: %s", e)
        return False
    if not scenes:
        return False
    try:
        flag = settings_model.get_flag("LEGACY_MIGRATION_DONE", "false")
    except Exception:
        flag = "false"
    return str(flag).lower() != "true"


def migrate_legacy_to_canal(
    canal_model,
    scene_model,
    canal_controller,
    canal_name: str = "Canal Legacy",
    udp_url: str = "udp://127.0.0.1:9001",
    secuencia_ids: list[int] | None = None,
) -> tuple[bool, int | None, str]:
    """Crea un canal nuevo que agrupa las secuencias existentes como
    items.

    Pasos:
    1. Crea un `canales` row con `nombre=canal_name` y
       `url_destino=udp_url`.
    2. Para cada `secuencia_id` listada (o todas las secuencias si
       `secuencia_ids=None`), crea un `canal_items` apuntando a esa
       secuencia (orden incremental).
    3. Llama `canal_controller.apply_canal(canal_id)` para crear la
       escena contenedora + filtro `udp_out` en OBS.

    Devuelve `(ok, canal_id, msg)`:
    - `ok=True`: el canal se creo y se aplico. `canal_id` es el id.
    - `ok=False`: fallo en algun paso. `canal_id` puede ser None (si
      no llego a crear) o el id del canal huerfano (si fallo apply).
    """
    try:
        all_scenes = scene_model.get_all_scenes() or []
    except Exception as e:
        return False, None, f"No se pudo leer secuencias: {e}"

    if secuencia_ids is None:
        secuencia_ids = [int(s["id"]) for s in all_scenes]

    if not secuencia_ids:
        return False, None, "No hay secuencias para migrar."

    # Validacion: no permitir nombre vacio o URL vacia.
    canal_name = (canal_name or "").strip()
    udp_url = (udp_url or "").strip()
    if not canal_name:
        return False, None, "El nombre del canal no puede estar vacio."
    if not udp_url:
        return False, None, "La URL UDP no puede estar vacia."

    try:
        canal_id = canal_model.add_canal(
            nombre=canal_name,
            url_destino=udp_url,
            habilitado=True,
        )
    except Exception as e:
        return False, None, f"No se pudo crear el canal: {e}"

    log.info("Migrator: canal '%s' creado (id=%d) para %d secuencias",
             canal_name, canal_id, len(secuencia_ids))

    added = 0
    for sid in secuencia_ids:
        try:
            canal_model.add_item(canal_id, int(sid))
            added += 1
        except Exception as e:
            log.warning(
                "Migrator: add_item(canal=%d, sec=%d) fallo: %s",
                canal_id, sid, e,
            )

    log.info("Migrator: %d/%d items agregados", added, len(secuencia_ids))

    # Apply en OBS (crea escena contenedora + scene items + filtro).
    try:
        ok, msg = canal_controller.apply_canal(canal_id)
    except Exception as e:
        return False, canal_id, (
            f"Canal {canal_name} creado en BD pero apply_canal lanzo: {e}"
        )

    if not ok:
        return False, canal_id, (
            f"Canal {canal_name} creado en BD pero apply_canal fallo: {msg}"
        )

    return True, canal_id, (
        f"Canal '{canal_name}' creado con {added} items y aplicado en OBS."
    )
