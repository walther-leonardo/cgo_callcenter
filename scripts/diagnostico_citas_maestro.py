from __future__ import annotations

import pandas as pd

from database import get_connection


def main() -> None:

    print()
    print("=" * 90)
    print("CGO CALL CENTER — DIAGNÓSTICO PARA CITAS MAESTRO")
    print("=" * 90)

    with get_connection() as conn:

        resumen = pd.read_sql_query(
            """
            SELECT
                COUNT(*) AS filas_snapshot,
                COUNT(DISTINCT id_cita) AS citas_unicas
            FROM citas_snapshot
            """,
            conn,
        )

        rango = pd.read_sql_query(
            """
            SELECT
                MIN(s.fecha_hora_corte) AS primer_corte,
                MAX(s.fecha_hora_corte) AS ultimo_corte
            FROM snapshots s
            """,
            conn,
        )

        ultimo_snapshot = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                fecha_hora_corte,
                cantidad_citas
            FROM snapshots
            ORDER BY snapshot_id DESC
            LIMIT 1
            """,
            conn,
        )

        apariciones = pd.read_sql_query(
            """
            SELECT
                id_cita,
                COUNT(*) AS apariciones
            FROM citas_snapshot
            GROUP BY id_cita
            """,
            conn,
        )

        if ultimo_snapshot.empty:

            citas_ultimo = 0

        else:

            snapshot_id = int(
                ultimo_snapshot.iloc[0][
                    "snapshot_id"
                ]
            )

            fila = conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                WHERE snapshot_id = ?
                """,
                (
                    snapshot_id,
                ),
            ).fetchone()

            citas_ultimo = int(
                fila[0]
            )

    filas_snapshot = int(
        resumen.iloc[0][
            "filas_snapshot"
        ]
    )

    citas_unicas = int(
        resumen.iloc[0][
            "citas_unicas"
        ]
    )

    historicas_fuera_actual = (
        citas_unicas
        -
        citas_ultimo
    )

    factor_repeticion = (
        filas_snapshot
        /
        citas_unicas
        if citas_unicas
        else 0
    )

    print()
    print("VOLUMEN")
    print("-" * 90)

    print(
        f"Filas en citas_snapshot       : "
        f"{filas_snapshot:>12,}"
    )

    print(
        f"IDs cita únicos               : "
        f"{citas_unicas:>12,}"
    )

    print(
        f"Citas en último snapshot      : "
        f"{citas_ultimo:>12,}"
    )

    print(
        f"Citas históricas fuera actual : "
        f"{historicas_fuera_actual:>12,}"
    )

    print(
        f"Repeticiones promedio por ID  : "
        f"{factor_repeticion:>12.1f}"
    )

    print()
    print("APARICIONES POR CITA")
    print("-" * 90)

    if not apariciones.empty:

        print(
            f"Mínimo   : "
            f"{int(apariciones['apariciones'].min()):,}"
        )

        print(
            f"Mediana  : "
            f"{apariciones['apariciones'].median():,.1f}"
        )

        print(
            f"Promedio : "
            f"{apariciones['apariciones'].mean():,.1f}"
        )

        print(
            f"Máximo   : "
            f"{int(apariciones['apariciones'].max()):,}"
        )

    print()
    print("RANGO HISTÓRICO")
    print("-" * 90)

    print(
        f"Primer corte : "
        f"{rango.iloc[0]['primer_corte']}"
    )

    print(
        f"Último corte : "
        f"{rango.iloc[0]['ultimo_corte']}"
    )

    print()
    print("ÚLTIMO SNAPSHOT")
    print("-" * 90)

    if not ultimo_snapshot.empty:

        print(
            ultimo_snapshot.to_string(
                index=False
            )
        )

    print()
    print("=" * 90)
    print("✅ DIAGNÓSTICO FINALIZADO — SOLO LECTURA")
    print("=" * 90)
    print()


if __name__ == "__main__":
    main()