from __future__ import annotations

from database import get_connection


def aplicar_retencion_citas_snapshot() -> dict:
    """
    Mantiene en citas_snapshot únicamente:

    - todos los snapshots del último día operativo;
    - el snapshot inmediatamente anterior a ese día.

    No elimina cabeceras de snapshots, métricas, cambios,
    maestro ni primeras detecciones.

    Devuelve estadísticas de la operación.
    """

    with get_connection() as conn:

        # ====================================================
        # ÚLTIMO SNAPSHOT
        # ====================================================

        ultimo = conn.execute(
            """
            SELECT
                snapshot_id,
                fecha_hora_corte,
                cantidad_citas
            FROM snapshots
            ORDER BY snapshot_id DESC
            LIMIT 1
            """
        ).fetchone()

        if ultimo is None:
            return {
                "filas_eliminadas": 0,
                "filas_restantes": 0,
                "snapshot_referencia": None,
                "primer_snapshot_dia": None,
                "ultimo_snapshot": None,
            }

        ultimo_snapshot_id = int(
            ultimo[0]
        )

        fecha_hora_ultimo = str(
            ultimo[1]
        )

        cantidad_ultimo = int(
            ultimo[2]
        )

        fecha_operativa = (
            fecha_hora_ultimo[:10]
        )

        # ====================================================
        # PRIMER SNAPSHOT DEL ÚLTIMO DÍA OPERATIVO
        # ====================================================

        primero_dia = conn.execute(
            """
            SELECT snapshot_id
            FROM snapshots
            WHERE substr(
                fecha_hora_corte,
                1,
                10
            ) = ?
            ORDER BY snapshot_id
            LIMIT 1
            """,
            (
                fecha_operativa,
            ),
        ).fetchone()

        if primero_dia is None:
            raise RuntimeError(
                "No fue posible identificar "
                "el primer snapshot del día."
            )

        primer_snapshot_dia_id = int(
            primero_dia[0]
        )

        # ====================================================
        # SNAPSHOT DE REFERENCIA
        # ====================================================

        anterior = conn.execute(
            """
            SELECT snapshot_id
            FROM snapshots
            WHERE snapshot_id < ?
            ORDER BY snapshot_id DESC
            LIMIT 1
            """,
            (
                primer_snapshot_dia_id,
            ),
        ).fetchone()

        # Primer día de vida del sistema:
        # todavía no hay nada que purgar.
        if anterior is None:

            filas_restantes = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM citas_snapshot
                    """
                ).fetchone()[0]
            )

            return {
                "filas_eliminadas": 0,
                "filas_restantes": filas_restantes,
                "snapshot_referencia": None,
                "primer_snapshot_dia":
                    primer_snapshot_dia_id,
                "ultimo_snapshot":
                    ultimo_snapshot_id,
            }

        snapshot_referencia_id = int(
            anterior[0]
        )

        # ====================================================
        # VALIDACIONES DE SEGURIDAD
        # ====================================================

        filas_referencia = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                WHERE snapshot_id = ?
                """,
                (
                    snapshot_referencia_id,
                ),
            ).fetchone()[0]
        )

        filas_inicio = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                WHERE snapshot_id = ?
                """,
                (
                    primer_snapshot_dia_id,
                ),
            ).fetchone()[0]
        )

        filas_ultimo = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                WHERE snapshot_id = ?
                """,
                (
                    ultimo_snapshot_id,
                ),
            ).fetchone()[0]
        )

        presentes_maestro = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_maestro
                WHERE presente_en_ultimo_snapshot = 1
                """
            ).fetchone()[0]
        )

        maestro_total = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_maestro
                """
            ).fetchone()[0]
        )

        primeras_total = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_primera_deteccion
                """
            ).fetchone()[0]
        )

        if filas_referencia <= 0:
            raise RuntimeError(
                "El snapshot de referencia "
                "no tiene fotografía disponible."
            )

        if filas_inicio <= 0:
            raise RuntimeError(
                "El primer snapshot del día "
                "no tiene fotografía disponible."
            )

        if filas_ultimo != cantidad_ultimo:
            raise RuntimeError(
                "El último snapshot no coincide "
                "con la cantidad declarada."
            )

        if presentes_maestro != cantidad_ultimo:
            raise RuntimeError(
                "citas_maestro no coincide "
                "con el último snapshot."
            )

        if maestro_total != primeras_total:
            raise RuntimeError(
                "citas_maestro y "
                "citas_primera_deteccion "
                "tienen cantidades diferentes."
            )

        # ====================================================
        # RETENCIÓN
        # ====================================================

        cursor = conn.execute(
            """
            DELETE FROM citas_snapshot
            WHERE snapshot_id < ?
            """,
            (
                snapshot_referencia_id,
            ),
        )

        filas_eliminadas = int(
            cursor.rowcount
        )

        # ====================================================
        # VALIDACIÓN POSTERIOR
        # ====================================================

        filas_restantes = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                """
            ).fetchone()[0]
        )

        antiguos_restantes = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                WHERE snapshot_id < ?
                """,
                (
                    snapshot_referencia_id,
                ),
            ).fetchone()[0]
        )

        referencia_despues = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                WHERE snapshot_id = ?
                """,
                (
                    snapshot_referencia_id,
                ),
            ).fetchone()[0]
        )

        ultimo_despues = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                WHERE snapshot_id = ?
                """,
                (
                    ultimo_snapshot_id,
                ),
            ).fetchone()[0]
        )

        if (
            antiguos_restantes != 0
            or referencia_despues != filas_referencia
            or ultimo_despues != filas_ultimo
        ):
            conn.rollback()

            raise RuntimeError(
                "La validación posterior de "
                "retención falló."
            )

        conn.commit()

    return {
        "filas_eliminadas":
            filas_eliminadas,
        "filas_restantes":
            filas_restantes,
        "snapshot_referencia":
            snapshot_referencia_id,
        "primer_snapshot_dia":
            primer_snapshot_dia_id,
        "ultimo_snapshot":
            ultimo_snapshot_id,
    }