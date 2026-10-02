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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cloudtalk_llamadas (
                id_evento TEXT PRIMARY KEY,

                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                fecha_hora TEXT NOT NULL,

                tipo_llamada TEXT NOT NULL,
                direccion TEXT NOT NULL,
                estado TEXT NOT NULL,

                duracion TEXT,
                duracion_segundos INTEGER NOT NULL,

                contacto TEXT,
                telefono_contacto TEXT,

                agente TEXT,
                canal_agente TEXT,
                telefono_agente TEXT,

                fecha_primera_carga TEXT NOT NULL,
                fecha_ultima_carga TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_cloudtalk_fecha_hora
            ON cloudtalk_llamadas (
                fecha_hora
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_cloudtalk_agente_fecha
            ON cloudtalk_llamadas (
                agente,
                fecha
            )
            """
        )
        
        conn.commit()


def guardar_llamadas_cloudtalk(
    llamadas,
) -> tuple[int, int]:
    """
    Inserta o sincroniza llamadas provenientes de CloudTalk.

    Usa id_evento como clave estable.

    Devuelve:
        (nuevas, sincronizadas)
    """

    if llamadas.empty:
        return 0, 0

    columnas = [
        "id_evento",
        "fecha",
        "hora",
        "fecha_hora",
        "tipo_llamada",
        "direccion",
        "estado",
        "duracion",
        "duracion_segundos",
        "contacto",
        "telefono_contacto",
        "agente",
        "canal_agente",
        "telefono_agente",
        "fecha_primera_carga",
        "fecha_ultima_carga",
    ]

    faltantes = [
        columna
        for columna in columnas
        if columna not in llamadas.columns
    ]

    if faltantes:
        raise ValueError(
            "Faltan columnas para guardar CloudTalk: "
            f"{faltantes}"
        )

    registros = (
        llamadas[
            columnas
        ]
        .where(
            llamadas[
                columnas
            ].notna(),
            None,
        )
        .to_dict(
            orient="records"
        )
    )

    ids_evento = [
        registro[
            "id_evento"
        ]
        for registro in registros
    ]

    nuevas = 0

    with get_connection() as conn:

        if ids_evento:

            placeholders = ",".join(
                "?"
                for _ in ids_evento
            )

            existentes = conn.execute(
                f"""
                SELECT id_evento
                FROM cloudtalk_llamadas
                WHERE id_evento IN (
                    {placeholders}
                )
                """,
                ids_evento,
            ).fetchall()

            ids_existentes = {
                fila[0]
                for fila in existentes
            }

            nuevas = sum(
                id_evento
                not in ids_existentes
                for id_evento in ids_evento
            )

        conn.executemany(
            """
            INSERT INTO cloudtalk_llamadas (
                id_evento,
                fecha,
                hora,
                fecha_hora,
                tipo_llamada,
                direccion,
                estado,
                duracion,
                duracion_segundos,
                contacto,
                telefono_contacto,
                agente,
                canal_agente,
                telefono_agente,
                fecha_primera_carga,
                fecha_ultima_carga
            )
            VALUES (
                :id_evento,
                :fecha,
                :hora,
                :fecha_hora,
                :tipo_llamada,
                :direccion,
                :estado,
                :duracion,
                :duracion_segundos,
                :contacto,
                :telefono_contacto,
                :agente,
                :canal_agente,
                :telefono_agente,
                :fecha_primera_carga,
                :fecha_ultima_carga
            )

            ON CONFLICT (
                id_evento
            )

            DO UPDATE SET
                fecha =
                    excluded.fecha,

                hora =
                    excluded.hora,

                fecha_hora =
                    excluded.fecha_hora,

                tipo_llamada =
                    excluded.tipo_llamada,

                direccion =
                    excluded.direccion,

                estado =
                    excluded.estado,

                duracion =
                    excluded.duracion,

                duracion_segundos =
                    excluded.duracion_segundos,

                contacto =
                    excluded.contacto,

                telefono_contacto =
                    excluded.telefono_contacto,

                agente =
                    excluded.agente,

                canal_agente =
                    excluded.canal_agente,

                telefono_agente =
                    excluded.telefono_agente,

                fecha_ultima_carga =
                    excluded.fecha_ultima_carga
            """,
            registros,
        )

        conn.commit()

    sincronizadas = (
        len(registros)
        - nuevas
    )

    return (
        nuevas,
        sincronizadas,
    )


