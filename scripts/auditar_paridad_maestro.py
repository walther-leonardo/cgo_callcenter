from __future__ import annotations

import pandas as pd

from database import get_connection


COLUMNAS_ESTADO = [
    "estatus_cita",
    "motivo_visita",
    "fecha_programada",
    "hora_programada",
    "origen_cita",
    "persona_agenda",
    "fecha_creacion",
    "nombre",
    "celular",
    "asesor_servicio",
    "modelo",
    "placa",
    "kilometraje",
]


def normalizar_valor(
    valor,
):
    """
    Normaliza valores para evitar diferencias falsas
    causadas únicamente por None / NaN.
    """

    if pd.isna(valor):
        return None

    return valor


def main() -> None:

    print()
    print("=" * 90)
    print("CGO CALL CENTER — AUDITORÍA PARIDAD CITAS MAESTRO")
    print("=" * 90)

    with get_connection() as conn:

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

        if ultimo_snapshot.empty:
            raise RuntimeError(
                "No existen snapshots registrados."
            )

        snapshot_id = int(
            ultimo_snapshot.iloc[0][
                "snapshot_id"
            ]
        )

        fecha_corte = (
            ultimo_snapshot.iloc[0][
                "fecha_hora_corte"
            ]
        )

        cantidad_esperada = int(
            ultimo_snapshot.iloc[0][
                "cantidad_citas"
            ]
        )

        snapshot = pd.read_sql_query(
            """
            SELECT *
            FROM citas_snapshot
            WHERE snapshot_id = ?
            """,
            conn,
            params=[
                snapshot_id,
            ],
        )

        maestro = pd.read_sql_query(
            """
            SELECT *
            FROM citas_maestro
            WHERE presente_en_ultimo_snapshot = 1
            """,
            conn,
        )

    # ========================================================
    # CONTROL DE CANTIDADES
    # ========================================================

    ids_snapshot = set(
        snapshot[
            "id_cita"
        ].astype(int)
    )

    ids_maestro = set(
        maestro[
            "id_cita"
        ].astype(int)
    )

    faltan_maestro = (
        ids_snapshot
        -
        ids_maestro
    )

    sobran_maestro = (
        ids_maestro
        -
        ids_snapshot
    )

    # ========================================================
    # CONTROL DE CAMPOS
    # ========================================================

    snapshot_idx = (
        snapshot
        .set_index(
            "id_cita"
        )
        .sort_index()
    )

    maestro_idx = (
        maestro
        .set_index(
            "id_cita"
        )
        .sort_index()
    )

    ids_comunes = sorted(
        ids_snapshot
        &
        ids_maestro
    )

    diferencias = []

    for id_cita in ids_comunes:

        fila_snapshot = (
            snapshot_idx.loc[
                id_cita
            ]
        )

        fila_maestro = (
            maestro_idx.loc[
                id_cita
            ]
        )

        for columna in COLUMNAS_ESTADO:

            valor_snapshot = normalizar_valor(
                fila_snapshot[
                    columna
                ]
            )

            valor_maestro = normalizar_valor(
                fila_maestro[
                    columna
                ]
            )

            if (
                valor_snapshot
                != valor_maestro
            ):

                diferencias.append(
                    {
                        "id_cita":
                            id_cita,

                        "campo":
                            columna,

                        "snapshot":
                            valor_snapshot,

                        "maestro":
                            valor_maestro,
                    }
                )

    diferencias_df = pd.DataFrame(
        diferencias
    )

    # ========================================================
    # CONTROL DE METADATA MAESTRO
    # ========================================================

    ultimo_snapshot_incorrecto = (
        maestro.loc[
            maestro[
                "ultimo_snapshot_id"
            ].ne(
                snapshot_id
            )
        ]
    )

    ultima_deteccion_incorrecta = (
        maestro.loc[
            maestro[
                "ultima_deteccion"
            ].ne(
                fecha_corte
            )
        ]
    )

    # ========================================================
    # RESULTADO
    # ========================================================

    print()
    print("ÚLTIMO CORTE")
    print("-" * 90)

    print(
        f"Snapshot ID       : "
        f"{snapshot_id}"
    )

    print(
        f"Fecha corte       : "
        f"{fecha_corte}"
    )

    print(
        f"Cantidad declarada: "
        f"{cantidad_esperada:,}"
    )

    print()
    print("CANTIDADES")
    print("-" * 90)

    print(
        f"Citas snapshot            : "
        f"{len(snapshot):,}"
    )

    print(
        f"Citas maestro presentes   : "
        f"{len(maestro):,}"
    )

    print(
        f"Faltan en maestro         : "
        f"{len(faltan_maestro):,}"
    )

    print(
        f"Sobran en maestro         : "
        f"{len(sobran_maestro):,}"
    )

    print()
    print("CONTENIDO")
    print("-" * 90)

    print(
        f"Diferencias de campos     : "
        f"{len(diferencias_df):,}"
    )

    print(
        f"ultimo_snapshot incorrecto: "
        f"{len(ultimo_snapshot_incorrecto):,}"
    )

    print(
        f"ultima_deteccion incorrecta: "
        f"{len(ultima_deteccion_incorrecta):,}"
    )

    # ========================================================
    # DETALLE SOLO SI HAY PROBLEMAS
    # ========================================================

    if faltan_maestro:

        print()
        print("IDS QUE FALTAN EN MAESTRO")
        print("-" * 90)

        print(
            sorted(
                faltan_maestro
            )[:20]
        )

    if sobran_maestro:

        print()
        print("IDS QUE SOBRAN EN MAESTRO")
        print("-" * 90)

        print(
            sorted(
                sobran_maestro
            )[:20]
        )

    if not diferencias_df.empty:

        print()
        print("DIFERENCIAS DE CONTENIDO")
        print("-" * 90)

        print(
            diferencias_df
            .head(30)
            .to_string(
                index=False
            )
        )

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    paridad_ok = (
        len(snapshot)
        == cantidad_esperada
        == len(maestro)
        and not faltan_maestro
        and not sobran_maestro
        and diferencias_df.empty
        and ultimo_snapshot_incorrecto.empty
        and ultima_deteccion_incorrecta.empty
    )

    print()
    print("=" * 90)

    if paridad_ok:

        print(
            "✅ PARIDAD 100% — MAESTRO Y ÚLTIMO SNAPSHOT COINCIDEN"
        )

    else:

        print(
            "⚠️ PARIDAD INCOMPLETA — REVISAR DIFERENCIAS"
        )

    print("=" * 90)
    print()


if __name__ == "__main__":
    main()