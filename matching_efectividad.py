from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd


# ============================================================
# CONFIGURACIÓN DE NIVELES
# ============================================================

NIVEL_1 = 1
NIVEL_2 = 2
NIVEL_3 = 3


def clasificar_nivel(
    diferencia_dias: int,
) -> int | None:
    """
    Clasifica la relación temporal entre cita y presencia.

    diferencia_dias =
        fecha_visita - fecha_cita

    Nivel 1:
        mismo día.

    Nivel 2:
        1 día antes
        o hasta 3 días después.

    Nivel 3:
        entre 4 y 2 días antes
        o entre 4 y 7 días después.
    """

    if diferencia_dias == 0:
        return NIVEL_1

    if (
        diferencia_dias == -1
        or 1 <= diferencia_dias <= 3
    ):
        return NIVEL_2

    if (
        -4 <= diferencia_dias <= -2
        or 4 <= diferencia_dias <= 7
    ):
        return NIVEL_3

    return None


# ============================================================
# HELPERS DE NEGOCIO
# ============================================================

def es_preventivo(
    valor,
) -> bool:
    if pd.isna(valor):
        return False

    return (
        "PREVENTIVO"
        in str(valor).upper()
    )


def normalizar_fecha(
    valor,
) -> date | None:
    fecha = pd.to_datetime(
        valor,
        errors="coerce",
    )

    if pd.isna(fecha):
        return None

    return fecha.date()


def numero_cita(
    valor,
) -> int:
    numero = pd.to_numeric(
        valor,
        errors="coerce",
    )

    if pd.isna(numero):
        return 10**12

    return int(numero)


# ============================================================
# CANDIDATOS
# ============================================================

