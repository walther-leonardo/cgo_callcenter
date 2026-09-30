from database import get_connection


SNAPSHOT_ID = 53


def main() -> None:

    with get_connection() as conn:

        existe = conn.execute(
            """
            SELECT snapshot_id
            FROM snapshots
            WHERE snapshot_id = ?
            """,
            (SNAPSHOT_ID,),
        ).fetchone()

        if existe is None:
            print(
                f"⚠️ El snapshot #{SNAPSHOT_ID} no existe."
            )
            return

        conn.execute(
            """
            DELETE FROM metricas_snapshot
            WHERE snapshot_id = ?
            """,
            (SNAPSHOT_ID,),
        )

        conn.execute(
            """
            DELETE FROM cambios_snapshot
            WHERE snapshot_id = ?
               OR snapshot_anterior_id = ?
            """,
            (
                SNAPSHOT_ID,
                SNAPSHOT_ID,
            ),
        )

        conn.execute(
            """
            DELETE FROM citas_snapshot
            WHERE snapshot_id = ?
            """,
            (SNAPSHOT_ID,),
        )

        conn.execute(
            """
            DELETE FROM snapshots
            WHERE snapshot_id = ?
            """,
            (SNAPSHOT_ID,),
        )

        conn.commit()

    print(
        f"✅ Snapshot #{SNAPSHOT_ID} eliminado correctamente."
    )

    print(
        "Ahora ejecuta recalcular_historico.py."
    )


if __name__ == "__main__":
    main()