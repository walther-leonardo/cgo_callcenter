from __future__ import annotations

import argparse
from datetime import (
    date,
    datetime,
    time,
    timedelta,
)
from database import get_connection

import pandas as pd
import plotly.graph_objects as go

from metricas_cloudtalk import (
    construir_timeline,
    segundos_a_texto,
)


# ============================================================
# CONFIGURACIÓN VISUAL
# ============================================================

HORA_INICIO = time(
    7,
    0,
)

HORA_FIN = time(
    19,
    0,
)


COLORES = {
    (
        "ENTRANTE",
        "ATENDIDA",
    ):
        "#2E7D32",

    (
        "SALIENTE",
        "CONECTADA",
    ):
        "#1565C0",

    (
        "SALIENTE",
        "NO_CONECTADA",
    ):
        "#F59E0B",

    (
        "ENTRANTE",
        "PERDIDA",
    ):
        "#D32F2F",
}

COLOR_CITA_AGENDADA = "#7C3AED"

ETIQUETAS = {
    (
        "ENTRANTE",
        "ATENDIDA",
    ):
        "Entrante atendida",

    (
        "SALIENTE",
        "CONECTADA",
    ):
        "Saliente conectada",

    (
        "SALIENTE",
        "NO_CONECTADA",
    ):
        "Saliente no conectada",

    (
        "ENTRANTE",
        "PERDIDA",
    ):
        "Entrante perdida",
}


ORDEN_AGENTES = [
    "Rocío",
    "Brenda",
]


# ============================================================
# HELPERS
# ============================================================

def nombre_corto_agente(
    agente,
) -> str:
    """
    Convierte el nombre completo de CloudTalk
    en un nombre operativo corto.
    """

    if pd.isna(
        agente
    ):
        return "Sin agente"

    texto = str(
        agente
    ).strip()

    texto_lower = texto.lower()

    if "roci" in texto_lower:
        return "Rocío"

    if "brenda" in texto_lower:
        return "Brenda"

    return texto


