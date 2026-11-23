from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import calendar
from database import (
    inicializar_base,
    cargar_detalle_efectividad,
    listar_conflictos_revision_matching,
    listar_candidatas_conflicto_matching,
    guardar_override_matching,
    cerrar_conflicto_revision_matching,
    listar_overrides_matching,
)

from efectividad_reportes import (
    construir_scorecards_operativos,
    construir_scorecard_diario,
    calcular_comision_agente,
    CONFIG_METAS_2026,
    CONFIG_INCENTIVOS_2026,
)

# ============================================================
# CONFIGURACIÓN
# ============================================================

st.set_page_config(
    page_title="CGO — Efectividad",
    page_icon="📊",
    layout="wide",
)


AGENTE_ROCIO = (
    "Rocio Miranda Ausejo"
)

AGENTE_BRENDA = (
    "Brenda Montalvan Cornejo"
)


inicializar_base()


# ============================================================
# CARGA
# ============================================================

@st.cache_data(
    ttl=30
)
def cargar_efectividad(
    anio: int,
) -> pd.DataFrame:

    return cargar_detalle_efectividad(
        anio=anio
    )


# ============================================================
# AVANCE
# ============================================================

def mostrar_avance(
    avance: dict,
) -> None:
    """
    Muestra un resumen compacto del avance mensual.

    Diseñado para ocupar poco espacio vertical en la
    columna derecha del scorecard.
    """

    meta_mensual = avance[
        "meta_mensual"
    ]

    meta_al_dia = avance[
        "meta_al_dia"
    ]

    efectivas = avance[
        "efectivas_al_dia"
    ]

    diferencia = avance[
        "diferencia"
    ]

    diferencia_pct = avance[
        "diferencia_pct"
    ]

    estado = avance[
        "estado"
    ]

    if meta_mensual is None:

        st.info(
            "Meta no configurada."
        )

        st.metric(
            "Efectivas al corte",
            f"{efectivas:,}",
        )

        return

    # ========================================================
    # FILA 1 — META Y META ESPERADA
    # ========================================================

    col_meta, col_esperada = st.columns(
        2,
        gap="small",
    )

    with col_meta:

        st.metric(
            "Meta mensual",
            f"{meta_mensual:,}",
        )

    with col_esperada:

        st.metric(
            "Meta al corte",
            f"{meta_al_dia:,}",
        )

    # ========================================================
    # FILA 2 — REAL Y BRECHA
    # ========================================================

    col_real, col_brecha = st.columns(
        2,
        gap="small",
    )

    with col_real:

        st.metric(
            "Efectivas",
            f"{efectivas:,}",
            delta=(
                f"{diferencia:+,} citas"
            ),
        )

    with col_brecha:

        st.metric(
            "Brecha",
            f"{diferencia_pct:+.1f}%",
        )

    # ========================================================
    # SEMÁFORO
    # ========================================================

    st.markdown(
        f"**{estado}**"
    )


# ============================================================
# EVOLUCIÓN
# ============================================================

def mostrar_grafico_evolucion(
    evolucion: pd.DataFrame,
) -> None:
    """
    Muestra una versión compacta de la evolución acumulada,
    pensada para la columna lateral del scorecard.
    """

    if evolucion.empty:

        st.caption(
            "Sin meta para mostrar tendencia."
        )

        return

    figura = go.Figure()

    figura.add_trace(
        go.Scatter(
            x=evolucion[
                "fecha"
            ],
            y=evolucion[
                "meta_acumulada"
            ],
            mode="lines",
            name="Meta",
            line=dict(
                dash="dot",
                width=2,
            ),
        )
    )

    figura.add_trace(
        go.Scatter(
            x=evolucion[
                "fecha"
            ],
            y=evolucion[
                "efectivas_acumuladas"
            ],
            mode="lines",
            name="Efectivas",
            line=dict(
                width=2,
            ),
        )
    )

    figura.update_layout(
        height=175,

        hovermode="x unified",

        margin=dict(
            l=0,
            r=0,
            t=5,
            b=0,
        ),

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            font=dict(
                size=10,
            ),
        ),

        plot_bgcolor=(
            "rgba(0,0,0,0)"
        ),

        paper_bgcolor=(
            "rgba(0,0,0,0)"
        ),

        xaxis=dict(
            title="",
            showgrid=False,
            tickformat="%d/%m",
            nticks=5,
            tickfont=dict(
                size=9,
            ),
        ),

        yaxis=dict(
            title="",
            showgrid=True,
            nticks=4,
            tickfont=dict(
                size=9,
            ),
        ),
    )

    st.plotly_chart(
        figura,
        use_container_width=True,
        config={
            "displayModeBar": False,
        },
    )


