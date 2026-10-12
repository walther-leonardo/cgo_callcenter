from __future__ import annotations

from database import (
    get_connection,
    inicializar_base,
)


def main() -> None:
    """
    Reconstruye citas_maestro a partir de todo el historial
    disponible en citas_snapshot.

    Solo modifica citas_maestro.
    No elimina ni altera snapshots históricos.
    """

    print()
    print("=" * 90)
    print("CGO CALL CENTER — BACKFILL CITAS MAESTRO")
    print("=" * 90)

    inicializar_base()

    with get_connection() as conn:

        total_snapshot = conn.execute(
            """
            SELECT COUNT(*)
            FROM citas_snapshot
            """
        ).fetchone()[0]

        total_unicas = conn.execute(
            """
            SELECT COUNT(
                DISTINCT id_cita
            )
            FROM citas_snapshot
            """
        ).fetchone()[0]

        ultimo_snapshot_id = conn.execute(
            """
            SELECT MAX(snapshot_id)
            FROM snapshots
            """
        ).fetchone()[0]

        print()
        print(
            f"Filas origen        : "
            f"{total_snapshot:,}"
        )

        print(
            f"Citas únicas origen : "
            f"{total_unicas:,}"
        )

        print(
            f"Último snapshot     : "
            f"{ultimo_snapshot_id}"
        )

        print()
        print(
            "🔄 Reconstruyendo citas_maestro..."
        )

        conn.execute(
            """
            DELETE FROM citas_maestro
            """
        )

        conn.execute(
            """
            WITH historial AS (
                SELECT
                    cs.*,
                    s.fecha_hora_corte,

                    ROW_NUMBER() OVER (
                        PARTITION BY cs.id_cita
                        ORDER BY
                            s.fecha_hora_corte,
                            cs.snapshot_id
                    ) AS orden_primera,

                    ROW_NUMBER() OVER (
                        PARTITION BY cs.id_cita
                        ORDER BY
                            s.fecha_hora_corte DESC,
                            cs.snapshot_id DESC
                    ) AS orden_ultima

                FROM citas_snapshot cs

                INNER JOIN snapshots s
                    ON s.snapshot_id = cs.snapshot_id
            ),

            primeras AS (
                SELECT
                    id_cita,
                    snapshot_id,
                    fecha_hora_corte
                FROM historial
                WHERE orden_primera = 1
            ),

            ultimas AS (
                SELECT
                    *
                FROM historial
                WHERE orden_ultima = 1
            )

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

            SELECT
                u.id_cita,

                p.snapshot_id,
                p.fecha_hora_corte,

                u.snapshot_id,
                u.fecha_hora_corte,

                CASE
                    WHEN u.snapshot_id = ?
                    THEN 1
                    ELSE 0
                END,

                u.estatus_cita,
                u.motivo_visita,
                u.fecha_programada,
                u.hora_programada,
                u.origen_cita,
                u.persona_agenda,
                u.fecha_creacion,

                u.nombre,
                u.celular,
                u.asesor_servicio,
                u.modelo,
                u.placa,
                u.kilometraje

            FROM ultimas u

            INNER JOIN primeras p
                ON p.id_cita = u.id_cita
            """,
            (
                ultimo_snapshot_id,
            ),
        )

        conn.commit()

        total_maestro = conn.execute(
            """
            SELECT COUNT(*)
            FROM citas_maestro
            """
        ).fetchone()[0]

        presentes = conn.execute(
            """
            SELECT COUNT(*)
            FROM citas_maestro
            WHERE presente_en_ultimo_snapshot = 1
            """
        ).fetchone()[0]

        historicas = conn.execute(
            """
            SELECT COUNT(*)
            FROM citas_maestro
            WHERE presente_en_ultimo_snapshot = 0
            """
        ).fetchone()[0]

    print()
    print("=" * 90)
    print("RESULTADO")
    print("=" * 90)

    print(
        f"Citas maestro       : "
        f"{total_maestro:,}"
    )

    print(
        f"Presentes actuales  : "
        f"{presentes:,}"
    )

    print(
        f"Históricas          : "
        f"{historicas:,}"
    )

    print()
    print("=" * 90)

    if (
        total_maestro == total_unicas
        and presentes > 0
    ):

        print(
            "✅ BACKFILL COMPLETADO CORRECTAMENTE"
        )

    else:

        print(
            "⚠️ REVISAR RESULTADOS DEL BACKFILL"
        )

    print("=" * 90)
    print()


if __name__ == "__main__":
    main()