from __future__ import annotations

import pandas as pd

from clasificaciones import clasificar_sentido_origen
from database import get_connection
from procesamiento import construir_vista_operativa_citas


# ============================================================
# CLASIFICACIÓN TEMPORAL DE LA AGENDA
# ============================================================

BUCKETS_PRINCIPALES = [
    "HOY",
    "MANANA",
    "PASADO_MANANA_O_MAS",
]

ORIGENES_CITA = [
    "ENTRANTE",
    "SALIENTE",
]

def preparar_citas(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convierte fechas almacenadas en SQLite a datetime.
    """

    resultado = df.copy()

    resultado[
        "fecha_programada"
    ] = pd.to_datetime(
        resultado[
            "fecha_programada"
        ],
        errors="coerce",
    ).dt.normalize()

    resultado[
        "fecha_creacion"
    ] = pd.to_datetime(
        resultado[
            "fecha_creacion"
        ],
        errors="coerce",
    )

    return resultado


def clasificar_fecha_programada(
    fecha_programada,
    fecha_base: pd.Timestamp,
) -> str:
    """
    Clasifica una cita según distancia respecto al día del corte.
    """

    if pd.isna(fecha_programada):
        return "SIN_FECHA"

    dias = (
        pd.Timestamp(
            fecha_programada
        ).normalize()
        -
        fecha_base.normalize()
    ).days

    if dias < 0:
        return "PASADO"

    if dias == 0:
        return "HOY"

    if dias == 1:
        return "MANANA"

    return "PASADO_MANANA_O_MAS"


def agregar_bucket(
    df: pd.DataFrame,
    fecha_base: pd.Timestamp,
) -> pd.DataFrame:
    """
    Añade clasificación HOY / MAÑANA / D+2+.
    """

    resultado = df.copy()

    resultado[
        "bucket"
    ] = resultado[
        "fecha_programada"
    ].apply(
        lambda fecha:
            clasificar_fecha_programada(
                fecha_programada=fecha,
                fecha_base=fecha_base,
            )
    )

    return resultado


# ============================================================
# CARGA DE SNAPSHOTS
# ============================================================

def cargar_info_snapshot(
    snapshot_id: int,
) -> tuple[dict, pd.DataFrame]:
    """
    Obtiene cabecera y citas de un snapshot concreto.
    """

    with get_connection() as conn:

        info = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                fecha_hora_corte,
                cantidad_citas
            FROM snapshots
            WHERE snapshot_id = ?
            """,
            conn,
            params=[
                snapshot_id
            ],
        )

        if info.empty:
            raise ValueError(
                f"No existe el snapshot #{snapshot_id}."
            )

        citas = pd.read_sql_query(
            """
            SELECT *
            FROM citas_snapshot
            WHERE snapshot_id = ?
            """,
            conn,
            params=[
                snapshot_id
            ],
        )

    return (
        info.iloc[0].to_dict(),
        preparar_citas(
            citas
        ),
    )


def obtener_snapshot_anterior(
    snapshot_id: int,
) -> int | None:
    """
    Obtiene el snapshot inmediatamente anterior.
    """

    with get_connection() as conn:

        cursor = conn.execute(
            """
            SELECT snapshot_id
            FROM snapshots
            WHERE snapshot_id < ?
            ORDER BY snapshot_id DESC
            LIMIT 1
            """,
            (
                snapshot_id,
            ),
        )

        fila = cursor.fetchone()

    if fila is None:
        return None

    return int(
        fila[0]
    )


def obtener_primer_snapshot_del_dia(
    snapshot_id: int,
    fecha_corte: pd.Timestamp,
) -> int:
    """
    Obtiene el primer snapshot registrado en la misma fecha.
    """

    fecha_texto = (
        fecha_corte
        .strftime(
            "%Y-%m-%d"
        )
    )

    with get_connection() as conn:

        cursor = conn.execute(
            """
            SELECT snapshot_id
            FROM snapshots
            WHERE
                snapshot_id <= ?
                AND substr(fecha_hora_corte, 1, 10) = ?
            ORDER BY snapshot_id
            LIMIT 1
            """,
            (
                snapshot_id,
                fecha_texto,
            ),
        )

        fila = cursor.fetchone()

    if fila is None:
        return snapshot_id

    return int(
        fila[0]
    )


