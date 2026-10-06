
import sqlite3
from config import DB_PATH

def obtener_conexion():
    """Crea una conexión limpia con la base de datos."""
    return sqlite3.connect(DB_PATH)

def inicializar_db():
    """Crea la tabla necesaria si no existe en el disco rígido."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS paginas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archivo TEXT,
                pagina INTEGER,
                texto TEXT
            )
        ''')
        conn.commit()

def obtener_archivos_indexados():
    """Devuelve un conjunto con los nombres de archivos ya procesados."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT archivo FROM paginas")
        return {row[0] for row in cursor.fetchall()}

def guardar_pagina(archivo, num_pagina, texto):
    """Guarda el texto de una página individual en la base de datos."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO paginas (archivo, pagina, texto) VALUES (?, ?, ?)",
            (archivo, num_pagina, texto)
        )
        conn.commit()

def obtener_todas_las_paginas():
    """Recupera todas las páginas guardadas para alimentar al buscador."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, archivo, pagina, texto FROM paginas")
        return cursor.fetchall()
