from __future__ import annotations

import calendar
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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
    filtrar_detalle_scorecard,
    CONFIG_METAS_2026,
    CONFIG_INCENTIVOS_2026,
)


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(
    page_title="CGO — Efectividad",
    page_icon="📊",
    layout="wide",
)


AGENTE_ROCIO = "Rocio Miranda Ausejo"
AGENTE_BRENDA = "Brenda Montalvan Cornejo"


# ============================================================
# CATÁLOGO VISUAL DE SERVICIOS
#
# El primer valor es lo que ve el usuario.
# El segundo es el valor técnico utilizado por
# clasificar_servicio().
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
    TIPOS_POR_GRUPO["PREVENTIVO"]
    +
    TIPOS_POR_GRUPO["NO_PREVENTIVO"]
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
    """
    Carga el detalle persistido de efectividad.
    """

    return cargar_detalle_efectividad(
        anio=anio
    )


# ============================================================
# FORMATO Y SEMÁFOROS
# ============================================================

def estilizar_tabla_efectividad(
    tabla: pd.DataFrame,
):
    """
    Aplica formato consistente:

    - cantidades sin decimales;
    - porcentajes con un decimal;
    - semáforo para % efectividad;
    - semáforo para % cumplimiento de meta.
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

    # --------------------------------------------------------
    # % EFECTIVIDAD
    #
    # Criterio preliminar:
    # >= 90 verde
    # >= 80 amarillo
    # < 80 rojo
    # --------------------------------------------------------

    def color_efectividad(
        valor,
    ) -> str:

        if pd.isna(valor):
            return ""

        valor = float(valor)

        if valor >= 90:
            return (
                "background-color: #d9ead3;"
                "color: #274e13;"
                "font-weight: 600;"
            )

        if valor >= 80:
            return (
                "background-color: #fff2cc;"
                "color: #7f6000;"
                "font-weight: 600;"
            )

        return (
            "background-color: #f4cccc;"
            "color: #990000;"
            "font-weight: 600;"
        )

    # --------------------------------------------------------
    # % CUMPLIMIENTO
    #
    # >= 100 verde
    # >= 90 amarillo
    # < 90 rojo
    # --------------------------------------------------------

    def color_cumplimiento(
        valor,
    ) -> str:

        if pd.isna(valor):
            return ""

        valor = float(valor)

        if valor >= 100:
            return (
                "background-color: #d9ead3;"
                "color: #274e13;"
                "font-weight: 600;"
            )

        if valor >= 90:
            return (
                "background-color: #fff2cc;"
                "color: #7f6000;"
                "font-weight: 600;"
            )

        return (
            "background-color: #f4cccc;"
            "color: #990000;"
            "font-weight: 600;"
        )

    if "% efectividad" in tabla.index:

        styler = styler.map(
            color_efectividad,
            subset=pd.IndexSlice[
                ["% efectividad"],
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
                ["% cumplimiento de meta"],
                :
            ],
        )

    return styler


# ============================================================
# AVANCE
# ============================================================

def mostrar_avance(
    avance: dict,
) -> None:
    """
    Resumen compacto de avance mensual.
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

    st.markdown(
        f"**{estado}**"
    )


# ============================================================
# GRÁFICO DE EVOLUCIÓN
# ============================================================