# ============================================================
# SCORECARD VISUAL
# ============================================================
def estilizar_tabla_efectividad(
    tabla: pd.DataFrame,
):
    """
    Formatea cantidades y porcentajes y aplica
    semáforos a las filas porcentuales.
    """

    styler = tabla.style

    filas_enteras = [
        fila
        for fila in [
            "Meta",
            "cita agendada",
            "cita efectiva",
            "N1",
            "N2",
            "N3",
        ]
        if fila in tabla.index
    ]

    filas_porcentaje = [
        fila
        for fila in [
            "% efectividad",
            "% cumplimiento de meta",
        ]
        if fila in tabla.index
    ]

    if filas_enteras:

        styler = styler.format(
            "{:.0f}",
            subset=pd.IndexSlice[
                filas_enteras,
                :
            ],
            na_rep="",
        )

    if filas_porcentaje:

        styler = styler.format(
            "{:.1f}%",
            subset=pd.IndexSlice[
                filas_porcentaje,
                :
            ],
            na_rep="",
        )

    def color_efectividad(
        valor,
    ):

        if pd.isna(
            valor
        ):
            return ""

        valor = float(
            valor
        )

        if valor >= 90:
            return (
                "background-color: #d9ead3;"
                "color: #274e13;"
            )

        if valor >= 80:
            return (
                "background-color: #fff2cc;"
                "color: #7f6000;"
            )

        return (
            "background-color: #f4cccc;"
            "color: #990000;"
        )

    def color_cumplimiento(
        valor,
    ):

        if pd.isna(
            valor
        ):
            return ""

        valor = float(
            valor
        )

        if valor >= 100:
            return (
                "background-color: #d9ead3;"
                "color: #274e13;"
            )

        if valor >= 90:
            return (
                "background-color: #fff2cc;"
                "color: #7f6000;"
            )

        return (
            "background-color: #f4cccc;"
            "color: #990000;"
        )

    if "% efectividad" in tabla.index:

        styler = styler.map(
            color_efectividad,
            subset=pd.IndexSlice[
                [
                    "% efectividad"
                ],
                :
            ],
        )

    if (
        "% cumplimiento de meta"
        in tabla.index
    ):

        styler = styler.map(
            color_cumplimiento,
            subset=pd.IndexSlice[
                [
                    "% cumplimiento de meta"
                ],
                :
            ],
        )

    return styler

def mostrar_scorecard(
    titulo: str,
    bloque: dict,
) -> None:
    """
    Muestra un bloque compacto de efectividad:

    izquierda:
        tabla mensual.

    derecha:
        avance del mes + tendencia acumulada.
    """

    mensual = bloque[
        "mensual"
    ]

    avance = bloque[
        "avance"
    ]

    evolucion = bloque[
        "evolucion"
    ]

    st.markdown(
        f"## {titulo}"
    )

    columna_tabla, columna_control = st.columns(
        [
            4.6,
            1.4,
        ],
        gap="large",
    )

    # ========================================================
    # IZQUIERDA — SCORECARD MENSUAL
    # ========================================================

    with columna_tabla:

        st.dataframe(
            estilizar_tabla_efectividad(mensual),
            use_container_width=True,
            height=285,
        )

    # ========================================================
    # DERECHA — AVANCE + TENDENCIA
    # ========================================================

    with columna_control:

        st.markdown(
            "#### Avance del mes"
        )

        mostrar_avance(
            avance
        )

        st.markdown(
            "##### Tendencia"
        )

        mostrar_grafico_evolucion(
            evolucion
        )

