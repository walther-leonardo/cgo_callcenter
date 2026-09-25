from __future__ import annotations

import sqlite3

from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    """
    Abre conexión a SQLite y garantiza que exista la carpeta.
    """

    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return sqlite3.connect(
        DATABASE_PATH
    )


def inicializar_base() -> None:
    """
    Crea las tablas iniciales del proyecto.
    """

    with get_connection() as conn:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_hora_corte TEXT NOT NULL,
                archivo_origen TEXT NOT NULL,
                cantidad_citas INTEGER NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS citas_snapshot (
                snapshot_id INTEGER NOT NULL,
                id_cita INTEGER NOT NULL,
                estatus_cita TEXT,
                motivo_visita TEXT,
                fecha_programada TEXT,
                hora_programada TEXT,
                origen_cita TEXT,
                persona_agenda TEXT,
                fecha_creacion TEXT,
                nombre TEXT,
                celular TEXT,
                asesor_servicio TEXT,
                modelo TEXT,
                placa TEXT,
                kilometraje REAL,

                PRIMARY KEY (
                    snapshot_id,
                    id_cita
                ),

                FOREIGN KEY (
                    snapshot_id
                )
                REFERENCES snapshots (
                    snapshot_id
                )
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cambios_snapshot (
                cambio_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                snapshot_anterior_id INTEGER,
                id_cita INTEGER NOT NULL,
                tipo_cambio TEXT NOT NULL,
                campo TEXT,
                valor_anterior TEXT,
                valor_actual TEXT,

                FOREIGN KEY (
                    snapshot_id
                )
                REFERENCES snapshots (
                    snapshot_id
                )
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metricas_snapshot (
                metrica_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                metrica TEXT NOT NULL,
                dimension TEXT NOT NULL,
                segmento TEXT NOT NULL,
                valor REAL NOT NULL,

                FOREIGN KEY (
                    snapshot_id
                )
                REFERENCES snapshots (
                    snapshot_id
                )
            )
            """
        )

        conn.commit()