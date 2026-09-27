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