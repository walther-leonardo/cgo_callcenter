from __future__ import annotations

import pandas as pd

from clasificaciones import enriquecer_clasificaciones


# ============================================================
# ÓRDENES DE PRESENTACIÓN
# ============================================================

ORDEN_SEDE = {
    "SAN ISIDRO": 1,
    "SAN MIGUEL": 2,
    "INDETERMINADO": 3,
}

ORDEN_FACTURACION = {
    "FACTURABLE": 1,
    "NO FACTURABLE": 2,
    "INDETERMINADO": 3,
}

ORDEN_SERVICIO = {
    "Preventivo": 1,
    "Correctivo": 2,
    "Garantía": 3,
    "PYP": 4,
    "01K": 5,
    "Diagnóstico": 6,
    "Otros": 7,
    "INDETERMINADO": 99,
}


# ============================================================
# HELPERS
# ============================================================

def _filtrar_fecha_programada(
    citas: pd.DataFrame,
    fecha_objetivo,
) -> pd.DataFrame:
    """
    Filtra citas por la fecha programada.

    La misma función permite construir:
        - reporte de hoy
        - reporte de mañana
        - cualquier fecha futura
    """

    df = citas.copy()

    if "fecha_programada" not in df.columns:
        raise ValueError(
            "La base de citas no contiene la columna "
            "'fecha_programada'."
        )

    df["fecha_programada"] = pd.to_datetime(
        df["fecha_programada"],
        errors="coerce",
    ).dt.normalize()

    fecha = pd.Timestamp(
        fecha_objetivo
    ).normalize()

    return (
        df.loc[
            df[
                "fecha_programada"
            ].eq(
                fecha
            )
        ]
        .copy()
    )