# ============================================================
# COMPARACIÓN
# ============================================================

def comparar_snapshots(
    anterior: pd.DataFrame,
    actual: pd.DataFrame,
) -> dict:
    """
    Identifica nuevas, desaparecidas y modificaciones.
    """

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
        ids_actual
        &
        ids_anterior
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

    anterior_idx = (
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
    )

    actual_idx = (
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
    )

    columnas_comparar = [
        "fecha_programada",
        "hora_programada",
        "estatus_cita",
        "persona_agenda",
        "asesor_servicio",
        "origen_cita",
    ]

    cambios = []

    for id_cita in sorted(
        ids_comunes
    ):

        fila_anterior = (
            anterior_idx.loc[
                id_cita
            ]
        )

        fila_actual = (
            actual_idx.loc[
                id_cita
            ]
        )

        for columna in columnas_comparar:

            anterior_valor = (
                fila_anterior[
                    columna
                ]
            )

            actual_valor = (
                fila_actual[
                    columna
                ]
            )

            anterior_nulo = (
                pd.isna(
                    anterior_valor
                )
            )

            actual_nulo = (
                pd.isna(
                    actual_valor
                )
            )

            if (
                anterior_nulo
                and actual_nulo
            ):
                continue

            iguales = (
                not anterior_nulo
                and not actual_nulo
                and str(
                    anterior_valor
                )
                ==
                str(
                    actual_valor
                )
            )

            if iguales:
                continue

            if columna == "estatus_cita":
                tipo = "CAMBIO_ESTADO"

            elif columna in [
                "fecha_programada",
                "hora_programada",
            ]:
                tipo = "REPROGRAMACION"

            else:
                tipo = "CAMBIO_OTRO"

            cambios.append(
                {
                    "id_cita":
                        int(
                            id_cita
                        ),

                    "tipo_cambio":
                        tipo,

                    "campo":
                        columna,

                    "valor_anterior":
                        (
                            None
                            if anterior_nulo
                            else str(
                                anterior_valor
                            )
                        ),

                    "valor_actual":
                        (
                            None
                            if actual_nulo
                            else str(
                                actual_valor
                            )
                        ),
                }
            )

    return {
        "nuevas":
            nuevas,

        "desaparecidas":
            desaparecidas,

        "cambios":
            cambios,
    }


# ============================================================
# MÉTRICAS
# ============================================================

def agregar_metrica(
    metricas: list[dict],
    metrica: str,
    dimension: str,
    segmento: str,
    valor,
) -> None:
    """
    Añade una métrica normalizada a la colección.
    """

    metricas.append(
        {
            "metrica":
                metrica,

            "dimension":
                dimension,

            "segmento":
                str(
                    segmento
                ),

            "valor":
                float(
                    valor
                ),
        }
    )


def guardar_metricas_bucket(
    metricas: list[dict],
    df: pd.DataFrame,
    nombre_metrica: str,
) -> None:
    """
    Guarda conteo por bucket temporal.
    """

    conteo = (
        df[
            "bucket"
        ]
        .value_counts()
        .to_dict()
    )

    for bucket in BUCKETS_PRINCIPALES:

        agregar_metrica(
            metricas=metricas,
            metrica=nombre_metrica,
            dimension="BUCKET",
            segmento=bucket,
            valor=conteo.get(
                bucket,
                0,
            ),
        )


def guardar_metricas_agente(
    metricas: list[dict],
    df: pd.DataFrame,
    nombre_metrica: str,
) -> None:
    """
    Guarda conteo por persona que agenda.
    """

    if df.empty:
        return

    conteo = (
        df[
            "persona_agenda"
        ]
        .fillna(
            "SIN_AGENTE"
        )
        .value_counts()
    )

    for agente, valor in conteo.items():

        agregar_metrica(
            metricas=metricas,
            metrica=nombre_metrica,
            dimension="AGENTE",
            segmento=agente,
            valor=valor,
        )


