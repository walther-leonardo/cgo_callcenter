from __future__ import annotations

import pandas as pd

from database import (
    get_connection,
    inicializar_base,
)
from metricas import guardar_analitica_snapshot


def cargar_snapshots_recalculables() -> pd.DataFrame:
    """
    Devuelve únicamente snapshots que pueden recalcularse
    de forma segura con las fotografías actualmente
    disponibles en citas_snapshot.

    Un snapshot es recalculable cuando:
    - tiene fotografía en citas_snapshot;
    - y su snapshot inmediatamente anterior también
      tiene fotografía.

    El primer snapshot conservado se utiliza como
    referencia y no se recalcula.
    """

    with get_connection() as conn:

        snapshots = pd.read_sql_query(
            """
            WITH snapshots_con_foto AS (
                SELECT DISTINCT
                    snapshot_id
                FROM citas_snapshot
            ),

            candidatos AS (
                SELECT
                    s.snapshot_id,

                    (
                        SELECT MAX(s2.snapshot_id)
                        FROM snapshots s2
                        WHERE s2.snapshot_id < s.snapshot_id
                    ) AS snapshot_anterior_id

                FROM snapshots s

                INNER JOIN snapshots_con_foto cf
                    ON cf.snapshot_id = s.snapshot_id
            )

            SELECT
                c.snapshot_id,
                c.snapshot_anterior_id

            FROM candidatos c

            INNER JOIN snapshots_con_foto anterior
                ON anterior.snapshot_id =
                   c.snapshot_anterior_id

            ORDER BY c.snapshot_id
            """,
            conn,
        )

    return snapshots


def main() -> None:

    inicializar_base()

    snapshots = (
        cargar_snapshots_recalculables()
    )

    print()
    print("=" * 72)
    print("CGO CALL CENTER — RECÁLCULO HISTÓRICO SEGURO")
    print("=" * 72)

    if snapshots.empty:

        print()
        print(
            "⚠️ No existen snapshots recalculables "
            "con fotografías consecutivas."
        )
        print()
        return

    print()
    print(
        f"Snapshots recalculables : "
        f"{len(snapshots):,}"
    )

    print(
        f"Primer recalculable     : "
        f"{int(snapshots.iloc[0]['snapshot_id'])}"
    )

    print(
        f"Último recalculable     : "
        f"{int(snapshots.iloc[-1]['snapshot_id'])}"
    )

    print()
    print("-" * 72)

    procesados = 0

    for fila in snapshots.itertuples(
        index=False
    ):

        snapshot_id = int(
            fila.snapshot_id
        )

        guardar_analitica_snapshot(
            snapshot_id
        )

        procesados += 1

        print(
            f"✅ Snapshot #{snapshot_id}"
        )

    print()
    print("=" * 72)

    print(
        f"✅ {procesados:,} snapshots "
        "recalculados correctamente."
    )

    print(
        "ℹ️ El primer snapshot conservado "
        "queda únicamente como referencia."
    )

    print("=" * 72)
    print()


if __name__ == "__main__":
    main()