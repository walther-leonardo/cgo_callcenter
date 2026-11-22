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


FILTROS_SERVICIO_VALIDOS = {
    "TODOS",
    "PREVENTIVO",
    "NO_PREVENTIVO",
}


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
        permite construir el grupo "Otros agentes".
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
            f"{filtro_servicio}. "
            "Use TODOS, PREVENTIVO "
            "o NO_PREVENTIVO."
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


def calcular_indicadores_periodo(
    detalle: pd.DataFrame,
) -> dict:
    """
    Calcula los indicadores básicos del scorecard
    sobre un subconjunto ya filtrado.
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
    meta: dict[int, float | int] | None = None,
    cpu: dict[int, float | int] | None = None,
    real: dict[int, float | int] | None = None,
    filtro_servicio: str = "TODOS",
    persona: str | None = None,
    excluir_personas: list[str] | None = None,
) -> pd.DataFrame:
    """
    Construye la matriz mensual enero-diciembre.

    Meta, CPU y Real son valores externos/hardcodeados.

    Las claves de los diccionarios son números de mes:

        {
            1: valor_enero,
            2: valor_febrero,
            ...
            12: valor_diciembre,
        }

    Diferencia:
        cita efectiva - Real

    Si Real no está informado, la diferencia queda vacía.
    """

    meta = meta or {}
    cpu = cpu or {}
    real = real or {}

    base = filtrar_detalle_scorecard(
        detalle=detalle,
        filtro_servicio=filtro_servicio,
        persona=persona,
        excluir_personas=excluir_personas,
    )

    base = base.copy()

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
    ].copy()

    filas = [
        "Meta",
        "CPU",
        "cita agendada",
        "cita efectiva",
        "Diferencia cita efectiva de Real",
        "N1",
        "N2",
        "N3",
        "% efectividad",
    ]

    resultado = pd.DataFrame(
        index=filas,
        columns=list(
            MESES.values()
        ),
        dtype="object",
    )

    for numero_mes, nombre_mes in (
        MESES.items()
    ):

        mes = base.loc[
            base[
                "_fecha_cita"
            ].dt.month.eq(
                numero_mes
            )
        ].copy()

        indicadores = (
            calcular_indicadores_periodo(
                mes
            )
        )

        resultado.loc[
            "Meta",
            nombre_mes,
        ] = meta.get(
            numero_mes,
            pd.NA,
        )

        resultado.loc[
            "CPU",
            nombre_mes,
        ] = cpu.get(
            numero_mes,
            pd.NA,
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
        ] = indicadores[
            "cita_efectiva"
        ]

        real_mes = real.get(
            numero_mes
        )

        if real_mes is None:

            diferencia = pd.NA

        else:

            diferencia = (
                indicadores[
                    "cita_efectiva"
                ]
                -
                real_mes
            )

        resultado.loc[
            "Diferencia cita efectiva de Real",
            nombre_mes,
        ] = diferencia

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

        resultado.loc[
            "% efectividad",
            nombre_mes,
        ] = indicadores[
            "efectividad_pct"
        ]

    resultado.index.name = (
        "Nivel mensual"
    )

    return resultado


def construir_scorecard_al_dia(
    detalle: pd.DataFrame,
    fecha_corte,
    meta_al_dia: float | int | None = None,
    cpu_al_dia: float | int | None = None,
    real_al_dia: float | int | None = None,
    filtro_servicio: str = "TODOS",
    persona: str | None = None,
    excluir_personas: list[str] | None = None,
) -> pd.DataFrame:
    """
    Construye la tabla compacta correspondiente al
    mes de fecha_corte, desde el primer día del mes
    hasta fecha_corte inclusive.

    Meta y CPU al día son hardcodeados.
    """

    fecha_corte = pd.Timestamp(
        fecha_corte
    ).date()

    base = filtrar_detalle_scorecard(
        detalle=detalle,
        filtro_servicio=filtro_servicio,
        persona=persona,
        excluir_personas=excluir_personas,
    )

    base = base.copy()

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
            fecha_corte.year
        )
        &
        base[
            "_fecha_cita"
        ].dt.month.eq(
            fecha_corte.month
        )
        &
        base[
            "_fecha_cita"
        ].dt.date.le(
            fecha_corte
        )
    ].copy()

    indicadores = (
        calcular_indicadores_periodo(
            base
        )
    )

    if real_al_dia is None:

        diferencia = pd.NA

    else:

        diferencia = (
            indicadores[
                "cita_efectiva"
            ]
            -
            real_al_dia
        )

    resultado = pd.DataFrame(
        {
            "Total": [
                meta_al_dia,
                cpu_al_dia,
                indicadores[
                    "cita_agendada"
                ],
                indicadores[
                    "cita_efectiva"
                ],
                diferencia,
            ],
        },
        index=[
            "Meta al día de hoy",
            "CPU al día de hoy",
            "cita agendada hasta el día de hoy",
            "cita efectiva hasta el día de hoy",
            "Diferencia cita efectiva de Real",
        ],
    )

    return resultado


def construir_scorecards_operativos(
    detalle: pd.DataFrame,
    anio: int,
    fecha_corte,
    agente_a: str,
    agente_b: str,
    filtro_servicio: str = "TODOS",
    configuracion: dict | None = None,
) -> dict:
    """
    Construye los ocho bloques principales:

    - General mensual
    - General al día
    - Agente A mensual
    - Agente A al día
    - Agente B mensual
    - Agente B al día
    - Otros agentes mensual
    - Otros agentes al día

    La configuración contiene Meta, CPU y Real
    de cada bloque.
    """

    configuracion = (
        configuracion
        or {}
    )

    def obtener_config(
        clave: str,
    ) -> dict:

        return configuracion.get(
            clave,
            {}
        )

    principales = [
        agente_a,
        agente_b,
    ]

    bloques = {
        "general_mensual":
            construir_scorecard_mensual(
                detalle=detalle,
                anio=anio,
                filtro_servicio=filtro_servicio,
                **obtener_config(
                    "general_mensual"
                ),
            ),

        "general_al_dia":
            construir_scorecard_al_dia(
                detalle=detalle,
                fecha_corte=fecha_corte,
                filtro_servicio=filtro_servicio,
                **obtener_config(
                    "general_al_dia"
                ),
            ),

        "agente_a_mensual":
            construir_scorecard_mensual(
                detalle=detalle,
                anio=anio,
                filtro_servicio=filtro_servicio,
                persona=agente_a,
                **obtener_config(
                    "agente_a_mensual"
                ),
            ),

        "agente_a_al_dia":
            construir_scorecard_al_dia(
                detalle=detalle,
                fecha_corte=fecha_corte,
                filtro_servicio=filtro_servicio,
                persona=agente_a,
                **obtener_config(
                    "agente_a_al_dia"
                ),
            ),

        "agente_b_mensual":
            construir_scorecard_mensual(
                detalle=detalle,
                anio=anio,
                filtro_servicio=filtro_servicio,
                persona=agente_b,
                **obtener_config(
                    "agente_b_mensual"
                ),
            ),

        "agente_b_al_dia":
            construir_scorecard_al_dia(
                detalle=detalle,
                fecha_corte=fecha_corte,
                filtro_servicio=filtro_servicio,
                persona=agente_b,
                **obtener_config(
                    "agente_b_al_dia"
                ),
            ),

        "otros_mensual":
            construir_scorecard_mensual(
                detalle=detalle,
                anio=anio,
                filtro_servicio=filtro_servicio,
                excluir_personas=principales,
                **obtener_config(
                    "otros_mensual"
                ),
            ),

        "otros_al_dia":
            construir_scorecard_al_dia(
                detalle=detalle,
                fecha_corte=fecha_corte,
                filtro_servicio=filtro_servicio,
                excluir_personas=principales,
                **obtener_config(
                    "otros_al_dia"
                ),
            ),
    }

    return bloques







