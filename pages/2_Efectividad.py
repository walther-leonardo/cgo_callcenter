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
            mensual,
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

    styled = (
        tabla.style
        .apply(
            estilo_columna,
            axis=0,
        )
        .format(
            na_rep="",
        )
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
    Muestra el cálculo mensual de comisión.

    La comisión siempre utiliza TODOS los servicios.
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

    c1, c2, c3 = st.columns(
        3
    )

    c1.metric(
        "Meta",
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
            f"{comision['incentivo_base']:,.2f}"
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
            f"{comision['comision']:,.2f}"
        ),
    )

    st.caption(
        (
            "La comisión se calcula siempre con "
            "TODOS los servicios, independientemente "
            "del filtro seleccionado arriba."
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
# FILTROS
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
#
# No usamos una fecha posterior a la última información
# disponible.
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


scorecards = construir_scorecards_operativos(
    detalle=detalle,
    anio=anio,
    fecha_corte=fecha_corte,
    agente_a=AGENTE_ROCIO,
    agente_b=AGENTE_BRENDA,
    filtro_servicio=filtro_servicio,
    configuracion_metas=CONFIG_METAS_2026,
)


st.caption(
    (
        f"Fecha de corte: "
        f"{fecha_corte:%d/%m/%Y}"
    )
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

    mostrar_scorecard(
        titulo="Nivel general",
        bloque=scorecards[
            "general"
        ],
    )

    st.divider()

    mostrar_scorecard(
        titulo="Rocío",
        bloque=scorecards[
            "rocio"
        ],
    )

    st.divider()

    mostrar_scorecard(
        titulo="Brenda",
        bloque=scorecards[
            "brenda"
        ],
    )

    st.divider()

    mostrar_scorecard(
        titulo="Otros agentes",
        bloque=scorecards[
            "otros"
        ],
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






