from __future__ import annotations

import pandas as pd

from database import (
    get_connection,
    inicializar_base,
)
from metricas import guardar_analitica_snapshot


def main() -> None:

    inicializar_base()

    with get_connection() as conn:

        snapshots = pd.read_sql_query(
            """
            SELECT snapshot_id
            FROM snapshots
            ORDER BY snapshot_id
            """,
            conn,
        )

    print()
    print("=" * 64)
    print("CGO CALL CENTER — RECÁLCULO HISTÓRICO")
    print("=" * 64)

    for snapshot_id in snapshots[
        "snapshot_id"
    ]:

        guardar_analitica_snapshot(
            int(
                snapshot_id
            )
        )

        print(
            f"✅ Snapshot #{snapshot_id}"
        )

    print()
    print(
        f"{len(snapshots):,} snapshots procesados."
    )
    print()


if __name__ == "__main__":
    main()