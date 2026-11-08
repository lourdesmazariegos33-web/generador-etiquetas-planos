"""Persistencia SQLite local y reserva atómica de versiones por proyecto."""
import json
import os
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from etiquetas import Registro, clean
import historial_git

DB = Path(os.environ.get("ETIQUETAS_DB", Path(__file__).resolve().parent / "datos" / "proyectos.sqlite3"))


def clave(proyecto):
    return unicodedata.normalize("NFC", clean(proyecto, "Proyecto", 80)).casefold()


def conectar():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=15)
    conn.execute('''CREATE TABLE IF NOT EXISTS versiones (
        proyecto_clave TEXT NOT NULL, version INTEGER NOT NULL,
        datos TEXT NOT NULL, creado TEXT NOT NULL,
        PRIMARY KEY (proyecto_clave, version))''')
    return conn


def siguiente(proyecto):
    if not proyecto.strip():
        return 1
    if historial_git.configuracion()[0]:
        return historial_git.siguiente(proyecto, clave)
    with closing(conectar()) as conn:
        last = conn.execute('SELECT MAX(version) FROM versiones WHERE proyecto_clave=?', (clave(proyecto),)).fetchone()[0]
    return (last or 0) + 1


def generar_y_guardar(proyecto, fecha, responsable, copias, exportador):
    """Si falla la exportación, la versión no se consume. Descargas no crean versiones."""
    if historial_git.configuracion()[0]:
        return historial_git.generar_y_guardar(proyecto, fecha, responsable, copias, exportador, clave)
    conn = conectar()
    try:
        conn.execute('BEGIN IMMEDIATE')
        last = conn.execute('SELECT MAX(version) FROM versiones WHERE proyecto_clave=?', (clave(proyecto),)).fetchone()[0]
        record = Registro.crear(proyecto, (last or 0) + 1, fecha, responsable)
        files = exportador(record, copias)
        conn.execute('INSERT INTO versiones VALUES (?, ?, ?, ?)',
                     (clave(proyecto), record.version, record.codigo, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return record, files
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def listar():
    if historial_git.configuracion()[0]:
        return historial_git.listar()
    with closing(conectar()) as conn:
        values = conn.execute('SELECT datos FROM versiones ORDER BY creado DESC').fetchall()
    return [json.loads(row[0]) for row in values]


def permanente():
    return bool(historial_git.configuracion()[0])
