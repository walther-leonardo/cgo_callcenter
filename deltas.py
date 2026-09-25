from __future__ import annotations

import pandas as pd

from database import get_connection


COLUMNAS_COMPARACION = [
    "fecha_programada",
    "hora_programada",
    "estatus_cita",
    "persona_agenda",
    "asesor_servicio",
    "origen_cita",
]


def cargar_ultimos_snapshots() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict,
    dict,
]:
    """
    Obtiene los dos últimos snapshots registrados.
    """

    with get_connection() as conn:

        snapshots = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                fecha_hora_corte,
                cantidad_citas
            FROM snapshots
            ORDER BY snapshot_id DESC
            LIMIT 2
            """,
            conn,
        )

        if len(snapshots) < 2:
            raise ValueError(
                "Se necesitan al menos dos snapshots "
                "para calcular deltas."
            )

        actual_info = (
            snapshots.iloc[0].to_dict()
        )

        anterior_info = (
            snapshots.iloc[1].to_dict()
        )

        actual = pd.read_sql_query(
            """
            SELECT *
            FROM citas_snapshot
            WHERE snapshot_id = ?
            """,
            conn,
            params=[
                actual_info[
                    "snapshot_id"
                ]
            ],
        )

        anterior = pd.read_sql_query(
            """
            SELECT *
            FROM citas_snapshot
            WHERE snapshot_id = ?
            """,
            conn,
            params=[
                anterior_info[
                    "snapshot_id"
                ]
            ],
        )

    return (
        anterior,
        actual,
        anterior_info,
        actual_info,
    )


def comparar_snapshots(
    anterior: pd.DataFrame,
    actual: pd.DataFrame,
) -> dict:
    """
    Compara dos fotografías completas de ClearMechanic.
    """

    anterior = anterior.copy()
    actual = actual.copy()

    ids_anterior = set(
        anterior[
            "id_cita"
        ]
    )

    ids_actual = set(
        actual[
            "id_cita"
        ]
    )

    ids_nuevas = (
        ids_actual
        -
        ids_anterior
    )

    ids_desaparecidas = (
        ids_anterior
        -
        ids_actual
    )

    ids_comunes = (
        ids_anterior
        &
        ids_actual
    )

    nuevas = (
        actual.loc[
            actual[
                "id_cita"
            ].isin(
                ids_nuevas
            )
        ]
        .copy()
    )

    desaparecidas = (
        anterior.loc[
            anterior[
                "id_cita"
            ].isin(
                ids_desaparecidas
            )
        ]
        .copy()
    )

    anterior_comun = (
        anterior.loc[
            anterior[
                "id_cita"
            ].isin(
                ids_comunes
            )
        ]
        .set_index(
            "id_cita"
        )
        .sort_index()
    )

    actual_comun = (
        actual.loc[
            actual[
                "id_cita"
            ].isin(
                ids_comunes
            )
        ]
        .set_index(
            "id_cita"
        )
        .sort_index()
    )

    cambios = []

    for id_cita in sorted(
        ids_comunes
    ):

        fila_anterior = (
            anterior_comun.loc[
                id_cita
            ]
        )

        fila_actual = (
            actual_comun.loc[
                id_cita
            ]
        )

        for columna in COLUMNAS_COMPARACION:

            valor_anterior = (
                fila_anterior[
                    columna
                ]
            )

            valor_actual = (
                fila_actual[
                    columna
                ]
            )

            anterior_nulo = (
                pd.isna(
                    valor_anterior
                )
            )

            actual_nulo = (
                pd.isna(
                    valor_actual
                )
            )

            if (
                anterior_nulo
                and actual_nulo
            ):
                continue

            if (
                anterior_nulo
                != actual_nulo
                or str(
                    valor_anterior
                )
                != str(
                    valor_actual
                )
            ):

                cambios.append(
                    {
                        "id_cita":
                            id_cita,

                        "campo":
                            columna,

                        "valor_anterior":
                            (
                                None
                                if anterior_nulo
                                else str(
                                    valor_anterior
                                )
                            ),

                        "valor_actual":
                            (
                                None
                                if actual_nulo
                                else str(
                                    valor_actual
                                )
                            ),
                    }
                )

    cambios = pd.DataFrame(
        cambios
    )

    if cambios.empty:

        cambios_estado = (
            pd.DataFrame()
        )

        reprogramaciones = (
            pd.DataFrame()
        )

    else:

        cambios_estado = (
            cambios.loc[
                cambios[
                    "campo"
                ].eq(
                    "estatus_cita"
                )
            ]
            .copy()
        )

        reprogramaciones = (
            cambios.loc[
                cambios[
                    "campo"
                ].isin(
                    [
                        "fecha_programada",
                        "hora_programada",
                    ]
                )
            ]
            .copy()
        )

    return {
        "nuevas":
            nuevas,

        "desaparecidas":
            desaparecidas,

        "cambios":
            cambios,

        "cambios_estado":
            cambios_estado,

        "reprogramaciones":
            reprogramaciones,
    }


def auditar_fecha_creacion(
    citas: pd.DataFrame,
    fecha_corte,
) -> pd.DataFrame:
    """
    Identifica registros cuya fecha de creación aparece
    posterior al momento en que se tomó el snapshot.
    """

    df = citas.copy()

    df[
        "fecha_creacion"
    ] = pd.to_datetime(
        df[
            "fecha_creacion"
        ],
        errors="coerce",
    )

    corte = pd.to_datetime(
        fecha_corte
    )

    return (
        df.loc[
            df[
                "fecha_creacion"
            ]
            >
            corte
        ]
        .copy()
    )


def main() -> None:

    print()
    print("=" * 76)
    print("CGO CALL CENTER — DELTA ENTRE SNAPSHOTS")
    print("=" * 76)

    (
        anterior,
        actual,
        anterior_info,
        actual_info,
    ) = cargar_ultimos_snapshots()

    resultado = comparar_snapshots(
        anterior=
            anterior,
        actual=
            actual,
    )

    nuevas = (
        resultado[
            "nuevas"
        ]
    )

    desaparecidas = (
        resultado[
            "desaparecidas"
        ]
    )

    cambios_estado = (
        resultado[
            "cambios_estado"
        ]
    )

    reprogramaciones = (
        resultado[
            "reprogramaciones"
        ]
    )

    fecha_anterior = pd.to_datetime(
        anterior_info[
            "fecha_hora_corte"
        ]
    )

    fecha_actual = pd.to_datetime(
        actual_info[
            "fecha_hora_corte"
        ]
    )

    intervalo = (
        fecha_actual
        -
        fecha_anterior
    )

    print()
    print("CORTES")
    print("-" * 76)

    print(
        f"Anterior : "
        f"#{anterior_info['snapshot_id']} "
        f"{fecha_anterior:%d/%m/%Y %H:%M:%S} "
        f"({len(anterior):,} citas)"
    )

    print(
        f"Actual   : "
        f"#{actual_info['snapshot_id']} "
        f"{fecha_actual:%d/%m/%Y %H:%M:%S} "
        f"({len(actual):,} citas)"
    )

    print(
        f"Intervalo: "
        f"{intervalo}"
    )

    print()
    print("DELTA")
    print("-" * 76)

    print(
        f"Nuevas citas          : {len(nuevas):,}"
    )

    print(
        f"Desaparecidas         : {len(desaparecidas):,}"
    )

    print(
        f"Reprogramaciones      : {len(reprogramaciones):,}"
    )

    print(
        f"Cambios de estado     : {len(cambios_estado):,}"
    )

    # ========================================================
    # NUEVAS CITAS
    # ========================================================

    print()
    print("NUEVAS CITAS")
    print("-" * 76)

    if nuevas.empty:

        print(
            "No se detectaron citas nuevas."
        )

    else:

        columnas = [
            "id_cita",
            "fecha_creacion",
            "fecha_programada",
            "hora_programada",
            "persona_agenda",
            "estatus_cita",
            "placa",
        ]

        print(
            nuevas[
                columnas
            ]
            .sort_values(
                [
                    "persona_agenda",
                    "fecha_programada",
                    "hora_programada",
                ]
            )
            .to_string(
                index=False
            )
        )

        print()
        print("NUEVAS POR PERSONA QUE AGENDA")
        print("-" * 76)

        por_agente = (
            nuevas[
                "persona_agenda"
            ]
            .value_counts(
                dropna=False
            )
            .rename_axis(
                "persona_agenda"
            )
            .reset_index(
                name="nuevas"
            )
        )

        print(
            por_agente.to_string(
                index=False
            )
        )

        print()
        print("NUEVAS POR FECHA PROGRAMADA")
        print("-" * 76)

        por_fecha = (
            nuevas[
                "fecha_programada"
            ]
            .value_counts()
            .sort_index()
            .rename_axis(
                "fecha_programada"
            )
            .reset_index(
                name="nuevas"
            )
        )

        print(
            por_fecha.to_string(
                index=False
            )
        )

    # ========================================================
    # CAMBIOS DE ESTADO
    # ========================================================

    if not cambios_estado.empty:

        print()
        print("CAMBIOS DE ESTADO")
        print("-" * 76)

        print(
            cambios_estado.to_string(
                index=False
            )
        )

    # ========================================================
    # REPROGRAMACIONES
    # ========================================================

    if not reprogramaciones.empty:

        print()
        print("REPROGRAMACIONES")
        print("-" * 76)

        print(
            reprogramaciones.to_string(
                index=False
            )
        )

    # ========================================================
    # AUDITORÍA FECHA CREACIÓN
    # ========================================================

    futuras = auditar_fecha_creacion(
        citas=actual,
        fecha_corte=
            actual_info[
                "fecha_hora_corte"
            ],
    )

    print()
    print("AUDITORÍA FECHA DE CREACIÓN")
    print("-" * 76)

    print(
        "Registros con fecha_creacion "
        "posterior al corte: "
        f"{len(futuras):,}"
    )

    if not futuras.empty:

        print()

        print(
            futuras[
                [
                    "id_cita",
                    "fecha_creacion",
                    "persona_agenda",
                ]
            ]
            .sort_values(
                "fecha_creacion"
            )
            .tail(10)
            .to_string(
                index=False
            )
        )

    print()


if __name__ == "__main__":
    main()