def mostrar_scorecard_diario(
    titulo: str,
    tabla: pd.DataFrame,
) -> None:
    """
    Muestra el seguimiento diario del mes actual.
    """

    st.markdown(
        f"#### {titulo}"
    )

    if tabla.empty:

        st.info(
            "No existe una meta configurada."
        )

        return

    def estilo_columna(
        columna: pd.Series,
    ):
        """
        Domingos en gris claro.
        """

        if str(
            columna.name
        ).endswith(
            "-dom"
        ):

            return [
                "background-color: rgba(128,128,128,0.14)"
            ] * len(
                columna
            )

        return [
            ""
        ] * len(
            columna
        )





    styled = estilizar_tabla_efectividad(
        tabla
    )


    def pintar_domingo(
        columna: pd.Series,
    ):

        if str(
            columna.name
        ).endswith(
            "-dom"
        ):

            return [
                (
                    "background-color: "
                    "#eeeeee;"
                )
            ] * len(
                columna
            )

        return [
            ""
        ] * len(
            columna
        )


    styled = styled.apply(
        pintar_domingo,
        axis=0,
    ).apply(
            estilo_columna,
            axis=0,
        ).format(
            na_rep="",
        )
    

    st.dataframe(
        styled,
        use_container_width=True,
        height=235,
    )

def mostrar_comision(
    titulo: str,
    comision: dict,
) -> None:
    """
    Presenta la comisión y permite identificar claramente
    el tramo actual y el siguiente objetivo.
    """

    st.markdown(
        f"#### 💰 Comisión — {titulo}"
    )

    if (
        comision[
            "meta"
        ] is None
        or
        comision[
            "incentivo_base"
        ] is None
    ):

        st.info(
            "Configuración de comisión incompleta."
        )

        return

    col1, col2, col3 = st.columns(
        3
    )

    col1.metric(
        "Objetivo",
        f"{comision['meta']:,}",
    )

    col2.metric(
        "Resultado",
        f"{comision['resultado']:,}",
    )

    col3.metric(
        "Cumplimiento",
        (
            f"{comision['cumplimiento_pct']:.1f}%"
        ),
    )

    col4, col5 = st.columns(
        2
    )

    col4.metric(
        "Incentivo",
        (
            f"S/ "
            f"{comision['incentivo_base']:,.0f}"
        ),
    )

    col5.metric(
        "Recibido / proyectado",
        (
            f"S/ "
            f"{comision['comision']:,.0f}"
        ),
    )

    cumplimiento = comision[
        "cumplimiento_pct"
    ]

    tramos = pd.DataFrame(
        {
            "Lím. inf. >=": [
                "0%",
                "50%",
                "60%",
                "70%",
                "80%",
                "90%",
                "95%",
                ">100%",
            ],

            "Lím. sup. <": [
                "50%",
                "60%",
                "70%",
                "80%",
                "90%",
                "95%",
                "100%",
                "150%",
            ],

            "Incentivo": [
                "0%",
                "50%",
                "60%",
                "70%",
                "80%",
                "90%",
                "100%",
                "Variable",
            ],
        }
    )

    def es_tramo_actual(
        indice: int,
    ) -> bool:

        limites = [
            (0, 50),
            (50, 60),
            (60, 70),
            (70, 80),
            (80, 90),
            (90, 95),
            (95, 100.000001),
            (100.000001, 150.000001),
        ]

        inferior, superior = limites[
            indice
        ]

        return (
            cumplimiento
            >= inferior
            and
            cumplimiento
            <
            superior
        )

    def resaltar_tramo(
        fila: pd.Series,
    ):

        if es_tramo_actual(
            fila.name
        ):

            return [
                (
                    "background-color: #d9ead3;"
                    "font-weight: bold;"
                )
            ] * len(
                fila
            )

        return [
            ""
        ] * len(
            fila
        )

    st.dataframe(
        tramos.style.apply(
            resaltar_tramo,
            axis=1,
        ),
        use_container_width=True,
        hide_index=True,
    )

    siguiente = comision[
        "siguiente_umbral_pct"
    ]

    faltantes = comision[
        "faltantes_siguiente_tramo"
    ]

    if (
        siguiente is not None
        and faltantes > 0
    ):

        st.info(
            (
                f"Te faltan **{faltantes:,} "
                f"citas efectivas** para alcanzar "
                f"el {siguiente:.0f}%."
            )
        )

    elif cumplimiento >= 150:

        st.success(
            (
                "🏆 Alcanzaste el techo máximo "
                "de comisión: 150%."
            )
        )

    else:

        st.success(
            "✅ Ya alcanzaste el siguiente nivel."
        )

    st.caption(
        (
            "La comisión siempre se calcula sobre "
            "TODOS los grupos de servicio, usando "
            "únicamente los tipos habilitados."
        )
    )

