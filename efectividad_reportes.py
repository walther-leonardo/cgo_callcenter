from __future__ import annotations

import pandas as pd
from clasificaciones import (
    clasificar_servicio,
)


CONFIG_SCORECARD_2026 = {
    "general_mensual": {
        "meta": {10:600,11:600},
        "cpu": {10:600,11:600},
        "real": {},
    },

    "general_al_dia": {
        "meta_al_dia": None,
        "cpu_al_dia": None,
        "real_al_dia": None,
    },

    "agente_a_mensual": {
        "meta": {10:300, 11:300},
        "cpu": {10:300, 11:300},
        "real": {},
    },

    "agente_a_al_dia": {
        "meta_al_dia": None,
        "cpu_al_dia": None,
        "real_al_dia": None,
    },

    "agente_b_mensual": {
        "meta": {10:300, 11:300},
        "cpu": {10:300, 11:300},
        "real": {},
    },

    "agente_b_al_dia": {
        "meta_al_dia": None,
        "cpu_al_dia": None,
        "real_al_dia": None,
    },

    "otros_mensual": {
        "meta": {},
        "cpu": {},
        "real": {},
    },

    "otros_al_dia": {
        "meta_al_dia": None,
        "cpu_al_dia": None,
        "real_al_dia": None,
    },
}



