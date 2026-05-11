from core.database import get_connection

class CountdownModel:
    def get_all_countdowns(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contadores")
        rows = cursor.fetchall()
        conn.close()
        
        countdowns = []
        for r in rows:
            countdowns.append({
                "id": r[0], "nombre": r[1], "fecha_objetivo": r[2],
                "source_dias": r[3], "source_horas": r[4], 
                "source_minutos": r[5], "source_segundos": r[6],
                "repetir_anual": bool(r[7])
            })
        return countdowns

    def add_countdown(self, data):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO contadores (nombre, fecha_objetivo, source_dias, source_horas, source_minutos, source_segundos, repetir_anual)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (data["nombre"], data["fecha_objetivo"], data["source_dias"], data["source_horas"], 
              data["source_minutos"], data["source_segundos"], int(data["repetir_anual"])))
        conn.commit()
        conn.close()

    def delete_countdown(self, countdown_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contadores WHERE id = ?", (countdown_id,))
        conn.commit()
        conn.close()