from core.database import get_connection


COLUMNS = (
    "id", "nombre", "fecha_objetivo",
    "source_dias", "source_horas", "source_minutos", "source_segundos",
    "repetir_anual", "escena",
    "pos_x_pct", "pos_y_pct", "spread_pct", "scale_pct",
)

LAYOUT_DEFAULTS = {
    "pos_x_pct": 50,
    "pos_y_pct": 50,
    "spread_pct": 100,
    "scale_pct": 100,
}


class CountdownModel:
    def get_all_countdowns(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT {', '.join(COLUMNS)} FROM contadores")
        rows = cursor.fetchall()
        conn.close()

        countdowns = []
        for r in rows:
            item = dict(zip(COLUMNS, r))
            item["repetir_anual"] = bool(item["repetir_anual"])
            item["escena"] = item["escena"] or ""
            for k, dflt in LAYOUT_DEFAULTS.items():
                if item.get(k) is None:
                    item[k] = dflt
            countdowns.append(item)
        return countdowns

    def add_countdown(self, data):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO contadores (nombre, fecha_objetivo, source_dias, source_horas,
                                    source_minutos, source_segundos, repetir_anual, escena)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data["nombre"], data["fecha_objetivo"], data["source_dias"], data["source_horas"],
              data["source_minutos"], data["source_segundos"],
              int(data["repetir_anual"]), data.get("escena", "") or ""))
        conn.commit()
        conn.close()

    def update_countdown(self, countdown_id, data):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE contadores
            SET nombre = ?, fecha_objetivo = ?, source_dias = ?, source_horas = ?,
                source_minutos = ?, source_segundos = ?, repetir_anual = ?, escena = ?
            WHERE id = ?
        ''', (data["nombre"], data["fecha_objetivo"], data["source_dias"],
              data["source_horas"], data["source_minutos"], data["source_segundos"],
              int(data["repetir_anual"]), data.get("escena", "") or "",
              countdown_id))
        conn.commit()
        conn.close()

    def update_layout(self, countdown_id, pos_x_pct, pos_y_pct, spread_pct, scale_pct):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE contadores
            SET pos_x_pct = ?, pos_y_pct = ?, spread_pct = ?, scale_pct = ?
            WHERE id = ?
        ''', (int(pos_x_pct), int(pos_y_pct), int(spread_pct), int(scale_pct),
              countdown_id))
        conn.commit()
        conn.close()

    def delete_countdown(self, countdown_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contadores WHERE id = ?", (countdown_id,))
        conn.commit()
        conn.close()
