from __future__ import annotations

import pandas as pd

from database import get_connection


def main() -> None:

    with get_connection() as conn:

        metricas = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                metrica,
                dimension,
                segmento,
                valor
            FROM metricas_snapshot
            ORDER BY
                snapshot_id,
                metrica,
                dimension,
                segmento
            """,
            conn,
        )

        cambios = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                snapshot_anterior_id,
                id_cita,
                tipo_cambio,
                campo,
                valor_anterior,
                valor_actual
            FROM cambios_snapshot
            ORDER BY
                snapshot_id,
                id_cita,
                tipo_cambio
            """,
            conn,
        )

    print()
    print("=" * 72)
    print("CGO CALL CENTER — VALIDACIÓN MÉTRICAS")
    print("=" * 72)

    print()
    print("MÉTRICAS SNAPSHOT #2")
    print("-" * 72)

    print(
        metricas.loc[
            metricas["snapshot_id"].eq(2)
        ].to_string(
            index=False
        )
    )

    print()
    print("CAMBIOS SNAPSHOT #2")
    print("-" * 72)

    print(
        cambios.loc[
            cambios["snapshot_id"].eq(2)
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()