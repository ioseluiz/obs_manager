"""CRUD headless de canales multi-salida y sus playlists.

Un `canal` representa un destino UDP independiente. Su `nombre` es también el
nombre de la escena OBS contenedora que tendrá anclado el filtro
`source_record_filter` (stream_mode=1 → url_destino). Rotación adentro del
canal = alternar `SetSceneItemEnabled` sobre `canal_items`; nunca
`change_scene`.

Esta capa NO habla con OBS — es puramente persistencia. La aplicación a OBS
vive en fases posteriores (1c: CanalController).
"""
from __future__ import annotations

from typing import Any

from core.database import get_connection


_CANAL_COLUMNS = (
    "id, nombre, url_destino, encoder, bitrate_kbps, habilitado, "
    "audio_track, orden, descripcion, creado_en, modificado_en"
)

_ITEM_COLUMNS = (
    "id, canal_id, secuencia_id, orden, duracion_override_seg"
)


def _canal_row_to_dict(r) -> dict[str, Any]:
    return {
        "id": r[0],
        "nombre": r[1],
        "url_destino": r[2],
        "encoder": r[3],
        "bitrate_kbps": r[4],
        "habilitado": bool(r[5]),
        "audio_track": r[6],
        "orden": r[7],
        "descripcion": r[8],
        "creado_en": r[9],
        "modificado_en": r[10],
    }


def _item_row_to_dict(r) -> dict[str, Any]:
    return {
        "id": r[0],
        "canal_id": r[1],
        "secuencia_id": r[2],
        "orden": r[3],
        "duracion_override_seg": r[4],
    }


class CanalModel:
    # ------------------------------------------------------------------
    # Canales
    # ------------------------------------------------------------------

    def get_all_canales(self) -> list[dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {_CANAL_COLUMNS} FROM canales ORDER BY orden ASC, id ASC")
            return [_canal_row_to_dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_canal(self, canal_id: int) -> dict | None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {_CANAL_COLUMNS} FROM canales WHERE id = ?", (canal_id,))
            r = cursor.fetchone()
            return _canal_row_to_dict(r) if r else None
        finally:
            conn.close()

    def get_canal_by_nombre(self, nombre: str) -> dict | None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {_CANAL_COLUMNS} FROM canales WHERE nombre = ?", (nombre,))
            r = cursor.fetchone()
            return _canal_row_to_dict(r) if r else None
        finally:
            conn.close()

    def canal_nombre_exists(self, nombre: str) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM canales WHERE nombre = ?", (nombre,))
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def add_canal(self, nombre: str, url_destino: str, encoder: str = "x264",
                  bitrate_kbps: int = 2500, habilitado: bool = True,
                  audio_track: int = 0, descripcion: str | None = None) -> int:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(orden), 0) + 1 FROM canales")
            next_order = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO canales "
                "(nombre, url_destino, encoder, bitrate_kbps, habilitado, "
                "audio_track, orden, descripcion) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    nombre, url_destino, encoder, int(bitrate_kbps),
                    1 if habilitado else 0, int(audio_track), int(next_order),
                    descripcion,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def update_canal(self, canal_id: int, nombre: str, url_destino: str,
                     encoder: str, bitrate_kbps: int, habilitado: bool,
                     audio_track: int = 0, descripcion: str | None = None) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE canales SET "
                "nombre = ?, url_destino = ?, encoder = ?, bitrate_kbps = ?, "
                "habilitado = ?, audio_track = ?, descripcion = ?, "
                "modificado_en = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (
                    nombre, url_destino, encoder, int(bitrate_kbps),
                    1 if habilitado else 0, int(audio_track), descripcion,
                    canal_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def set_habilitado(self, canal_id: int, habilitado: bool) -> None:
        """Toggle rápido sin tocar el resto de campos."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE canales SET habilitado = ?, "
                "modificado_en = CURRENT_TIMESTAMP WHERE id = ?",
                (1 if habilitado else 0, canal_id),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_canal(self, canal_id: int) -> None:
        """Elimina el canal y todos sus items (cascade manual)."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM canal_items WHERE canal_id = ?", (canal_id,))
            cursor.execute("DELETE FROM canales WHERE id = ?", (canal_id,))
            conn.commit()
        finally:
            conn.close()

    def reorder_canal(self, canal_id: int, direction: int) -> bool:
        """Intercambia orden con el canal vecino inmediato.

        direction: -1 sube, +1 baja. True si hizo swap, False si estaba en el borde.
        """
        if direction not in (-1, 1):
            return False
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT orden FROM canales WHERE id = ?", (canal_id,))
            row = cursor.fetchone()
            if not row:
                return False
            current = row[0]
            target = current + direction
            cursor.execute("SELECT id FROM canales WHERE orden = ?", (target,))
            neighbor = cursor.fetchone()
            if not neighbor:
                return False
            neighbor_id = neighbor[0]
            cursor.execute("UPDATE canales SET orden = ? WHERE id = ?", (target, canal_id))
            cursor.execute("UPDATE canales SET orden = ? WHERE id = ?", (current, neighbor_id))
            conn.commit()
            return True
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Playlist (canal_items)
    # ------------------------------------------------------------------

    def get_items(self, canal_id: int) -> list[dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {_ITEM_COLUMNS} FROM canal_items "
                "WHERE canal_id = ? ORDER BY orden ASC, id ASC",
                (canal_id,),
            )
            return [_item_row_to_dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def add_item(self, canal_id: int, secuencia_id: int,
                 duracion_override_seg: int | None = None) -> int:
        """Añade un item al final de la playlist del canal."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(MAX(orden), 0) + 1 FROM canal_items WHERE canal_id = ?",
                (canal_id,),
            )
            next_order = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO canal_items "
                "(canal_id, secuencia_id, orden, duracion_override_seg) "
                "VALUES (?, ?, ?, ?)",
                (
                    canal_id, secuencia_id, int(next_order),
                    int(duracion_override_seg) if duracion_override_seg is not None else None,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def update_item_duracion(self, item_id: int, duracion_override_seg: int | None) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE canal_items SET duracion_override_seg = ? WHERE id = ?",
                (
                    int(duracion_override_seg) if duracion_override_seg is not None else None,
                    item_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def remove_item(self, item_id: int) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM canal_items WHERE id = ?", (item_id,))
            conn.commit()
        finally:
            conn.close()

    def reorder_item(self, item_id: int, direction: int) -> bool:
        """Swap con el item vecino dentro del mismo canal."""
        if direction not in (-1, 1):
            return False
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT canal_id, orden FROM canal_items WHERE id = ?",
                (item_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            canal_id, current = row
            target = current + direction
            cursor.execute(
                "SELECT id FROM canal_items WHERE canal_id = ? AND orden = ?",
                (canal_id, target),
            )
            neighbor = cursor.fetchone()
            if not neighbor:
                return False
            neighbor_id = neighbor[0]
            cursor.execute(
                "UPDATE canal_items SET orden = ? WHERE id = ?", (target, item_id)
            )
            cursor.execute(
                "UPDATE canal_items SET orden = ? WHERE id = ?", (current, neighbor_id)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def clear_items(self, canal_id: int) -> None:
        """Vacía toda la playlist de un canal (sin borrar el canal)."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM canal_items WHERE canal_id = ?", (canal_id,))
            conn.commit()
        finally:
            conn.close()