def guardar_metricas_agente_bucket(
    metricas: list[dict],
    df: pd.DataFrame,
    nombre_metrica: str,
) -> None:
    """
    Guarda el volumen de citas por agente y bucket temporal.

    El segmento se almacena como:
        AGENTE||BUCKET

    Ejemplo:
        Rocio Miranda Ausejo||MANANA
    """

    if df.empty:
        return

    base = df.copy()

    base["persona_agenda"] = (
        base["persona_agenda"]
        .fillna("SIN_AGENTE")
        .astype(str)
    )

    resumen = (
        base
        .groupby(
            [
                "persona_agenda",
                "bucket",
            ],
            observed=True,
        )
        .size()
        .reset_index(
            name="valor"
        )
    )

    for fila in resumen.itertuples(
        index=False
    ):

        agregar_metrica(
            metricas=metricas,
            metrica=nombre_metrica,
            dimension="AGENTE_BUCKET",
            segmento=(
                f"{fila.persona_agenda}"
                f"||"
                f"{fila.bucket}"
            ),
            valor=fila.valor,
        )


def guardar_metricas_origen(
    metricas: list[dict],
    df: pd.DataFrame,
    nombre_metrica: str,
) -> None:
    """
    Guarda el volumen de citas segmentado por origen:
    ENTRANTE / SALIENTE.
    """

    if df.empty:

        for origen in ORIGENES_CITA:

            agregar_metrica(
                metricas=metricas,
                metrica=nombre_metrica,
                dimension="ORIGEN",
                segmento=origen,
                valor=0,
            )

        return

    base = df.copy()

    base[
        "sentido_origen"
    ] = base[
        "origen_cita"
    ].apply(
        clasificar_sentido_origen
    )

    conteo = (
        base[
            "sentido_origen"
        ]
        .value_counts()
        .to_dict()
    )

    for origen in ORIGENES_CITA:

        agregar_metrica(
            metricas=metricas,
            metrica=nombre_metrica,
            dimension="ORIGEN",
            segmento=origen,
            valor=conteo.get(
                origen,
                0,
            ),
        )


# ============================================================
# PERSISTENCIA ANALÍTICA
# ============================================================

