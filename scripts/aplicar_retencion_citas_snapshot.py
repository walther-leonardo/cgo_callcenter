from __future__ import annotations

from database import get_connection


def main() -> None:

    print()
    print("=" * 90)
    print("CGO CALL CENTER — RETENCIÓN CITAS SNAPSHOT")
    print("=" * 90)

    with get_connection() as conn:

        # ====================================================
        # ÚLTIMO SNAPSHOT DISPONIBLE
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
            raise RuntimeError(
                "No existen snapshots registrados."
            )

        ultimo_snapshot_id = int(
            ultimo[0]
        )

        ultima_fecha_hora = str(
            ultimo[1]
        )

        cantidad_ultimo_snapshot = int(
            ultimo[2]
        )

        fecha_operativa = (
            ultima_fecha_hora[:10]
        )

        # ====================================================
        # PRIMER SNAPSHOT DEL ÚLTIMO DÍA OPERATIVO
        # ====================================================

        primero_dia = conn.execute(
            """
            SELECT
                snapshot_id,
                fecha_hora_corte
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
        # SNAPSHOT INMEDIATAMENTE ANTERIOR
        # ====================================================

        anterior = conn.execute(
            """
            SELECT
                snapshot_id,
                fecha_hora_corte
            FROM snapshots
            WHERE snapshot_id < ?
            ORDER BY snapshot_id DESC
            LIMIT 1
            """,
            (
                primer_snapshot_dia_id,
            ),
        ).fetchone()

        if anterior is None:
            raise RuntimeError(
                "No existe un snapshot anterior "
                "para utilizar como referencia."
            )

        snapshot_referencia_id = int(
            anterior[0]
        )

        fecha_referencia = str(
            anterior[1]
        )

        # ====================================================
        # VALIDACIONES PREVIAS
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

        filas_inicio_dia = int(
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

        maestro_total = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_maestro
                """
            ).fetchone()[0]
        )

        primera_total = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_primera_deteccion
                """
            ).fetchone()[0]
        )

        faltan_primera = int(
            conn.execute(
                """
                SELECT COUNT(*)

                FROM citas_maestro m

                LEFT JOIN citas_primera_deteccion p
                    ON p.id_cita = m.id_cita

                WHERE p.id_cita IS NULL
                """
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

        total_antes = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                """
            ).fetchone()[0]
        )

        eliminables = int(
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

        # ====================================================
        # CONTROL DE SEGURIDAD
        # ====================================================

        errores = []

        if filas_referencia <= 0:
            errores.append(
                "El snapshot de referencia no tiene citas."
            )

        if filas_inicio_dia <= 0:
            errores.append(
                "El primer snapshot del día no tiene citas."
            )

        if filas_ultimo <= 0:
            errores.append(
                "El último snapshot no tiene citas."
            )

        if (
            filas_ultimo
            != cantidad_ultimo_snapshot
        ):
            errores.append(
                "La cantidad del último snapshot "
                "no coincide con su cabecera."
            )

        if (
            presentes_maestro
            != cantidad_ultimo_snapshot
        ):
            errores.append(
                "citas_maestro no coincide con "
                "el último snapshot."
            )

        if (
            maestro_total
            != primera_total
        ):
            errores.append(
                "citas_maestro y "
                "citas_primera_deteccion "
                "tienen cantidades distintas."
            )

        if faltan_primera != 0:
            errores.append(
                "Existen citas maestro sin "
                "primera detección."
            )

        # ====================================================
        # RESUMEN PREVIO
        # ====================================================

        print()
        print("VENTANA OPERATIVA")
        print("-" * 90)

        print(
            f"Fecha operativa              : "
            f"{fecha_operativa}"
        )

        print(
            f"Snapshot referencia          : "
            f"{snapshot_referencia_id}"
        )

        print(
            f"Fecha referencia             : "
            f"{fecha_referencia}"
        )

        print(
            f"Primer snapshot del día      : "
            f"{primer_snapshot_dia_id}"
        )

        print(
            f"Último snapshot              : "
            f"{ultimo_snapshot_id}"
        )

        print()
        print("VALIDACIONES")
        print("-" * 90)

        print(
            f"Filas referencia             : "
            f"{filas_referencia:,}"
        )

        print(
            f"Filas inicio del día         : "
            f"{filas_inicio_dia:,}"
        )

        print(
            f"Filas último snapshot        : "
            f"{filas_ultimo:,}"
        )

        print(
            f"Presentes en maestro         : "
            f"{presentes_maestro:,}"
        )

        print(
            f"Citas maestro                : "
            f"{maestro_total:,}"
        )

        print(
            f"Primeras detecciones         : "
            f"{primera_total:,}"
        )

        print(
            f"Faltantes primera detección  : "
            f"{faltan_primera:,}"
        )

        print()
        print("RETENCIÓN")
        print("-" * 90)

        print(
            f"Filas antes                  : "
            f"{total_antes:,}"
        )

        print(
            f"Filas a eliminar             : "
            f"{eliminables:,}"
        )

        if errores:

            print()
            print("=" * 90)
            print(
                "❌ RETENCIÓN CANCELADA"
            )
            print("=" * 90)

            for error in errores:
                print(
                    f"- {error}"
                )

            print()
            return

        # ====================================================
        # DELETE
        # ====================================================

        print()
        print(
            "🔄 Aplicando retención..."
        )

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
        # VALIDACIONES POSTERIORES
        # ====================================================

        total_despues = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM citas_snapshot
                """
            ).fetchone()[0]
        )

        filas_referencia_despues = int(
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

        filas_ultimo_despues = int(
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

        post_ok = (
            filas_eliminadas
            == eliminables
            and total_despues
            == total_antes - eliminables
            and filas_referencia_despues
            == filas_referencia
            and filas_ultimo_despues
            == filas_ultimo
            and antiguos_restantes == 0
        )

        if not post_ok:

            conn.rollback()

            raise RuntimeError(
                "La validación posterior falló. "
                "Se ejecutó ROLLBACK."
            )

        conn.commit()

    # ========================================================
    # RESULTADO
    # ========================================================

    reduccion = (
        filas_eliminadas
        /
        total_antes
        *
        100
        if total_antes
        else 0
    )

    print()
    print("=" * 90)
    print("RESULTADO")
    print("=" * 90)

    print(
        f"Filas eliminadas             : "
        f"{filas_eliminadas:,}"
    )

    print(
        f"Filas restantes              : "
        f"{total_despues:,}"
    )

    print(
        f"Reducción lógica             : "
        f"{reduccion:.2f}%"
    )

    print(
        f"Primer snapshot conservado   : "
        f"{snapshot_referencia_id}"
    )

    print(
        f"Último snapshot conservado   : "
        f"{ultimo_snapshot_id}"
    )

    print()
    print(
        "✅ RETENCIÓN APLICADA CORRECTAMENTE"
    )

    print()
    print(
        "ℹ️ No se eliminaron registros de "
        "snapshots, metricas_snapshot, "
        "cambios_snapshot ni tablas maestro."
    )

    print()


if __name__ == "__main__":
    main()