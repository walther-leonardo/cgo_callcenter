from __future__ import annotations

import pandas as pd

from database import get_connection


def main() -> None:

    print()
    print("=" * 72)
    print("CGO CALL CENTER — VALIDACIÓN SQLITE")
    print("=" * 72)

    with get_connection() as conn:

        snapshots = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                fecha_hora_corte,
                archivo_origen,
                cantidad_citas
            FROM snapshots
            ORDER BY snapshot_id
            """,
            conn,
        )

        citas = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                id_cita,
                fecha_creacion,
                fecha_programada,
                hora_programada,
                persona_agenda,
                estatus_cita,
                placa,
                modelo
            FROM citas_snapshot
            ORDER BY
                snapshot_id,
                fecha_programada,
                hora_programada
            """,
            conn,
        )

    print()
    print("SNAPSHOTS")
    print("-" * 72)

    print(
        snapshots.to_string(
            index=False
        )
    )

    print()
    print("CITAS REGISTRADAS")
    print("-" * 72)

    print(
        citas.head(20).to_string(
            index=False
        )
    )

    print()
    print("CONTROL")
    print("-" * 72)

    print(
        f"Snapshots registrados : {len(snapshots):,}"
    )

    print(
        f"Citas almacenadas      : {len(citas):,}"
    )

    print(
        f"IDs cita únicos        : {citas['id_cita'].nunique():,}"
    )

    print(
        f"Fechas creación nulas  : {citas['fecha_creacion'].isna().sum():,}"
    )

    print(
        f"Fechas programa nulas  : {citas['fecha_programada'].isna().sum():,}"
    )

    print(
        f"Persona agenda nula    : {citas['persona_agenda'].isna().sum():,}"
    )

    print()
    print("PERSONAS QUE AGENDA")
    print("-" * 72)

    resumen_agentes = (
        citas[
            "persona_agenda"
        ]
        .value_counts(
            dropna=False
        )
        .rename_axis(
            "persona_agenda"
        )
        .reset_index(
            name="citas"
        )
    )

    print(
        resumen_agentes.to_string(
            index=False
        )
    )

    print()


if __name__ == "__main__":
    main()