def construir_candidatos(
    citas: pd.DataFrame,
    presencias: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye todas las combinaciones temporalmente válidas
    entre cita y presencia de la misma placa.
    """

    columnas = [
        "id_cita",
        "appointment_number",
        "placa_normalizada",
        "fecha_cita",
        "fecha_hora_cita_lima",
        "fecha_creacion_lima",
        "agente",
        "motivos",
        "presencia_id",
        "fecha_visita",
        "fuente",
        "diferencia_dias",
        "distancia",
        "nivel",
    ]

    if citas.empty or presencias.empty:
        return pd.DataFrame(
            columns=columnas
        )

    registros = []

    presencias_por_placa = {
        placa: grupo.copy()
        for placa, grupo
        in presencias.groupby(
            "placa_normalizada"
        )
    }

    for cita in citas.itertuples(
        index=False
    ):

        placa = (
            cita.placa_normalizada
        )

        fecha_cita = normalizar_fecha(
            cita.fecha_cita
        )

        if (
            not placa
            or fecha_cita is None
            or placa
            not in presencias_por_placa
        ):
            continue

        grupo_presencias = (
            presencias_por_placa[
                placa
            ]
        )

        for presencia in (
            grupo_presencias
            .itertuples(
                index=False
            )
        ):

            fecha_visita = (
                normalizar_fecha(
                    presencia.fecha_visita
                )
            )

            if fecha_visita is None:
                continue

            diferencia = (
                fecha_visita
                -
                fecha_cita
            ).days

            nivel = clasificar_nivel(
                diferencia
            )

            if nivel is None:
                continue

            registros.append(
                {
                    "id_cita":
                        cita.id_cita,

                    "appointment_number":
                        cita.appointment_number,

                    "placa_normalizada":
                        placa,

                    "fecha_cita":
                        fecha_cita,

                    "fecha_hora_cita_lima":
                        getattr(
                            cita,
                            "fecha_hora_cita_lima",
                            pd.Timestamp(
                                fecha_cita
                            ),
                        ),

                    "fecha_creacion_lima":
                        cita.fecha_creacion_lima,

                    "agente":
                        cita.agente,

                    "motivos":
                        cita.motivos,

                    "presencia_id":
                        presencia.presencia_id,

                    "fecha_visita":
                        fecha_visita,

                    "fuente":
                        presencia.fuente,

                    "diferencia_dias":
                        diferencia,

                    "distancia":
                        abs(
                            diferencia
                        ),

                    "nivel":
                        nivel,
                }
            )

    return pd.DataFrame(
        registros,
        columns=columnas,
    )


# ============================================================
# COSTO LEXICOGRÁFICO
# ============================================================

Costo = tuple[
    int,
    int,
    int,
    int,
    int,
]


def costo_candidato(
    nivel: int,
    distancia: int,
    prioridad_negocio: int,
    desempate: int,
) -> Costo:
    """
    El flujo ya maximiza primero la cantidad de matches.

    Luego el costo minimiza, en este orden:

    1. cantidad no-Nivel-1;
    2. cantidad Nivel-3;
    3. distancia total;
    4. prioridad de negocio;
    5. desempate determinístico.

    Con flujo total fijo:

    minimizar no-N1
        = maximizar Nivel 1.

    Luego minimizar Nivel 3
        = maximizar Nivel 2.
    """

    penaliza_no_nivel_1 = (
        0
        if nivel == NIVEL_1
        else 1
    )

    penaliza_nivel_3 = (
        1
        if nivel == NIVEL_3
        else 0
    )

    return (
        penaliza_no_nivel_1,
        penaliza_nivel_3,
        distancia,
        prioridad_negocio,
        desempate,
    )


def sumar_costos(
    a: Costo,
    b: Costo,
) -> Costo:
    return tuple(
        x + y
        for x, y
        in zip(a, b)
    )


def negar_costo(
    costo: Costo,
) -> Costo:
    return tuple(
        -x
        for x in costo
    )


COSTO_CERO: Costo = (
    0,
    0,
    0,
    0,
    0,
)


# ============================================================
# GRAFO DE FLUJO
# ============================================================

@dataclass
class Arista:
    destino: int
    reversa: int
    capacidad: int
    costo: Costo
    metadata: dict[str, Any] | None = None


def agregar_arista(
    grafo: list[list[Arista]],
    origen: int,
    destino: int,
    capacidad: int,
    costo: Costo,
    metadata: dict[str, Any] | None = None,
) -> None:

    directa = Arista(
        destino=destino,
        reversa=len(
            grafo[
                destino
            ]
        ),
        capacidad=capacidad,
        costo=costo,
        metadata=metadata,
    )

    reversa = Arista(
        destino=origen,
        reversa=len(
            grafo[
                origen
            ]
        ),
        capacidad=0,
        costo=negar_costo(
            costo
        ),
        metadata=None,
    )

    grafo[
        origen
    ].append(
        directa
    )

    grafo[
        destino
    ].append(
        reversa
    )


# ============================================================
# PRIORIDADES DE NEGOCIO
# ============================================================

def agregar_prioridades_negocio(
    candidatos: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aplica desempates de negocio únicamente después de que
    nivel y distancia temporal ya fueron determinados.

    REGLAS
    ------

    Para candidatas de:
        - misma presencia
        - misma agente
        - mismo nivel
        - misma distancia

    prioridad:

    1. Si son Nivel 1 y corresponden al mismo día:
       gana la cita con HORA PROGRAMADA MÁS TARDE.

       Interpretación:
       una cita posterior durante el mismo día normalmente
       representa una reprogramación del cliente.

    2. Si todavía existe empate:
       si exactamente una cita es Preventivo,
       gana Preventivo.

    3. Si todavía existe empate:
       gana la cita creada primero.

    4. Finalmente:
       appointmentNumber menor.

    Entre agentes diferentes NO se asigna prioridad comercial.
    Esos casos pueden quedar marcados para revisión manual.
    """

    resultado = candidatos.copy()

    resultado[
        "prioridad_negocio"
    ] = 0

    resultado[
        "desempate"
    ] = 0

    columnas_grupo = [
        "presencia_id",
        "agente",
        "nivel",
        "distancia",
    ]

    for _, grupo in resultado.groupby(
        columnas_grupo,
        dropna=False,
    ):

        if len(grupo) <= 1:
            continue

        indices = grupo.index.tolist()

        trabajo = grupo.copy()

        # ====================================================
        # 1. NIVEL 1:
        #    PRIORIZAR HORA PROGRAMADA MÁS TARDE
        # ====================================================

        nivel = int(
            trabajo[
                "nivel"
            ].iloc[0]
        )

        if nivel == NIVEL_1:

            horas = pd.to_datetime(
                trabajo[
                    "fecha_hora_cita_lima"
                ],
                errors="coerce",
                utc=True,
            )

            if horas.notna().any():

                hora_maxima = (
                    horas.max()
                )

                mask_hora_ganadora = (
                    horas.eq(
                        hora_maxima
                    )
                )

                # Si una sola cita tiene la hora más tardía,
                # el desempate queda resuelto aquí.
                if int(
                    mask_hora_ganadora.sum()
                ) == 1:

                    indice_ganador = (
                        trabajo.loc[
                            mask_hora_ganadora
                        ].index[0]
                    )

                    resultado.loc[
                        indices,
                        "prioridad_negocio",
                    ] = 1

                    resultado.loc[
                        indice_ganador,
                        "prioridad_negocio",
                    ] = 0

                    continue

                # Si varias tienen exactamente la misma hora,
                # continuamos únicamente con ellas.
                trabajo = trabajo.loc[
                    mask_hora_ganadora
                ].copy()

        # ====================================================
        # 2. PREVENTIVO ÚNICO
        # ====================================================

        preventivos = trabajo[
            "motivos"
        ].apply(
            es_preventivo
        )

        if int(
            preventivos.sum()
        ) == 1:

            indice_ganador = (
                trabajo.loc[
                    preventivos
                ].index[0]
            )

            resultado.loc[
                indices,
                "prioridad_negocio",
            ] = 1

            resultado.loc[
                indice_ganador,
                "prioridad_negocio",
            ] = 0

            continue

        # ====================================================
        # 3. CITA CREADA PRIMERO
        # ====================================================

        fechas_creacion = pd.to_datetime(
            trabajo[
                "fecha_creacion_lima"
            ],
            errors="coerce",
            utc=True,
        )

        orden = pd.DataFrame(
            {
                "fecha_creacion":
                    fechas_creacion,

                "appointment":
                    trabajo[
                        "appointment_number"
                    ].apply(
                        numero_cita
                    ),
            },
            index=trabajo.index,
        ).sort_values(
            [
                "fecha_creacion",
                "appointment",
            ],
            ascending=[
                True,
                True,
            ],
            na_position="last",
            kind="stable",
        )

        ranking = {
            indice: posicion
            for posicion, indice
            in enumerate(
                orden.index
            )
        }

        # Las filas que ya quedaron fuera de la selección
        # reciben una penalización superior.
        penalizacion_base = (
            len(
                orden
            )
            +
            1
        )

        resultado.loc[
            indices,
            "prioridad_negocio",
        ] = penalizacion_base

        for indice, posicion in (
            ranking.items()
        ):

            resultado.loc[
                indice,
                "prioridad_negocio",
            ] = posicion

    # ========================================================
    # DESEMPATE GLOBAL DETERMINÍSTICO
    # ========================================================

    orden_global = sorted(
        resultado[
            "id_cita"
        ].unique(),
        key=lambda valor:
            str(valor),
    )

    ranking_global = {
        valor: posicion
        for posicion, valor
        in enumerate(
            orden_global
        )
    }

    resultado[
        "desempate"
    ] = resultado[
        "id_cita"
    ].map(
        ranking_global
    )

    return resultado


# ============================================================
# MATCHING DE UNA PLACA
# ============================================================

def resolver_placa(
    candidatos_placa: pd.DataFrame,
) -> pd.DataFrame:
    """
    Resuelve matching máximo + costo mínimo para una placa.

    La red residual permite reasignar asociaciones previas.

    Ejemplo:
        F -> T
        aparece G más cercana a T
        aparece U

    El algoritmo puede terminar:
        F -> T
        G -> U

    sin utilizar T ni U dos veces.
    """

    if candidatos_placa.empty:
        return pd.DataFrame()

    candidatos = (
        agregar_prioridades_negocio(
            candidatos_placa
        )
    )

    citas = list(
        candidatos[
            "id_cita"
        ].drop_duplicates()
    )

    presencias = list(
        candidatos[
            "presencia_id"
        ].drop_duplicates()
    )

    # --------------------------------------------------------
    # NODOS
    # --------------------------------------------------------

    source = 0

    nodo_cita = {
        id_cita: posicion + 1
        for posicion, id_cita
        in enumerate(
            citas
        )
    }

    offset_presencias = (
        1
        +
        len(
            citas
        )
    )

    nodo_presencia = {
        presencia_id:
            offset_presencias
            +
            posicion

        for posicion, presencia_id
        in enumerate(
            presencias
        )
    }

    sink = (
        offset_presencias
        +
        len(
            presencias
        )
    )

    grafo: list[
        list[Arista]
    ] = [
        []
        for _ in range(
            sink + 1
        )
    ]

    # --------------------------------------------------------
    # SOURCE -> CITAS
    # --------------------------------------------------------

    for id_cita in citas:

        agregar_arista(
            grafo=grafo,
            origen=source,
            destino=nodo_cita[
                id_cita
            ],
            capacidad=1,
            costo=COSTO_CERO,
        )

    # --------------------------------------------------------
    # PRESENCIAS -> SINK
    # --------------------------------------------------------

    for presencia_id in presencias:

        agregar_arista(
            grafo=grafo,
            origen=nodo_presencia[
                presencia_id
            ],
            destino=sink,
            capacidad=1,
            costo=COSTO_CERO,
        )

    # --------------------------------------------------------
    # CITAS -> PRESENCIAS
    # --------------------------------------------------------

    for indice, fila in (
        candidatos.iterrows()
    ):

        costo = costo_candidato(
            nivel=int(
                fila[
                    "nivel"
                ]
            ),
            distancia=int(
                fila[
                    "distancia"
                ]
            ),
            prioridad_negocio=int(
                fila[
                    "prioridad_negocio"
                ]
            ),
            desempate=int(
                fila[
                    "desempate"
                ]
            ),
        )

        agregar_arista(
            grafo=grafo,
            origen=nodo_cita[
                fila[
                    "id_cita"
                ]
            ],
            destino=nodo_presencia[
                fila[
                    "presencia_id"
                ]
            ],
            capacidad=1,
            costo=costo,
            metadata={
                "tipo":
                    "MATCH",

                "indice_candidato":
                    indice,
            },
        )

    # ========================================================
    # FLUJO MÁXIMO DE COSTO MÍNIMO
    #
    # Bellman-Ford permite costos residuales negativos.
    # Los grupos por placa son pequeños, por lo que aquí
    # priorizamos claridad sobre sofisticación.
    # ========================================================

    while True:

        distancias: list[
            Costo | None
        ] = [
            None
            for _ in grafo
        ]

        anterior_nodo = [
            -1
            for _ in grafo
        ]

        anterior_arista = [
            -1
            for _ in grafo
        ]

        distancias[
            source
        ] = COSTO_CERO

        # Bellman-Ford
        for _ in range(
            len(grafo) - 1
        ):

            cambio = False

            for origen in range(
                len(grafo)
            ):

                if (
                    distancias[
                        origen
                    ]
                    is None
                ):
                    continue

                for posicion, arista in enumerate(
                    grafo[
                        origen
                    ]
                ):

                    if (
                        arista.capacidad
                        <= 0
                    ):
                        continue

                    nuevo_costo = (
                        sumar_costos(
                            distancias[
                                origen
                            ],
                            arista.costo,
                        )
                    )

                    destino = (
                        arista.destino
                    )

                    if (
                        distancias[
                            destino
                        ]
                        is None
                        or nuevo_costo
                        <
                        distancias[
                            destino
                        ]
                    ):

                        distancias[
                            destino
                        ] = (
                            nuevo_costo
                        )

                        anterior_nodo[
                            destino
                        ] = origen

                        anterior_arista[
                            destino
                        ] = posicion

                        cambio = True

            if not cambio:
                break

        # No existe más camino aumentante.
        if (
            distancias[
                sink
            ]
            is None
        ):
            break

        # ----------------------------------------------------
        # AUMENTAR UNA UNIDAD DE FLUJO
        # ----------------------------------------------------

        actual = sink

        while actual != source:

            origen = (
                anterior_nodo[
                    actual
                ]
            )

            posicion = (
                anterior_arista[
                    actual
                ]
            )

            arista = (
                grafo[
                    origen
                ][
                    posicion
                ]
            )

            arista.capacidad -= 1

            grafo[
                actual
            ][
                arista.reversa
            ].capacidad += 1

            actual = origen

    # ========================================================
    # EXTRAER MATCHES FINALES
    # ========================================================

    indices_seleccionados = []

    for id_cita in citas:

        nodo = nodo_cita[
            id_cita
        ]

        for arista in grafo[
            nodo
        ]:

            if (
                arista.metadata
                and arista.metadata.get(
                    "tipo"
                )
                ==
                "MATCH"
                and arista.capacidad == 0
            ):

                indices_seleccionados.append(
                    arista.metadata[
                        "indice_candidato"
                    ]
                )

    if not indices_seleccionados:
        return candidatos.iloc[
            0:0
        ].copy()

    return (
        candidatos.loc[
            indices_seleccionados
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )


# ============================================================
# DETECCIÓN DE AMBIGÜEDADES ENTRE PERSONAS
# ============================================================

def marcar_revision_manual(
    matches: pd.DataFrame,
    candidatos: pd.DataFrame,
) -> pd.DataFrame:
    """
    Marca únicamente conflictos reales entre personas.

    Un match requiere revisión manual cuando existe otra cita:

    - para la misma presencia;
    - con el mismo nivel;
    - con la misma distancia temporal;
    - de otra persona;
    - y esa cita alternativa quedó SIN match.

    Si ambas citas ya consiguieron presencias distintas,
    no existe una disputa real por efectividad y no se
    solicita revisión manual.
    """

    resultado = matches.copy()

    resultado[
        "requiere_revision_manual"
    ] = False

    if resultado.empty:
        return resultado

    ids_matcheados = set(
        resultado[
            "id_cita"
        ]
    )

    for indice, match in resultado.iterrows():

        alternativas = candidatos.loc[
            candidatos[
                "presencia_id"
            ].eq(
                match[
                    "presencia_id"
                ]
            )
            &
            candidatos[
                "nivel"
            ].eq(
                match[
                    "nivel"
                ]
            )
            &
            candidatos[
                "distancia"
            ].eq(
                match[
                    "distancia"
                ]
            )
            &
            candidatos[
                "id_cita"
            ].ne(
                match[
                    "id_cita"
                ]
            )
            &
            candidatos[
                "agente"
            ].ne(
                match[
                    "agente"
                ]
            )
            &
            ~candidatos[
                "id_cita"
            ].isin(
                ids_matcheados
            )
        ]

        if not alternativas.empty:

            resultado.loc[
                indice,
                "requiere_revision_manual",
            ] = True

    return resultado

# ============================================================
# MOTOR COMPLETO
# ============================================================

def calcular_matching_efectividad(
    citas: pd.DataFrame,
    presencias: pd.DataFrame,
) -> pd.DataFrame:
    """
    Ejecuta el matching global por placa.

    Una presencia se utiliza como máximo una vez.
    Una cita se utiliza como máximo una vez.

    Los matches pueden redistribuirse cuando aparecen nuevas
    citas o nuevas presencias.
    """

    candidatos = construir_candidatos(
        citas=citas,
        presencias=presencias,
    )

    if candidatos.empty:

        return pd.DataFrame(
            columns=[
                "id_cita",
                "appointment_number",
                "placa_normalizada",
                "agente_original",
                "persona_creditada",
                "fecha_cita",
                "presencia_id",
                "fecha_visita",
                "diferencia_dias",
                "nivel_efectividad",
                "estado_efectividad",
                "fuente",
                "criterio_matching",
                "requiere_revision_manual",
            ]
        )

    resultados = []

    for _, grupo in candidatos.groupby(
        "placa_normalizada",
        sort=False,
    ):

        matches = resolver_placa(
            grupo
        )

        if not matches.empty:
            resultados.append(
                matches
            )

    if not resultados:
        return pd.DataFrame()

    matches = pd.concat(
        resultados,
        ignore_index=True,
    )

    matches = marcar_revision_manual(
        matches=matches,
        candidatos=candidatos,
    )

    matches[
        "agente_original"
    ] = matches[
        "agente"
    ]

    matches[
        "persona_creditada"
    ] = matches[
        "agente"
    ]

    matches[
        "nivel_efectividad"
    ] = matches[
        "nivel"
    ].astype(int)

    matches[
        "estado_efectividad"
    ] = (
        "EFECTIVA_NIVEL_"
        +
        matches[
            "nivel_efectividad"
        ].astype(str)
    )

    matches[
        "criterio_matching"
    ] = matches.apply(
        lambda fila:
            (
                f"NIVEL_{fila['nivel_efectividad']}"
                f"_DISTANCIA_{fila['distancia']}"
            ),
        axis=1,
    )

    columnas = [
        "id_cita",
        "appointment_number",
        "placa_normalizada",
        "agente_original",
        "persona_creditada",
        "fecha_cita",
        "presencia_id",
        "fecha_visita",
        "diferencia_dias",
        "nivel_efectividad",
        "estado_efectividad",
        "fuente",
        "criterio_matching",
        "requiere_revision_manual",
    ]

    return (
        matches[
            columnas
        ]
        .sort_values(
            [
                "fecha_cita",
                "placa_normalizada",
                "appointment_number",
            ],
            kind="stable",
        )
        .reset_index(
            drop=True
        )
    )