def guardar_analitica_snapshot(
    snapshot_id: int,
) -> None:
    """
    Calcula y persiste deltas/KPI asociados a un snapshot.

    Los snapshots almacenan la fotografía completa de
    ClearMechanic, incluidas citas Canceladas y duplicados.

    Los KPI operativos utilizan una vista depurada:
    - excluye Canceladas;
    - deduplica según las reglas de negocio.

    Es idempotente:
    si se ejecuta nuevamente para el mismo snapshot,
    reemplaza sus métricas y cambios anteriores.
    """

    # ========================================================
    # SNAPSHOT ACTUAL — RAW
    # ========================================================

    (
        actual_info,
        actual_raw,
    ) = cargar_info_snapshot(
        snapshot_id
    )

    fecha_corte = pd.to_datetime(
        actual_info[
            "fecha_hora_corte"
        ]
    )

    fecha_base = (
        fecha_corte
        .normalize()
    )

    # ========================================================
    # SNAPSHOT ACTUAL — VISTA OPERATIVA
    # ========================================================

    actual = (
        construir_vista_operativa_citas(
            actual_raw
        )
    )

    actual = agregar_bucket(
        df=actual,
        fecha_base=fecha_base,
    )

    # ========================================================
    # REFERENCIAS
    # ========================================================

    snapshot_anterior_id = (
        obtener_snapshot_anterior(
            snapshot_id
        )
    )

    primer_snapshot_id = (
        obtener_primer_snapshot_del_dia(
            snapshot_id=
                snapshot_id,
            fecha_corte=
                fecha_corte,
        )
    )

    # ========================================================
    # MÉTRICAS
    # ========================================================

    metricas: list[dict] = []

    # --------------------------------------------------------
    # AGENDA ACTUAL
    # --------------------------------------------------------

    agregar_metrica(
        metricas=metricas,
        metrica="AGENDA_ACTUAL",
        dimension="TOTAL",
        segmento="TOTAL",
        valor=len(
            actual
        ),
    )

    guardar_metricas_bucket(
        metricas=metricas,
        df=actual,
        nombre_metrica="AGENDA_ACTUAL",
    )

    cambios_db = []

    # ========================================================
    # DELTA CONTRA CORTE ANTERIOR
    # ========================================================

    if snapshot_anterior_id is not None:

        (
            _,
            anterior_raw,
        ) = cargar_info_snapshot(
            snapshot_anterior_id
        )

        # ----------------------------------------------------
        # VISTA OPERATIVA ANTERIOR
        # ----------------------------------------------------

        anterior = (
            construir_vista_operativa_citas(
                anterior_raw
            )
        )

        anterior = agregar_bucket(
            df=anterior,
            fecha_base=fecha_base,
        )

        # ----------------------------------------------------
        # DELTA OPERATIVO
        #
        # Sirve para:
        # - nuevas
        # - desaparecidas de agenda activa
        # ----------------------------------------------------

        delta_operativo = comparar_snapshots(
            anterior=anterior,
            actual=actual,
        )

        nuevas = delta_operativo[
            "nuevas"
        ]

        desaparecidas = delta_operativo[
            "desaparecidas"
        ]

        agregar_metrica(
            metricas=metricas,
            metrica="NUEVAS_ULTIMO_CORTE",
            dimension="TOTAL",
            segmento="TOTAL",
            valor=len(
                nuevas
            ),
        )

        guardar_metricas_bucket(
            metricas=metricas,
            df=nuevas,
            nombre_metrica="NUEVAS_ULTIMO_CORTE",
        )

        guardar_metricas_agente(
            metricas=metricas,
            df=nuevas,
            nombre_metrica="NUEVAS_ULTIMO_CORTE",
        )

        guardar_metricas_agente_bucket(
            metricas=metricas,
            df=nuevas,
            nombre_metrica="NUEVAS_ULTIMO_CORTE",
        )

        agregar_metrica(
            metricas=metricas,
            metrica="DESAPARECIDAS_ULTIMO_CORTE",
            dimension="TOTAL",
            segmento="TOTAL",
            valor=len(
                desaparecidas
            ),
        )

        # ----------------------------------------------------
        # REGISTRAR CAMBIOS OPERATIVOS
        # ----------------------------------------------------

        for fila in nuevas.itertuples(
            index=False
        ):

            cambios_db.append(
                {
                    "id_cita":
                        int(
                            fila.id_cita
                        ),

                    "tipo_cambio":
                        "NUEVA_CITA",

                    "campo":
                        None,

                    "valor_anterior":
                        None,

                    "valor_actual":
                        None,
                }
            )

        for fila in desaparecidas.itertuples(
            index=False
        ):

            cambios_db.append(
                {
                    "id_cita":
                        int(
                            fila.id_cita
                        ),

                    "tipo_cambio":
                        "DESAPARECE_DE_AGENDA_ACTIVA",

                    "campo":
                        None,

                    "valor_anterior":
                        None,

                    "valor_actual":
                        None,
                }
            )

        # ----------------------------------------------------
        # DELTA RAW
        #
        # Permite conservar cambios reales de ClearMechanic,
        # especialmente:
        #
        # Orden creada → Cancelada
        # ----------------------------------------------------

        delta_raw = comparar_snapshots(
            anterior=anterior_raw,
            actual=actual_raw,
        )

        cambios_raw = delta_raw[
            "cambios"
        ]

        cambios_db.extend(
            cambios_raw
        )

        # ----------------------------------------------------
        # CAMBIOS DE ESTADO
        # ----------------------------------------------------

        agregar_metrica(
            metricas=metricas,
            metrica="CAMBIOS_ESTADO_ULTIMO_CORTE",
            dimension="TOTAL",
            segmento="TOTAL",
            valor=sum(
                cambio[
                    "tipo_cambio"
                ]
                ==
                "CAMBIO_ESTADO"

                for cambio
                in cambios_raw
            ),
        )

        # ----------------------------------------------------
        # REPROGRAMACIONES
        # ----------------------------------------------------

        agregar_metrica(
            metricas=metricas,
            metrica="REPROGRAMACIONES_ULTIMO_CORTE",
            dimension="TOTAL",
            segmento="TOTAL",
            valor=len(
                {
                    cambio[
                        "id_cita"
                    ]
                    for cambio
                    in cambios_raw
                    if cambio[
                        "tipo_cambio"
                    ]
                    ==
                    "REPROGRAMACION"
                }
            ),
        )

    # ========================================================
    # DELTA DESDE PRIMER CORTE DEL DÍA
    # ========================================================

    (
        _,
        inicio_dia_raw,
    ) = cargar_info_snapshot(
        primer_snapshot_id
    )

    inicio_dia = (
        construir_vista_operativa_citas(
            inicio_dia_raw
        )
    )

    inicio_dia = agregar_bucket(
        df=inicio_dia,
        fecha_base=fecha_base,
    )

    ids_inicio = set(
        inicio_dia[
            "id_cita"
        ]
    )

    nuevas_dia = (
        actual.loc[
            ~actual[
                "id_cita"
            ].isin(
                ids_inicio
            )
        ]
        .copy()
    )

    agregar_metrica(
        metricas=metricas,
        metrica="NUEVAS_DESDE_INICIO_DIA",
        dimension="TOTAL",
        segmento="TOTAL",
        valor=len(
            nuevas_dia
        ),
    )

    guardar_metricas_bucket(
        metricas=metricas,
        df=nuevas_dia,
        nombre_metrica="NUEVAS_DESDE_INICIO_DIA",
    )

    guardar_metricas_agente(
        metricas=metricas,
        df=nuevas_dia,
        nombre_metrica="NUEVAS_DESDE_INICIO_DIA",
    )

    guardar_metricas_agente_bucket(
        metricas=metricas,
        df=nuevas_dia,
        nombre_metrica="NUEVAS_DESDE_INICIO_DIA",
    )

    guardar_metricas_origen(
        metricas=metricas,
        df=nuevas_dia,
        nombre_metrica="NUEVAS_DESDE_INICIO_DIA",
    )

    # ========================================================
    # PERSISTENCIA
    # ========================================================

    with get_connection() as conn:

        conn.execute(
            """
            DELETE FROM metricas_snapshot
            WHERE snapshot_id = ?
            """,
            (
                snapshot_id,
            ),
        )

        conn.execute(
            """
            DELETE FROM cambios_snapshot
            WHERE snapshot_id = ?
            """,
            (
                snapshot_id,
            ),
        )

        conn.executemany(
            """
            INSERT INTO metricas_snapshot (
                snapshot_id,
                metrica,
                dimension,
                segmento,
                valor
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_id,
                    fila[
                        "metrica"
                    ],
                    fila[
                        "dimension"
                    ],
                    fila[
                        "segmento"
                    ],
                    fila[
                        "valor"
                    ],
                )
                for fila in metricas
            ],
        )

        if cambios_db:

            conn.executemany(
                """
                INSERT INTO cambios_snapshot (
                    snapshot_id,
                    snapshot_anterior_id,
                    id_cita,
                    tipo_cambio,
                    campo,
                    valor_anterior,
                    valor_actual
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_id,
                        snapshot_anterior_id,
                        cambio[
                            "id_cita"
                        ],
                        cambio[
                            "tipo_cambio"
                        ],
                        cambio[
                            "campo"
                        ],
                        cambio[
                            "valor_anterior"
                        ],
                        cambio[
                            "valor_actual"
                        ],
                    )
                    for cambio
                    in cambios_db
                ],
            )

        conn.commit()


def mostrar_resumen_snapshot(
    snapshot_id: int,
) -> None:
    """
    Muestra en consola los principales KPI persistidos.
    """

    with get_connection() as conn:

        metricas = pd.read_sql_query(
            """
            SELECT
                metrica,
                dimension,
                segmento,
                valor
            FROM metricas_snapshot
            WHERE snapshot_id = ?
            ORDER BY
                metrica,
                dimension,
                segmento
            """,
            conn,
            params=[
                snapshot_id
            ],
        )

    print()
    print("ANALÍTICA DEL CORTE")
    print("-" * 64)

    principales = metricas.loc[
        (
            metricas[
                "dimension"
            ].eq(
                "TOTAL"
            )
        )
        |
        (
            metricas[
                "dimension"
            ].eq(
                "BUCKET"
            )
            &
            metricas[
                "metrica"
            ].isin(
                [
                    "NUEVAS_ULTIMO_CORTE",
                    "NUEVAS_DESDE_INICIO_DIA",
                ]
            )
        )
    ]

    for fila in principales.itertuples(
        index=False
    ):

        print(
            f"{fila.metrica:<30} "
            f"{fila.segmento:<25} "
            f"{int(fila.valor):>5}"
        )