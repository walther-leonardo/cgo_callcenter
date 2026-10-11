import pandas as pd

from database import get_connection


with get_connection() as conn:

    df = pd.read_sql_query(
        """
        SELECT
            s.snapshot_id,
            s.fecha_hora_corte,
            c.id_cita,
            c.persona_agenda,
            c.fecha_creacion,
            c.origen_cita
        FROM citas_snapshot c
        INNER JOIN snapshots s
            ON s.snapshot_id = c.snapshot_id
        WHERE date(c.fecha_creacion) = '2026-10-01'
        ORDER BY
            s.snapshot_id DESC,
            c.fecha_creacion
        """,
        conn,
    )


print()
print("=" * 80)
print("CITAS CREADAS EL 2026-10-01")
print("=" * 80)

print(
    f"Registros encontrados: {len(df)}"
)

if not df.empty:

    print()
    print(
        df[
            [
                "snapshot_id",
                "fecha_hora_corte",
                "id_cita",
                "persona_agenda",
                "fecha_creacion",
                "origen_cita",
            ]
        ]
        .head(
            100
        )
        .to_string(
            index=False
        )
    )

    print()
    print("=" * 80)
    print("PERSONAS QUE AGENDARON")
    print("=" * 80)

    print(
        df[
            "persona_agenda"
        ]
        .value_counts(
            dropna=False
        )
        .to_string()
    )