# ============================================================
# REVISIÓN MANUAL
# ============================================================

def mostrar_revision_manual() -> None:

    tab_pendientes, tab_decisiones = st.tabs(
        [
            "⚠️ Casos por revisar",
            "✅ Decisiones guardadas",
        ]
    )

    with tab_pendientes:

        conflictos = (
            listar_conflictos_revision_matching()
        )

        if conflictos.empty:

            st.success(
                "No existen casos pendientes de revisión."
            )

        else:

            st.info(
                (
                    f"{len(conflictos):,} "
                    "caso(s) pendiente(s)."
                )
            )

            for conflicto in conflictos.itertuples(
                index=False
            ):

                presencia_id = (
                    conflicto.presencia_id
                )

                with st.expander(
                    (
                        f"{conflicto.placa} · "
                        f"{conflicto.fecha_visita} · "
                        f"N{conflicto.nivel}"
                    ),
                    expanded=True,
                ):

                    candidatas = (
                        listar_candidatas_conflicto_matching(
                            presencia_id
                        )
                    )

                    if candidatas.empty:

                        st.warning(
                            "No existen candidatas."
                        )

                        continue

                    vista = candidatas[
                        [
                            "appointment_number",
                            "agente",
                            "fecha_hora_cita",
                            "motivos",
                            "diferencia_dias",
                        ]
                    ].copy()

                    vista.columns = [
                        "Cita",
                        "Agente",
                        "Fecha / hora",
                        "Motivo",
                        "Diferencia días",
                    ]

                    st.dataframe(
                        vista,
                        use_container_width=True,
                        hide_index=True,
                    )

                    opciones = {}

                    for fila in candidatas.itertuples(
                        index=False
                    ):

                        etiqueta = (
                            f"#{fila.appointment_number}"
                            f" · {fila.agente}"
                            f" · {fila.motivos}"
                        )

                        opciones[
                            etiqueta
                        ] = fila

                    seleccion = st.selectbox(
                        "Cita que recibe la efectividad",
                        options=list(
                            opciones.keys()
                        ),
                        key=(
                            "efectividad_"
                            +
                            presencia_id
                        ),
                    )

                    if st.button(
                        "Guardar decisión",
                        key=(
                            "guardar_"
                            +
                            presencia_id
                        ),
                        type="primary",
                    ):

                        elegida = opciones[
                            seleccion
                        ]

                        guardar_override_matching(
                            presencia_id=
                                presencia_id,

                            id_cita_elegida=
                                elegida.id_cita,

                            appointment_number=
                                elegida.appointment_number,

                            persona_creditada=
                                elegida.agente,

                            canal_decision=
                                "STREAMLIT",

                            usuario_decision=
                                "SUPERVISORA",

                            motivo=
                                (
                                    "CONFLICTO_"
                                    "MATCHING_EFECTIVIDAD"
                                ),
                        )

                        cerrar_conflicto_revision_matching(
                            presencia_id
                        )

                        st.success(
                            "Decisión guardada."
                        )

                        st.rerun()

    with tab_decisiones:

        registros = listar_overrides_matching(
            solo_activos=True
        )

        if not registros:

            st.info(
                "No existen decisiones guardadas."
            )

        else:

            df = pd.DataFrame(
                registros
            )

            columnas = [
                "presencia_id",
                "appointment_number",
                "persona_creditada",
                "canal_decision",
                "usuario_decision",
                "fecha_actualizacion",
            ]

            vista = df[
                columnas
            ].copy()

            vista = vista.rename(
                columns={
                    "presencia_id":
                        "Presencia",

                    "appointment_number":
                        "Cita",

                    "persona_creditada":
                        "Persona acreditada",

                    "canal_decision":
                        "Canal",

                    "usuario_decision":
                        "Usuario",

                    "fecha_actualizacion":
                        "Última actualización",
                }
            )

            st.dataframe(
                vista,
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# ENCABEZADO
# ============================================================

st.title(
    "📊 Efectividad de citas"
)

st.caption(
    (
        "Seguimiento de citas agendadas, "
        "efectividad N1 / N2 / N3 y "
        "cumplimiento de metas."
    )
)


# ============================================================
# FILTROS PRINCIPALES
# ============================================================

col_filtro, col_anio = st.columns(
    [
        2,
        1,
    ]
)

with col_filtro:

    opcion = st.segmented_control(
        "Tipo de servicio",
        options=[
            "Todos",
            "Preventivo",
            "No preventivo",
        ],
        default="Todos",
    )

with col_anio:

    anio = st.selectbox(
        "Año",
        options=[
            2026,
        ],
        index=0,
    )


MAPA_FILTRO = {
    "Todos":
        "TODOS",

    "Preventivo":
        "PREVENTIVO",

    "No preventivo":
        "NO_PREVENTIVO",
}


filtro_servicio = MAPA_FILTRO[
    opcion
]


# ============================================================
# FILTRO DETALLADO DE SERVICIOS
# ============================================================

TIPOS_POR_GRUPO = {
    "PREVENTIVO": [
        ("Preventivo", "Preventivo"),
        ("01K", "01K"),
    ],

    "NO_PREVENTIVO": [
        ("Correctivo", "Correctivo"),
        ("P&P", "PYP"),
        ("Diagnóstico", "Diagnóstico"),
        ("Garantía", "Garantía"),
        ("Indeterminado", "INDETERMINADO"),
    ],
}


TODOS_TIPOS = (
    TIPOS_POR_GRUPO[
        "PREVENTIVO"
    ]
    +
    TIPOS_POR_GRUPO[
        "NO_PREVENTIVO"
    ]
)


# Inicializar una sola vez.
for _, valor in TODOS_TIPOS:

    clave = (
        f"cuenta_servicio_{valor}"
    )

    if clave not in st.session_state:

        st.session_state[
            clave
        ] = True


if filtro_servicio == "PREVENTIVO":

    opciones_tipo = TIPOS_POR_GRUPO[
        "PREVENTIVO"
    ]

elif filtro_servicio == "NO_PREVENTIVO":

    opciones_tipo = TIPOS_POR_GRUPO[
        "NO_PREVENTIVO"
    ]

else:

    opciones_tipo = TODOS_TIPOS


with st.expander(
    "⚙️ Servicios considerados",
    expanded=False,
):

    st.caption(
        (
            "Estos checks determinan qué tipos de "
            "servicio participan en los indicadores."
        )
    )

    columnas_check = st.columns(
        min(
            len(
                opciones_tipo
            ),
            4,
        )
    )

    for posicion, (
        etiqueta,
        valor,
    ) in enumerate(
        opciones_tipo
    ):

        clave = (
            f"cuenta_servicio_{valor}"
        )

        with columnas_check[
            posicion
            %
            len(
                columnas_check
            )
        ]:

            st.checkbox(
                etiqueta,
                key=clave,
            )


tipos_servicio_seleccionados = [
    valor
    for _, valor
    in TODOS_TIPOS
    if st.session_state[
        f"cuenta_servicio_{valor}"
    ]
]


tipos_servicio_visual = [
    valor
    for _, valor
    in opciones_tipo
    if st.session_state[
        f"cuenta_servicio_{valor}"
    ]
]



# ============================================================
# DATOS
# ============================================================

detalle = cargar_efectividad(
    anio
)

if detalle.empty:

    st.warning(
        (
            "Todavía no existen resultados de "
            "efectividad para este año."
        )
    )

    st.stop()


# ============================================================
# FECHA DE CORTE
#
# Primero calculamos esto porque los feriados y el
# scorecard diario dependen de esta fecha.
# ============================================================

ultima_fecha_datos = max(
    detalle[
        "fecha_cita"
    ]
)

fecha_corte = min(
    date.today(),
    ultima_fecha_datos,
)


st.caption(
    (
        f"Fecha de corte: "
        f"{fecha_corte:%d/%m/%Y}"
    )
)


# ============================================================
# FERIADOS DEL MES ACTUAL
# ============================================================

dias_mes_actual = pd.date_range(
    start=(
        f"{fecha_corte.year}-"
        f"{fecha_corte.month:02d}-01"
    ),
    end=pd.Timestamp(
        year=fecha_corte.year,
        month=fecha_corte.month,
        day=calendar.monthrange(
            fecha_corte.year,
            fecha_corte.month,
        )[1],
    ),
    freq="D",
)


opciones_feriados = [
    fecha.date()
    for fecha in dias_mes_actual
    if fecha.weekday() != 6
]


feriados = st.multiselect(
    "Feriados del mes",
    options=opciones_feriados,
    default=[],
    format_func=lambda fecha:
        fecha.strftime(
            "%d/%m/%Y"
        ),
)


# ============================================================
# SCORECARDS MENSUALES
# ============================================================

scorecards = construir_scorecards_operativos(
    detalle=detalle,
    anio=anio,
    fecha_corte=fecha_corte,
    agente_a=AGENTE_ROCIO,
    agente_b=AGENTE_BRENDA,
    filtro_servicio=filtro_servicio,
    configuracion_metas=CONFIG_METAS_2026,
    tipos_servicio=    tipos_servicio_visual,
)


# ============================================================
# SCORECARDS DIARIOS
# ============================================================

mes_actual = fecha_corte.month


diario_general = construir_scorecard_diario(
    detalle=detalle,
    anio=anio,
    mes=mes_actual,
    grupo_meta="GENERAL",
    configuracion_metas=
        CONFIG_METAS_2026,
    filtro_servicio=
        filtro_servicio,
    feriados=
        feriados,
    tipos_servicio=
    tipos_servicio_visual,
)


diario_rocio = construir_scorecard_diario(
    detalle=detalle,
    anio=anio,
    mes=mes_actual,
    grupo_meta="ROCIO",
    configuracion_metas=
        CONFIG_METAS_2026,
    filtro_servicio=
        filtro_servicio,
    persona=
        AGENTE_ROCIO,
    feriados=
        feriados,
    tipos_servicio=
    tipos_servicio_visual,
)


diario_brenda = construir_scorecard_diario(
    detalle=detalle,
    anio=anio,
    mes=mes_actual,
    grupo_meta="BRENDA",
    configuracion_metas=
        CONFIG_METAS_2026,
    filtro_servicio=
        filtro_servicio,
    persona=
        AGENTE_BRENDA,
    feriados=
        feriados,
    tipos_servicio=
    tipos_servicio_visual,
)


diario_otros = construir_scorecard_diario(
    detalle=detalle,
    anio=anio,
    mes=mes_actual,
    grupo_meta="OTROS",
    configuracion_metas=
        CONFIG_METAS_2026,
    filtro_servicio=
        filtro_servicio,
    excluir_personas=[
        AGENTE_ROCIO,
        AGENTE_BRENDA,
    ],
    feriados=
        feriados,
    tipos_servicio=
    tipos_servicio_visual,
)


# ============================================================
# COMISIONES
#
# IMPORTANTE:
# calcular_comision_agente() usa internamente TODOS.
# El filtro visual de arriba no afecta la comisión.
# ============================================================

comision_rocio = calcular_comision_agente(
    detalle=detalle,
    anio=anio,
    mes=mes_actual,
    agente=AGENTE_ROCIO,
    grupo_meta="ROCIO",
    configuracion_metas=
        CONFIG_METAS_2026,
    configuracion_incentivos=
        CONFIG_INCENTIVOS_2026,
    tipos_servicio_comision=
    tipos_servicio_seleccionados,
)


comision_brenda = calcular_comision_agente(
    detalle=detalle,
    anio=anio,
    mes=mes_actual,
    agente=AGENTE_BRENDA,
    grupo_meta="BRENDA",
    configuracion_metas=
        CONFIG_METAS_2026,
    configuracion_incentivos=
        CONFIG_INCENTIVOS_2026,
    tipos_servicio_comision=
    tipos_servicio_seleccionados,
)


# ============================================================
# PESTAÑAS
# ============================================================

tab_resumen, tab_detalle, tab_revision = st.tabs(
    [
        "📊 Resumen",
        "📋 Detalle",
        "⚖️ Revisión manual",
    ]
)


# ============================================================
# RESUMEN
# ============================================================

with tab_resumen:

    # --------------------------------------------------------
    # GENERAL
    # --------------------------------------------------------

    mostrar_scorecard(
        titulo="Nivel general",
        bloque=scorecards[
            "general"
        ],
    )

    mostrar_scorecard_diario(
        titulo="Seguimiento diario — General",
        tabla=diario_general,
    )

    st.divider()

    # --------------------------------------------------------
    # ROCÍO
    # --------------------------------------------------------

    mostrar_scorecard(
        titulo="Rocío",
        bloque=scorecards[
            "rocio"
        ],
    )

    mostrar_scorecard_diario(
        titulo="Seguimiento diario — Rocío",
        tabla=diario_rocio,
    )

    mostrar_comision(
        titulo="Rocío",
        comision=
            comision_rocio,
    )

    st.divider()

    # --------------------------------------------------------
    # BRENDA
    # --------------------------------------------------------

    mostrar_scorecard(
        titulo="Brenda",
        bloque=scorecards[
            "brenda"
        ],
    )

    mostrar_scorecard_diario(
        titulo="Seguimiento diario — Brenda",
        tabla=diario_brenda,
    )

    mostrar_comision(
        titulo="Brenda",
        comision=
            comision_brenda,
    )

    st.divider()

    # --------------------------------------------------------
    # OTROS
    # --------------------------------------------------------

    mostrar_scorecard(
        titulo="Otros agentes",
        bloque=scorecards[
            "otros"
        ],
    )

    mostrar_scorecard_diario(
        titulo="Seguimiento diario — Otros agentes",
        tabla=diario_otros,
    )


# ============================================================
# DETALLE
# ============================================================

with tab_detalle:

    detalle_filtrado = detalle.copy()

    if filtro_servicio != "TODOS":

        detalle_filtrado = detalle_filtrado.loc[
            detalle_filtrado[
                "grupo_servicio"
            ].eq(
                filtro_servicio
            )
        ].copy()

    columnas = [
        "fecha_cita",
        "hora_cita",
        "appointment_number",
        "placa_normalizada",
        "motivos",
        "grupo_servicio",
        "agente",
        "persona_creditada",
        "resultado_efectividad",
        "fecha_visita",
        "confirmacion_presencia",
        "numeros_cotizacion",
        "numeros_orden",
    ]

    st.dataframe(
        detalle_filtrado[
            columnas
        ],
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# REVISIÓN MANUAL
# ============================================================

with tab_revision:

    mostrar_revision_manual()



