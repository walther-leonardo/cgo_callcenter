from __future__ import annotations

import pandas as pd
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
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
            CREATE TABLE IF NOT EXISTS citas_maestro (
                id_cita INTEGER PRIMARY KEY,

                primer_snapshot_id INTEGER NOT NULL,
                primera_deteccion TEXT NOT NULL,

                ultimo_snapshot_id INTEGER NOT NULL,
                ultima_deteccion TEXT NOT NULL,

                presente_en_ultimo_snapshot INTEGER NOT NULL,

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

                FOREIGN KEY (
                    primer_snapshot_id
                )
                REFERENCES snapshots (
                    snapshot_id
                ),

                FOREIGN KEY (
                    ultimo_snapshot_id
                )
                REFERENCES snapshots (
                    snapshot_id
                )
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS citas_primera_deteccion (
                id_cita INTEGER PRIMARY KEY,

                snapshot_id INTEGER NOT NULL,
                fecha_detectada TEXT NOT NULL,

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
            CREATE INDEX IF NOT EXISTS
            idx_citas_primera_deteccion_fecha
            ON citas_primera_deteccion (
                fecha_detectada
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_citas_primera_deteccion_agente_fecha
            ON citas_primera_deteccion (
                persona_agenda,
                fecha_detectada
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

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_citas_maestro_primera_deteccion
            ON citas_maestro (
                primera_deteccion
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_citas_maestro_agente_deteccion
            ON citas_maestro (
                persona_agenda,
                primera_deteccion
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_citas_maestro_presente
            ON citas_maestro (
                presente_en_ultimo_snapshot
            )
            """
        )

        # ====================================================
        # OVERRIDES MANUALES — MATCHING DE EFECTIVIDAD
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS
            efectividad_matching_overrides (
                presencia_id TEXT PRIMARY KEY,

                id_cita_elegida TEXT NOT NULL,
                appointment_number INTEGER,

                persona_creditada TEXT NOT NULL,

                canal_decision TEXT NOT NULL,
                usuario_decision TEXT NOT NULL,

                motivo TEXT,

                fecha_creacion TEXT NOT NULL,
                fecha_actualizacion TEXT NOT NULL,

                activo INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_efectividad_matching_override_cita
            ON efectividad_matching_overrides (
                id_cita_elegida
            )
            """
        )

        # ====================================================
        # CASOS PENDIENTES — REVISIÓN DE EFECTIVIDAD
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS
            efectividad_conflictos_pendientes (
                presencia_id TEXT PRIMARY KEY,

                placa TEXT NOT NULL,
                fecha_visita TEXT NOT NULL,
                nivel INTEGER NOT NULL,

                fecha_detectada TEXT NOT NULL,
                fecha_actualizacion TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS
            efectividad_conflicto_candidatas (
                presencia_id TEXT NOT NULL,
                id_cita TEXT NOT NULL,

                appointment_number INTEGER,
                agente TEXT,
                fecha_cita TEXT,
                fecha_hora_cita TEXT,
                motivos TEXT,
                diferencia_dias INTEGER,

                PRIMARY KEY (
                    presencia_id,
                    id_cita
                ),

                FOREIGN KEY (
                    presencia_id
                )
                REFERENCES efectividad_conflictos_pendientes (
                    presencia_id
                )
                ON DELETE CASCADE
            )
            """
        )

        # ====================================================
        # DETALLE MAESTRO — EFECTIVIDAD
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS efectividad_detalle (
                id_cita TEXT PRIMARY KEY,

                appointment_number INTEGER,
                fecha_cita TEXT NOT NULL,
                hora_cita TEXT,

                placa_normalizada TEXT,
                motivos TEXT,
                grupo_servicio TEXT,

                agente TEXT,
                persona_creditada TEXT,
                canal_agenda TEXT,

                status TEXT,

                fecha_visita TEXT,
                es_efectiva INTEGER NOT NULL,

                nivel TEXT,
                diferencia_dias INTEGER,

                resultado_efectividad TEXT,
                confirmacion_presencia TEXT,

                numeros_cotizacion TEXT,
                numeros_orden TEXT,

                tipo_asignacion TEXT,
                requiere_revision_manual INTEGER NOT NULL,

                criterio_matching TEXT,
                presencia_id TEXT,

                fecha_actualizacion TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_efectividad_detalle_fecha
            ON efectividad_detalle (
                fecha_cita
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_efectividad_detalle_agente
            ON efectividad_detalle (
                persona_creditada,
                fecha_cita
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


# ============================================================
# OVERRIDES MANUALES — MATCHING DE EFECTIVIDAD
# ============================================================

ZONA_LIMA = ZoneInfo(
    "America/Lima"
)


def obtener_override_matching(
    presencia_id: str,
) -> dict | None:
    """
    Recupera la decisión manual activa asociada
    a una presencia.

    Devuelve None cuando no existe decisión activa.
    """

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        fila = conn.execute(
            """
            SELECT
                presencia_id,
                id_cita_elegida,
                appointment_number,
                persona_creditada,
                canal_decision,
                usuario_decision,
                motivo,
                fecha_creacion,
                fecha_actualizacion,
                activo

            FROM efectividad_matching_overrides

            WHERE presencia_id = ?
              AND activo = 1
            """,
            (
                presencia_id,
            ),
        ).fetchone()

    if fila is None:
        return None

    return dict(
        fila
    )


def guardar_override_matching(
    presencia_id: str,
    id_cita_elegida: str,
    appointment_number,
    persona_creditada: str,
    canal_decision: str,
    usuario_decision: str,
    motivo: str | None = None,
) -> None:
    """
    Guarda o actualiza la decisión manual correspondiente
    a una presencia ambigua.

    Solo puede existir una decisión activa por presencia.
    """

    ahora = datetime.now(
        ZONA_LIMA
    ).isoformat(
        timespec="seconds"
    )

    with get_connection() as conn:

        conn.execute(
            """
            INSERT INTO efectividad_matching_overrides (
                presencia_id,
                id_cita_elegida,
                appointment_number,
                persona_creditada,
                canal_decision,
                usuario_decision,
                motivo,
                fecha_creacion,
                fecha_actualizacion,
                activo
            )

            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                1
            )

            ON CONFLICT (
                presencia_id
            )

            DO UPDATE SET
                id_cita_elegida =
                    excluded.id_cita_elegida,

                appointment_number =
                    excluded.appointment_number,

                persona_creditada =
                    excluded.persona_creditada,

                canal_decision =
                    excluded.canal_decision,

                usuario_decision =
                    excluded.usuario_decision,

                motivo =
                    excluded.motivo,

                fecha_actualizacion =
                    excluded.fecha_actualizacion,

                activo = 1
            """,
            (
                presencia_id,
                str(
                    id_cita_elegida
                ),
                (
                    int(
                        appointment_number
                    )
                    if appointment_number
                    is not None
                    else None
                ),
                persona_creditada,
                canal_decision,
                usuario_decision,
                motivo,
                ahora,
                ahora,
            ),
        )

        conn.commit()


def desactivar_override_matching(
    presencia_id: str,
) -> None:
    """
    Desactiva una decisión manual sin borrar
    su registro histórico.
    """

    ahora = datetime.now(
        ZONA_LIMA
    ).isoformat(
        timespec="seconds"
    )

    with get_connection() as conn:

        conn.execute(
            """
            UPDATE efectividad_matching_overrides

            SET
                activo = 0,
                fecha_actualizacion = ?

            WHERE presencia_id = ?
            """,
            (
                ahora,
                presencia_id,
            ),
        )

        conn.commit()


def listar_overrides_matching(
    solo_activos: bool = True,
) -> list[dict]:
    """
    Devuelve las decisiones manuales almacenadas.

    Será útil posteriormente para una pantalla de
    administración en Streamlit.
    """

    consulta = """
        SELECT
            presencia_id,
            id_cita_elegida,
            appointment_number,
            persona_creditada,
            canal_decision,
            usuario_decision,
            motivo,
            fecha_creacion,
            fecha_actualizacion,
            activo

        FROM efectividad_matching_overrides
    """

    parametros = ()

    if solo_activos:

        consulta += """
            WHERE activo = 1
        """

    consulta += """
        ORDER BY fecha_actualizacion DESC
    """

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        filas = conn.execute(
            consulta,
            parametros,
        ).fetchall()

    return [
        dict(
            fila
        )
        for fila in filas
    ]


def limpiar_conflictos_revision_matching() -> None:
    """
    Vacía la cola temporal de conflictos.

    Se ejecuta antes de reconstruir los conflictos actuales.
    Los overrides permanentes NO se eliminan.
    """

    with get_connection() as conn:

        conn.execute(
            """
            DELETE FROM efectividad_conflicto_candidatas
            """
        )

        conn.execute(
            """
            DELETE FROM efectividad_conflictos_pendientes
            """
        )

        conn.commit()


def guardar_conflicto_revision_matching(
    presencia_id: str,
    placa: str,
    fecha_visita,
    nivel: int,
    candidatas: pd.DataFrame,
) -> None:
    """
    Guarda un conflicto real y las citas candidatas
    que pueden recibir la presencia.

    Esta información es la que posteriormente consume
    Streamlit.
    """

    ahora = datetime.now(
        ZONA_LIMA
    ).isoformat(
        timespec="seconds"
    )

    with get_connection() as conn:

        conn.execute(
            """
            INSERT INTO efectividad_conflictos_pendientes (
                presencia_id,
                placa,
                fecha_visita,
                nivel,
                fecha_detectada,
                fecha_actualizacion
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT (
                presencia_id
            )

            DO UPDATE SET
                placa =
                    excluded.placa,

                fecha_visita =
                    excluded.fecha_visita,

                nivel =
                    excluded.nivel,

                fecha_actualizacion =
                    excluded.fecha_actualizacion
            """,
            (
                presencia_id,
                placa,
                str(
                    fecha_visita
                ),
                int(
                    nivel
                ),
                ahora,
                ahora,
            ),
        )

        conn.execute(
            """
            DELETE FROM efectividad_conflicto_candidatas
            WHERE presencia_id = ?
            """,
            (
                presencia_id,
            ),
        )

        registros = []

        for fila in candidatas.itertuples(
            index=False
        ):

            fecha_hora = getattr(
                fila,
                "fecha_hora_cita_lima",
                None,
            )

            if pd.notna(
                fecha_hora
            ):
                fecha_hora = str(
                    fecha_hora
                )
            else:
                fecha_hora = None

            registros.append(
                (
                    presencia_id,
                    str(
                        fila.id_cita
                    ),
                    (
                        int(
                            fila.appointment_number
                        )
                        if pd.notna(
                            fila.appointment_number
                        )
                        else None
                    ),
                    str(
                        fila.agente
                    ),
                    str(
                        fila.fecha_cita
                    ),
                    fecha_hora,
                    str(
                        fila.motivos
                    ),
                    int(
                        fila.diferencia_dias
                    ),
                )
            )

        conn.executemany(
            """
            INSERT INTO efectividad_conflicto_candidatas (
                presencia_id,
                id_cita,
                appointment_number,
                agente,
                fecha_cita,
                fecha_hora_cita,
                motivos,
                diferencia_dias
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            registros,
        )

        conn.commit()


def cerrar_conflicto_revision_matching(
    presencia_id: str,
) -> None:
    """
    Retira un conflicto de la cola una vez resuelto.

    El override permanente permanece guardado.
    """

    with get_connection() as conn:

        conn.execute(
            """
            DELETE FROM efectividad_conflicto_candidatas
            WHERE presencia_id = ?
            """,
            (
                presencia_id,
            ),
        )

        conn.execute(
            """
            DELETE FROM efectividad_conflictos_pendientes
            WHERE presencia_id = ?
            """,
            (
                presencia_id,
            ),
        )

        conn.commit()


def listar_conflictos_revision_matching() -> pd.DataFrame:
    """
    Devuelve los conflictos actualmente pendientes
    para Streamlit.
    """

    with get_connection() as conn:

        return pd.read_sql_query(
            """
            SELECT
                presencia_id,
                placa,
                fecha_visita,
                nivel,
                fecha_detectada,
                fecha_actualizacion

            FROM efectividad_conflictos_pendientes

            ORDER BY
                fecha_visita,
                placa
            """,
            conn,
        )


def listar_candidatas_conflicto_matching(
    presencia_id: str,
) -> pd.DataFrame:
    """
    Devuelve las citas candidatas de un conflicto.
    """

    with get_connection() as conn:

        return pd.read_sql_query(
            """
            SELECT
                presencia_id,
                id_cita,
                appointment_number,
                agente,
                fecha_cita,
                fecha_hora_cita,
                motivos,
                diferencia_dias

            FROM efectividad_conflicto_candidatas

            WHERE presencia_id = ?

            ORDER BY
                fecha_hora_cita,
                appointment_number
            """,
            conn,
            params=[
                presencia_id,
            ],
        )


def guardar_detalle_efectividad(
    detalle: pd.DataFrame,
    desde,
    hasta,
) -> int:
    """
    Sustituye completamente el detalle de efectividad
    correspondiente al período [desde, hasta).

    Esta estrategia es intencional:

    si una cita anteriormente válida fue posteriormente
    cancelada, eliminada o sustituida por un duplicado,
    desaparece del período al recalcularlo.
    """

    columnas = [
        "id_cita",
        "appointment_number",
        "fecha_cita",
        "hora_cita",
        "placa_normalizada",
        "motivos",
        "grupo_servicio",
        "agente",
        "persona_creditada",
        "canal_agenda",
        "status",
        "fecha_visita",
        "es_efectiva",
        "nivel",
        "diferencia_dias",
        "resultado_efectividad",
        "confirmacion_presencia",
        "numeros_cotizacion",
        "numeros_orden",
        "tipo_asignacion",
        "requiere_revision_manual",
        "criterio_matching",
        "presencia_id",
    ]

    faltantes = [
        columna
        for columna in columnas
        if columna not in detalle.columns
    ]

    if faltantes:

        raise ValueError(
            "Faltan columnas para guardar efectividad: "
            f"{faltantes}"
        )

    ahora = datetime.now(
        ZONA_LIMA
    ).isoformat(
        timespec="seconds"
    )

    registros = detalle[
        columnas
    ].copy()

    registros[
        "fecha_cita"
    ] = registros[
        "fecha_cita"
    ].astype(str)

    registros[
        "fecha_visita"
    ] = registros[
        "fecha_visita"
    ].apply(
        lambda valor:
            (
                None
                if pd.isna(valor)
                else str(valor)
            )
    )

    registros[
        "es_efectiva"
    ] = registros[
        "es_efectiva"
    ].astype(int)

    registros[
        "requiere_revision_manual"
    ] = registros[
        "requiere_revision_manual"
    ].astype(int)

    registros[
        "fecha_actualizacion"
    ] = ahora

    registros = registros.where(
        pd.notna(registros),
        None,
    )

    registros = registros.to_dict(
        orient="records"
    )

    with get_connection() as conn:

        # ----------------------------------------------------
        # REEMPLAZAR EL PERÍODO COMPLETO
        # ----------------------------------------------------

        conn.execute(
            """
            DELETE FROM efectividad_detalle
            WHERE fecha_cita >= ?
              AND fecha_cita < ?
            """,
            (
                str(desde),
                str(hasta),
            ),
        )

        conn.executemany(
            """
            INSERT INTO efectividad_detalle (
                id_cita,
                appointment_number,
                fecha_cita,
                hora_cita,
                placa_normalizada,
                motivos,
                grupo_servicio,
                agente,
                persona_creditada,
                canal_agenda,
                status,
                fecha_visita,
                es_efectiva,
                nivel,
                diferencia_dias,
                resultado_efectividad,
                confirmacion_presencia,
                numeros_cotizacion,
                numeros_orden,
                tipo_asignacion,
                requiere_revision_manual,
                criterio_matching,
                presencia_id,
                fecha_actualizacion
            )
            VALUES (
                :id_cita,
                :appointment_number,
                :fecha_cita,
                :hora_cita,
                :placa_normalizada,
                :motivos,
                :grupo_servicio,
                :agente,
                :persona_creditada,
                :canal_agenda,
                :status,
                :fecha_visita,
                :es_efectiva,
                :nivel,
                :diferencia_dias,
                :resultado_efectividad,
                :confirmacion_presencia,
                :numeros_cotizacion,
                :numeros_orden,
                :tipo_asignacion,
                :requiere_revision_manual,
                :criterio_matching,
                :presencia_id,
                :fecha_actualizacion
            )
            """,
            registros,
        )

        conn.commit()

    return len(
        registros
    )


def cargar_detalle_efectividad(
    anio: int | None = None,
) -> pd.DataFrame:
    """
    Carga el detalle maestro utilizado por los reportes
    de Streamlit.
    """

    consulta = """
        SELECT *
        FROM efectividad_detalle
    """

    parametros = []

    if anio is not None:

        consulta += """
            WHERE fecha_cita >= ?
              AND fecha_cita < ?
        """

        parametros = [
            f"{anio}-01-01",
            f"{anio + 1}-01-01",
        ]

    consulta += """
        ORDER BY
            fecha_cita,
            hora_cita,
            appointment_number
    """

    with get_connection() as conn:

        detalle = pd.read_sql_query(
            consulta,
            conn,
            params=parametros,
        )

    if detalle.empty:
        return detalle

    detalle[
        "fecha_cita"
    ] = pd.to_datetime(
        detalle[
            "fecha_cita"
        ],
        errors="coerce",
    ).dt.date

    detalle[
        "fecha_visita"
    ] = pd.to_datetime(
        detalle[
            "fecha_visita"
        ],
        errors="coerce",
    ).dt.date

    detalle[
        "es_efectiva"
    ] = detalle[
        "es_efectiva"
    ].astype(bool)

    detalle[
        "requiere_revision_manual"
    ] = detalle[
        "requiere_revision_manual"
    ].astype(bool)

    return detalle










