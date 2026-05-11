from core.database import get_connection

class SceneModel:
    def get_all_scenes(self):
        """Obtiene todas las escenas ordenadas."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre_escena, duracion_segundos, orden FROM secuencias ORDER BY orden ASC")
        rows = cursor.fetchall()
        conn.close()
        # Retornamos una lista de diccionarios para que sea fácil de leer en la vista
        return [{"id": r[0], "name": r[1], "duration": r[2], "order": r[3]} for r in rows]

    def add_scene(self, name, duration):
        """Añade una nueva escena al final de la lista."""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Calcular el siguiente número de orden
        cursor.execute("SELECT MAX(orden) FROM secuencias")
        max_order = cursor.fetchone()[0]
        next_order = (max_order or 0) + 1
        
        cursor.execute(
            "INSERT INTO secuencias (nombre_escena, duracion_segundos, orden) VALUES (?, ?, ?)",
            (name, duration, next_order)
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