from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import argparse

from database import get_connection


# ============================================================
# CONFIGURACIÓN
# ============================================================

HORA_INICIO_OPERACION = time(
    7,
    0,
)

HORA_FIN_OPERACION = time(
    19,
    0,
)


# ============================================================
# HELPERS
# ============================================================

def segundos_a_texto(
    segundos: int | float,
) -> str:
    """
    Convierte segundos en una representación compacta.

    Ejemplos:
        538  -> 8m 58s
        3738 -> 1h 2m
    """

    segundos = int(
        segundos or 0
    )

    horas, resto = divmod(
        segundos,
        3600,
    )

    minutos, segundos = divmod(
        resto,
        60,
    )

    if horas:

        return (
            f"{horas}h "
            f"{minutos}m"
        )

    if minutos:

        return (
            f"{minutos}m "
            f"{segundos}s"
        )

    return (
        f"{segundos}s"
    )


def obtener_hora_corte(
    ahora: datetime | None = None,
) -> time:
    """
    Obtiene la hora comparable del día.

    Antes de las 07:00:
        07:00

    Entre 07:00 y 19:00:
        hora actual

    Después de las 19:00:
        19:00
    """

    ahora = (
        ahora
        or datetime.now()
    )

    hora_actual = ahora.time()

    if hora_actual < HORA_INICIO_OPERACION:
        return HORA_INICIO_OPERACION

    if hora_actual > HORA_FIN_OPERACION:
        return HORA_FIN_OPERACION

    return hora_actual.replace(
        microsecond=0
    )


# ============================================================
# CONSULTA BASE
# ============================================================

def cargar_llamadas(
    fecha: date,
    hora_hasta: time | None = None,
) -> pd.DataFrame:
    """
    Obtiene llamadas de una fecha determinada.

    Si hora_hasta está definida, considera únicamente
    llamadas entre 07:00 y dicha hora.
    """

    parametros = [
        fecha.isoformat(),
        HORA_INICIO_OPERACION.strftime(
            "%H:%M:%S"
        ),
    ]

    sql = """
        SELECT
            id_evento,
            fecha,
            hora,
            fecha_hora,
            tipo_llamada,
            direccion,
            estado,
            duracion,
            duracion_segundos,
            contacto,
            telefono_contacto,
            agente,
            canal_agente,
            telefono_agente
        FROM cloudtalk_llamadas
        WHERE fecha = ?
          AND hora >= ?
    """

    if hora_hasta is not None:

        sql += """
          AND hora <= ?
        """

        parametros.append(
            hora_hasta.strftime(
                "%H:%M:%S"
            )
        )

    sql += """
        ORDER BY fecha_hora
    """

    with get_connection() as conn:

        df = pd.read_sql_query(
            sql,
            conn,
            params=parametros,
        )

    # --------------------------------------------------------
    # NORMALIZACIÓN DE TIPOS
    # --------------------------------------------------------

    if not df.empty:

        df[
            "duracion_segundos"
        ] = (
            pd.to_numeric(
                df[
                    "duracion_segundos"
                ],
                errors="coerce",
            )
            .fillna(
                0
            )
            .astype(
                int
            )
        )

    return df


# ============================================================
# KPI POR AGENTE
# ============================================================

