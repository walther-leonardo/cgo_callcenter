from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database import get_connection

from reportes import (
    construir_control_indeterminados,
    construir_reporte_canal_agenda,
    construir_reporte_servicios,
)



# ============================================================
# CONFIGURACIÓN
# ============================================================

st.set_page_config(
    page_title="CGO — Call Center",
    page_icon="📞",
    layout="wide",
)

AGENTES_CALLCENTER = [
    "Brenda Montalvan Cornejo",
    "Rocio Miranda Ausejo",
]


# ============================================================
# ESTILOS VISUALES
# ============================================================

def aplicar_estilos_compactos() -> None:
    """
    Reduce espacios verticales y compacta tarjetas KPI.
    """

    st.markdown(
        """
        <style>

        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 1.2rem;
            padding-left: 2rem;
            padding-right: 2rem;
            max-width: 1500px;
        }

        h1 {
            margin-bottom: 0.2rem;
        }

        h2, h3 {
            margin-top: 0.35rem;
            margin-bottom: 0.25rem;
        }

        div[data-testid="stMetric"] {
            background-color: rgba(250, 250, 250, 0.60);
            border: 1px solid rgba(49, 51, 63, 0.12);
            border-radius: 9px;
            padding: 0.55rem 0.70rem;
        }

        div[data-testid="stMetricLabel"] {
            font-size: 0.82rem;
        }

        div[data-testid="stMetricValue"] {
            font-size: 1.55rem;
        }

        .compact-caption {
            color: #6b7280;
            font-size: 0.82rem;
            margin-top: -0.15rem;
            margin-bottom: 0.35rem;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


aplicar_estilos_compactos()


# ============================================================
# HELPERS — CARGA
# ============================================================

@st.cache_data(ttl=30)
def cargar_snapshots() -> pd.DataFrame:

    with get_connection() as conn:

        df = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                fecha_hora_corte,
                cantidad_citas
            FROM snapshots
            ORDER BY fecha_hora_corte
            """,
            conn,
        )

    df["fecha_hora_corte"] = pd.to_datetime(
        df["fecha_hora_corte"],
        errors="coerce",
    )

    return df