def preparar_timeline(
    timeline: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepara las llamadas para representación visual.
    """

    if timeline.empty:
        return timeline.copy()

    df = timeline.copy()

    df[
        "inicio"
    ] = pd.to_datetime(
        df[
            "inicio"
        ],
        errors="coerce",
    )

    df[
        "fin"
    ] = pd.to_datetime(
        df[
            "fin"
        ],
        errors="coerce",
    )

    df = df.loc[
        df[
            "inicio"
        ].notna()
    ].copy()

    df[
        "agente_dashboard"
    ] = (
        df[
            "agente"
        ]
        .apply(
            nombre_corto_agente
        )
    )

    df[
        "duracion_texto"
    ] = (
        df[
            "duracion_segundos"
        ]
        .apply(
            segundos_a_texto
        )
    )

    return df


def construir_hover(
    fila,
) -> str:
    """
    Construye el tooltip de una llamada.
    """

    contacto = (
        fila.contacto
        if pd.notna(
            fila.contacto
        )
        else ""
    )

    telefono = (
        fila.telefono_contacto
        if pd.notna(
            fila.telefono_contacto
        )
        else ""
    )

    clave_categoria = (
        fila.direccion,
        fila.estado,
    )

    categoria = ETIQUETAS.get(
        clave_categoria,
        fila.tipo_llamada,
    )

    return (
        f"<b>{categoria}</b>"
        f"<br>Agente: {fila.agente_dashboard}"
        f"<br>Inicio: {fila.inicio:%H:%M:%S}"
        f"<br>Duración: {fila.duracion_texto}"
        f"<br>Contacto: {contacto}"
        f"<br>Teléfono: {telefono}"
    )


def construir_hover_cita(
    fila,
) -> str:
    """
    Tooltip de una cita detectada por primera vez.
    """

    nombre = (
        fila.nombre
        if pd.notna(
            fila.nombre
        )
        else ""
    )

    celular = (
        fila.celular
        if pd.notna(
            fila.celular
        )
        else ""
    )

    placa = (
        fila.placa
        if pd.notna(
            fila.placa
        )
        else ""
    )

    modelo = (
        fila.modelo
        if pd.notna(
            fila.modelo
        )
        else ""
    )

    origen = (
        fila.origen_cita
        if pd.notna(
            fila.origen_cita
        )
        else ""
    )

    return (
        "<b>Cita agendada</b>"
        f"<br>Agente: {fila.agente_dashboard}"
        f"<br>Detectada: {fila.fecha_detectada:%H:%M:%S}"
        f"<br>ID cita: {fila.id_cita}"
        f"<br>Cliente: {nombre}"
        f"<br>Celular: {celular}"
        f"<br>Placa: {placa}"
        f"<br>Modelo: {modelo}"
        f"<br>Origen: {origen}"
    )


def cargar_citas_agendadas_timeline(
    fecha_objetivo: date,
) -> pd.DataFrame:
    """
    Obtiene las citas cuya primera aparición en los snapshots
    ocurrió durante la fecha objetivo.

    La posición temporal del rombo usa fecha_detectada:
    el primer corte en que la cita apareció en nuestra base.

    No utiliza fecha_creacion de ClearMechanic como hora del
    evento porque ese campo puede contener horas posteriores
    al momento real del snapshot.
    """

    with get_connection() as conn:

        query = """
        WITH primeras_apariciones AS (
            SELECT
                cs.id_cita,
                cs.persona_agenda,
                cs.origen_cita,
                cs.nombre,
                cs.celular,
                cs.placa,
                cs.modelo,

                s.fecha_hora_corte AS fecha_detectada,

                ROW_NUMBER() OVER (
                    PARTITION BY cs.id_cita
                    ORDER BY
                        s.fecha_hora_corte,
                        s.snapshot_id
                ) AS orden_aparicion

            FROM citas_snapshot cs

            INNER JOIN snapshots s
                ON s.snapshot_id = cs.snapshot_id
        )

        SELECT
            id_cita,
            persona_agenda,
            origen_cita,
            nombre,
            celular,
            placa,
            modelo,
            fecha_detectada

        FROM primeras_apariciones

        WHERE orden_aparicion = 1
          AND date(fecha_detectada) = ?

        ORDER BY fecha_detectada
        """

        df = pd.read_sql_query(
            query,
            conn,
            params=[
                fecha_objetivo.isoformat()
            ],
        )

    if df.empty:
        return df

    df[
        "fecha_detectada"
    ] = pd.to_datetime(
        df[
            "fecha_detectada"
        ],
        errors="coerce",
    )

    df = df.loc[
        df[
            "fecha_detectada"
        ].notna()
    ].copy()

    df[
        "agente_dashboard"
    ] = (
        df[
            "persona_agenda"
        ]
        .apply(
            nombre_corto_agente
        )
    )

    df = df.loc[
        df[
            "agente_dashboard"
        ].isin(
            ORDEN_AGENTES
        )
    ].copy()

    return (
        df.sort_values(
            "fecha_detectada"
        )
        .reset_index(
            drop=True
        )
    )


def formatear_duracion_kpi(
    segundos: int,
) -> str:
    """
    Formatea segundos para tarjetas KPI.
    """

    segundos = int(
        segundos
    )

    horas, resto = divmod(
        segundos,
        3600,
    )

    minutos, segundos = divmod(
        resto,
        60,
    )

    if horas > 0:

        return (
            f"{horas}h "
            f"{minutos:02d}m"
        )

    if minutos > 0:

        return (
            f"{minutos}m "
            f"{segundos:02d}s"
        )

    return (
        f"{segundos}s"
    )


def formatear_delta_duracion(
    segundos: int,
) -> str:
    """
    Formatea diferencia de duración contra ayer.
    """

    segundos = int(
        segundos
    )

    signo = (
        "+"
        if segundos >= 0
        else "-"
    )

    return (
        signo
        +
        formatear_duracion_kpi(
            abs(
                segundos
            )
        )
    )


def construir_kpis_cloudtalk(
    fecha_objetivo: date,
    hora_corte: time,
) -> pd.DataFrame:
    """
    Construye KPI CloudTalk por agente comparando:

        fecha_objetivo
        vs
        día anterior

    usando exactamente la misma hora de corte.

    Devuelve una fila por agente.
    """

    hora_inicio = HORA_INICIO

    if hora_corte < HORA_INICIO:
        hora_corte = HORA_INICIO

    elif hora_corte > HORA_FIN:
        hora_corte = HORA_FIN

    fecha_anterior = (
        fecha_objetivo
        - timedelta(
            days=1
        )
    )

    fechas = [
        fecha_objetivo.isoformat(),
        fecha_anterior.isoformat(),
    ]

    hora_inicio_texto = (
        hora_inicio.strftime(
            "%H:%M:%S"
        )
    )

    hora_corte_texto = (
        hora_corte.strftime(
            "%H:%M:%S"
        )
    )

    with get_connection() as conn:

        df = pd.read_sql_query(
            """
            SELECT
                fecha,
                hora,
                direccion,
                estado,
                duracion_segundos,
                agente
            FROM cloudtalk_llamadas
            WHERE fecha IN (?, ?)
              AND hora >= ?
              AND hora <= ?
            """,
            conn,
            params=[
                fechas[0],
                fechas[1],
                hora_inicio_texto,
                hora_corte_texto,
            ],
        )

    columnas_salida = [
        "agente",
        "entrantes_hoy",
        "entrantes_ayer",
        "salientes_hoy",
        "salientes_ayer",
        "conectadas_hoy",
        "conectadas_ayer",
        "duracion_hoy",
        "duracion_ayer",
    ]

    if df.empty:

        filas = []

        for agente in ORDEN_AGENTES:

            filas.append(
                {
                    "agente": agente,
                    "entrantes_hoy": 0,
                    "entrantes_ayer": 0,
                    "salientes_hoy": 0,
                    "salientes_ayer": 0,
                    "conectadas_hoy": 0,
                    "conectadas_ayer": 0,
                    "duracion_hoy": 0,
                    "duracion_ayer": 0,
                }
            )

        return pd.DataFrame(
            filas,
            columns=columnas_salida,
        )

    df[
        "duracion_segundos"
    ] = (
        pd.to_numeric(
            df[
                "duracion_segundos"
            ],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    df[
        "agente_dashboard"
    ] = (
        df[
            "agente"
        ]
        .apply(
            nombre_corto_agente
        )
    )

    df = df.loc[
        df[
            "agente_dashboard"
        ].isin(
            ORDEN_AGENTES
        )
    ].copy()

    filas = []

    for agente in ORDEN_AGENTES:

        fila = {
            "agente": agente,
        }

        for etiqueta, fecha in [
            (
                "hoy",
                fecha_objetivo,
            ),
            (
                "ayer",
                fecha_anterior,
            ),
        ]:

            vista = df.loc[
                (
                    df[
                        "agente_dashboard"
                    ].eq(
                        agente
                    )
                )
                &
                (
                    df[
                        "fecha"
                    ].eq(
                        fecha.isoformat()
                    )
                )
            ].copy()

            entrantes = (
                (
                    vista[
                        "direccion"
                    ].eq(
                        "ENTRANTE"
                    )
                )
                &
                (
                    vista[
                        "estado"
                    ].eq(
                        "ATENDIDA"
                    )
                )
            )

            salientes = (
                vista[
                    "direccion"
                ].eq(
                    "SALIENTE"
                )
            )

            conectadas = (
                (
                    vista[
                        "direccion"
                    ].eq(
                        "SALIENTE"
                    )
                )
                &
                (
                    vista[
                        "estado"
                    ].eq(
                        "CONECTADA"
                    )
                )
            )

            llamadas_conectadas = (
                entrantes
                |
                conectadas
            )

            fila[
                f"entrantes_{etiqueta}"
            ] = int(
                entrantes.sum()
            )

            fila[
                f"salientes_{etiqueta}"
            ] = int(
                salientes.sum()
            )

            fila[
                f"conectadas_{etiqueta}"
            ] = int(
                conectadas.sum()
            )

            fila[
                f"duracion_{etiqueta}"
            ] = int(
                vista.loc[
                    llamadas_conectadas,
                    "duracion_segundos",
                ].sum()
            )

        filas.append(
            fila
        )

    return pd.DataFrame(
        filas,
        columns=columnas_salida,
    )



# ============================================================
# TIMELINE
# ============================================================

def construir_timeline_cloudtalk(
    fecha_objetivo: date,
) -> go.Figure:
    """
    Construye el timeline operativo de CloudTalk
    entre 07:00 y 19:00.

    Visualización:
    - Barra base horizontal por agente.
    - Llamadas conectadas/atendidas como bloques.
    - Llamadas no conectadas/perdidas como líneas verticales.
    - Citas agendadas como rombos sobre la barra.
    """

    timeline = construir_timeline(
        fecha_objetivo
    )

    df = preparar_timeline(
        timeline
    )

    df_citas = (
        cargar_citas_agendadas_timeline(
            fecha_objetivo
        )
    )

    inicio_eje = datetime.combine(
        fecha_objetivo,
        HORA_INICIO,
    )

    fin_eje = datetime.combine(
        fecha_objetivo,
        HORA_FIN,
    )

    figura = go.Figure()

    # ========================================================
    # ANCLA TEMPORAL INVISIBLE
    # ========================================================

    # Plotly necesita al menos una traza real con datetime
    # para mantener el eje X como eje temporal.
    figura.add_trace(
        go.Scatter(
            x=[
                inicio_eje,
                fin_eje,
            ],
            y=[
                0,
                0,
            ],
            mode="markers",
            marker=dict(
                size=1,
                opacity=0,
            ),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # ========================================================
    # AGENTES
    # ========================================================

    agentes_llamadas = (
        df[
            "agente_dashboard"
        ]
        .dropna()
        .unique()
        .tolist()
        if not df.empty
        else []
    )

    agentes_citas = (
        df_citas[
            "agente_dashboard"
        ]
        .dropna()
        .unique()
        .tolist()
        if not df_citas.empty
        else []
    )

    agentes_presentes = list(
        dict.fromkeys(
            agentes_llamadas
            + agentes_citas
        )
    )

    orden_agentes = [
        agente
        for agente in ORDEN_AGENTES
        if agente in agentes_presentes
    ]

    otros_agentes = [
        agente
        for agente in agentes_presentes
        if agente not in orden_agentes
    ]

    orden_agentes.extend(
        otros_agentes
    )

    if not orden_agentes:
        orden_agentes = (
            ORDEN_AGENTES.copy()
        )

    y_map = {
        agente: indice
        for indice, agente
        in enumerate(
            orden_agentes
        )
    }

    alto_barra = 0.18
    desfase_marcador = 0.24

    # ========================================================
    # BARRAS BASE
    # ========================================================

    for agente in orden_agentes:

        y = y_map[
            agente
        ]

        figura.add_shape(
            type="rect",
            x0=inicio_eje,
            x1=fin_eje,
            y0=y - alto_barra,
            y1=y + alto_barra,
            line=dict(
                color="rgba(90, 90, 90, 0.45)",
                width=1,
            ),
            fillcolor="rgba(180, 180, 180, 0.14)",
            layer="below",
        )

    # ========================================================
    # LEYENDA
    # ========================================================

    categorias_leyenda = [
        (
            "ENTRANTE",
            "ATENDIDA",
        ),
        (
            "SALIENTE",
            "CONECTADA",
        ),
        (
            "SALIENTE",
            "NO_CONECTADA",
        ),
        (
            "ENTRANTE",
            "PERDIDA",
        ),
    ]

    if not df.empty:
        for categoria in categorias_leyenda:

            existe = (
                (
                    df[
                        "direccion"
                    ].eq(
                        categoria[0]
                    )
                )
                &
                (
                    df[
                        "estado"
                    ].eq(
                        categoria[1]
                    )
                )
            ).any()

            if not existe:
                continue

            figura.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="lines",
                    name=ETIQUETAS.get(
                        categoria,
                        str(categoria),
                    ),
                    line=dict(
                        color=COLORES.get(
                            categoria,
                            "#7F8C8D",
                        ),
                        width=8,
                    ),
                    hoverinfo="skip",
                )
            )

    if not df_citas.empty:
        figura.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name="Cita agendada",
                marker=dict(
                    symbol="diamond",
                    size=10,
                    color=COLOR_CITA_AGENDADA,
                    line=dict(
                        color="white",
                        width=1,
                    ),
                ),
                hoverinfo="skip",
            )
        )

    # ========================================================
    # MENSAJE SI NO HAY NADA
    # ========================================================

    if df.empty and df_citas.empty:

        figura.add_annotation(
            x=(
                inicio_eje
                + (
                    fin_eje
                    - inicio_eje
                ) / 2
            ),
            y=0,
            text=(
                "Sin actividad registrada "
                "para esta fecha"
            ),
            showarrow=False,
            font=dict(
                size=16,
                color="#6B7280",
            ),
        )

    # ========================================================
    # LLAMADAS
    # ========================================================

    if not df.empty:

        for fila in df.itertuples():

            categoria = (
                fila.direccion,
                fila.estado,
            )

            color = COLORES.get(
                categoria,
                "#7F8C8D",
            )

            hover = construir_hover(
                fila
            )

            duracion_segundos = int(
                fila.duracion_segundos
                or 0
            )

            # ------------------------------------------------
            # ENTRANTE PERDIDA:
            # se dibuja en ambas barras.
            # ------------------------------------------------
            if categoria == (
                "ENTRANTE",
                "PERDIDA",
            ):
                agentes_objetivo = [
                    agente
                    for agente in orden_agentes
                    if agente in y_map
                ]
                hover = (
                    hover
                    + "<br><i>Visualización: "
                    "marcada en ambas barras</i>"
                )
            else:
                agentes_objetivo = [
                    fila.agente_dashboard
                ]

            for agente in agentes_objetivo:

                if agente not in y_map:
                    continue

                y = y_map[
                    agente
                ]

                # ============================================
                # LLAMADAS CON DURACIÓN
                # ============================================
                if duracion_segundos > 0:

                    x0 = fila.inicio
                    x1 = fila.fin

                    duracion_visual_minima = 20

                    if (
                        x1 - x0
                    ).total_seconds() < (
                        duracion_visual_minima
                    ):
                        x1 = (
                            x0
                            + timedelta(
                                seconds=(
                                    duracion_visual_minima
                                )
                            )
                        )

                    figura.add_shape(
                        type="rect",
                        x0=x0,
                        x1=x1,
                        y0=y - alto_barra,
                        y1=y + alto_barra,
                        line=dict(
                            color=color,
                            width=0,
                        ),
                        fillcolor=color,
                        opacity=0.95,
                        layer="above",
                    )

                    punto_hover = (
                        x0
                        + (
                            x1
                            - x0
                        ) / 2
                    )

                    figura.add_trace(
                        go.Scatter(
                            x=[
                                punto_hover
                            ],
                            y=[
                                y
                            ],
                            mode="markers",
                            marker=dict(
                                size=14,
                                color=color,
                                opacity=0.01,
                            ),
                            text=[
                                hover
                            ],
                            hovertemplate=(
                                "%{text}"
                                "<extra></extra>"
                            ),
                            showlegend=False,
                        )
                    )

                # ============================================
                # EVENTOS SIN DURACIÓN
                # ============================================
                else:

                    figura.add_shape(
                        type="line",
                        x0=fila.inicio,
                        x1=fila.inicio,
                        y0=y - alto_barra,
                        y1=y + alto_barra,
                        line=dict(
                            color=color,
                            width=3,
                        ),
                        layer="above",
                    )

                    figura.add_trace(
                        go.Scatter(
                            x=[
                                fila.inicio
                            ],
                            y=[
                                y
                            ],
                            mode="markers",
                            marker=dict(
                                size=12,
                                color=color,
                                opacity=0.01,
                            ),
                            text=[
                                hover
                            ],
                            hovertemplate=(
                                "%{text}"
                                "<extra></extra>"
                            ),
                            showlegend=False,
                        )
                    )

    # ========================================================
    # CITAS AGENDADAS
    # ========================================================

    if not df_citas.empty:

        for fila in df_citas.itertuples():

            agente = (
                fila.agente_dashboard
            )

            if agente not in y_map:
                continue

            y = (
                y_map[agente]
                - desfase_marcador
            )

            hover_cita = (
                construir_hover_cita(
                    fila
                )
            )

            figura.add_trace(
                go.Scatter(
                    x=[
                        fila.fecha_detectada
                    ],
                    y=[
                        y
                    ],
                    mode="markers",
                    marker=dict(
                        symbol="diamond",
                        size=11,
                        color=COLOR_CITA_AGENDADA,
                        line=dict(
                            color="white",
                            width=1,
                        ),
                    ),
                    text=[
                        hover_cita
                    ],
                    hovertemplate=(
                        "%{text}"
                        "<extra></extra>"
                    ),
                    showlegend=False,
                )
            )

    # ========================================================
    # EJE X
    # ========================================================

    figura.update_xaxes(
        type="date",
        range=[
            inicio_eje,
            fin_eje,
        ],
        tickformat="%H:%M",
        dtick=60 * 60 * 1000,
        title=None,
        showgrid=True,
        gridcolor="rgba(0,0,0,0.08)",
        zeroline=False,
    )

    # ========================================================
    # EJE Y
    # ========================================================

    figura.update_yaxes(
        tickmode="array",
        tickvals=[
            y_map[
                agente
            ]
            for agente
            in orden_agentes
        ],
        ticktext=orden_agentes,
        range=[
            len(
                orden_agentes
            )
            - 0.45,
            -0.55,
        ],
        title=None,
        showgrid=False,
        zeroline=False,
    )

    # ========================================================
    # LAYOUT
    # ========================================================

    figura.update_layout(
        title=dict(
            text=(
                "Actividad de llamadas "
                "07:00 – 19:00"
            ),
            font=dict(
                size=18,
            ),
        ),
        height=350,
        margin=dict(
            l=70,
            r=25,
            t=70,
            b=45,
        ),
        hovermode="closest",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=True,
    )

    return figura

# ============================================================
# CLI
# ============================================================

def leer_argumentos():
    """
    Permite probar el gráfico con una fecha concreta.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Timeline operativo de CloudTalk."
        )
    )

    parser.add_argument(
        "--fecha",
        type=str,
        default=None,
        help=(
            "Fecha en formato YYYY-MM-DD. "
            "Default: hoy."
        ),
    )

    return parser.parse_args()


def main() -> None:

    argumentos = leer_argumentos()

    if argumentos.fecha:

        fecha_objetivo = (
            datetime.strptime(
                argumentos.fecha,
                "%Y-%m-%d",
            )
            .date()
        )

    else:

        fecha_objetivo = (
            datetime.now().date()
        )

    print()
    print("=" * 72)
    print("CGO CALL CENTER — TIMELINE CLOUDTALK")
    print("=" * 72)

    print(
        f"Fecha: {fecha_objetivo}"
    )
    

    figura = construir_timeline_cloudtalk(
        fecha_objetivo
    )

    print(
        "✅ Timeline generado."
    )

    print(
        "Abriendo vista previa..."
    )

    figura.show()


if __name__ == "__main__":
    main()