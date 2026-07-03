from core.database import get_connection


_SELECT_COLUMNS = (
    "id, nombre_escena, duracion_segundos, orden, "
    "tipo, contenido, ancho, alto, fps, reload_on_activate, keep_session, custom_css, "
    "zoom_pct, pan_x, pan_y, refresh_interval_seg, "
    "video_loop, video_restart_on_activate, video_mute, video_volume_pct, video_offset_seg, "
    "active_days, active_time_start, active_time_end"
)


def _row_to_dict(r):
    return {
        "id": r[0],
        "name": r[1],
        "duration": r[2],
        "order": r[3],
        "tipo": r[4] or "file",
        "contenido": r[5],
        "ancho": r[6] or 1920,
        "alto": r[7] or 1080,
        "fps": r[8] or 30,
        "reload_on_activate": bool(r[9]),
        "keep_session": bool(r[10]) if r[10] is not None else True,
        "custom_css": r[11],
        "zoom_pct": r[12] if r[12] is not None else 100,
        "pan_x": r[13] if r[13] is not None else 0,
        "pan_y": r[14] if r[14] is not None else 0,
        "refresh_interval_seg": r[15] if r[15] is not None else 0,
        "video_loop": bool(r[16]) if r[16] is not None else True,
        "video_restart_on_activate": bool(r[17]) if r[17] is not None else True,
        "video_mute": bool(r[18]) if r[18] is not None else False,
        "video_volume_pct": r[19] if r[19] is not None else 100,
        "video_offset_seg": r[20] if r[20] is not None else 0,
        "active_days": r[21] if r[21] is not None else 127,
        "active_time_start": r[22],
        "active_time_end": r[23],
    }


class SceneModel:
    def get_all_scenes(self):
        """Obtiene todas las escenas ordenadas."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT {_SELECT_COLUMNS} FROM secuencias ORDER BY orden ASC")
        rows = cursor.fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

    def add_scene(self, name, duration, tipo="file", contenido=None,
                  ancho=1920, alto=1080, fps=30,
                  reload_on_activate=False, keep_session=True, custom_css=None,
                  zoom_pct=100, pan_x=0, pan_y=0, refresh_interval_seg=0,
                  video_loop=True, video_restart_on_activate=True,
                  video_mute=False, video_volume_pct=100, video_offset_seg=0,
                  active_days=127, active_time_start=None, active_time_end=None):
        """Añade una nueva escena al final de la lista."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(orden) FROM secuencias")
        max_order = cursor.fetchone()[0]
        next_order = (max_order or 0) + 1

        cursor.execute(
            "INSERT INTO secuencias "
            "(nombre_escena, duracion_segundos, orden, tipo, contenido, "
            "ancho, alto, fps, reload_on_activate, keep_session, custom_css, "
            "zoom_pct, pan_x, pan_y, refresh_interval_seg, "
            "video_loop, video_restart_on_activate, video_mute, video_volume_pct, video_offset_seg, "
            "active_days, active_time_start, active_time_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name, duration, next_order, tipo, contenido,
                int(ancho), int(alto), int(fps),
                1 if reload_on_activate else 0,
                1 if keep_session else 0,
                custom_css if custom_css else None,
                int(zoom_pct), int(pan_x), int(pan_y),
                int(refresh_interval_seg),
                1 if video_loop else 0,
                1 if video_restart_on_activate else 0,
                1 if video_mute else 0,
                int(video_volume_pct),
                int(video_offset_seg),
                int(active_days),
                active_time_start,
                active_time_end,
            ),
        )
        conn.commit()
        conn.close()

    def delete_scene(self, scene_id):
        """Elimina una escena por su ID."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM secuencias WHERE id = ?", (scene_id,))
        conn.commit()
        conn.close()

    def scene_name_exists(self, name):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM secuencias WHERE nombre_escena = ?", (name,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def update_scene_transform(self, scene_id, zoom_pct, pan_x, pan_y):
        """Update quirúrgico de zoom/pan sin tocar los demás campos."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE secuencias SET zoom_pct = ?, pan_x = ?, pan_y = ? WHERE id = ?",
            (int(zoom_pct), int(pan_x), int(pan_y), scene_id),
        )
        conn.commit()
        conn.close()

    def reorder_scene(self, scene_id, direction):
        """Intercambia la escena con su vecina inmediata.

        direction = -1 (mover arriba) o +1 (mover abajo).
        Retorna True si se hizo swap, False si ya estaba en el borde.
        """
        if direction not in (-1, 1):
            return False
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT orden FROM secuencias WHERE id = ?", (scene_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        current_orden = row[0]
        target_orden = current_orden + direction
        cursor.execute("SELECT id FROM secuencias WHERE orden = ?", (target_orden,))
        neighbor = cursor.fetchone()
        if not neighbor:
            conn.close()
            return False
        neighbor_id = neighbor[0]
        cursor.execute("UPDATE secuencias SET orden = ? WHERE id = ?", (target_orden, scene_id))
        cursor.execute("UPDATE secuencias SET orden = ? WHERE id = ?", (current_orden, neighbor_id))
        conn.commit()
        conn.close()
        return True

    def get_scene(self, scene_id):
        """Obtiene una escena por su ID."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_SELECT_COLUMNS} FROM secuencias WHERE id = ?",
            (scene_id,),
        )
        r = cursor.fetchone()
        conn.close()
        if not r:
            return None
        return _row_to_dict(r)

    def update_scene(self, scene_id, name, duration, tipo, contenido,
                     ancho, alto, fps, reload_on_activate, keep_session,
                     custom_css=None, zoom_pct=100, pan_x=0, pan_y=0,
                     refresh_interval_seg=0,
                     video_loop=True, video_restart_on_activate=True,
                     video_mute=False, video_volume_pct=100, video_offset_seg=0,
                     active_days=127, active_time_start=None, active_time_end=None):
        """Actualiza todos los campos de una escena por ID."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE secuencias SET "
            "nombre_escena = ?, duracion_segundos = ?, tipo = ?, contenido = ?, "
            "ancho = ?, alto = ?, fps = ?, reload_on_activate = ?, keep_session = ?, "
            "custom_css = ?, zoom_pct = ?, pan_x = ?, pan_y = ?, refresh_interval_seg = ?, "
            "video_loop = ?, video_restart_on_activate = ?, video_mute = ?, "
            "video_volume_pct = ?, video_offset_seg = ?, "
            "active_days = ?, active_time_start = ?, active_time_end = ? "
            "WHERE id = ?",
            (
                name, duration, tipo, contenido,
                int(ancho), int(alto), int(fps),
                1 if reload_on_activate else 0,
                1 if keep_session else 0,
                custom_css if custom_css else None,
                int(zoom_pct), int(pan_x), int(pan_y),
                int(refresh_interval_seg),
                1 if video_loop else 0,
                1 if video_restart_on_activate else 0,
                1 if video_mute else 0,
                int(video_volume_pct),
                int(video_offset_seg),
                int(active_days),
                active_time_start,
                active_time_end,
                scene_id,
            ),
        )
        conn.commit()
        conn.close()
