import sqlite3
import os

DB_PATH = "obs_manager.db"

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
    
    conn.commit()
    conn.close()