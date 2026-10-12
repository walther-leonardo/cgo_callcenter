from __future__ import annotations

from database import (
    get_connection,
    inicializar_base,
)


def main() -> None:

    print()
    print("=" * 90)
    print("CGO CALL CENTER — BACKFILL PRIMERA DETECCIÓN")
    print("=" * 90)

    inicializar_base()

    with get_connection() as conn:

        citas_unicas = int(
            conn.execute(
                """
                SELECT COUNT(DISTINCT id_cita)
                FROM citas_snapshot
                """
            ).fetchone()[0]
        )

        print()
        print(
            f"Citas únicas origen : "
            f"{citas_unicas:,}"
        )

        print()
        print(
            "🔄 Reconstruyendo primeras detecciones..."
        )

        conn.execute(
            """
            DELETE FROM citas_primera_deteccion
            """
        )

        conn.execute(
            """
            WITH primeras AS (
                SELECT
                    cs.*,
                    s.fecha_hora_corte,

                    ROW_NUMBER() OVER (
                        PARTITION BY cs.id_cita
                        ORDER BY
                            s.fecha_hora_corte,
                            cs.snapshot_id
                    ) AS orden_aparicion

                FROM citas_snapshot cs

                INNER JOIN snapshots s
                    ON s.snapshot_id = cs.snapshot_id
            )

            INSERT INTO citas_primera_deteccion (
                id_cita,
                snapshot_id,
                fecha_detectada,

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
                id_cita,
                snapshot_id,
                fecha_hora_corte,

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

            FROM primeras

            WHERE orden_aparicion = 1
            """
        )

        conn.commit()

        total = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_primera_deteccion
                """
            ).fetchone()[0]
        )

        diferencias_fecha = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_primera_deteccion pd

                INNER JOIN citas_maestro cm
                    ON cm.id_cita = pd.id_cita

                WHERE pd.fecha_detectada
                      <> cm.primera_deteccion
                """
            ).fetchone()[0]
        )

        faltantes_maestro = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_primera_deteccion pd

                LEFT JOIN citas_maestro cm
                    ON cm.id_cita = pd.id_cita

                WHERE cm.id_cita IS NULL
                """
            ).fetchone()[0]
        )

    print()
    print("=" * 90)
    print("RESULTADO")
    print("=" * 90)

    print(
        f"Primeras detecciones : "
        f"{total:,}"
    )

    print(
        f"Diferencias de fecha : "
        f"{diferencias_fecha:,}"
    )

    print(
        f"Faltantes en maestro : "
        f"{faltantes_maestro:,}"
    )

    print()
    print("=" * 90)

    if (
        total == citas_unicas
        and diferencias_fecha == 0
        and faltantes_maestro == 0
    ):

        print(
            "✅ BACKFILL PRIMERA DETECCIÓN CORRECTO"
        )

    else:

        print(
            "⚠️ REVISAR BACKFILL PRIMERA DETECCIÓN"
        )

    print("=" * 90)
    print()


if __name__ == "__main__":
    main()