def _ordenar_reporte(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aplica el orden gerencial definido para sede,
    tipo de facturación y tipo de servicio.
    """

    resultado = df.copy()

    resultado["_orden_sede"] = (
        resultado["sede"]
        .map(
            ORDEN_SEDE
        )
        .fillna(99)
    )

    resultado["_orden_facturacion"] = (
        resultado["tipo_facturacion"]
        .map(
            ORDEN_FACTURACION
        )
        .fillna(99)
    )

    resultado["_orden_servicio"] = (
        resultado["tipo_servicio"]
        .map(
            ORDEN_SERVICIO
        )
        .fillna(99)
    )

    resultado = (
        resultado
        .sort_values(
            [
                "_orden_sede",
                "_orden_facturacion",
                "_orden_servicio",
                "tipo_servicio",
            ],
            kind="stable",
        )
        .drop(
            columns=[
                "_orden_sede",
                "_orden_facturacion",
                "_orden_servicio",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return resultado


# ============================================================
# REPORTE POR TIPO DE SERVICIO
# ============================================================

def construir_reporte_servicios(
    citas: pd.DataFrame,
    fecha_objetivo,
) -> pd.DataFrame:
    """
    Construye el reporte operativo equivalente a la tabla
    dinámica actualmente utilizada por Call Center.

    Filas:
        sede
        tipo_facturacion
        tipo_servicio

    Columnas:
        asesor_canonico

    Valor:
        cantidad de citas únicas

    Incluye:
        - subtotal por sede
        - total general
        - orden FACTURABLE / NO FACTURABLE / INDETERMINADO
    """

    # --------------------------------------------------------
    # Filtrar fecha
    # --------------------------------------------------------

    df = _filtrar_fecha_programada(
        citas=citas,
        fecha_objetivo=fecha_objetivo,
    )

    if df.empty:
        return pd.DataFrame()

    # --------------------------------------------------------
    # Clasificaciones de negocio
    # --------------------------------------------------------

    df = enriquecer_clasificaciones(
        df
    )

    columnas_requeridas = [
        "id_cita",
        "sede",
        "tipo_facturacion",
        "tipo_servicio",
        "asesor_canonico",
    ]

    faltantes = [
        columna
        for columna in columnas_requeridas
        if columna not in df.columns
    ]

    if faltantes:
        raise ValueError(
            "No se pueden construir los reportes. "
            f"Faltan columnas: {faltantes}"
        )

    # --------------------------------------------------------
    # Normalización defensiva
    # --------------------------------------------------------

    for columna in [
        "sede",
        "tipo_facturacion",
        "tipo_servicio",
        "asesor_canonico",
    ]:

        df[columna] = (
            df[columna]
            .fillna(
                "INDETERMINADO"
            )
            .astype(str)
            .str.strip()
        )

    # --------------------------------------------------------
    # Resumen base
    # --------------------------------------------------------

    resumen = (
        df
        .groupby(
            [
                "sede",
                "tipo_facturacion",
                "tipo_servicio",
                "asesor_canonico",
            ],
            as_index=False,
            observed=True,
        )
        .agg(
            citas=(
                "id_cita",
                "nunique",
            )
        )
    )

    # --------------------------------------------------------
    # Pivot
    # --------------------------------------------------------

    pivot = (
        resumen
        .pivot_table(
            index=[
                "sede",
                "tipo_facturacion",
                "tipo_servicio",
            ],
            columns="asesor_canonico",
            values="citas",
            aggfunc="sum",
            fill_value=0,
            observed=True,
        )
        .reset_index()
    )

    # Quitar nombre técnico del eje de columnas
    pivot.columns.name = None

    # --------------------------------------------------------
    # Ordenar detalle
    # --------------------------------------------------------

    pivot = _ordenar_reporte(
        pivot
    )

    columnas_fijas = [
        "sede",
        "tipo_facturacion",
        "tipo_servicio",
    ]

    columnas_asesores = [
        columna
        for columna in pivot.columns
        if columna not in columnas_fijas
    ]

    # Orden alfabético para presentación estable
    columnas_asesores = sorted(
        columnas_asesores
    )

    pivot = pivot[
        columnas_fijas
        +
        columnas_asesores
    ]

    # --------------------------------------------------------
    # Total de cada fila
    # --------------------------------------------------------

    pivot["Total general"] = (
        pivot[
            columnas_asesores
        ]
        .sum(
            axis=1
        )
    )

    columnas_numericas = (
        columnas_asesores
        +
        [
            "Total general",
        ]
    )

    # --------------------------------------------------------
    # Insertar subtotales por sede
    # --------------------------------------------------------

    filas_finales = []

    sedes_presentes = (
        pivot[
            "sede"
        ]
        .drop_duplicates()
        .tolist()
    )

    sedes_presentes = sorted(
        sedes_presentes,
        key=lambda sede:
            ORDEN_SEDE.get(
                sede,
                99,
            ),
    )

    for sede in sedes_presentes:

        bloque = (
            pivot.loc[
                pivot[
                    "sede"
                ].eq(
                    sede
                )
            ]
            .copy()
        )

        if bloque.empty:
            continue

        # Detalle de la sede
        filas_finales.append(
            bloque
        )

        # Subtotal de sede
        total_sede = {
            "sede":
                sede,

            "tipo_facturacion":
                "TOTAL SEDE",

            "tipo_servicio":
                "",
        }

        for columna in columnas_numericas:

            total_sede[
                columna
            ] = int(
                bloque[
                    columna
                ]
                .sum()
            )

        filas_finales.append(
            pd.DataFrame(
                [
                    total_sede
                ]
            )
        )

    reporte = pd.concat(
        filas_finales,
        ignore_index=True,
    )

    # --------------------------------------------------------
    # Total general
    #
    # IMPORTANTE:
    # se calcula desde el detalle original para no duplicar
    # los subtotales por sede.
    # --------------------------------------------------------

    total_general = {
        "sede":
            "Total general",

        "tipo_facturacion":
            "",

        "tipo_servicio":
            "",
    }

    for columna in columnas_numericas:

        total_general[
            columna
        ] = int(
            pivot[
                columna
            ]
            .sum()
        )

    reporte = pd.concat(
        [
            reporte,
            pd.DataFrame(
                [
                    total_general
                ]
            ),
        ],
        ignore_index=True,
    )

    # --------------------------------------------------------
    # Garantizar enteros
    # --------------------------------------------------------

    for columna in columnas_numericas:

        reporte[
            columna
        ] = (
            pd.to_numeric(
                reporte[
                    columna
                ],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    return reporte


# ============================================================
# CONTROL DE INDETERMINADOS
# ============================================================

def construir_control_indeterminados(
    citas: pd.DataFrame,
    fecha_objetivo=None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Detecta asesores y servicios todavía sin clasificación.

    Si fecha_objetivo es informada, revisa solamente las citas
    correspondientes a esa fecha.

    Si no se informa, revisa toda la base recibida.
    """

    df = citas.copy()

    if fecha_objetivo is not None:

        df = _filtrar_fecha_programada(
            citas=df,
            fecha_objetivo=fecha_objetivo,
        )

    if df.empty:

        return (
            pd.DataFrame(
                columns=[
                    "asesor_servicio",
                ]
            ),
            pd.DataFrame(
                columns=[
                    "motivo_visita",
                ]
            ),
        )

    df = enriquecer_clasificaciones(
        df
    )

    # --------------------------------------------------------
    # Asesores sin sede conocida
    # --------------------------------------------------------

    asesores = (
        df.loc[
            df[
                "sede"
            ].eq(
                "INDETERMINADO"
            ),
            [
                "asesor_servicio",
            ],
        ]
        .dropna()
        .drop_duplicates()
        .sort_values(
            "asesor_servicio"
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # Servicios sin clasificación conocida
    # --------------------------------------------------------

    servicios = (
        df.loc[
            df[
                "tipo_servicio"
            ].eq(
                "INDETERMINADO"
            ),
            [
                "motivo_visita",
            ],
        ]
        .dropna()
        .drop_duplicates()
        .sort_values(
            "motivo_visita"
        )
        .reset_index(
            drop=True
        )
    )

    return (
        asesores,
        servicios,
    )

def construir_reporte_canal_agenda(
    citas: pd.DataFrame,
    fecha_objetivo,
) -> pd.DataFrame:
    """
    Construye la matriz de generación de citas.

    Filas:
        sede
        tipo_facturacion
        tipo_servicio

    Columnas:
        Nivel 1: CALL CENTER / TALLER / TOTAL
        Nivel 2: persona que agenda

    Incluye:
        - Total Call Center
        - Total Taller
        - Total general
        - % Total
        - subtotal por sede
        - total general final
    """

    # --------------------------------------------------------
    # FILTRAR FECHA
    # --------------------------------------------------------

    df = _filtrar_fecha_programada(
        citas=citas,
        fecha_objetivo=fecha_objetivo,
    )

    if df.empty:
        return pd.DataFrame()

    # --------------------------------------------------------
    # CLASIFICACIONES
    # --------------------------------------------------------

    df = enriquecer_clasificaciones(
        df
    )

    columnas_requeridas = [
        "id_cita",
        "sede",
        "tipo_facturacion",
        "tipo_servicio",
        "persona_agenda_canonica",
        "canal_agenda",
    ]

    faltantes = [
        columna
        for columna in columnas_requeridas
        if columna not in df.columns
    ]

    if faltantes:
        raise ValueError(
            "No se puede construir el reporte por canal. "
            f"Faltan columnas: {faltantes}"
        )

    # --------------------------------------------------------
    # NORMALIZACIÓN
    # --------------------------------------------------------

    for columna in [
        "sede",
        "tipo_facturacion",
        "tipo_servicio",
        "persona_agenda_canonica",
        "canal_agenda",
    ]:
        df[columna] = (
            df[columna]
            .fillna("INDETERMINADO")
            .astype(str)
            .str.strip()
        )

    # --------------------------------------------------------
    # DETALLE
    # --------------------------------------------------------

    resumen = (
        df
        .groupby(
            [
                "sede",
                "tipo_facturacion",
                "tipo_servicio",
                "canal_agenda",
                "persona_agenda_canonica",
            ],
            as_index=False,
            observed=True,
        )
        .agg(
            citas=(
                "id_cita",
                "nunique",
            )
        )
    )

    # --------------------------------------------------------
    # PIVOT CON DOS NIVELES DE COLUMNAS
    # --------------------------------------------------------

    pivot = resumen.pivot_table(
        index=[
            "sede",
            "tipo_facturacion",
            "tipo_servicio",
        ],
        columns=[
            "canal_agenda",
            "persona_agenda_canonica",
        ],
        values="citas",
        aggfunc="sum",
        fill_value=0,
        observed=True,
    )

    # --------------------------------------------------------
    # ASEGURAR COLUMNAS CALL CENTER
    # --------------------------------------------------------

    personas_call = [
        "Brenda",
        "Rocio",
        "Yesika",
    ]

    for persona in personas_call:

        columna = (
            "CALL CENTER",
            persona,
        )

        if columna not in pivot.columns:
            pivot[
                columna
            ] = 0

    # --------------------------------------------------------
    # ORDENAR PERSONAS POR CANAL
    # --------------------------------------------------------

    columnas_call = [
        columna
        for columna in pivot.columns
        if columna[0] == "CALL CENTER"
        and columna[1] in personas_call
    ]

    columnas_call = sorted(
        columnas_call,
        key=lambda columna:
            personas_call.index(
                columna[1]
            ),
    )

    columnas_taller = sorted(
        [
            columna
            for columna in pivot.columns
            if columna[0] == "TALLER"
        ],
        key=lambda columna:
            columna[1],
    )

    columnas_indeterminadas = sorted(
        [
            columna
            for columna in pivot.columns
            if columna[0] == "INDETERMINADO"
        ],
        key=lambda columna:
            columna[1],
    )

    columnas_detalle = (
        columnas_call
        +
        columnas_taller
        +
        columnas_indeterminadas
    )

    pivot = pivot.reindex(
        columns=columnas_detalle,
        fill_value=0,
    )

    # --------------------------------------------------------
    # TOTALES POR CANAL
    # --------------------------------------------------------

    if columnas_call:

        pivot[
            (
                "CALL CENTER",
                "Total Call Center",
            )
        ] = (
            pivot[
                columnas_call
            ]
            .sum(
                axis=1
            )
        )

    else:

        pivot[
            (
                "CALL CENTER",
                "Total Call Center",
            )
        ] = 0

    if columnas_taller:

        pivot[
            (
                "TALLER",
                "Total Taller",
            )
        ] = (
            pivot[
                columnas_taller
            ]
            .sum(
                axis=1
            )
        )

    else:

        pivot[
            (
                "TALLER",
                "Total Taller",
            )
        ] = 0

    if columnas_indeterminadas:

        pivot[
            (
                "INDETERMINADO",
                "Total Indeterminado",
            )
        ] = (
            pivot[
                columnas_indeterminadas
            ]
            .sum(
                axis=1
            )
        )

    # --------------------------------------------------------
    # TOTAL GENERAL
    # --------------------------------------------------------

    columnas_personas = (
        columnas_call
        +
        columnas_taller
        +
        columnas_indeterminadas
    )

    pivot[
        (
            "TOTAL",
            "Total general",
        )
    ] = (
        pivot[
            columnas_personas
        ]
        .sum(
            axis=1
        )
    )

    total_fecha = int(
        pivot[
            (
                "TOTAL",
                "Total general",
            )
        ]
        .sum()
    )

    pivot[
        (
            "TOTAL",
            "% Total",
        )
    ] = (
        pivot[
            (
                "TOTAL",
                "Total general",
            )
        ]
        /
        total_fecha
        if total_fecha
        else 0
    )

    # --------------------------------------------------------
    # VOLVER FILAS A COLUMNAS
    # --------------------------------------------------------

    pivot = pivot.reset_index()

    # --------------------------------------------------------
    # ORDENAR FILAS
    # --------------------------------------------------------

    pivot[
        (
            "_CONTROL",
            "_orden_sede",
        )
    ] = (
        pivot[
            (
                "sede",
                "",
            )
        ]
        .map(
            ORDEN_SEDE
        )
        .fillna(99)
    )

    pivot[
        (
            "_CONTROL",
            "_orden_facturacion",
        )
    ] = (
        pivot[
            (
                "tipo_facturacion",
                "",
            )
        ]
        .map(
            ORDEN_FACTURACION
        )
        .fillna(99)
    )

    pivot[
        (
            "_CONTROL",
            "_orden_servicio",
        )
    ] = (
        pivot[
            (
                "tipo_servicio",
                "",
            )
        ]
        .map(
            ORDEN_SERVICIO
        )
        .fillna(99)
    )

    pivot = (
        pivot
        .sort_values(
            [
                (
                    "_CONTROL",
                    "_orden_sede",
                ),
                (
                    "_CONTROL",
                    "_orden_facturacion",
                ),
                (
                    "_CONTROL",
                    "_orden_servicio",
                ),
            ],
            kind="stable",
        )
        .drop(
            columns=[
                (
                    "_CONTROL",
                    "_orden_sede",
                ),
                (
                    "_CONTROL",
                    "_orden_facturacion",
                ),
                (
                    "_CONTROL",
                    "_orden_servicio",
                ),
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # SUBTOTALES POR SEDE
    # --------------------------------------------------------

    filas_finales = []

    for sede in [
        "SAN ISIDRO",
        "SAN MIGUEL",
        "INDETERMINADO",
    ]:

        mascara = (
            pivot[
                (
                    "sede",
                    "",
                )
            ]
            .eq(
                sede
            )
        )

        bloque = (
            pivot.loc[
                mascara
            ]
            .copy()
        )

        if bloque.empty:
            continue

        filas_finales.append(
            bloque
        )

        subtotal = {}

        for columna in pivot.columns:

            if columna == (
                "sede",
                "",
            ):

                subtotal[
                    columna
                ] = sede

            elif columna == (
                "tipo_facturacion",
                "",
            ):

                subtotal[
                    columna
                ] = "TOTAL SEDE"

            elif columna == (
                "tipo_servicio",
                "",
            ):

                subtotal[
                    columna
                ] = ""

            elif columna == (
                "TOTAL",
                "% Total",
            ):

                subtotal[
                    columna
                ] = (
                    bloque[
                        (
                            "TOTAL",
                            "Total general",
                        )
                    ]
                    .sum()
                    /
                    total_fecha
                    if total_fecha
                    else 0
                )

            else:

                subtotal[
                    columna
                ] = (
                    pd.to_numeric(
                        bloque[
                            columna
                        ],
                        errors="coerce",
                    )
                    .fillna(0)
                    .sum()
                )

        filas_finales.append(
            pd.DataFrame(
                [
                    subtotal
                ],
                columns=pivot.columns,
            )
        )

    reporte = pd.concat(
        filas_finales,
        ignore_index=True,
    )

    # --------------------------------------------------------
    # TOTAL GENERAL
    # --------------------------------------------------------

    total = {}

    for columna in pivot.columns:

        if columna == (
            "sede",
            "",
        ):

            total[
                columna
            ] = "Total general"

        elif columna in [
            (
                "tipo_facturacion",
                "",
            ),
            (
                "tipo_servicio",
                "",
            ),
        ]:

            total[
                columna
            ] = ""

        elif columna == (
            "TOTAL",
            "% Total",
        ):

            total[
                columna
            ] = (
                1.0
                if total_fecha
                else 0
            )

        else:

            total[
                columna
            ] = (
                pd.to_numeric(
                    pivot[
                        columna
                    ],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            )

    reporte = pd.concat(
        [
            reporte,
            pd.DataFrame(
                [
                    total
                ],
                columns=pivot.columns,
            ),
        ],
        ignore_index=True,
    )

    return reporte