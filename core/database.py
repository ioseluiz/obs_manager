import sqlite3
from core.paths import get_app_data_dir

DB_PATH = str(get_app_data_dir() / "obs_manager.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Tabla para el rotador de escenas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS secuencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_escena TEXT NOT NULL,
            duracion_segundos INTEGER NOT NULL,
            orden INTEGER NOT NULL
        )
    ''')

    # Migración: nuevas columnas para escenas web / dashboards
    _add_column_if_missing(cursor, "secuencias", "tipo", "TEXT DEFAULT 'file'")
    _add_column_if_missing(cursor, "secuencias", "contenido", "TEXT")
    _add_column_if_missing(cursor, "secuencias", "ancho", "INTEGER DEFAULT 1920")
    _add_column_if_missing(cursor, "secuencias", "alto", "INTEGER DEFAULT 1080")
    _add_column_if_missing(cursor, "secuencias", "fps", "INTEGER DEFAULT 30")
    _add_column_if_missing(cursor, "secuencias", "reload_on_activate", "INTEGER DEFAULT 0")
    _add_column_if_missing(cursor, "secuencias", "keep_session", "INTEGER DEFAULT 1")
    _add_column_if_missing(cursor, "secuencias", "custom_css", "TEXT")
    _add_column_if_missing(cursor, "secuencias", "zoom_pct", "INTEGER DEFAULT 100")
    _add_column_if_missing(cursor, "secuencias", "pan_x", "INTEGER DEFAULT 0")
    _add_column_if_missing(cursor, "secuencias", "pan_y", "INTEGER DEFAULT 0")
    _add_column_if_missing(cursor, "secuencias", "refresh_interval_seg", "INTEGER DEFAULT 0")
    _add_column_if_missing(cursor, "secuencias", "video_loop", "INTEGER DEFAULT 1")
    _add_column_if_missing(cursor, "secuencias", "video_restart_on_activate", "INTEGER DEFAULT 1")
    _add_column_if_missing(cursor, "secuencias", "video_mute", "INTEGER DEFAULT 0")
    _add_column_if_missing(cursor, "secuencias", "video_volume_pct", "INTEGER DEFAULT 100")
    _add_column_if_missing(cursor, "secuencias", "video_offset_seg", "INTEGER DEFAULT 0")
    _add_column_if_missing(cursor, "secuencias", "active_days", "INTEGER DEFAULT 127")
    _add_column_if_missing(cursor, "secuencias", "active_time_start", "TEXT")
    _add_column_if_missing(cursor, "secuencias", "active_time_end", "TEXT")

    # Nueva Tabla para Contadores de Fecha
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            fecha_objetivo TEXT NOT NULL,
            source_dias TEXT,
            source_horas TEXT,
            source_minutos TEXT,
            source_segundos TEXT,
            repetir_anual INTEGER DEFAULT 0
        )
    ''')

    # Migración: escena OBS asociada al contador (dónde viven sus text sources)
    _add_column_if_missing(cursor, "contadores", "escena", "TEXT DEFAULT ''")
    # Migración: layout por contador (posición y tamaño de la fila D H M s)
    _add_column_if_missing(cursor, "contadores", "pos_x_pct", "INTEGER DEFAULT 50")
    _add_column_if_missing(cursor, "contadores", "pos_y_pct", "INTEGER DEFAULT 50")
    _add_column_if_missing(cursor, "contadores", "spread_pct", "INTEGER DEFAULT 100")
    _add_column_if_missing(cursor, "contadores", "scale_pct", "INTEGER DEFAULT 100")

    conn.commit()
    conn.close()


def _add_column_if_missing(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")