def construir_detalle_efectividad(
    citas: pd.DataFrame,
    matches: pd.DataFrame,
    presencias: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye el detalle operativo de efectividad.

    IMPORTANTE
    ----------
    `citas` debe contener exclusivamente el universo operativo
    válido después de:

    - excluir isDeleted;
    - excluir status cancelado;
    - resolver duplicados operativos.

    Por tanto, una cita que posteriormente fue cancelada,
    eliminada o reemplazada por un duplicado deja de aparecer
    en este reporte operativo.

    La tabla resultante será la fuente común para:
    - reporte de supervisión;
    - reporte por agente;
    - scorecards mensuales;
    - Streamlit.
    """

    resultado = citas.copy()

    # ========================================================
    # 1. MATCHING
    # ========================================================

    columnas_match = [
        "id_cita",
        "presencia_id",
        "fecha_visita",
        "diferencia_dias",
        "nivel_efectividad",
        "estado_efectividad",
        "fuente",
        "criterio_matching",
        "persona_creditada",
        "requiere_revision_manual",
    ]

    if matches.empty:

        for columna in columnas_match[1:]:
            resultado[
                columna
            ] = pd.NA

    else:

        resultado = resultado.merge(
            matches[
                columnas_match
            ],
            on="id_cita",
            how="left",
            validate="one_to_one",
        )

    # ========================================================
    # 2. DOCUMENTOS QUE CONFIRMAN LA PRESENCIA
    # ========================================================

    columnas_presencia = [
        "presencia_id",
        "tiene_cotizacion",
        "tiene_orden",
        "numeros_cotizacion",
        "numeros_orden",
    ]

    presencia_documental = (
        presencias[
            columnas_presencia
        ]
        .drop_duplicates(
            subset=[
                "presencia_id"
            ]
        )
        .copy()
    )

    resultado = resultado.merge(
        presencia_documental,
        on="presencia_id",
        how="left",
        validate="many_to_one",
    )

    # ========================================================
    # 3. NORMALIZAR ESTADOS
    # ========================================================

    resultado[
        "estado_efectividad"
    ] = (
        resultado[
            "estado_efectividad"
        ]
        .fillna(
            "SIN_PRESENCIA"
        )
    )

    resultado[
        "persona_creditada"
    ] = (
        resultado[
            "persona_creditada"
        ]
        .fillna(
            resultado[
                "agente"
            ]
        )
    )

    resultado[
        "requiere_revision_manual"
    ] = (
        resultado[
            "requiere_revision_manual"
        ]
        .fillna(False)
        .astype(bool)
    )

    resultado[
        "tiene_cotizacion"
    ] = (
        resultado[
            "tiene_cotizacion"
        ]
        .fillna(False)
        .astype(bool)
    )

    resultado[
        "tiene_orden"
    ] = (
        resultado[
            "tiene_orden"
        ]
        .fillna(False)
        .astype(bool)
    )

    resultado[
        "numeros_cotizacion"
    ] = (
        resultado[
            "numeros_cotizacion"
        ]
        .fillna("")
        .astype(str)
    )

    resultado[
        "numeros_orden"
    ] = (
        resultado[
            "numeros_orden"
        ]
        .fillna("")
        .astype(str)
    )

    # ========================================================
    # 4. HORA DE CITA
    # ========================================================

    fecha_hora = pd.to_datetime(
        resultado[
            "fecha_hora_cita_lima"
        ],
        errors="coerce",
    )

    resultado[
        "hora_cita"
    ] = fecha_hora.dt.strftime(
        "%H:%M"
    )

    # ========================================================
    # 5. GRUPO DE SERVICIO PARA EL ÚNICO FILTRO DEL REPORTE
    # ========================================================

    resultado[
        "grupo_servicio"
    ] = resultado[
        "motivos"
    ].apply(
        _clasificar_grupo_servicio
    )

    # ========================================================
    # 6. CAMPOS DE REPORTE
    # ========================================================

    resultado[
        "es_efectiva"
    ] = resultado[
        "nivel_efectividad"
    ].isin(
        [
            1,
            2,
            3,
        ]
    )

    resultado[
        "nivel"
    ] = resultado[
        "nivel_efectividad"
    ].apply(
        lambda valor:
            (
                f"N{int(valor)}"
                if pd.notna(valor)
                else ""
            )
    )

    resultado[
        "confirmacion_presencia"
    ] = resultado.apply(
        _describir_confirmacion,
        axis=1,
    )

    resultado[
        "resultado_efectividad"
    ] = resultado.apply(
        _describir_resultado,
        axis=1,
    )

    resultado[
        "tipo_asignacion"
    ] = (
        resultado[
            "criterio_matching"
        ]
        .fillna("")
        .apply(
            _clasificar_tipo_asignacion
        )
    )

    # ========================================================
    # 7. COLUMNAS FINALES
    # ========================================================

    columnas = [
        "id_cita",
        "appointment_number",
        "fecha_cita",
        "hora_cita",
        "placa_normalizada",
        "motivos",
        "grupo_servicio",
        "agente",
        "persona_creditada",
        "canal_agenda",
        "status",
        "fecha_visita",
        "es_efectiva",
        "nivel",
        "diferencia_dias",
        "resultado_efectividad",
        "confirmacion_presencia",
        "numeros_cotizacion",
        "numeros_orden",
        "tipo_asignacion",
        "requiere_revision_manual",
        "criterio_matching",
        "presencia_id",
    ]

    columnas = [
        columna
        for columna in columnas
        if columna in resultado.columns
    ]

    return (
        resultado[
            columnas
        ]
        .sort_values(
            [
                "fecha_cita",
                "hora_cita",
                "appointment_number",
            ],
            kind="stable",
        )
        .reset_index(
            drop=True
        )
    )


def _clasificar_grupo_servicio(
    motivo,
) -> str:
    """
    Agrupa los servicios para el filtro del scorecard usando
    la clasificación oficial del proyecto.

    PREVENTIVO:
        únicamente cuando clasificar_servicio() determina
        tipo_servicio = Preventivo.

    NO_PREVENTIVO:
        cualquier otro servicio.
    """

    _, tipo_servicio = clasificar_servicio(
        motivo
    )

    if tipo_servicio == "Preventivo":
        return "PREVENTIVO"

    return "NO_PREVENTIVO"


def _describir_confirmacion(
    fila: pd.Series,
) -> str:

    cotizacion = bool(
        fila[
            "tiene_cotizacion"
        ]
    )

    orden = bool(
        fila[
            "tiene_orden"
        ]
    )

    if cotizacion and orden:
        return "Cotización + Orden"

    if cotizacion:
        return "Cotización"

    if orden:
        return "Orden"

    return "Sin presencia confirmada"


def _describir_resultado(
    fila: pd.Series,
) -> str:

    nivel = fila[
        "nivel_efectividad"
    ]

    diferencia = fila[
        "diferencia_dias"
    ]

    if pd.isna(
        nivel
    ):
        return "Sin presencia"

    nivel = int(
        nivel
    )

    diferencia = int(
        diferencia
    )

    if nivel == 1:
        return "Efectiva N1 — mismo día"

    if diferencia < 0:

        dias = abs(
            diferencia
        )

        return (
            f"Efectiva N{nivel} — "
            f"{dias} día"
            f"{'s' if dias != 1 else ''} antes"
        )

    return (
        f"Efectiva N{nivel} — "
        f"{diferencia} día"
        f"{'s' if diferencia != 1 else ''} después"
    )


def _clasificar_tipo_asignacion(
    criterio,
) -> str:

    texto = str(
        criterio
    ).upper()

    if not texto:
        return ""

    if "RESOLUCION_MANUAL" in texto:
        return "MANUAL"

    return "AUTOMATICA"


def validar_detalle_efectividad(
    detalle: pd.DataFrame,
    citas: pd.DataFrame,
    matches: pd.DataFrame,
) -> dict:
    """
    Valida que el detalle de efectividad sea consistente con
    el universo operativo y con el matching definitivo.

    Esta validación debe ejecutarse antes de construir
    scorecards, Excel o Streamlit.
    """

    errores = []

    # ========================================================
    # 1. UNA FILA POR CITA OPERATIVA
    # ========================================================

    total_citas = len(
        citas
    )

    total_detalle = len(
        detalle
    )

    if total_detalle != total_citas:

        errores.append(
            "El detalle no contiene exactamente "
            "una fila por cita operativa. "
            f"Citas={total_citas:,}, "
            f"detalle={total_detalle:,}."
        )

    duplicados = int(
        detalle[
            "id_cita"
        ]
        .duplicated()
        .sum()
    )

    if duplicados:

        errores.append(
            f"Existen {duplicados:,} "
            "id_cita duplicados en el detalle."
        )

    # ========================================================
    # 2. EFECTIVAS = MATCHES
    # ========================================================

    total_matches = len(
        matches
    )

    total_efectivas = int(
        detalle[
            "es_efectiva"
        ].sum()
    )

    if total_efectivas != total_matches:

        errores.append(
            "La cantidad de citas efectivas no coincide "
            "con el matching. "
            f"Matches={total_matches:,}, "
            f"efectivas={total_efectivas:,}."
        )

    # ========================================================
    # 3. TODA EFECTIVA DEBE TENER PRESENCIA
    # ========================================================

    efectivas_sin_presencia = int(
        detalle.loc[
            detalle[
                "es_efectiva"
            ]
            &
            detalle[
                "presencia_id"
            ].isna()
        ].shape[0]
    )

    if efectivas_sin_presencia:

        errores.append(
            f"Existen {efectivas_sin_presencia:,} "
            "citas efectivas sin presencia_id."
        )

    # ========================================================
    # 4. UNA PRESENCIA NO PUEDE ACREDITAR DOS CITAS
    # ========================================================

    presencias_duplicadas = int(
        detalle.loc[
            detalle[
                "es_efectiva"
            ],
            "presencia_id",
        ]
        .duplicated()
        .sum()
    )

    if presencias_duplicadas:

        errores.append(
            f"Existen {presencias_duplicadas:,} "
            "presencias utilizadas más de una vez."
        )

    # ========================================================
    # 5. NIVELES VÁLIDOS
    # ========================================================

    niveles_invalidos = set(
        detalle.loc[
            detalle[
                "es_efectiva"
            ],
            "nivel",
        ]
        .dropna()
        .unique()
    ) - {
        "N1",
        "N2",
        "N3",
    }

    if niveles_invalidos:

        errores.append(
            "Se encontraron niveles de efectividad "
            f"no reconocidos: {sorted(niveles_invalidos)}."
        )

    # ========================================================
    # 6. GRUPOS DE SERVICIO VÁLIDOS
    # ========================================================

    grupos_invalidos = set(
        detalle[
            "grupo_servicio"
        ]
        .dropna()
        .unique()
    ) - {
        "PREVENTIVO",
        "NO_PREVENTIVO",
    }

    if grupos_invalidos:

        errores.append(
            "Se encontraron grupos de servicio "
            f"no reconocidos: {sorted(grupos_invalidos)}."
        )

    # ========================================================
    # 7. DOCUMENTOS DE RESPALDO
    #
    # No genera error porque puede existir una presencia cuya
    # fuente esté identificada aunque el número documental
    # tenga problemas de calidad.
    # ========================================================

    efectivas_sin_numero_documental = int(
        detalle.loc[
            detalle[
                "es_efectiva"
            ]
            &
            detalle[
                "numeros_cotizacion"
            ].eq("")
            &
            detalle[
                "numeros_orden"
            ].eq("")
        ].shape[0]
    )

    if errores:

        mensaje = "\n".join(
            f"- {error}"
            for error in errores
        )

        raise ValueError(
            "La auditoría del detalle de efectividad "
            "detectó inconsistencias:\n"
            f"{mensaje}"
        )

    return {
        "citas_operativas":
            total_citas,

        "efectivas":
            total_efectivas,

        "sin_presencia":
            total_citas
            -
            total_efectivas,

        "nivel_1":
            int(
                detalle[
                    "nivel"
                ].eq(
                    "N1"
                ).sum()
            ),

        "nivel_2":
            int(
                detalle[
                    "nivel"
                ].eq(
                    "N2"
                ).sum()
            ),

        "nivel_3":
            int(
                detalle[
                    "nivel"
                ].eq(
                    "N3"
                ).sum()
            ),

        "preventivo":
            int(
                detalle[
                    "grupo_servicio"
                ].eq(
                    "PREVENTIVO"
                ).sum()
            ),

        "no_preventivo":
            int(
                detalle[
                    "grupo_servicio"
                ].eq(
                    "NO_PREVENTIVO"
                ).sum()
            ),

        "efectivas_sin_numero_documental":
            efectivas_sin_numero_documental,
    }


def imprimir_auditoria_detalle(
    detalle: pd.DataFrame,
    resumen: dict,
) -> None:
    """
    Imprime una auditoría breve y una muestra del detalle
    que posteriormente alimentará los reportes.
    """

    print()
    print("=" * 88)
    print(
        "AUDITORÍA — DETALLE MAESTRO DE EFECTIVIDAD"
    )
    print("=" * 88)

    print(
        f"Citas operativas                  "
        f"{resumen['citas_operativas']:>10,}"
    )

    print(
        f"Efectivas                         "
        f"{resumen['efectivas']:>10,}"
    )

    print(
        f"Sin presencia                     "
        f"{resumen['sin_presencia']:>10,}"
    )

    print(
        f"Nivel 1                           "
        f"{resumen['nivel_1']:>10,}"
    )

    print(
        f"Nivel 2                           "
        f"{resumen['nivel_2']:>10,}"
    )

    print(
        f"Nivel 3                           "
        f"{resumen['nivel_3']:>10,}"
    )

    print(
        f"Citas Preventivo                  "
        f"{resumen['preventivo']:>10,}"
    )

    print(
        f"Citas No Preventivo               "
        f"{resumen['no_preventivo']:>10,}"
    )

    print(
        f"Efectivas sin número documental   "
        f"{resumen['efectivas_sin_numero_documental']:>10,}"
    )

    # ========================================================
    # MUESTRA LEGIBLE
    # ========================================================

    print()
    print("-" * 88)
    print(
        "MUESTRA — CITAS EFECTIVAS"
    )
    print("-" * 88)

    muestra = detalle.loc[
        detalle[
            "es_efectiva"
        ]
    ].copy()

    columnas = [
        "appointment_number",
        "fecha_cita",
        "hora_cita",
        "placa_normalizada",
        "motivos",
        "grupo_servicio",
        "agente",
        "persona_creditada",
        "fecha_visita",
        "nivel",
        "resultado_efectividad",
        "confirmacion_presencia",
        "numeros_cotizacion",
        "numeros_orden",
        "tipo_asignacion",
    ]

    columnas = [
        columna
        for columna in columnas
        if columna in muestra.columns
    ]

    print(
        muestra[
            columnas
        ]
        .head(
            20
        )
        .to_string(
            index=False
        )
    )


# ============================================================
# SCORECARD DE EFECTIVIDAD
# ============================================================

import calendar


MESES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "setiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

DIAS_SEMANA_CORTO = {
    0: "lun",
    1: "mar",
    2: "mié",
    3: "jue",
    4: "vie",
    5: "sáb",
    6: "dom",
}


PESO_LUNES_VIERNES = 1.0
PESO_SABADO = 0.5
PESO_DOMINGO = 0.0


FILTROS_SERVICIO_VALIDOS = {
    "TODOS",
    "PREVENTIVO",
    "NO_PREVENTIVO",
}


def construir_distribucion_meta_diaria(
    anio: int,
    mes: int,
    meta_mensual: int | float,
    feriados: set | list | tuple | None = None,
) -> pd.DataFrame:
    """
    Distribuye una meta mensual entre los días del mes.

    Pesos:
    - lunes-viernes: 1.0
    - sábado: 0.5
    - domingo: 0
    - feriado: 0

    La suma final de meta_dia coincide exactamente con
    meta_mensual.

    Los feriados deben recibirse como fechas o valores
    convertibles a fecha.
    """

    if meta_mensual is None:

        return pd.DataFrame()

    meta_mensual = int(
        round(
            float(
                meta_mensual
            )
        )
    )

    feriados = feriados or []

    feriados_normalizados = {
        pd.Timestamp(
            fecha
        ).date()
        for fecha in feriados
    }

    dias_mes = calendar.monthrange(
        anio,
        mes,
    )[1]

    registros = []

    for dia in range(
        1,
        dias_mes + 1,
    ):

        fecha = pd.Timestamp(
            year=anio,
            month=mes,
            day=dia,
        )

        fecha_date = fecha.date()

        weekday = fecha.weekday()

        es_domingo = (
            weekday == 6
        )

        es_sabado = (
            weekday == 5
        )

        es_feriado = (
            fecha_date
            in feriados_normalizados
        )

        if es_domingo or es_feriado:

            peso = 0.0

        elif es_sabado:

            peso = (
                PESO_SABADO
            )

        else:

            peso = (
                PESO_LUNES_VIERNES
            )

        registros.append(
            {
                "fecha":
                    fecha_date,

                "dia":
                    dia,

                "dia_semana":
                    DIAS_SEMANA_CORTO[
                        weekday
                    ],

                "etiqueta":
                    (
                        f"{dia:02d}-"
                        f"{DIAS_SEMANA_CORTO[weekday]}"
                    ),

                "es_domingo":
                    es_domingo,

                "es_feriado":
                    es_feriado,

                "peso":
                    peso,
            }
        )

    distribucion = pd.DataFrame(
        registros
    )

    peso_total = distribucion[
        "peso"
    ].sum()

    if peso_total <= 0:

        raise ValueError(
            "El mes no contiene días disponibles "
            "para distribuir la meta."
        )

    distribucion[
        "_cuota_exacta"
    ] = (
        meta_mensual
        *
        distribucion[
            "peso"
        ]
        /
        peso_total
    )

    distribucion[
        "meta_dia"
    ] = (
        distribucion[
            "_cuota_exacta"
        ]
        .fillna(0)
        .astype(int)
    )

    # ========================================================
    # AJUSTE DE REDONDEO
    #
    # Garantiza:
    #
    # sum(meta_dia) == meta_mensual
    # ========================================================

    faltante = (
        meta_mensual
        -
        int(
            distribucion[
                "meta_dia"
            ].sum()
        )
    )

    if faltante > 0:

        distribucion[
            "_residuo"
        ] = (
            distribucion[
                "_cuota_exacta"
            ]
            -
            distribucion[
                "meta_dia"
            ]
        )

        candidatos = (
            distribucion.loc[
                distribucion[
                    "peso"
                ].gt(0)
            ]
            .sort_values(
                [
                    "_residuo",
                    "fecha",
                ],
                ascending=[
                    False,
                    True,
                ],
                kind="stable",
            )
            .index
            .tolist()
        )

        for indice in candidatos[
            :faltante
        ]:

            distribucion.loc[
                indice,
                "meta_dia",
            ] += 1

    distribucion[
        "meta_acumulada"
    ] = distribucion[
        "meta_dia"
    ].cumsum()

    return distribucion[
        [
            "fecha",
            "dia",
            "dia_semana",
            "etiqueta",
            "es_domingo",
            "es_feriado",
            "peso",
            "meta_dia",
            "meta_acumulada",
        ]
    ]


def construir_scorecard_diario(
    detalle: pd.DataFrame,
    anio: int,
    mes: int,
    grupo_meta: str,
    configuracion_metas: dict,
    filtro_servicio: str = "TODOS",
    persona: str | None = None,
    excluir_personas: list[str] | None = None,
    feriados: set | list | tuple | None = None,
) -> pd.DataFrame:
    """
    Construye el scorecard diario del mes seleccionado.

    Filas:
    - Meta
    - cita agendada
    - cita efectiva
    - % efectividad
    - % cumplimiento de meta

    Domingos:
        columna completamente vacía.

    Feriados:
        Meta vacía / cero operativo.
        Los resultados reales se conservan si existen.
    """

    meta_mensual = obtener_meta_mensual(
        configuracion_metas=
            configuracion_metas,
        grupo=
            grupo_meta,
        filtro_servicio=
            filtro_servicio,
        mes=
            mes,
    )

    if meta_mensual is None:

        return pd.DataFrame()

    distribucion = (
        construir_distribucion_meta_diaria(
            anio=anio,
            mes=mes,
            meta_mensual=
                meta_mensual,
            feriados=
                feriados,
        )
    )

    base = filtrar_detalle_scorecard(
        detalle=detalle,
        filtro_servicio=filtro_servicio,
        persona=persona,
        excluir_personas=excluir_personas,
    ).copy()

    base[
        "_fecha_cita"
    ] = pd.to_datetime(
        base[
            "fecha_cita"
        ],
        errors="coerce",
    ).dt.date

    filas = [
        "Meta",
        "cita agendada",
        "cita efectiva",
        "% efectividad",
        "% cumplimiento de meta",
    ]

    columnas = distribucion[
        "etiqueta"
    ].tolist()

    resultado = pd.DataFrame(
        index=filas,
        columns=columnas,
        dtype="object",
    )

    for fila_dia in distribucion.itertuples(
        index=False
    ):

        etiqueta = (
            fila_dia.etiqueta
        )

        fecha = fila_dia.fecha

        if fila_dia.es_domingo:

            resultado.loc[
                :,
                etiqueta,
            ] = pd.NA

            continue

        detalle_dia = base.loc[
            base[
                "_fecha_cita"
            ].eq(
                fecha
            )
        ].copy()

        indicadores = (
            calcular_indicadores_periodo(
                detalle_dia
            )
        )

        meta_dia = int(
            fila_dia.meta_dia
        )

        resultado.loc[
            "Meta",
            etiqueta,
        ] = (
            pd.NA
            if fila_dia.es_feriado
            else meta_dia
        )

        resultado.loc[
            "cita agendada",
            etiqueta,
        ] = indicadores[
            "cita_agendada"
        ]

        resultado.loc[
            "cita efectiva",
            etiqueta,
        ] = indicadores[
            "cita_efectiva"
        ]

        resultado.loc[
            "% efectividad",
            etiqueta,
        ] = indicadores[
            "efectividad_pct"
        ]

        if fila_dia.es_feriado:

            cumplimiento = pd.NA

        elif meta_dia == 0:

            cumplimiento = pd.NA

        else:

            cumplimiento = round(
                indicadores[
                    "cita_efectiva"
                ]
                /
                meta_dia
                *
                100,
                1,
            )

        resultado.loc[
            "% cumplimiento de meta",
            etiqueta,
        ] = cumplimiento

    resultado.index.name = (
        "Nivel diario"
    )

    return resultado


# ============================================================
# METAS
#
# Coloca aquí los valores que defina Gerencia.
#
# IMPORTANTE:
# - Preventivo y No Preventivo tienen metas independientes.
# - TODOS se calcula automáticamente sumando ambas.
# - No es necesario registrar una meta TOTAL aparte.
# ============================================================

CONFIG_METAS_2026 = {
    "GENERAL": {
        "PREVENTIVO": {
            1:600,
            2:533,
            3:658,
            4:551,
            5:540,
            6:596,
            7:609,
            8:533,
            9:552,
            10:542,
            11:559,
            12:560,
        },
        "NO_PREVENTIVO": {
            1:563,
            2:380,
            3:433,
            4:404,
            5:381,
            6:398,
            7:469,
            8:498,
            9:532,
            10:506,
            11:441,
            12:443,
        },
    },

    "ROCIO": {
        "PREVENTIVO": {
            1:300,
            2:267,
            3:329,
            4:276,
            5:270,
            6:298,
            7:305,
            8:267,
            9:276,
            10:271,
            11:280,
            12:280,
        },
        "NO_PREVENTIVO": {
            1:282,
            2:190,
            3:217,
            4:202,
            5:191,
            6:199,
            7:235,
            8:249,
            9:266,
            10:253,
            11:221,
            12:222,
        },
    },

    "BRENDA": {
        "PREVENTIVO": {
            1:300,
            2:267,
            3:329,
            4:276,
            5:270,
            6:298,
            7:305,
            8:267,
            9:276,
            10:271,
            11:280,
            12:280,
        },
        "NO_PREVENTIVO": {
            1:282,
            2:190,
            3:217,
            4:202,
            5:191,
            6:199,
            7:235,
            8:249,
            9:266,
            10:253,
            11:221,
            12:222,
        },
    },

    "OTROS": {
        "PREVENTIVO": {},
        "NO_PREVENTIVO": {},
    },
}

CONFIG_INCENTIVOS_2026 = {
    "ROCIO": {
        11: 1000,
        12: 1000,
    },

    "BRENDA": {
        11: 1000,
        12: 1000,
    },
}

def calcular_comision_agente(
    detalle: pd.DataFrame,
    anio: int,
    mes: int,
    agente: str,
    grupo_meta: str,
    configuracion_metas: dict,
    configuracion_incentivos: dict,
) -> dict:
    """
    Calcula la comisión oficial del agente.

    IMPORTANTE:
    La comisión SIEMPRE usa TODOS los servicios,
    independientemente del filtro visual del dashboard.
    """

    meta = obtener_meta_mensual(
        configuracion_metas=
            configuracion_metas,
        grupo=
            grupo_meta,
        filtro_servicio=
            "TODOS",
        mes=
            mes,
    )

    incentivo_base = (
        configuracion_incentivos
        .get(
            grupo_meta,
            {},
        )
        .get(
            mes
        )
    )

    if (
        meta is None
        or incentivo_base is None
    ):

        return {
            "meta":
                meta,

            "resultado":
                None,

            "cumplimiento_pct":
                None,

            "factor_incentivo_pct":
                None,

            "incentivo_base":
                incentivo_base,

            "comision":
                None,
        }

    base = filtrar_detalle_scorecard(
        detalle=detalle,
        filtro_servicio="TODOS",
        persona=agente,
    ).copy()

    base[
        "_fecha_cita"
    ] = pd.to_datetime(
        base[
            "fecha_cita"
        ],
        errors="coerce",
    )

    base = base.loc[
        base[
            "_fecha_cita"
        ].dt.year.eq(
            anio
        )
        &
        base[
            "_fecha_cita"
        ].dt.month.eq(
            mes
        )
    ].copy()

    resultado = int(
        base.loc[
            base[
                "es_efectiva"
            ],
            "id_cita",
        ].nunique()
    )

    cumplimiento = (
        resultado
        /
        meta
        if meta
        else 0.0
    )

    # ========================================================
    # ESCALA DE INCENTIVO
    # ========================================================

    if cumplimiento < 0.50:

        factor = 0.00

    elif cumplimiento < 0.60:

        factor = 0.50

    elif cumplimiento < 0.70:

        factor = 0.60

    elif cumplimiento < 0.80:

        factor = 0.70

    elif cumplimiento < 0.90:

        factor = 0.80

    elif cumplimiento < 0.95:

        factor = 0.90

    elif cumplimiento <= 1.00:

        factor = 1.00

    else:

        factor = min(
            cumplimiento,
            1.50,
        )

    comision = (
        float(
            incentivo_base
        )
        *
        factor
    )

    return {
        "meta":
            int(
                meta
            ),

        "resultado":
            resultado,

        "cumplimiento_pct":
            round(
                cumplimiento
                *
                100,
                1,
            ),

        "factor_incentivo_pct":
            round(
                factor
                *
                100,
                1,
            ),

        "incentivo_base":
            float(
                incentivo_base
            ),

        "comision":
            round(
                comision,
                2,
            ),
    }

# ============================================================
# SEMÁFORO
# ============================================================

UMBRAL_VERDE = 1.00
UMBRAL_AMARILLO = 0.90


def filtrar_detalle_scorecard(
    detalle: pd.DataFrame,
    filtro_servicio: str = "TODOS",
    persona: str | None = None,
    excluir_personas: list[str] | None = None,
) -> pd.DataFrame:
    """
    Aplica los filtros comunes del scorecard.

    filtro_servicio:
        TODOS
        PREVENTIVO
        NO_PREVENTIVO

    persona:
        filtra una única persona acreditada.

    excluir_personas:
        permite construir el grupo Otros agentes.
    """

    filtro_servicio = (
        str(
            filtro_servicio
        )
        .strip()
        .upper()
    )

    if (
        filtro_servicio
        not in FILTROS_SERVICIO_VALIDOS
    ):
        raise ValueError(
            "Filtro de servicio no válido: "
            f"{filtro_servicio}"
        )

    resultado = detalle.copy()

    if filtro_servicio != "TODOS":

        resultado = resultado.loc[
            resultado[
                "grupo_servicio"
            ].eq(
                filtro_servicio
            )
        ].copy()

    if persona is not None:

        resultado = resultado.loc[
            resultado[
                "persona_creditada"
            ].eq(
                persona
            )
        ].copy()

    if excluir_personas:

        resultado = resultado.loc[
            ~resultado[
                "persona_creditada"
            ].isin(
                excluir_personas
            )
        ].copy()

    return resultado


def obtener_meta_mensual(
    configuracion_metas: dict,
    grupo: str,
    filtro_servicio: str,
    mes: int,
):
    """
    Devuelve la meta correspondiente al grupo, filtro y mes.

    TODOS:
        Preventivo + No Preventivo.

    Si alguna de las dos metas necesarias para TODOS no está
    configurada, devuelve None para evitar mostrar una meta
    parcial como si fuera total.
    """

    grupo = str(
        grupo
    ).upper()

    filtro_servicio = str(
        filtro_servicio
    ).upper()

    config_grupo = configuracion_metas.get(
        grupo,
        {},
    )

    preventivo = config_grupo.get(
        "PREVENTIVO",
        {},
    ).get(
        mes
    )

    no_preventivo = config_grupo.get(
        "NO_PREVENTIVO",
        {},
    ).get(
        mes
    )

    if filtro_servicio == "PREVENTIVO":
        return preventivo

    if filtro_servicio == "NO_PREVENTIVO":
        return no_preventivo

    if filtro_servicio == "TODOS":

        if (
            preventivo is None
            or no_preventivo is None
        ):
            return None

        return (
            preventivo
            +
            no_preventivo
        )

    raise ValueError(
        f"Filtro no reconocido: {filtro_servicio}"
    )


def calcular_indicadores_periodo(
    detalle: pd.DataFrame,
) -> dict:
    """
    Calcula indicadores básicos sobre un subconjunto
    previamente filtrado.
    """

    agendadas = int(
        detalle[
            "id_cita"
        ].nunique()
    )

    efectivas = int(
        detalle.loc[
            detalle[
                "es_efectiva"
            ],
            "id_cita",
        ].nunique()
    )

    nivel_1 = int(
        detalle[
            "nivel"
        ].eq(
            "N1"
        ).sum()
    )

    nivel_2 = int(
        detalle[
            "nivel"
        ].eq(
            "N2"
        ).sum()
    )

    nivel_3 = int(
        detalle[
            "nivel"
        ].eq(
            "N3"
        ).sum()
    )

    porcentaje = (
        efectivas
        /
        agendadas
        *
        100
        if agendadas
        else 0.0
    )

    return {
        "cita_agendada":
            agendadas,

        "cita_efectiva":
            efectivas,

        "n1":
            nivel_1,

        "n2":
            nivel_2,

        "n3":
            nivel_3,

        "efectividad_pct":
            round(
                porcentaje,
                1,
            ),
    }


def construir_scorecard_mensual(
    detalle: pd.DataFrame,
    anio: int,
    grupo_meta: str,
    configuracion_metas: dict,
    filtro_servicio: str = "TODOS",
    persona: str | None = None,
    excluir_personas: list[str] | None = None,
) -> pd.DataFrame:
    """
    Construye la matriz mensual enero-diciembre.

    Indicadores:
    - Meta
    - cita agendada
    - cita efectiva
    - % efectividad
    - % cumplimiento de meta
    - N1
    - N2
    - N3

    % efectividad:
        cita efectiva / cita agendada

    % cumplimiento de meta:
        cita efectiva / meta
    """

    base = filtrar_detalle_scorecard(
        detalle=detalle,
        filtro_servicio=filtro_servicio,
        persona=persona,
        excluir_personas=excluir_personas,
    ).copy()

    base["_fecha_cita"] = pd.to_datetime(
        base["fecha_cita"],
        errors="coerce",
    )

    base = base.loc[
        base["_fecha_cita"].dt.year.eq(anio)
    ].copy()

    filas = [
        "Meta",
        "cita agendada",
        "cita efectiva",
        "% efectividad",
        "% cumplimiento de meta",
        "N1",
        "N2",
        "N3",
    ]

    resultado = pd.DataFrame(
        index=filas,
        columns=list(MESES.values()),
        dtype="object",
    )

    for numero_mes, nombre_mes in MESES.items():

        detalle_mes = base.loc[
            base["_fecha_cita"].dt.month.eq(
                numero_mes
            )
        ].copy()

        indicadores = calcular_indicadores_periodo(
            detalle_mes
        )

        meta = obtener_meta_mensual(
            configuracion_metas=
                configuracion_metas,
            grupo=
                grupo_meta,
            filtro_servicio=
                filtro_servicio,
            mes=
                numero_mes,
        )

        efectivas = indicadores[
            "cita_efectiva"
        ]

        if meta is None:
            cumplimiento_meta = pd.NA

        elif meta == 0:
            cumplimiento_meta = 0.0

        else:
            cumplimiento_meta = round(
                efectivas
                /
                meta
                *
                100,
                1,
            )

        resultado.loc[
            "Meta",
            nombre_mes,
        ] = (
            meta
            if meta is not None
            else pd.NA
        )

        resultado.loc[
            "cita agendada",
            nombre_mes,
        ] = indicadores[
            "cita_agendada"
        ]

        resultado.loc[
            "cita efectiva",
            nombre_mes,
        ] = efectivas

        resultado.loc[
            "% efectividad",
            nombre_mes,
        ] = indicadores[
            "efectividad_pct"
        ]

        resultado.loc[
            "% cumplimiento de meta",
            nombre_mes,
        ] = cumplimiento_meta

        resultado.loc[
            "N1",
            nombre_mes,
        ] = indicadores[
            "n1"
        ]

        resultado.loc[
            "N2",
            nombre_mes,
        ] = indicadores[
            "n2"
        ]

        resultado.loc[
            "N3",
            nombre_mes,
        ] = indicadores[
            "n3"
        ]

    resultado.index.name = (
        "Nivel mensual"
    )

    return resultado


def construir_avance_al_dia(
    detalle: pd.DataFrame,
    fecha_corte,
    grupo_meta: str,
    configuracion_metas: dict,
    filtro_servicio: str = "TODOS",
    persona: str | None = None,
    excluir_personas: list[str] | None = None,
    feriados: set | list | tuple | None = None,
) -> dict:
    """
    Calcula el avance acumulado contra la meta diaria
    ponderada.

    La meta acumulada respeta:
    - lunes-viernes = 1
    - sábado = 0.5
    - domingo = 0
    - feriado = 0
    """

    fecha_corte = pd.Timestamp(
        fecha_corte
    ).date()

    meta_mensual = obtener_meta_mensual(
        configuracion_metas=
            configuracion_metas,
        grupo=
            grupo_meta,
        filtro_servicio=
            filtro_servicio,
        mes=
            fecha_corte.month,
    )

    base = filtrar_detalle_scorecard(
        detalle=detalle,
        filtro_servicio=filtro_servicio,
        persona=persona,
        excluir_personas=excluir_personas,
    ).copy()

    base[
        "_fecha_cita"
    ] = pd.to_datetime(
        base[
            "fecha_cita"
        ],
        errors="coerce",
    ).dt.date

    efectivas = int(
        base.loc[
            base[
                "es_efectiva"
            ]
            &
            base[
                "_fecha_cita"
            ].ge(
                pd.Timestamp(
                    year=
                        fecha_corte.year,
                    month=
                        fecha_corte.month,
                    day=1,
                ).date()
            )
            &
            base[
                "_fecha_cita"
            ].le(
                fecha_corte
            ),
            "id_cita",
        ].nunique()
    )

    if meta_mensual is None:

        return {
            "meta_mensual":
                None,

            "meta_al_dia":
                None,

            "efectivas_al_dia":
                efectivas,

            "diferencia":
                None,

            "diferencia_pct":
                None,

            "cumplimiento_pct":
                None,

            "estado":
                "⚪ Meta no configurada",
        }

    distribucion = (
        construir_distribucion_meta_diaria(
            anio=
                fecha_corte.year,
            mes=
                fecha_corte.month,
            meta_mensual=
                meta_mensual,
            feriados=
                feriados,
        )
    )

    meta_al_dia = int(
        distribucion.loc[
            distribucion[
                "fecha"
            ].le(
                fecha_corte
            ),
            "meta_dia",
        ].sum()
    )

    diferencia = (
        efectivas
        -
        meta_al_dia
    )

    diferencia_pct = (
        diferencia
        /
        meta_al_dia
        *
        100
        if meta_al_dia
        else 0.0
    )

    cumplimiento = (
        efectivas
        /
        meta_al_dia
        if meta_al_dia
        else 0.0
    )

    if cumplimiento >= UMBRAL_VERDE:

        estado = (
            "🟢 En meta / adelantado"
        )

    elif cumplimiento >= UMBRAL_AMARILLO:

        estado = (
            "🟡 Ligeramente atrasado"
        )

    else:

        estado = (
            "🔴 Atrasado"
        )

    return {
        "meta_mensual":
            int(
                meta_mensual
            ),

        "meta_al_dia":
            meta_al_dia,

        "efectivas_al_dia":
            efectivas,

        "diferencia":
            diferencia,

        "diferencia_pct":
            round(
                diferencia_pct,
                1,
            ),

        "cumplimiento_pct":
            round(
                cumplimiento
                *
                100,
                1,
            ),

        "estado":
            estado,
    }


def construir_evolucion_acumulada(
    detalle: pd.DataFrame,
    fecha_corte,
    grupo_meta: str,
    configuracion_metas: dict,
    filtro_servicio: str = "TODOS",
    persona: str | None = None,
    excluir_personas: list[str] | None = None,
    feriados: set | list | tuple | None = None,
) -> pd.DataFrame:
    """
    Construye la evolución acumulada real del mes.

    Meta:
        acumulación de la meta diaria ponderada.

    Efectivas:
        acumulación de citas efectivas según fecha de cita.
    """

    fecha_corte = pd.Timestamp(
        fecha_corte
    ).date()

    meta_mensual = obtener_meta_mensual(
        configuracion_metas=
            configuracion_metas,
        grupo=
            grupo_meta,
        filtro_servicio=
            filtro_servicio,
        mes=
            fecha_corte.month,
    )

    if meta_mensual is None:

        return pd.DataFrame()

    distribucion = (
        construir_distribucion_meta_diaria(
            anio=
                fecha_corte.year,
            mes=
                fecha_corte.month,
            meta_mensual=
                meta_mensual,
            feriados=
                feriados,
        )
    )

    base = filtrar_detalle_scorecard(
        detalle=detalle,
        filtro_servicio=filtro_servicio,
        persona=persona,
        excluir_personas=excluir_personas,
    ).copy()

    base[
        "_fecha_cita"
    ] = pd.to_datetime(
        base[
            "fecha_cita"
        ],
        errors="coerce",
    ).dt.date

    efectivas = base.loc[
        base[
            "es_efectiva"
        ]
        &
        base[
            "_fecha_cita"
        ].apply(
            lambda fecha:
                (
                    fecha is not None
                    and
                    fecha.year
                    ==
                    fecha_corte.year
                    and
                    fecha.month
                    ==
                    fecha_corte.month
                )
        )
    ].copy()

    por_dia = (
        efectivas
        .groupby(
            "_fecha_cita"
        )[
            "id_cita"
        ]
        .nunique()
        .to_dict()
    )

    evolucion = distribucion[
        [
            "fecha",
            "meta_acumulada",
        ]
    ].copy()

    evolucion[
        "efectivas_dia"
    ] = evolucion[
        "fecha"
    ].map(
        por_dia
    ).fillna(
        0
    ).astype(
        int
    )

    evolucion[
        "efectivas_acumuladas"
    ] = evolucion[
        "efectivas_dia"
    ].cumsum()

    evolucion.loc[
        evolucion[
            "fecha"
        ].gt(
            fecha_corte
        ),
        "efectivas_acumuladas",
    ] = pd.NA

    return evolucion[
        [
            "fecha",
            "meta_acumulada",
            "efectivas_acumuladas",
        ]
    ]


def construir_bloque_scorecard(
    detalle: pd.DataFrame,
    anio: int,
    fecha_corte,
    grupo_meta: str,
    configuracion_metas: dict,
    filtro_servicio: str,
    persona: str | None = None,
    excluir_personas: list[str] | None = None,
) -> dict:
    """
    Construye todo lo necesario para una sección:
    mensual + avance + evolución.
    """

    return {
        "mensual":
            construir_scorecard_mensual(
                detalle=detalle,
                anio=anio,
                grupo_meta=grupo_meta,
                configuracion_metas=
                    configuracion_metas,
                filtro_servicio=
                    filtro_servicio,
                persona=persona,
                excluir_personas=
                    excluir_personas,
            ),

        "avance":
            construir_avance_al_dia(
                detalle=detalle,
                fecha_corte=fecha_corte,
                grupo_meta=grupo_meta,
                configuracion_metas=
                    configuracion_metas,
                filtro_servicio=
                    filtro_servicio,
                persona=persona,
                excluir_personas=
                    excluir_personas,
            ),

        "evolucion":
            construir_evolucion_acumulada(
                detalle=detalle,
                fecha_corte=fecha_corte,
                grupo_meta=grupo_meta,
                configuracion_metas=
                    configuracion_metas,
                filtro_servicio=
                    filtro_servicio,
                persona=persona,
                excluir_personas=
                    excluir_personas,
            ),
    }


def construir_scorecards_operativos(
    detalle: pd.DataFrame,
    anio: int,
    fecha_corte,
    agente_a: str,
    agente_b: str,
    filtro_servicio: str = "TODOS",
    configuracion_metas: dict | None = None,
) -> dict:
    """
    Construye los cuatro bloques del reporte:

        General
        Rocío
        Brenda
        Otros agentes
    """

    if configuracion_metas is None:

        configuracion_metas = (
            CONFIG_METAS_2026
        )

    principales = [
        agente_a,
        agente_b,
    ]

    return {
        "general":
            construir_bloque_scorecard(
                detalle=detalle,
                anio=anio,
                fecha_corte=fecha_corte,
                grupo_meta="GENERAL",
                configuracion_metas=
                    configuracion_metas,
                filtro_servicio=
                    filtro_servicio,
            ),

        "rocio":
            construir_bloque_scorecard(
                detalle=detalle,
                anio=anio,
                fecha_corte=fecha_corte,
                grupo_meta="ROCIO",
                configuracion_metas=
                    configuracion_metas,
                filtro_servicio=
                    filtro_servicio,
                persona=agente_a,
            ),

        "brenda":
            construir_bloque_scorecard(
                detalle=detalle,
                anio=anio,
                fecha_corte=fecha_corte,
                grupo_meta="BRENDA",
                configuracion_metas=
                    configuracion_metas,
                filtro_servicio=
                    filtro_servicio,
                persona=agente_b,
            ),

        "otros":
            construir_bloque_scorecard(
                detalle=detalle,
                anio=anio,
                fecha_corte=fecha_corte,
                grupo_meta="OTROS",
                configuracion_metas=
                    configuracion_metas,
                filtro_servicio=
                    filtro_servicio,
                excluir_personas=
                    principales,
            ),
    }