def construir_resumen_agentes(
    llamadas: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye los KPI operativos por agente.
    """

    columnas = [
        "agente",
        "entrantes_atendidas",
        "salientes_realizadas",
        "salientes_conectadas",
        "salientes_no_conectadas",
        "duracion_segundos",
    ]

    if llamadas.empty:

        return pd.DataFrame(
            columns=columnas
        )

    df = llamadas.copy()

    agentes = (
        df[
            "agente"
        ]
        .dropna()
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    resultados = []

    for agente in agentes:

        vista = df.loc[
            df[
                "agente"
            ].eq(
                agente
            )
        ]

        entrantes_atendidas = int(
            (
                vista[
                    "direccion"
                ].eq(
                    "ENTRANTE"
                )
                &
                vista[
                    "estado"
                ].eq(
                    "ATENDIDA"
                )
            )
            .sum()
        )

        salientes_realizadas = int(
            vista[
                "direccion"
            ]
            .eq(
                "SALIENTE"
            )
            .sum()
        )

        salientes_conectadas = int(
            (
                vista[
                    "direccion"
                ].eq(
                    "SALIENTE"
                )
                &
                vista[
                    "estado"
                ].eq(
                    "CONECTADA"
                )
            )
            .sum()
        )

        salientes_no_conectadas = int(
            (
                vista[
                    "direccion"
                ].eq(
                    "SALIENTE"
                )
                &
                vista[
                    "estado"
                ].eq(
                    "NO_CONECTADA"
                )
            )
            .sum()
        )

        # Inbound atendida + outbound conectada.
        conectadas = vista.loc[
            (
                vista[
                    "direccion"
                ].eq(
                    "ENTRANTE"
                )
                &
                vista[
                    "estado"
                ].eq(
                    "ATENDIDA"
                )
            )
            |
            (
                vista[
                    "direccion"
                ].eq(
                    "SALIENTE"
                )
                &
                vista[
                    "estado"
                ].eq(
                    "CONECTADA"
                )
            )
        ]

        duracion_segundos = int(
            conectadas[
                "duracion_segundos"
            ]
            .sum()
        )

        resultados.append(
            {
                "agente":
                    agente,

                "entrantes_atendidas":
                    entrantes_atendidas,

                "salientes_realizadas":
                    salientes_realizadas,

                "salientes_conectadas":
                    salientes_conectadas,

                "salientes_no_conectadas":
                    salientes_no_conectadas,

                "duracion_segundos":
                    duracion_segundos,
            }
        )

    return pd.DataFrame(
        resultados,
        columns=columnas,
    )


# ============================================================
# HOY VS AYER
# ============================================================

def construir_comparativo_hoy_ayer(
    ahora: datetime | None = None,
) -> pd.DataFrame:
    """
    Compara hoy contra ayer utilizando exactamente
    el mismo intervalo horario.
    """

    ahora = (
        ahora
        or datetime.now()
    )

    fecha_hoy = ahora.date()

    fecha_ayer = (
        fecha_hoy
        - timedelta(
            days=1
        )
    )

    hora_corte = obtener_hora_corte(
        ahora
    )

    llamadas_hoy = cargar_llamadas(
        fecha=fecha_hoy,
        hora_hasta=hora_corte,
    )

    llamadas_ayer = cargar_llamadas(
        fecha=fecha_ayer,
        hora_hasta=hora_corte,
    )

    hoy = construir_resumen_agentes(
        llamadas_hoy
    )

    ayer = construir_resumen_agentes(
        llamadas_ayer
    )

    metricas = [
        "entrantes_atendidas",
        "salientes_realizadas",
        "salientes_conectadas",
        "salientes_no_conectadas",
        "duracion_segundos",
    ]

    agentes = sorted(
        set(
            hoy.get(
                "agente",
                pd.Series(
                    dtype=str
                ),
            )
            .dropna()
            .tolist()
        )
        |
        set(
            ayer.get(
                "agente",
                pd.Series(
                    dtype=str
                ),
            )
            .dropna()
            .tolist()
        )
    )

    resultados = []

    for agente in agentes:

        hoy_agente = hoy.loc[
            hoy[
                "agente"
            ].eq(
                agente
            )
        ]

        ayer_agente = ayer.loc[
            ayer[
                "agente"
            ].eq(
                agente
            )
        ]

        registro = {
            "agente":
                agente,

            "hora_corte":
                hora_corte.strftime(
                    "%H:%M:%S"
                ),
        }

        for metrica in metricas:

            valor_hoy = (
                int(
                    hoy_agente[
                        metrica
                    ].iloc[0]
                )
                if not hoy_agente.empty
                else 0
            )

            valor_ayer = (
                int(
                    ayer_agente[
                        metrica
                    ].iloc[0]
                )
                if not ayer_agente.empty
                else 0
            )

            registro[
                f"{metrica}_hoy"
            ] = valor_hoy

            registro[
                f"{metrica}_ayer"
            ] = valor_ayer

            registro[
                f"{metrica}_delta"
            ] = (
                valor_hoy
                - valor_ayer
            )

        resultados.append(
            registro
        )

    return pd.DataFrame(
        resultados
    )


# ============================================================
# TIMELINE
# ============================================================

def construir_timeline(
    fecha: date,
) -> pd.DataFrame:
    """
    Devuelve una fila por evento preparada para construir
    el timeline operativo entre 07:00 y 19:00.
    """

    llamadas = cargar_llamadas(
        fecha=fecha,
        hora_hasta=HORA_FIN_OPERACION,
    )

    if llamadas.empty:
        return llamadas

    df = llamadas.copy()

    df[
        "inicio"
    ] = pd.to_datetime(
        df[
            "fecha_hora"
        ],
        errors="coerce",
    )

    df[
        "fin"
    ] = (
        df[
            "inicio"
        ]
        +
        pd.to_timedelta(
            df[
                "duracion_segundos"
            ],
            unit="s",
        )
    )

    # Para eventos de duración 0 dejamos inicio=fin.
    # En el gráfico serán marcadores, no barras.
    df[
        "es_evento_puntual"
    ] = (
        df[
            "duracion_segundos"
        ]
        .eq(
            0
        )
    )

    return df


# ============================================================
# TERMINAL
# ============================================================

def mostrar_comparativo(
    comparativo: pd.DataFrame,
) -> None:

    print()
    print("=" * 84)
    print("CLOUDTALK — HOY VS AYER A LA MISMA HORA")
    print("=" * 84)

    if comparativo.empty:

        print(
            "No existen datos suficientes para comparar."
        )

        return

    for fila in comparativo.itertuples(
        index=False
    ):

        print()
        print(
            fila.agente
        )

        print(
            f"Corte comparable: "
            f"{fila.hora_corte}"
        )

        print(
            "  Entrantes atendidas : "
            f"{fila.entrantes_atendidas_hoy:>4} "
            f"| ayer "
            f"{fila.entrantes_atendidas_ayer:>4} "
            f"| Δ "
            f"{fila.entrantes_atendidas_delta:+}"
        )

        print(
            "  Salientes realizadas: "
            f"{fila.salientes_realizadas_hoy:>4} "
            f"| ayer "
            f"{fila.salientes_realizadas_ayer:>4} "
            f"| Δ "
            f"{fila.salientes_realizadas_delta:+}"
        )

        print(
            "  Conectadas           : "
            f"{fila.salientes_conectadas_hoy:>4} "
            f"| ayer "
            f"{fila.salientes_conectadas_ayer:>4} "
            f"| Δ "
            f"{fila.salientes_conectadas_delta:+}"
        )

        print(
            "  No conectadas        : "
            f"{fila.salientes_no_conectadas_hoy:>4} "
            f"| ayer "
            f"{fila.salientes_no_conectadas_ayer:>4} "
            f"| Δ "
            f"{fila.salientes_no_conectadas_delta:+}"
        )

        print(
            "  Duración llamadas    : "
            f"{segundos_a_texto(fila.duracion_segundos_hoy):>8} "
            f"| ayer "
            f"{segundos_a_texto(fila.duracion_segundos_ayer):>8}"
        )



def leer_argumentos():
    """
    Permite consultar una fecha específica.

    Sin argumentos:
        usa hoy.

    Ejemplo:
        py metricas_cloudtalk.py --fecha 2026-10-01
    """

    parser = argparse.ArgumentParser(
        description=(
            "Métricas operativas de CloudTalk."
        )
    )

    parser.add_argument(
        "--fecha",
        type=str,
        default=None,
        help=(
            "Fecha objetivo en formato YYYY-MM-DD. "
            "Si se omite, utiliza hoy."
        ),
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main(
    fecha_objetivo: date | None = None,
) -> None:

    if fecha_objetivo is None:

        comparativo = (
            construir_comparativo_hoy_ayer()
        )

        mostrar_comparativo(
            comparativo
        )

        fecha_timeline = (
            datetime.now().date()
        )

    else:

        fecha_timeline = fecha_objetivo

        llamadas = cargar_llamadas(
            fecha=fecha_objetivo,
            hora_hasta=HORA_FIN_OPERACION,
        )

        resumen = construir_resumen_agentes(
            llamadas
        )

        print()
        print("=" * 84)
        print(
            f"CLOUDTALK — RESUMEN "
            f"{fecha_objetivo.isoformat()}"
        )
        print("=" * 84)

        if resumen.empty:

            print(
                "No existen llamadas para esa fecha."
            )

        else:

            for fila in resumen.itertuples(
                index=False
            ):

                print()
                print(
                    fila.agente
                )

                print(
                    "  Entrantes atendidas : "
                    f"{fila.entrantes_atendidas}"
                )

                print(
                    "  Salientes realizadas: "
                    f"{fila.salientes_realizadas}"
                )

                print(
                    "  Conectadas           : "
                    f"{fila.salientes_conectadas}"
                )

                print(
                    "  No conectadas        : "
                    f"{fila.salientes_no_conectadas}"
                )

                print(
                    "  Duración llamadas    : "
                    f"{segundos_a_texto(
                        fila.duracion_segundos
                    )}"
                )

    timeline = construir_timeline(
        fecha_timeline
    )

    print()
    print("=" * 84)
    print("TIMELINE")
    print("=" * 84)

    print(
        f"Fecha: {fecha_timeline.isoformat()}"
    )

    print(
        f"Eventos entre 07:00 y 19:00: "
        f"{len(timeline)}"
    )

    if not timeline.empty:

        print(
            f"Llamadas con duración: "
            f"{int(
                (~timeline['es_evento_puntual']).sum()
            )}"
        )

        print(
            f"Eventos de duración cero: "
            f"{int(
                timeline['es_evento_puntual'].sum()
            )}"
        )

if __name__ == "__main__":

    argumentos = leer_argumentos()

    fecha_objetivo = None

    if argumentos.fecha:

        fecha_objetivo = datetime.strptime(
            argumentos.fecha,
            "%Y-%m-%d",
        ).date()

    main(
        fecha_objetivo=fecha_objetivo
    )