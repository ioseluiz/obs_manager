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

    # Tabla para canales multi-salida (feature Fase 1).
    # Cada fila = 1 destino UDP independiente. Su `nombre` es también el nombre
    # de la escena contenedora en OBS (el filtro source_record_filter va anclado
    # a esa escena, con stream_mode=1 apuntando a `url_destino`).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS canales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            url_destino TEXT NOT NULL,
            encoder TEXT NOT NULL DEFAULT 'x264',
            bitrate_kbps INTEGER NOT NULL DEFAULT 2500,
            habilitado INTEGER NOT NULL DEFAULT 1,
            audio_track INTEGER NOT NULL DEFAULT 0,
            orden INTEGER NOT NULL DEFAULT 0,
            descripcion TEXT,
            creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
            modificado_en TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migración: resolución y fps por canal (config por-salida — Opción B de
    # Fase 2). Sin estos, todos los canales cuentan como 1080p30 para el
    # validador. Con estos, cada canal declara su preset explícito y el
    # validador computa el costo real via budget_cost().
    _add_column_if_missing(cursor, "canales", "output_width", "INTEGER DEFAULT 1920")
    _add_column_if_missing(cursor, "canales", "output_height", "INTEGER DEFAULT 1080")
    _add_column_if_missing(cursor, "canales", "output_fps", "INTEGER DEFAULT 30")

    # Playlist de un canal: referencias a escenas existentes de `secuencias`.
    # No duplica contenido — cada item es un puntero al secuencia_id.
    # Cascade delete manual desde CanalModel (SQLite en este proyecto no fuerza FKs).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS canal_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canal_id INTEGER NOT NULL,
            secuencia_id INTEGER NOT NULL,
            orden INTEGER NOT NULL,
            duracion_override_seg INTEGER,
            FOREIGN KEY (canal_id) REFERENCES canales(id),
            FOREIGN KEY (secuencia_id) REFERENCES secuencias(id)
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_canal_items_canal "
        "ON canal_items(canal_id, orden)"
    )

    conn.commit()
    conn.close()


def _add_column_if_missing(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")