@st.cache_data(ttl=30)
def cargar_metricas() -> pd.DataFrame:

    with get_connection() as conn:

        df = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                metrica,
                dimension,
                segmento,
                valor
            FROM metricas_snapshot
            """,
            conn,
        )

    return df


@st.cache_data(ttl=30)
def cargar_citas_snapshot(
    snapshot_id: int,
) -> pd.DataFrame:

    with get_connection() as conn:

        df = pd.read_sql_query(
            """
            SELECT *
            FROM citas_snapshot
            WHERE snapshot_id = ?
            """,
            conn,
            params=[snapshot_id],
        )

    df["fecha_programada"] = pd.to_datetime(
        df["fecha_programada"],
        errors="coerce",
    ).dt.normalize()

    return df


# ============================================================
# HELPERS — MÉTRICAS
# ============================================================

def obtener_valor(
    metricas: pd.DataFrame,
    snapshot_id: int,
    metrica: str,
    dimension: str,
    segmento: str,
) -> float:

    fila = metricas.loc[
        metricas["snapshot_id"].eq(snapshot_id)
        &
        metricas["metrica"].eq(metrica)
        &
        metricas["dimension"].eq(dimension)
        &
        metricas["segmento"].eq(segmento)
    ]

    if fila.empty:
        return 0

    return float(
        fila["valor"].iloc[0]
    )

def mostrar_reporte_operativo(
    reporte: pd.DataFrame,
) -> None:
    """
    Renderiza el reporte completo como HTML compacto,
    evitando barras de desplazamiento.

    Reglas visuales:
    - SAN ISIDRO: azul
    - SAN MIGUEL: verde
    - FACTURABLE primero
    - NO FACTURABLE después
    - INDETERMINADO al final
    - TOTAL SEDE resaltado
    - TOTAL GENERAL resaltado
    """

    if reporte.empty:
        st.info(
            "No existen citas para la fecha seleccionada."
        )
        return

    df = reporte.copy()

    def estilo_fila(
        fila: pd.Series,
    ) -> list[str]:

        estilos = [
            ""
            for _ in fila.index
        ]

        sede = str(
            fila.get(
                "sede",
                "",
            )
        )

        tipo_facturacion = str(
            fila.get(
                "tipo_facturacion",
                "",
            )
        )

        # ----------------------------------------------------
        # Color de sede
        # ----------------------------------------------------

        if "sede" in fila.index:

            posicion_sede = (
                fila.index.get_loc(
                    "sede"
                )
            )

            if sede == "SAN ISIDRO":

                estilos[
                    posicion_sede
                ] += (
                    "color:#1A73E8;"
                    "font-weight:700;"
                )

            elif sede == "SAN MIGUEL":

                estilos[
                    posicion_sede
                ] += (
                    "color:#188038;"
                    "font-weight:700;"
                )

        # ----------------------------------------------------
        # FACTURABLE / NO FACTURABLE / INDETERMINADO
        # ----------------------------------------------------

        if "tipo_facturacion" in fila.index:

            posicion_fact = (
                fila.index.get_loc(
                    "tipo_facturacion"
                )
            )

            if tipo_facturacion == "FACTURABLE":

                estilos[
                    posicion_fact
                ] += (
                    "font-weight:700;"
                )

            elif tipo_facturacion == "NO FACTURABLE":

                estilos[
                    posicion_fact
                ] += (
                    "font-weight:700;"
                    "color:#5F6368;"
                )

            elif tipo_facturacion == "INDETERMINADO":

                estilos[
                    posicion_fact
                ] += (
                    "font-weight:700;"
                    "color:#B06000;"
                )

        # ----------------------------------------------------
        # Total de sede
        # ----------------------------------------------------

        if tipo_facturacion == "TOTAL SEDE":

            color_fondo = (
                "#E8F0FE"
                if sede == "SAN ISIDRO"
                else "#E6F4EA"
                if sede == "SAN MIGUEL"
                else "#F1F3F4"
            )

            estilos = [
                (
                    estilo
                    +
                    f"background-color:{color_fondo};"
                    "font-weight:700;"
                    "border-top:2px solid #9AA0A6;"
                )
                for estilo in estilos
            ]

        # ----------------------------------------------------
        # Total general
        # ----------------------------------------------------

        if sede == "Total general":

            estilos = [
                (
                    estilo
                    +
                    "background-color:#D2E3FC;"
                    "font-weight:700;"
                    "border-top:2px solid #5F6368;"
                )
                for estilo in estilos
            ]

        return estilos

    styler = (
        df.style
        .apply(
            estilo_fila,
            axis=1,
        )
        .hide(
            axis="index"
        )
        .format(
            na_rep="",
        )
        .set_table_styles(
            [
                {
                    "selector":
                        "table",

                    "props": [
                        (
                            "width",
                            "100%",
                        ),
                        (
                            "border-collapse",
                            "collapse",
                        ),
                        (
                            "font-size",
                            "10px",
                        ),
                        (
                            "table-layout",
                            "fixed",
                        ),
                    ],
                },
                {
                    "selector":
                        "th",

                    "props": [
                        (
                            "background-color",
                            "#D9EAF7",
                        ),
                        (
                            "font-weight",
                            "700",
                        ),
                        (
                            "text-align",
                            "center",
                        ),
                        (
                            "padding",
                            "4px 3px",
                        ),
                        (
                            "border",
                            "1px solid #DADCE0",
                        ),
                        (
                            "white-space",
                            "normal",
                        ),
                        (
                            "word-wrap",
                            "break-word",
                        ),
                    ],
                },
                {
                    "selector":
                        "td",

                    "props": [
                        (
                            "padding",
                            "3px 3px",
                        ),
                        (
                            "text-align",
                            "center",
                        ),
                        (
                            "border",
                            "1px solid #E8EAED",
                        ),
                        (
                            "white-space",
                            "normal",
                        ),
                        (
                            "word-wrap",
                            "break-word",
                        ),
                    ],
                },
            ]
        )
    )

    st.markdown(
        """
        <style>
        .reporte-callcenter {
            width: 100%;
            overflow: visible;
        }

        .reporte-callcenter table {
            width: 100% !important;
        }

        .reporte-callcenter th:nth-child(1),
        .reporte-callcenter td:nth-child(1) {
            width: 7%;
            text-align: left;
        }

        .reporte-callcenter th:nth-child(2),
        .reporte-callcenter td:nth-child(2) {
            width: 8%;
            text-align: left;
        }

        .reporte-callcenter th:nth-child(3),
        .reporte-callcenter td:nth-child(3) {
            width: 8%;
            text-align: left;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        (
            '<div class="reporte-callcenter">'
            +
            styler.to_html()
            +
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def mostrar_reporte_canal_agenda(
    reporte: pd.DataFrame,
) -> None:
    """
    Renderiza la matriz Canal → Persona que agenda.

    Mantiene:
    - SAN ISIDRO azul
    - SAN MIGUEL verde
    - subtotales por sede
    - encabezado jerárquico CALL CENTER / TALLER
    - porcentaje del total
    """

    if reporte.empty:
        st.info(
            "No existen datos para mostrar."
        )
        return

    df = reporte.copy()

    # --------------------------------------------------------
    # FORMATEAR % TOTAL
    # --------------------------------------------------------

    columna_pct = (
        "TOTAL",
        "% Total",
    )

    if columna_pct in df.columns:

        df[
            columna_pct
        ] = (
            pd.to_numeric(
                df[
                    columna_pct
                ],
                errors="coerce",
            )
            .fillna(0)
            .map(
                lambda valor:
                    f"{valor:.1%}"
            )
        )

    # --------------------------------------------------------
    # STYLER
    # --------------------------------------------------------

    def estilo_fila(
        fila: pd.Series,
    ) -> list[str]:

        estilos = [
            ""
            for _ in fila.index
        ]

        sede = str(
            fila.get(
                (
                    "sede",
                    "",
                ),
                "",
            )
        )

        tipo_facturacion = str(
            fila.get(
                (
                    "tipo_facturacion",
                    "",
                ),
                "",
            )
        )

        if tipo_facturacion == "TOTAL SEDE":

            fondo = (
                "#E8F0FE"
                if sede == "SAN ISIDRO"
                else "#E6F4EA"
                if sede == "SAN MIGUEL"
                else "#F1F3F4"
            )

            estilos = [
                (
                    estilo
                    +
                    f"background-color:{fondo};"
                    "font-weight:700;"
                    "border-top:2px solid #9AA0A6;"
                )
                for estilo in estilos
            ]

        if sede == "Total general":

            estilos = [
                (
                    estilo
                    +
                    "background-color:#D2E3FC;"
                    "font-weight:700;"
                    "border-top:2px solid #5F6368;"
                )
                for estilo in estilos
            ]

        return estilos

    styler = (
        df.style
        .apply(
            estilo_fila,
            axis=1,
        )
        .hide(
            axis="index"
        )
        .set_table_styles(
            [
                {
                    "selector":
                        "table",

                    "props": [
                        (
                            "width",
                            "100%",
                        ),
                        (
                            "border-collapse",
                            "collapse",
                        ),
                        (
                            "font-size",
                            "9px",
                        ),
                    ],
                },
                {
                    "selector":
                        "th",

                    "props": [
                        (
                            "background-color",
                            "#D9EAF7",
                        ),
                        (
                            "font-weight",
                            "700",
                        ),
                        (
                            "text-align",
                            "center",
                        ),
                        (
                            "padding",
                            "3px",
                        ),
                        (
                            "border",
                            "1px solid #DADCE0",
                        ),
                    ],
                },
                {
                    "selector":
                        "td",

                    "props": [
                        (
                            "padding",
                            "3px",
                        ),
                        (
                            "text-align",
                            "center",
                        ),
                        (
                            "border",
                            "1px solid #E8EAED",
                        ),
                    ],
                },
            ]
        )
    )

    st.markdown(
        styler.to_html(),
        unsafe_allow_html=True,
    )


def obtener_valor_agente_bucket(
    metricas: pd.DataFrame,
    snapshot_id: int,
    metrica: str,
    agente: str,
    bucket: str,
) -> float:
    """
    Recupera una métrica segmentada simultáneamente
    por agente y bucket temporal.
    """

    segmento = (
        f"{agente}"
        f"||"
        f"{bucket}"
    )

    return obtener_valor(
        metricas=metricas,
        snapshot_id=snapshot_id,
        metrica=metrica,
        dimension="AGENTE_BUCKET",
        segmento=segmento,
    )

def obtener_snapshots_dia(
    snapshots: pd.DataFrame,
    fecha_objetivo,
) -> pd.DataFrame:

    return (
        snapshots.loc[
            snapshots["fecha_hora_corte"]
            .dt.date
            .eq(fecha_objetivo)
        ]
        .sort_values("fecha_hora_corte")
        .copy()
    )

def construir_comparativo_agenda(
    snapshot_inicio: int,
    snapshot_actual: int,
) -> pd.DataFrame:

    inicio = cargar_citas_snapshot(
        snapshot_inicio
    )

    actual = cargar_citas_snapshot(
        snapshot_actual
    )

    serie_inicio = (
        inicio
        .groupby(
            "fecha_programada",
            as_index=False,
        )
        .agg(
            citas_inicio=(
                "id_cita",
                "nunique",
            )
        )
    )

    serie_actual = (
        actual
        .groupby(
            "fecha_programada",
            as_index=False,
        )
        .agg(
            citas_actual=(
                "id_cita",
                "nunique",
            )
        )
    )

    comparativo = (
        serie_inicio
        .merge(
            serie_actual,
            on="fecha_programada",
            how="outer",
        )
        .fillna(0)
        .sort_values(
            "fecha_programada"
        )
    )

    comparativo["citas_inicio"] = (
        comparativo["citas_inicio"]
        .astype(int)
    )

    comparativo["citas_actual"] = (
        comparativo["citas_actual"]
        .astype(int)
    )

    comparativo["delta"] = (
        comparativo["citas_actual"]
        -
        comparativo["citas_inicio"]
    )

    return comparativo

def buscar_snapshot_referencia(
    snapshots: pd.DataFrame,
    fecha_objetivo,
    hora_objetivo,
):
    """
    Busca el snapshot del día objetivo cuya hora sea
    la más cercana a la hora solicitada.
    """

    candidatos = obtener_snapshots_dia(
        snapshots,
        fecha_objetivo,
    )

    if candidatos.empty:
        return None

    candidatos = candidatos.copy()

    candidatos["diferencia"] = (
        candidatos["fecha_hora_corte"]
        .dt.time
        .apply(
            lambda hora:
                abs(
                    (
                        hora.hour * 60
                        + hora.minute
                    )
                    -
                    (
                        hora_objetivo.hour * 60
                        + hora_objetivo.minute
                    )
                )
        )
    )

    return (
        candidatos
        .sort_values("diferencia")
        .iloc[0]
    )

def construir_ritmo_intradia(
    snapshots: pd.DataFrame,
    metricas: pd.DataFrame,
    fecha_objetivo,
) -> pd.DataFrame:
    """
    Construye la evolución acumulada de citas nuevas
    desde el primer corte del día.

    Devuelve una fila por snapshot y columnas:
        fecha_hora_corte
        TOTAL
        Brenda Montalvan Cornejo
        Rocio Miranda Ausejo
    """

    snapshots_dia = obtener_snapshots_dia(
        snapshots=snapshots,
        fecha_objetivo=fecha_objetivo,
    )

    if snapshots_dia.empty:
        return pd.DataFrame()

    filas = []

    for snapshot in snapshots_dia.itertuples(
        index=False
    ):

        snapshot_id = int(
            snapshot.snapshot_id
        )

        fila = {
            "snapshot_id":
                snapshot_id,

            "fecha_hora_corte":
                snapshot.fecha_hora_corte,

            "TOTAL":
                obtener_valor(
                    metricas=metricas,
                    snapshot_id=snapshot_id,
                    metrica="NUEVAS_DESDE_INICIO_DIA",
                    dimension="TOTAL",
                    segmento="TOTAL",
                ),
        }

        for agente in AGENTES_CALLCENTER:

            fila[
                agente
            ] = obtener_valor(
                metricas=metricas,
                snapshot_id=snapshot_id,
                metrica="NUEVAS_DESDE_INICIO_DIA",
                dimension="AGENTE",
                segmento=agente,
            )

        filas.append(
            fila
        )

    return (
        pd.DataFrame(
            filas
        )
        .sort_values(
            "fecha_hora_corte"
        )
        .reset_index(
            drop=True
        )
    )

# ============================================================
# HELPERS — GRÁFICO
# ============================================================

def construir_grafico_agenda(
    comparativo: pd.DataFrame,
    fecha_dia,
):
    """
    Construye gráfico inicio del día vs situación actual
    para hoy + 7 días.
    """

    fecha_inicio = pd.Timestamp(
        fecha_dia
    )

    fecha_fin = (
        fecha_inicio
        +
        pd.Timedelta(
            days=7
        )
    )

    vista = (
        comparativo.loc[
            comparativo[
                "fecha_programada"
            ].between(
                fecha_inicio,
                fecha_fin,
            )
        ]
        .copy()
    )

    calendario = pd.DataFrame(
        {
            "fecha_programada":
                pd.date_range(
                    start=fecha_inicio,
                    end=fecha_fin,
                    freq="D",
                )
        }
    )

    vista = (
        calendario
        .merge(
            vista,
            on="fecha_programada",
            how="left",
        )
    )

    columnas_numericas = [
        "citas_inicio",
        "citas_actual",
        "delta",
    ]

    vista[
        columnas_numericas
    ] = (
        vista[
            columnas_numericas
        ]
        .fillna(0)
        .astype(int)
    )

    figura = go.Figure()

    figura.add_trace(
        go.Scatter(
            x=vista["fecha_programada"],
            y=vista["citas_inicio"],
            mode="lines+markers",
            name="Inicio del día",
            line=dict(
                color="#3C4043",
                width=3,
            ),
            marker=dict(
                size=7,
            ),
        )
    )

    figura.add_trace(
        go.Scatter(
            x=vista["fecha_programada"],
            y=vista["citas_actual"],
            mode="lines+markers",
            name="Actual",
            line=dict(
                color="#00A82D",
                width=4,
            ),
            marker=dict(
                size=8,
            ),
        )
    )

    crecimientos = (
        vista.loc[
            vista[
                "delta"
            ].gt(0)
        ]
    )

    for fila in crecimientos.itertuples(
        index=False
    ):

        figura.add_annotation(
            x=fila.fecha_programada,
            y=fila.citas_actual,
            text=f"+{fila.delta}",
            showarrow=True,
            arrowhead=2,
            ay=-28,
            font=dict(
                size=12,
                color="#00A82D",
            ),
        )

    figura.update_xaxes(
        tickmode="array",
        tickvals=vista["fecha_programada"],
        ticktext=[
            fecha.strftime(
                "%d/%m"
            )
            for fecha
            in vista[
                "fecha_programada"
            ]
        ],
    )

    figura.update_yaxes(
        rangemode="tozero",
    )

    figura.update_layout(
        height=430,
        hovermode="x unified",
        xaxis_title="",
        yaxis_title="Citas",
        legend_title_text="",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        margin=dict(
            l=10,
            r=10,
            t=20,
            b=10,
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return figura

# ============================================================
# CARGA
# ============================================================

snapshots = cargar_snapshots()
metricas = cargar_metricas()

if snapshots.empty:

    st.warning(
        "Todavía no existen snapshots registrados."
    )

    st.stop()


ultimo = (
    snapshots.iloc[-1]
)

snapshot_actual = int(
    ultimo["snapshot_id"]
)

fecha_actual = (
    ultimo["fecha_hora_corte"]
)

fecha_dia = (
    fecha_actual.date()
)

snapshots_hoy = obtener_snapshots_dia(
    snapshots,
    fecha_dia,
)

snapshot_inicio = int(
    snapshots_hoy.iloc[0][
        "snapshot_id"
    ]
)


# ============================================================
# MÉTRICAS PRINCIPALES
# ============================================================

agenda_hoy = obtener_valor(
    metricas,
    snapshot_actual,
    "AGENDA_ACTUAL",
    "BUCKET",
    "HOY",
)

agenda_manana = obtener_valor(
    metricas,
    snapshot_actual,
    "AGENDA_ACTUAL",
    "BUCKET",
    "MANANA",
)

agenda_futura = obtener_valor(
    metricas,
    snapshot_actual,
    "AGENDA_ACTUAL",
    "BUCKET",
    "PASADO_MANANA_O_MAS",
)


inicio_hoy = obtener_valor(
    metricas,
    snapshot_actual,
    "NUEVAS_DESDE_INICIO_DIA",
    "BUCKET",
    "HOY",
)

inicio_manana = obtener_valor(
    metricas,
    snapshot_actual,
    "NUEVAS_DESDE_INICIO_DIA",
    "BUCKET",
    "MANANA",
)

inicio_futuro = obtener_valor(
    metricas,
    snapshot_actual,
    "NUEVAS_DESDE_INICIO_DIA",
    "BUCKET",
    "PASADO_MANANA_O_MAS",
)


ultimo_total = obtener_valor(
    metricas,
    snapshot_actual,
    "NUEVAS_ULTIMO_CORTE",
    "TOTAL",
    "TOTAL",
)

ultimo_hoy = obtener_valor(
    metricas,
    snapshot_actual,
    "NUEVAS_ULTIMO_CORTE",
    "BUCKET",
    "HOY",
)

ultimo_manana = obtener_valor(
    metricas,
    snapshot_actual,
    "NUEVAS_ULTIMO_CORTE",
    "BUCKET",
    "MANANA",
)

ultimo_futuro = obtener_valor(
    metricas,
    snapshot_actual,
    "NUEVAS_ULTIMO_CORTE",
    "BUCKET",
    "PASADO_MANANA_O_MAS",
)


snapshot_previo = (
    snapshots_hoy.iloc[-2]
    if len(
        snapshots_hoy
    ) >= 2
    else None
)

minutos_desde_anterior = None

if snapshot_previo is not None:

    minutos_desde_anterior = int(
        (
            fecha_actual
            -
            snapshot_previo[
                "fecha_hora_corte"
            ]
        )
        .total_seconds()
        /
        60
    )


# ============================================================
# ENCABEZADO
# ============================================================

st.title(
    "CGO — Call Center"
)

st.caption(
    (
        "Seguimiento intradía de generación "
        "y cobertura de citas."
    )
)

st.caption(
    (
        f"Último corte: "
        f"{fecha_actual:%d/%m/%Y %H:%M}"
    )
)


# ============================================================
# BLOQUE PRINCIPAL — KPI + GRÁFICO
# ============================================================

col_resumen, col_grafico = st.columns(
    [
        0.95,
        1.55,
    ],
    gap="large",
)


# ------------------------------------------------------------
# COLUMNA IZQUIERDA
# ------------------------------------------------------------

with col_resumen:

    # ========================================================
    # AGENDA ACTUAL
    # ========================================================

    st.subheader(
        "Agenda actual"
    )

    a1, a2, a3 = (
        st.columns(3)
    )

    a1.metric(
        "Hoy",
        f"{int(agenda_hoy):,}",
    )

    a2.metric(
        "Mañana",
        f"{int(agenda_manana):,}",
    )

    a3.metric(
        "D+2 o más",
        f"{int(agenda_futura):,}",
    )

    # ========================================================
    # CONSTRUCCIÓN
    # ========================================================

    st.subheader(
        "Construcción de agenda"
    )

    c1, c2, c3 = (
        st.columns(3)
    )

    c1.metric(
        "Hoy",
        f"+{int(inicio_hoy):,}",
    )

    c2.metric(
        "Mañana",
        f"+{int(inicio_manana):,}",
    )

    c3.metric(
        "D+2 o más",
        f"+{int(inicio_futuro):,}",
    )

    # ========================================================
    # ÚLTIMO CORTE
    # ========================================================

    st.subheader(
        "Último corte"
    )

    if (
        minutos_desde_anterior
        is not None
    ):

        st.markdown(
            (
                '<div class="compact-caption">'
                f"Variación respecto del corte anterior "
                f"hace {minutos_desde_anterior} minutos."
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    u1, u2 = (
        st.columns(2)
    )

    u3, u4 = (
        st.columns(2)
    )

    u1.metric(
        "Nuevas",
        f"+{int(ultimo_total):,}",
    )

    u2.metric(
        "Para hoy",
        f"+{int(ultimo_hoy):,}",
    )

    u3.metric(
        "Para mañana",
        f"+{int(ultimo_manana):,}",
    )

    u4.metric(
        "D+2 o más",
        f"+{int(ultimo_futuro):,}",
    )


# ------------------------------------------------------------
# COLUMNA DERECHA — GRÁFICO
# ------------------------------------------------------------

with col_grafico:

    st.subheader(
        "Agenda en construcción"
    )

    st.caption(
        (
            "Primer corte del día vs situación actual. "
            "Las etiquetas verdes muestran crecimiento."
        )
    )

    comparativo = (
        construir_comparativo_agenda(
            snapshot_inicio=
                snapshot_inicio,
            snapshot_actual=
                snapshot_actual,
        )
    )

    figura = construir_grafico_agenda(
        comparativo=
            comparativo,
        fecha_dia=
            fecha_dia,
    )

    st.plotly_chart(
        figura,
        use_container_width=True,
    )


# ============================================================
# SEGUNDA FILA — AGENTES + RITMO
# ============================================================

st.divider()

col_agentes, col_ritmo = (
    st.columns(
        [
            1.15,
            1,
        ],
        gap="large",
    )
)


# ============================================================
# RENDIMIENTO POR AGENTE
# ============================================================

with col_agentes:

    st.subheader(
        "Rendimiento por agente"
    )

    total_dia = obtener_valor(
        metricas=metricas,
        snapshot_id=snapshot_actual,
        metrica="NUEVAS_DESDE_INICIO_DIA",
        dimension="TOTAL",
        segmento="TOTAL",
    )

    filas_agentes = []

    for agente in AGENTES_CALLCENTER:

        nuevas_dia = obtener_valor(
            metricas=metricas,
            snapshot_id=snapshot_actual,
            metrica="NUEVAS_DESDE_INICIO_DIA",
            dimension="AGENTE",
            segmento=agente,
        )

        nuevas_ultimo = obtener_valor(
            metricas=metricas,
            snapshot_id=snapshot_actual,
            metrica="NUEVAS_ULTIMO_CORTE",
            dimension="AGENTE",
            segmento=agente,
        )

        hoy_dia = obtener_valor_agente_bucket(
            metricas=metricas,
            snapshot_id=snapshot_actual,
            metrica="NUEVAS_DESDE_INICIO_DIA",
            agente=agente,
            bucket="HOY",
        )

        manana_dia = obtener_valor_agente_bucket(
            metricas=metricas,
            snapshot_id=snapshot_actual,
            metrica="NUEVAS_DESDE_INICIO_DIA",
            agente=agente,
            bucket="MANANA",
        )

        futuro_dia = obtener_valor_agente_bucket(
            metricas=metricas,
            snapshot_id=snapshot_actual,
            metrica="NUEVAS_DESDE_INICIO_DIA",
            agente=agente,
            bucket="PASADO_MANANA_O_MAS",
        )

        participacion_pct = (
            nuevas_dia
            /
            total_dia
            *
            100
            if total_dia
            else 0
        )

        filas_agentes.append(
            {
                "Agente":
                    agente,

                "Desde inicio":
                    int(
                        nuevas_dia
                    ),

                "Último corte":
                    int(
                        nuevas_ultimo
                    ),

                "Para hoy":
                    int(
                        hoy_dia
                    ),

                "Para mañana":
                    int(
                        manana_dia
                    ),

                "D+2 o más":
                    int(
                        futuro_dia
                    ),

                "Participación":
                    participacion_pct,
            }
        )

    tabla_agentes = pd.DataFrame(
        filas_agentes
    )

    st.dataframe(
        tabla_agentes,
        use_container_width=True,
        hide_index=True,
        height=150,
        column_config={
            "Participación":
                st.column_config.ProgressColumn(
                    "Participación",
                    min_value=0,
                    max_value=100,
                    format="%.1f%%",
                ),
        },
    )


# ============================================================
    # RITMO COMPARATIVO
# ============================================================

with col_ritmo:

    st.subheader(
        "Ritmo intradía"
    )

    ritmo_hoy = construir_ritmo_intradia(
        snapshots=snapshots,
        metricas=metricas,
        fecha_objetivo=fecha_dia,
    )

    if ritmo_hoy.empty:

        st.info(
            "Todavía no existen suficientes cortes del día."
        )

    else:

        figura_ritmo = go.Figure()

        # ----------------------------------------------------
        # TOTAL
        # ----------------------------------------------------

        figura_ritmo.add_trace(
            go.Scatter(
                x=ritmo_hoy[
                    "fecha_hora_corte"
                ],
                y=ritmo_hoy[
                    "TOTAL"
                ],
                mode="lines+markers",
                name="Total",
                line=dict(
                    color="#1A73E8",
                    width=4,
                ),
                marker=dict(
                    size=8,
                ),
            )
        )

        # ----------------------------------------------------
        # BRENDA
        # ----------------------------------------------------

        figura_ritmo.add_trace(
            go.Scatter(
                x=ritmo_hoy[
                    "fecha_hora_corte"
                ],
                y=ritmo_hoy[
                    "Brenda Montalvan Cornejo"
                ],
                mode="lines+markers",
                name="Brenda",
                line=dict(
                    color="#EA4335",
                    width=3,
                ),
                marker=dict(
                    size=7,
                ),
            )
        )

        # ----------------------------------------------------
        # ROCÍO
        # ----------------------------------------------------

        figura_ritmo.add_trace(
            go.Scatter(
                x=ritmo_hoy[
                    "fecha_hora_corte"
                ],
                y=ritmo_hoy[
                    "Rocio Miranda Ausejo"
                ],
                mode="lines+markers",
                name="Rocío",
                line=dict(
                    color="#34A853",
                    width=3,
                ),
                marker=dict(
                    size=7,
                ),
            )
        )

        figura_ritmo.update_xaxes(
            tickformat="%H:%M",
            title="",
        )

        figura_ritmo.update_yaxes(
            title="Citas nuevas acumuladas",
            rangemode="tozero",
            dtick=2,
        )

        figura_ritmo.update_layout(
            height=280,
            hovermode="x unified",
            legend_title_text="",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
            ),
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )

        st.plotly_chart(
            figura_ritmo,
            use_container_width=True,
        )

    # ========================================================
    # COMPARACIÓN VS AYER
    # ========================================================

    fecha_ayer = (
        fecha_actual.date()
        -
        timedelta(
            days=1
        )
    )

    snapshot_ayer = buscar_snapshot_referencia(
        snapshots=snapshots,
        fecha_objetivo=fecha_ayer,
        hora_objetivo=fecha_actual.time(),
    )

    if snapshot_ayer is None:

        st.caption(
            (
                "📅 La comparación vs ayer aparecerá "
                "automáticamente cuando exista histórico "
                "del día anterior."
            )
        )

    else:

        snapshot_ayer_id = int(
            snapshot_ayer[
                "snapshot_id"
            ]
        )

        hoy_total = obtener_valor(
            metricas=metricas,
            snapshot_id=snapshot_actual,
            metrica="NUEVAS_DESDE_INICIO_DIA",
            dimension="TOTAL",
            segmento="TOTAL",
        )

        ayer_total = obtener_valor(
            metricas=metricas,
            snapshot_id=snapshot_ayer_id,
            metrica="NUEVAS_DESDE_INICIO_DIA",
            dimension="TOTAL",
            segmento="TOTAL",
        )

        diferencia = (
            hoy_total
            -
            ayer_total
        )

        variacion = (
            diferencia
            /
            ayer_total
            if ayer_total
            else None
        )

        r1, r2, r3 = (
            st.columns(3)
        )

        r1.metric(
            "Hoy a esta hora",
            f"{int(hoy_total):,}",
        )

        r2.metric(
            "Ayer a esta hora",
            f"{int(ayer_total):,}",
        )

        r3.metric(
            "Brecha",
            f"{int(diferencia):+d}",
            delta=(
                f"{variacion:+.1%}"
                if variacion
                is not None
                else None
            ),
        )


# ============================================================
# REPORTE OPERATIVO POR SERVICIO
# ============================================================

st.divider()

st.subheader(
    "Distribución de citas por servicio"
)

st.caption(
    (
        "Distribución de la carga programada por sede, "
        "tipo de servicio y asesor."
    )
)

# ============================================================
# BASE DEL ÚLTIMO SNAPSHOT
# ============================================================

citas_actuales = cargar_citas_snapshot(
    snapshot_actual
)

fecha_hoy = pd.Timestamp(
    fecha_dia
).normalize()

fecha_manana = (
    fecha_hoy
    +
    pd.Timedelta(
        days=1
    )
)

fecha_pasado_manana = (
    fecha_hoy
    +
    pd.Timedelta(
        days=2
    )
)


# ============================================================
# CONSTRUIR REPORTES
# ============================================================

reporte_hoy = construir_reporte_servicios(
    citas=citas_actuales,
    fecha_objetivo=fecha_hoy,
)

reporte_manana = construir_reporte_servicios(
    citas=citas_actuales,
    fecha_objetivo=fecha_manana,
)

reporte_pasado_manana = construir_reporte_servicios(
    citas=citas_actuales,
    fecha_objetivo=fecha_pasado_manana,
)

# ============================================================
# PESTAÑAS HOY / MAÑANA
# ============================================================

tab_hoy, tab_manana, tab_pasado_manana = st.tabs(
    [
        f"📅 Hoy {fecha_hoy:%d/%m}",
        f"➡️ Mañana {fecha_manana:%d/%m}",
        f"⏩ Pasado mañana {fecha_pasado_manana:%d/%m}",
    ]
)


# ============================================================
# HOY
# ============================================================

with tab_hoy:

    st.markdown(
        (
            f"#### Citas programadas para "
            f"{fecha_hoy:%d/%m/%Y}"
        )
    )

    mostrar_reporte_operativo(
        reporte_hoy
    )

    if not reporte_hoy.empty:

        total_hoy_reporte = int(
            reporte_hoy.loc[
                reporte_hoy[
                    "sede"
                ].eq(
                    "Total general"
                ),
                "Total general",
            ]
            .iloc[0]
        )

        st.caption(
            (
                f"Total reporte: "
                f"{total_hoy_reporte:,} citas"
            )
        )

# ============================================================
# MAÑANA
# ============================================================

with tab_manana:

    st.markdown(
        (
            f"#### Citas programadas para "
            f"{fecha_manana:%d/%m/%Y}"
        )
    )

    mostrar_reporte_operativo(
        reporte_manana
    )

    if not reporte_manana.empty:

        total_manana_reporte = int(
            reporte_manana.loc[
                reporte_manana[
                    "sede"
                ].eq(
                    "Total general"
                ),
                "Total general",
            ]
            .iloc[0]
        )

        st.caption(
            (
                f"Total reporte: "
                f"{total_manana_reporte:,} citas"
            )
        )

# ============================================================
# PASADO MAÑANA
# ============================================================

with tab_pasado_manana:

    st.markdown(
        (
            f"#### Citas programadas para "
            f"{fecha_pasado_manana:%d/%m/%Y}"
        )
    )

    mostrar_reporte_operativo(
        reporte_pasado_manana
    )

    if not reporte_pasado_manana.empty:

        total_pasado_manana = int(
            reporte_pasado_manana.loc[
                reporte_pasado_manana[
                    "sede"
                ].eq(
                    "Total general"
                ),
                "Total general",
            ]
            .iloc[0]
        )

        st.caption(
            (
                f"Total reporte: "
                f"{total_pasado_manana:,} citas"
            )
        )





# ============================================================
# DISTRIBUCIÓN POR CANAL Y PERSONA QUE AGENDA
# ============================================================

st.divider()

st.subheader(
    "Origen operativo de las citas"
)

st.caption(
    (
        "Distribución de las citas según quién las agenda, "
        "agrupando Call Center y Taller."
    )
)

reporte_canal_hoy = construir_reporte_canal_agenda(
    citas=citas_actuales,
    fecha_objetivo=fecha_hoy,
)

reporte_canal_manana = construir_reporte_canal_agenda(
    citas=citas_actuales,
    fecha_objetivo=fecha_manana,
)

reporte_canal_pasado_manana = construir_reporte_canal_agenda(
    citas=citas_actuales,
    fecha_objetivo=fecha_pasado_manana,
)


(
    tab_canal_hoy,
    tab_canal_manana,
    tab_canal_pasado_manana,
) = st.tabs(
    [
        f"📅 Hoy {fecha_hoy:%d/%m}",
        f"➡️ Mañana {fecha_manana:%d/%m}",
        f"⏩ Pasado mañana {fecha_pasado_manana:%d/%m}",
    ]
)


with tab_canal_hoy:

    st.markdown(
        f"#### Generación de citas para {fecha_hoy:%d/%m/%Y}"
    )

    if reporte_canal_hoy.empty:

        st.info(
            "No existen citas para esta fecha."
        )

    else:

        mostrar_reporte_canal_agenda(
            reporte_canal_hoy
        )


with tab_canal_manana:

    st.markdown(
        f"#### Generación de citas para {fecha_manana:%d/%m/%Y}"
    )

    if reporte_canal_manana.empty:

        st.info(
            "No existen citas para esta fecha."
        )

    else:

        mostrar_reporte_canal_agenda(
            reporte_canal_manana
        )


with tab_canal_pasado_manana:

    st.markdown(
        (
            f"#### Generación de citas para "
            f"{fecha_pasado_manana:%d/%m/%Y}"
        )
    )

    if reporte_canal_pasado_manana.empty:

        st.info(
            "No existen citas para esta fecha."
        )

    else:

        mostrar_reporte_canal_agenda(
            reporte_canal_pasado_manana
        )



# ============================================================
# CONTROL DE CLASIFICACIONES
# ============================================================

with st.expander(
    "⚠️ Revisar clasificaciones pendientes"
):

    (
        asesores_indeterminados,
        servicios_indeterminados,
    ) = construir_control_indeterminados(
        citas_actuales
    )

    control_1, control_2 = (
        st.columns(2)
    )

    with control_1:

        st.markdown(
            "**Asesores sin sede definida**"
        )

        if asesores_indeterminados.empty:

            st.success(
                "Todos los asesores están clasificados."
            )

        else:

            st.dataframe(
                asesores_indeterminados,
                use_container_width=True,
                hide_index=True,
            )

    with control_2:

        st.markdown(
            "**Servicios sin clasificación**"
        )

        if servicios_indeterminados.empty:

            st.success(
                "Todos los servicios están clasificados."
            )

        else:

            st.dataframe(
                servicios_indeterminados,
                use_container_width=True,
                hide_index=True,
            )