def mostrar_grafico_evolucion(
    evolucion: pd.DataFrame,
) -> None:
    """
    Curva compacta:
    meta acumulada vs citas efectivas acumuladas.
    """

    if evolucion.empty:

        st.caption(
            "Sin meta para mostrar tendencia."
        )

        return

    figura = go.Figure()

    figura.add_trace(
        go.Scatter(
            x=evolucion["fecha"],
            y=evolucion["meta_acumulada"],
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
            x=evolucion["fecha"],
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

        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",

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
# SCORECARD MENSUAL VISUAL
# ============================================================

def mostrar_scorecard(
    titulo: str,
    bloque: dict,
) -> None:
    """
    Tabla mensual a la izquierda.

    Avance + tendencia a la derecha.
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

    columna_tabla, columna_control = (
        st.columns(
            [
                4.6,
                1.4,
            ],
            gap="large",
        )
    )

    with columna_tabla:

        st.dataframe(
            estilizar_tabla_efectividad(
                mensual
            ),
            use_container_width=True,
            height=305,
        )

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


# ============================================================
# SCORECARD DIARIO VISUAL
# ============================================================

def mostrar_scorecard_diario(
    titulo: str,
    tabla: pd.DataFrame,
) -> None:
    """
    Seguimiento diario del mes actual.
    """

    st.markdown(
        f"#### {titulo}"
    )

    if tabla.empty:

        st.info(
            "No existe una meta configurada."
        )

        return

    styled = estilizar_tabla_efectividad(
        tabla
    )

    # --------------------------------------------------------
    # DOMINGOS EN GRIS
    # --------------------------------------------------------

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
    )

    st.dataframe(
        styled,
        use_container_width=True,
        height=235,
    )


# ============================================================
# COMISIÓN
# ============================================================

def mostrar_comision(
    titulo: str,
    comision: dict,
) -> None:
    """
    Presenta:

    - objetivo;
    - resultado;
    - cumplimiento;
    - incentivo base;
    - comisión proyectada;
    - tramo actual;
    - siguiente tramo;
    - efectivas faltantes.
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

    # ========================================================
    # RESUMEN
    # ========================================================

    c1, c2, c3 = st.columns(
        3
    )

    c1.metric(
        "Objetivo",
        f"{comision['meta']:,}",
    )

    c2.metric(
        "Resultado",
        f"{comision['resultado']:,}",
    )

    c3.metric(
        "Cumplimiento",
        (
            f"{comision['cumplimiento_pct']:.1f}%"
        ),
    )

    c4, c5, c6 = st.columns(
        3
    )

    c4.metric(
        "Incentivo base",
        (
            f"S/ "
            f"{comision['incentivo_base']:,.0f}"
        ),
    )

    c5.metric(
        "Factor aplicado",
        (
            f"{comision['factor_incentivo_pct']:.1f}%"
        ),
    )

    c6.metric(
        "Comisión proyectada",
        (
            f"S/ "
            f"{comision['comision']:,.0f}"
        ),
    )

    # ========================================================
    # ESCALA
    # ========================================================

    cumplimiento = float(
        comision[
            "cumplimiento_pct"
        ]
    )

    tramos = pd.DataFrame(
        {
            "Lím. inf. ≥": [
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

    # --------------------------------------------------------
    # IDENTIFICAR FILA ACTUAL
    # --------------------------------------------------------

    def obtener_indice_tramo() -> int:

        if cumplimiento < 50:
            return 0

        if cumplimiento < 60:
            return 1

        if cumplimiento < 70:
            return 2

        if cumplimiento < 80:
            return 3

        if cumplimiento < 90:
            return 4

        if cumplimiento < 95:
            return 5

        if cumplimiento <= 100:
            return 6

        return 7

    indice_actual = obtener_indice_tramo()

    def resaltar_tramo(
        fila: pd.Series,
    ):

        if fila.name == indice_actual:

            return [
                (
                    "background-color: #d9ead3;"
                    "font-weight: bold;"
                    "color: #274e13;"
                )
            ] * len(
                fila
            )

        return [
            ""
        ] * len(
            fila
        )

    izquierda, derecha = st.columns(
        [
            1.35,
            1,
        ],
        gap="large",
    )

    with izquierda:

        st.dataframe(
            tramos.style.apply(
                resaltar_tramo,
                axis=1,
            ),
            use_container_width=True,
            hide_index=True,
            height=315,
        )

    with derecha:

        st.markdown(
            "##### Situación actual"
        )

        tramo_actual = tramos.iloc[
            indice_actual
        ]

        st.write(
            (
                "**Rango actual:** "
                f"{tramo_actual['Lím. inf. ≥']} "
                f"a {tramo_actual['Lím. sup. <']}"
            )
        )

        st.write(
            (
                "**Incentivo aplicado:** "
                f"{comision['factor_incentivo_pct']:.1f}%"
            )
        )

        siguiente = comision[
            "siguiente_umbral_pct"
        ]

        faltantes = comision[
            "faltantes_siguiente_tramo"
        ]

        if (
            siguiente is not None
            and faltantes is not None
            and faltantes > 0
        ):

            st.info(
                (
                    f"Te faltan **{faltantes:,} "
                    "citas efectivas** para alcanzar "
                    f"el **{siguiente:.0f}%**."
                )
            )

        elif cumplimiento >= 150:

            st.success(
                (
                    "🏆 Alcanzaste el techo máximo "
                    "de comisión: **150%**."
                )
            )

        elif cumplimiento >= 100:

            st.success(
                (
                    "✅ Superaste el 100%. "
                    "La comisión continúa creciendo "
                    "hasta un máximo de 150%."
                )
            )

        else:

            st.success(
                "✅ Objetivo del tramo alcanzado."
            )

    st.caption(
        (
            "La comisión siempre utiliza TODOS los grupos "
            "de servicio, pero respeta los tipos de servicio "
            "habilitados en la configuración superior."
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

    # ========================================================
    # PENDIENTES
    # ========================================================

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

    # ========================================================
    # DECISIONES GUARDADAS
    # ========================================================

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
        "efectividad N1 / N2 / N3, "
        "cumplimiento de metas y comisiones."
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
# SEGUNDA CAPA — TIPOS DE SERVICIO
# ============================================================

# Inicializar checks una sola vez.
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
            "Selecciona qué tipos de servicio participan "
            "en los indicadores. Esta configuración también "
            "determina qué servicios cuentan para comisión."
        )
    )

    numero_columnas = min(
        max(
            len(
                opciones_tipo
            ),
            1,
        ),
        4,
    )

    columnas_check = st.columns(
        numero_columnas
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
            numero_columnas
        ]:

            st.checkbox(
                etiqueta,
                key=clave,
            )


# ------------------------------------------------------------
# FILTRO VISUAL
#
# Solo considera los tipos pertenecientes al filtro superior.
# ------------------------------------------------------------

tipos_servicio_visual = [
    valor
    for _, valor
    in opciones_tipo
    if st.session_state[
        f"cuenta_servicio_{valor}"
    ]
]


# ------------------------------------------------------------
# FILTRO DE COMISIÓN
#
# La comisión ignora Preventivo / No preventivo / Todos,
# pero respeta todos los checks globales.
# ------------------------------------------------------------

tipos_servicio_comision = [
    valor
    for _, valor
    in TODOS_TIPOS
    if st.session_state[
        f"cuenta_servicio_{valor}"
    ]
]


# ============================================================
# FERIADOS
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
    configuracion_metas=
        CONFIG_METAS_2026,
    tipos_servicio=
        tipos_servicio_visual,
    feriados=
        feriados,
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
    tipos_servicio=
        tipos_servicio_visual,
    feriados=
        feriados,
    fecha_corte=
        fecha_corte,
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
    tipos_servicio=
        tipos_servicio_visual,
    feriados=
        feriados,
    fecha_corte=
        fecha_corte,
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
    tipos_servicio=
        tipos_servicio_visual,
    feriados=
        feriados,
    fecha_corte=
        fecha_corte,
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
    tipos_servicio=
        tipos_servicio_visual,
    feriados=
        feriados,
    fecha_corte=
        fecha_corte,
)


# ============================================================
# COMISIONES
#
# Siempre TODOS.
# Solo cambia según los checks comerciales.
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
        tipos_servicio_comision,
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
        tipos_servicio_comision,
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

    detalle_filtrado = filtrar_detalle_scorecard(
        detalle=detalle,
        filtro_servicio=
            filtro_servicio,
        tipos_servicio=
            tipos_servicio_visual,
    ).copy()

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

    columnas = [
        columna
        for columna in columnas
        if columna
        in detalle_filtrado.columns
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