from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from config import CLEARMECHANIC_FILE
from database import (
    get_connection,
    inicializar_base,
)
from metricas import (
    guardar_analitica_snapshot,
    mostrar_resumen_snapshot,
)
from procesamiento import cargar_clearmechanic


def registrar_snapshot(
    archivo: str | Path | None = None,
) -> int:
    """
    Lee un Excel de ClearMechanic y registra una fotografía
    completa en SQLite.

    Si no se proporciona archivo, mantiene el flujo manual
    tradicional usando CLEARMECHANIC_FILE.
    """

    ruta_archivo = (
        Path(archivo)
        if archivo is not None
        else CLEARMECHANIC_FILE
    )

    if not ruta_archivo.exists():
        raise FileNotFoundError(
            "No encontré el archivo:\n"
            f"{ruta_archivo}\n\n"
            "Verifica que el archivo exista antes de "
            "registrar el snapshot."
        )

    df = cargar_clearmechanic(
        ruta_archivo
    )

    fecha_hora_corte = datetime.now()

    def valor_sql(valor):
        """
        Convierte valores pandas/numpy a tipos compatibles
        con SQLite.
        """

        if pd.isna(valor):
            return None

        return valor

    def fecha_sql(valor):
        """
        Convierte fechas pandas a texto ISO compatible
        con SQLite.
        """

        if pd.isna(valor):
            return None

        return pd.Timestamp(
            valor
        ).isoformat()

    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO snapshots (
                fecha_hora_corte,
                archivo_origen,
                cantidad_citas
            )
            VALUES (?, ?, ?)
            """,
            (
                fecha_hora_corte.isoformat(
                    timespec="seconds"
                ),
                ruta_archivo.name,
                len(df),
            ),
        )

        snapshot_id = (
            cursor.lastrowid
        )

        registros = []

        for fila in df.itertuples(
            index=False
        ):

            registros.append(
                (
                    snapshot_id,

                    int(
                        fila.id_cita
                    ),

                    valor_sql(
                        fila.estatus_cita
                    ),

                    valor_sql(
                        fila.motivo_visita
                    ),

                    fecha_sql(
                        fila.fecha_programada
                    ),

                    valor_sql(
                        fila.hora_programada
                    ),

                    valor_sql(
                        fila.origen_cita
                    ),

                    valor_sql(
                        fila.persona_agenda
                    ),

                    fecha_sql(
                        fila.fecha_creacion
                    ),

                    valor_sql(
                        fila.nombre
                    ),

                    valor_sql(
                        fila.celular
                    ),

                    valor_sql(
                        fila.asesor_servicio
                    ),

                    valor_sql(
                        fila.modelo
                    ),

                    valor_sql(
                        fila.placa
                    ),

                    (
                        float(
                            fila.kilometraje
                        )
                        if not pd.isna(
                            fila.kilometraje
                        )
                        else None
                    ),
                )
            )

        conn.executemany(
            """
            INSERT INTO citas_snapshot (
                snapshot_id,
                id_cita,
                estatus_cita,
                motivo_visita,
                fecha_programada,
                hora_programada,
                origen_cita,
                persona_agenda,
                fecha_creacion,
                nombre,
                celular,
                asesor_servicio,
                modelo,
                placa,
                kilometraje
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            registros,
        )

        # ====================================================
        # SINCRONIZAR CITAS MAESTRO
        # ====================================================

        fecha_hora_corte_sql = (
            fecha_hora_corte.isoformat(
                timespec="seconds"
            )
        )

        # Las citas que estaban presentes en el corte anterior
        # dejan de considerarse presentes hasta que vuelvan
        # a aparecer en el snapshot actual.
        conn.execute(
            """
            UPDATE citas_maestro
            SET presente_en_ultimo_snapshot = 0
            WHERE presente_en_ultimo_snapshot = 1
            """
        )

        registros_maestro = []

        for fila in df.itertuples(
            index=False
        ):

            registros_maestro.append(
                {
                    "id_cita":
                        int(
                            fila.id_cita
                        ),

                    "snapshot_id":
                        snapshot_id,

                    "fecha_deteccion":
                        fecha_hora_corte_sql,

                    "estatus_cita":
                        valor_sql(
                            fila.estatus_cita
                        ),

                    "motivo_visita":
                        valor_sql(
                            fila.motivo_visita
                        ),

                    "fecha_programada":
                        fecha_sql(
                            fila.fecha_programada
                        ),

                    "hora_programada":
                        valor_sql(
                            fila.hora_programada
                        ),

                    "origen_cita":
                        valor_sql(
                            fila.origen_cita
                        ),

                    "persona_agenda":
                        valor_sql(
                            fila.persona_agenda
                        ),

                    "fecha_creacion":
                        fecha_sql(
                            fila.fecha_creacion
                        ),

                    "nombre":
                        valor_sql(
                            fila.nombre
                        ),

                    "celular":
                        valor_sql(
                            fila.celular
                        ),

                    "asesor_servicio":
                        valor_sql(
                            fila.asesor_servicio
                        ),

                    "modelo":
                        valor_sql(
                            fila.modelo
                        ),

                    "placa":
                        valor_sql(
                            fila.placa
                        ),

                    "kilometraje":
                        (
                            float(
                                fila.kilometraje
                            )
                            if not pd.isna(
                                fila.kilometraje
                            )
                            else None
                        ),
                }
            )

        conn.executemany(
            """
            INSERT INTO citas_maestro (
                id_cita,

                primer_snapshot_id,
                primera_deteccion,

                ultimo_snapshot_id,
                ultima_deteccion,

                presente_en_ultimo_snapshot,

                estatus_cita,
                motivo_visita,
                fecha_programada,
                hora_programada,
                origen_cita,
                persona_agenda,
                fecha_creacion,

                nombre,
                celular,
                asesor_servicio,
                modelo,
                placa,
                kilometraje
            )

            VALUES (
                :id_cita,

                :snapshot_id,
                :fecha_deteccion,

                :snapshot_id,
                :fecha_deteccion,

                1,

                :estatus_cita,
                :motivo_visita,
                :fecha_programada,
                :hora_programada,
                :origen_cita,
                :persona_agenda,
                :fecha_creacion,

                :nombre,
                :celular,
                :asesor_servicio,
                :modelo,
                :placa,
                :kilometraje
            )

            ON CONFLICT (
                id_cita
            )

            DO UPDATE SET

                ultimo_snapshot_id =
                    excluded.ultimo_snapshot_id,

                ultima_deteccion =
                    excluded.ultima_deteccion,

                presente_en_ultimo_snapshot =
                    1,

                estatus_cita =
                    excluded.estatus_cita,

                motivo_visita =
                    excluded.motivo_visita,

                fecha_programada =
                    excluded.fecha_programada,

                hora_programada =
                    excluded.hora_programada,

                origen_cita =
                    excluded.origen_cita,

                persona_agenda =
                    excluded.persona_agenda,

                fecha_creacion =
                    excluded.fecha_creacion,

                nombre =
                    excluded.nombre,

                celular =
                    excluded.celular,

                asesor_servicio =
                    excluded.asesor_servicio,

                modelo =
                    excluded.modelo,

                placa =
                    excluded.placa,

                kilometraje =
                    excluded.kilometraje
            """,
            registros_maestro,
        )

        conn.commit()

    return snapshot_id


def main() -> None:

    print()
    print("=" * 64)
    print("CGO CALL CENTER — REGISTRO DE SNAPSHOT")
    print("=" * 64)

    inicializar_base()

    snapshot_id = (
        registrar_snapshot()
    )

    print(
        f"✅ Snapshot #{snapshot_id} registrado correctamente."
    )

    guardar_analitica_snapshot(
        snapshot_id
    )

    print(
        "✅ Deltas e indicadores guardados correctamente."
    )

    mostrar_resumen_snapshot(
        snapshot_id
    )

    print()


if __name__ == "__main__":
    main()