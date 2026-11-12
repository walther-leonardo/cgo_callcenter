from __future__ import annotations

import argparse
import os
import re

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from databricks import sql
from dotenv import load_dotenv


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ZONA_LIMA = ZoneInfo("America/Lima")
ZONA_UTC = ZoneInfo("UTC")

AGENTES_CALLCENTER = {
    "Rocio Miranda Ausejo",
    "Brenda Montalvan Cornejo",
}

TABLA_CITAS = (
    "db_silver.ro_pa_cmos_citas"
)

TABLA_COTIZACIONES = (
    "catalog_lhcl_prod_gp."
    "gp_adv_app_cotizador.cotizacionser_pa"
)

TABLA_ORDENES = (
    "hive_metastore.db_gold.ordenes_unegocio_s4"
)


# ============================================================
# ARGUMENTOS
# ============================================================

def leer_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnóstico reconstruible de efectividad "
            "de citas desde Databricks."
        )
    )

    parser.add_argument(
        "--desde",
        required=True,
        help=(
            "Fecha inicial inclusiva YYYY-MM-DD."
        ),
    )

    parser.add_argument(
        "--hasta",
        required=True,
        help=(
            "Fecha final exclusiva YYYY-MM-DD."
        ),
    )

    parser.add_argument(
        "--explorar-dias",
        type=int,
        default=7,
        help=(
            "Ventana máxima temporal usada únicamente "
            "para estudiar posibles coincidencias Nivel 2. "
            "No define todavía la tolerancia oficial."
        ),
    )

    argumentos = parser.parse_args()

    if argumentos.explorar_dias < 1:
        parser.error(
            "--explorar-dias debe ser mayor o igual a 1."
        )

    return argumentos

def validar_fechas(
    desde_texto: str,
    hasta_texto: str,
) -> tuple[date, date]:
    try:
        desde = date.fromisoformat(
            desde_texto
        )

        hasta = date.fromisoformat(
            hasta_texto
        )

    except ValueError as exc:
        raise ValueError(
            "Las fechas deben usar formato YYYY-MM-DD."
        ) from exc

    if hasta <= desde:
        raise ValueError(
            "--hasta debe ser posterior a --desde."
        )

    return desde, hasta


# ============================================================
# DATABRICKS
# ============================================================

def cargar_configuracion() -> tuple[str, str]:
    load_dotenv(
        PROJECT_ROOT / ".env"
    )

    hostname = os.getenv(
        "DATABRICKS_SERVER_HOSTNAME"
    )

    http_path = os.getenv(
        "DATABRICKS_HTTP_PATH"
    )

    if not hostname or not http_path:
        raise ValueError(
            "Faltan DATABRICKS_SERVER_HOSTNAME "
            "o DATABRICKS_HTTP_PATH en .env."
        )

    return hostname, http_path


def consultar_databricks(
    consulta: str,
    parametros: dict,
) -> pd.DataFrame:
    hostname, http_path = (
        cargar_configuracion()
    )

    with sql.connect(
        server_hostname=hostname,
        http_path=http_path,
        auth_type="databricks-oauth",
    ) as conexion:

        with conexion.cursor() as cursor:

            cursor.execute(
                consulta,
                parameters=parametros,
            )

            columnas = [
                columna[0]
                for columna
                in cursor.description
            ]

            registros = []

            while True:

                bloque = cursor.fetchmany(
                    10_000
                )

                if not bloque:
                    break

                registros.extend(
                    tuple(fila)
                    for fila in bloque
                )

    return pd.DataFrame.from_records(
        registros,
        columns=columnas,
    )


# ============================================================
# FECHAS
# ============================================================

def limites_utc_desde_lima(
    desde: date,
    hasta: date,
) -> tuple[str, str]:
    """
    Convierte medianoche Lima a UTC.

    Esto permite consultar startDate respetando el día
    calendario de Lima aunque startDate esté almacenado UTC.
    """

    desde_lima = datetime.combine(
        desde,
        time.min,
        tzinfo=ZONA_LIMA,
    )

    hasta_lima = datetime.combine(
        hasta,
        time.min,
        tzinfo=ZONA_LIMA,
    )

    desde_utc = (
        desde_lima
        .astimezone(
            ZONA_UTC
        )
        .replace(
            tzinfo=None
        )
    )

    hasta_utc = (
        hasta_lima
        .astimezone(
            ZONA_UTC
        )
        .replace(
            tzinfo=None
        )
    )

    return (
        desde_utc.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        hasta_utc.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    )


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalizar_placa(
    valor,
) -> str:
    if pd.isna(valor):
        return ""

    texto = str(
        valor
    ).strip().upper()

    return re.sub(
        r"[^A-Z0-9]",
        "",
        texto,
    )


def convertir_booleano(
    valor,
) -> bool:
    if isinstance(
        valor,
        bool,
    ):
        return valor

    if pd.isna(valor):
        return False

    texto = str(
        valor
    ).strip().lower()

    return texto in {
        "true",
        "1",
        "yes",
        "si",
        "sí",
    }


def agregar_textos_unicos(
    serie: pd.Series,
) -> str:
    valores = sorted(
        {
            str(valor).strip()
            for valor in serie
            if pd.notna(valor)
            and str(valor).strip()
        }
    )

    return " | ".join(
        valores
    )


# ============================================================
# TABLA A — CITAS
# ============================================================

def obtener_citas(
    desde: date,
    hasta: date,
) -> pd.DataFrame:

    desde_utc, hasta_utc = (
        limites_utc_desde_lima(
            desde=desde,
            hasta=hasta,
        )
    )

    consulta = f"""
        SELECT
            Key_merge,
            appointmentNumber,
            workshop_id,
            licensePlate,
            mobile,
            userWhoSchedule,
            appointmentOrigin,
            creationDate,
            startDate,
            isDeleted,
            description,
            detalle_description

        FROM {TABLA_CITAS}

        WHERE startDate >= CAST(
            :desde_utc AS TIMESTAMP
        )
          AND startDate < CAST(
            :hasta_utc AS TIMESTAMP
        )
    """

    return consultar_databricks(
        consulta,
        {
            "desde_utc":
                desde_utc,
            "hasta_utc":
                hasta_utc,
        },
    )


def consolidar_citas(
    citas_raw: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:

    if citas_raw.empty:
        return (
            pd.DataFrame(),
            {
                "filas_raw": 0,
                "citas_unicas": 0,
                "eliminadas": 0,
                "elegibles": 0,
                "sin_placa": 0,
            },
        )

    citas = citas_raw.copy()

    if citas[
        "Key_merge"
    ].isna().any():

        cantidad = int(
            citas[
                "Key_merge"
            ].isna().sum()
        )

        raise ValueError(
            f"Tabla A contiene {cantidad:,} "
            "filas sin Key_merge."
        )

    # --------------------------------------------------------
    # VALIDAR CONSISTENCIA DENTRO DE Key_merge
    # --------------------------------------------------------

    campos_criticos = [
        "appointmentNumber",
        "workshop_id",
        "licensePlate",
        "startDate",
        "userWhoSchedule",
        "isDeleted",
    ]

    inconsistentes = []

    agrupado = citas.groupby(
        "Key_merge",
        dropna=False,
    )

    for campo in campos_criticos:

        cantidades = agrupado[
            campo
        ].nunique(
            dropna=False
        )

        ids = cantidades[
            cantidades > 1
        ].index.tolist()

        for id_cita in ids:
            inconsistentes.append(
                (
                    id_cita,
                    campo,
                )
            )

    if inconsistentes:

        muestra = inconsistentes[
            :10
        ]

        raise ValueError(
            "Se encontraron Key_merge con "
            "campos críticos inconsistentes. "
            f"Muestra: {muestra}"
        )

    # --------------------------------------------------------
    # CONSOLIDAR UNA FILA POR CITA
    # --------------------------------------------------------

    citas = (
        citas
        .groupby(
            "Key_merge",
            as_index=False,
            dropna=False,
        )
        .agg(
            appointmentNumber=(
                "appointmentNumber",
                "first",
            ),
            workshop_id=(
                "workshop_id",
                "first",
            ),
            licensePlate=(
                "licensePlate",
                "first",
            ),
            mobile=(
                "mobile",
                "first",
            ),
            userWhoSchedule=(
                "userWhoSchedule",
                "first",
            ),
            appointmentOrigin=(
                "appointmentOrigin",
                "first",
            ),
            creationDate=(
                "creationDate",
                "first",
            ),
            startDate=(
                "startDate",
                "first",
            ),
            isDeleted=(
                "isDeleted",
                "first",
            ),
            motivos=(
                "description",
                agregar_textos_unicos,
            ),
            detalle_motivos=(
                "detalle_description",
                agregar_textos_unicos,
            ),
        )
    )

    citas = citas.rename(
        columns={
            "Key_merge":
                "id_cita",
            "appointmentNumber":
                "appointment_number",
            "licensePlate":
                "placa",
            "mobile":
                "telefono",
            "userWhoSchedule":
                "agente",
            "appointmentOrigin":
                "origen",
            "creationDate":
                "fecha_creacion",
        }
    )

    # --------------------------------------------------------
    # ELIMINADAS
    # --------------------------------------------------------

    citas[
        "is_deleted"
    ] = citas[
        "isDeleted"
    ].apply(
        convertir_booleano
    )

    # --------------------------------------------------------
    # NORMALIZAR PLACA
    # --------------------------------------------------------

    citas[
        "placa_normalizada"
    ] = citas[
        "placa"
    ].apply(
        normalizar_placa
    )

    # --------------------------------------------------------
    # FECHA/HORA DE CITA
    # startDate viene en UTC.
    # --------------------------------------------------------

    fecha_hora_utc = pd.to_datetime(
        citas[
            "startDate"
        ],
        errors="coerce",
        utc=True,
    )

    citas[
        "fecha_hora_cita_lima"
    ] = (
        fecha_hora_utc
        .dt.tz_convert(
            "America/Lima"
        )
    )

    citas[
        "fecha_cita"
    ] = (
        citas[
            "fecha_hora_cita_lima"
        ]
        .dt.date
    )

    # --------------------------------------------------------
    # FECHA/HORA DE CREACIÓN
    # creationDate también viene en UTC.
    #
    # La conservamos en hora Lima para estudiar las citas
    # solapadas y luego definir un desempate auditable.
    # --------------------------------------------------------

    fecha_creacion_utc = pd.to_datetime(
        citas[
            "fecha_creacion"
        ],
        errors="coerce",
        utc=True,
    )

    citas[
        "fecha_creacion_lima"
    ] = (
        fecha_creacion_utc
        .dt.tz_convert(
            "America/Lima"
        )
    )

    # --------------------------------------------------------
    # RESUMEN
    # --------------------------------------------------------

    total_unicas = len(
        citas
    )

    eliminadas = int(
        citas[
            "is_deleted"
        ].sum()
    )

    elegibles = citas.loc[
        ~citas[
            "is_deleted"
        ]
    ].copy()

    sin_placa = int(
        elegibles[
            "placa_normalizada"
        ].eq(
            ""
        ).sum()
    )

    resumen = {
        "filas_raw":
            len(citas_raw),
        "citas_unicas":
            total_unicas,
        "eliminadas":
            eliminadas,
        "elegibles":
            len(elegibles),
        "sin_placa":
            sin_placa,
    }

    return (
        elegibles,
        resumen,
    )

# ============================================================
# TABLA B — COTIZACIONES
# ============================================================

def obtener_cotizaciones(
    desde: date,
    hasta: date,
) -> pd.DataFrame:

    consulta = f"""
        SELECT
            Placa,
            NumeroDocumento,
            FechaDocumento

        FROM {TABLA_COTIZACIONES}

        WHERE `categoría1` = '358'
          AND FechaDocumento >= :desde
          AND FechaDocumento < :hasta
    """

    return consultar_databricks(
        consulta,
        {
            "desde":
                desde.isoformat(),
            "hasta":
                hasta.isoformat(),
        },
    )


def consolidar_cotizaciones(
    cotizaciones_raw: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:

    if cotizaciones_raw.empty:

        return (
            pd.DataFrame(
                columns=[
                    "placa_normalizada",
                    "fecha_visita",
                    "cotizaciones",
                    "tiene_cotizacion",
                ]
            ),
            {
                "filas_raw": 0,
                "documentos": 0,
                "presencias": 0,
                "sin_placa": 0,
            },
        )

    df = cotizaciones_raw.copy()

    df[
        "placa_normalizada"
    ] = df[
        "Placa"
    ].apply(
        normalizar_placa
    )

    df[
        "fecha_visita"
    ] = pd.to_datetime(
        df[
            "FechaDocumento"
        ],
        errors="coerce",
    ).dt.date

    sin_placa = int(
        df[
            "placa_normalizada"
        ].eq(
            ""
        ).sum()
    )

    documentos = int(
        df[
            "NumeroDocumento"
        ].nunique(
            dropna=True
        )
    )

    validos = df.loc[
        df[
            "placa_normalizada"
        ].ne(
            ""
        )
        &
        df[
            "fecha_visita"
        ].notna()
    ].copy()

    presencia = (
        validos
        .groupby(
            [
                "placa_normalizada",
                "fecha_visita",
            ],
            as_index=False,
        )
        .agg(
            cotizaciones=(
                "NumeroDocumento",
                lambda serie:
                    serie.nunique(
                        dropna=True
                    ),
            ),
        )
    )

    presencia[
        "tiene_cotizacion"
    ] = True

    resumen = {
        "filas_raw":
            len(df),
        "documentos":
            documentos,
        "presencias":
            len(presencia),
        "sin_placa":
            sin_placa,
    }

    return (
        presencia,
        resumen,
    )


# ============================================================
# TABLA C — ÓRDENES
# ============================================================

def obtener_ordenes(
    desde: date,
    hasta: date,
) -> pd.DataFrame:

    consulta = f"""
        SELECT
            ID_OPERACION,
            FECHA_CONTABILIZACION,
            PLACA

        FROM {TABLA_ORDENES}

        WHERE ORG_VENTAS = 'PA22'
          AND SECTOR = '13'
          AND FECHA_CONTABILIZACION >= :desde
          AND FECHA_CONTABILIZACION < :hasta
          AND COALESCE(
                UPPER(
                    TRIM(
                        STATUS_CANCELACION_ORDEN
                    )
                ),
                ''
          ) <> 'X'
    """

    return consultar_databricks(
        consulta,
        {
            "desde":
                desde.isoformat(),
            "hasta":
                hasta.isoformat(),
        },
    )


def consolidar_ordenes(
    ordenes_raw: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:

    if ordenes_raw.empty:

        return (
            pd.DataFrame(
                columns=[
                    "placa_normalizada",
                    "fecha_visita",
                    "ordenes",
                    "tiene_orden",
                ]
            ),
            {
                "filas_raw": 0,
                "ordenes": 0,
                "presencias": 0,
                "sin_placa": 0,
            },
        )

    df = ordenes_raw.copy()

    df[
        "placa_normalizada"
    ] = df[
        "PLACA"
    ].apply(
        normalizar_placa
    )

    df[
        "fecha_visita"
    ] = pd.to_datetime(
        df[
            "FECHA_CONTABILIZACION"
        ],
        errors="coerce",
    ).dt.date

    sin_placa = int(
        df[
            "placa_normalizada"
        ].eq(
            ""
        ).sum()
    )

    ordenes_distintas = int(
        df[
            "ID_OPERACION"
        ].nunique(
            dropna=True
        )
    )

    validos = df.loc[
        df[
            "placa_normalizada"
        ].ne(
            ""
        )
        &
        df[
            "fecha_visita"
        ].notna()
    ].copy()

    presencia = (
        validos
        .groupby(
            [
                "placa_normalizada",
                "fecha_visita",
            ],
            as_index=False,
        )
        .agg(
            ordenes=(
                "ID_OPERACION",
                lambda serie:
                    serie.nunique(
                        dropna=True
                    ),
            ),
        )
    )

    presencia[
        "tiene_orden"
    ] = True

    resumen = {
        "filas_raw":
            len(df),
        "ordenes":
            ordenes_distintas,
        "presencias":
            len(presencia),
        "sin_placa":
            sin_placa,
    }

    return (
        presencia,
        resumen,
    )


# ============================================================
# UNIFICAR PRESENCIAS B + C
# ============================================================

def construir_presencias(
    cotizaciones: pd.DataFrame,
    ordenes: pd.DataFrame,
) -> pd.DataFrame:

    presencias = cotizaciones.merge(
        ordenes,
        on=[
            "placa_normalizada",
            "fecha_visita",
        ],
        how="outer",
    )

    presencias[
        "tiene_cotizacion"
    ] = presencias[
        "tiene_cotizacion"
    ].fillna(
        False
    ).astype(
        bool
    )

    presencias[
        "tiene_orden"
    ] = presencias[
        "tiene_orden"
    ].fillna(
        False
    ).astype(
        bool
    )

    presencias[
        "cotizaciones"
    ] = presencias[
        "cotizaciones"
    ].fillna(
        0
    ).astype(
        int
    )

    presencias[
        "ordenes"
    ] = presencias[
        "ordenes"
    ].fillna(
        0
    ).astype(
        int
    )

    def determinar_fuente(
        fila,
    ) -> str:

        if (
            fila.tiene_cotizacion
            and fila.tiene_orden
        ):
            return "COTIZACION_Y_ORDEN"

        if fila.tiene_cotizacion:
            return "COTIZACION"

        return "ORDEN"

    presencias[
        "fuente"
    ] = presencias.apply(
        determinar_fuente,
        axis=1,
    )

    # --------------------------------------------------------
    # ID DETERMINÍSTICO DE PRESENCIA
    #
    # Una presencia real para nuestro modelo es:
    # placa + fecha.
    # --------------------------------------------------------

    presencias[
        "presencia_id"
    ] = (
        presencias[
            "placa_normalizada"
        ].astype(str)
        +
        "|"
        +
        presencias[
            "fecha_visita"
        ].astype(str)
    )

    return presencias

# ============================================================
# EFECTIVIDAD NIVEL 1
# ============================================================

def calcular_nivel_1(
    citas: pd.DataFrame,
    presencias: pd.DataFrame,
    desde: date,
    hasta: date,
) -> pd.DataFrame:
    """
    Calcula efectividad Nivel 1:

        misma placa + misma fecha.

    Reglas:
    - Una presencia solo puede acreditar una cita.
    - Una cita solo puede recibir una presencia.
    - Se conserva todo el universo de agentes.
    - Call Center se identifica únicamente como dimensión
      para reportería posterior.
    - Si varias citas de la misma placa/fecha pertenecen
      al mismo agente y exactamente una corresponde a
      Preventivo, se prioriza Preventivo.
    - Si la ambigüedad continúa, queda pendiente para
      resolución manual.
    """

    resultado = citas.copy()

    # --------------------------------------------------------
    # IDENTIFICAR AGENTES CALL CENTER
    # --------------------------------------------------------

    resultado[
        "es_callcenter"
    ] = resultado[
        "agente"
    ].isin(
        AGENTES_CALLCENTER
    )

    # --------------------------------------------------------
    # IDENTIFICAR PERÍODO EVALUADO
    # --------------------------------------------------------

    resultado[
        "en_periodo_evaluado"
    ] = resultado[
        "fecha_cita"
    ].apply(
        lambda fecha:
            (
                fecha is not None
                and pd.notna(fecha)
                and desde <= fecha < hasta
            )
    )

    # --------------------------------------------------------
    # PREPARAR EVIDENCIA
    # --------------------------------------------------------

    evidencia = presencias[
        [
            "placa_normalizada",
            "fecha_visita",
            "tiene_cotizacion",
            "tiene_orden",
            "cotizaciones",
            "ordenes",
            "fuente",
        ]
    ].copy()

    evidencia = evidencia.rename(
        columns={
            "fecha_visita":
                "fecha_cita",
        }
    )

    resultado = resultado.merge(
        evidencia,
        on=[
            "placa_normalizada",
            "fecha_cita",
        ],
        how="left",
    )

    # --------------------------------------------------------
    # ESTADOS INICIALES
    # --------------------------------------------------------

    resultado[
        "estado_nivel_1"
    ] = "SIN_EVIDENCIA"

    resultado[
        "criterio_asignacion"
    ] = ""

    resultado[
        "es_ambigua"
    ] = False

    tiene_presencia = resultado[
        "fuente"
    ].notna()

    candidatos = resultado.loc[
        tiene_presencia
    ].copy()

    if candidatos.empty:
        return resultado

    # --------------------------------------------------------
    # RESOLVER CADA PRESENCIA PLACA + FECHA
    # --------------------------------------------------------

    for (
        placa,
        fecha_cita,
    ), grupo in candidatos.groupby(
        [
            "placa_normalizada",
            "fecha_cita",
        ],
        dropna=False,
    ):

        indices = grupo.index.tolist()

        # ----------------------------------------------------
        # CASO 1 — UNA SOLA CITA
        # ----------------------------------------------------

        if len(indices) == 1:

            indice = indices[0]

            resultado.loc[
                indice,
                "estado_nivel_1",
            ] = "EFECTIVA_NIVEL_1"

            resultado.loc[
                indice,
                "criterio_asignacion",
            ] = "COINCIDENCIA_EXACTA"

            continue

        # ----------------------------------------------------
        # CASO 2 — PRIORIDAD POR PERÍODO
        #
        # Esta protección será especialmente útil cuando
        # posteriormente ampliemos B/C por tolerancias X/Y
        # y entren citas de meses vecinos.
        # ----------------------------------------------------

        grupo_periodo = grupo.loc[
            grupo[
                "en_periodo_evaluado"
            ]
        ].copy()

        if len(grupo_periodo) == 1:

            indice_ganador = (
                grupo_periodo.index[0]
            )

            indices_perdedores = [
                indice
                for indice in indices
                if indice != indice_ganador
            ]

            resultado.loc[
                indice_ganador,
                "estado_nivel_1",
            ] = "EFECTIVA_NIVEL_1"

            resultado.loc[
                indice_ganador,
                "criterio_asignacion",
            ] = "PRIORIDAD_PERIODO"

            resultado.loc[
                indices_perdedores,
                "estado_nivel_1",
            ] = "SOLAPADA_NO_ASIGNADA"

            resultado.loc[
                indices_perdedores,
                "criterio_asignacion",
            ] = (
                "PRESENCIA_ASIGNADA_A_OTRA_CITA"
            )

            continue

        # ----------------------------------------------------
        # CASO 3 — MISMO AGENTE + PREVENTIVO
        # ----------------------------------------------------

        agentes = (
            grupo[
                "agente"
            ]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
        )

        mismo_agente = (
            len(agentes) == 1
        )

        if mismo_agente:

            es_preventivo = (
                grupo[
                    "motivos"
                ]
                .fillna("")
                .astype(str)
                .str.upper()
                .str.contains(
                    r"\bPREVENTIVO\b",
                    regex=True,
                )
            )

            grupo_preventivo = (
                grupo.loc[
                    es_preventivo
                ]
            )

            if len(
                grupo_preventivo
            ) == 1:

                indice_ganador = (
                    grupo_preventivo
                    .index[0]
                )

                indices_perdedores = [
                    indice
                    for indice in indices
                    if indice
                    != indice_ganador
                ]

                resultado.loc[
                    indice_ganador,
                    "estado_nivel_1",
                ] = "EFECTIVA_NIVEL_1"

                resultado.loc[
                    indice_ganador,
                    "criterio_asignacion",
                ] = (
                    "PRIORIDAD_PREVENTIVO_"
                    "MISMO_AGENTE"
                )

                resultado.loc[
                    indices_perdedores,
                    "estado_nivel_1",
                ] = (
                    "SOLAPADA_NO_ASIGNADA"
                )

                resultado.loc[
                    indices_perdedores,
                    "criterio_asignacion",
                ] = (
                    "PRESENCIA_ASIGNADA_"
                    "A_PREVENTIVO"
                )

                continue

        # ----------------------------------------------------
        # CASO 4 — AMBIGÜEDAD REAL
        # ----------------------------------------------------

        resultado.loc[
            indices,
            "estado_nivel_1",
        ] = "AMBIGUA_NIVEL_1"

        resultado.loc[
            indices,
            "criterio_asignacion",
        ] = "REQUIERE_DECISION_MANUAL"

        resultado.loc[
            indices,
            "es_ambigua",
        ] = True

    return resultado


def resolver_ambiguedades_terminal(
    resultado: pd.DataFrame,
) -> pd.DataFrame:
    """
    Resuelve únicamente las ambigüedades que no pudieron
    resolverse con reglas automáticas.

    En esta fase diagnóstica las decisiones viven solamente
    durante la ejecución actual.

    Posteriormente se persistirán para que los recálculos
    históricos reutilicen la misma decisión.
    """

    resultado = resultado.copy()

    ambiguas = resultado.loc[
        resultado[
            "estado_nivel_1"
        ].eq(
            "AMBIGUA_NIVEL_1"
        )
    ].copy()

    if ambiguas.empty:

        print()
        print(
            "✅ No existen ambigüedades "
            "Nivel 1 por resolver manualmente."
        )

        return resultado

    grupos = list(
        ambiguas.groupby(
            [
                "placa_normalizada",
                "fecha_cita",
            ],
            dropna=False,
        )
    )

    print()
    print("=" * 72)
    print(
        "🐿️ RESOLUCIÓN MANUAL DE AMBIGÜEDADES"
    )
    print("=" * 72)

    print(
        f"Grupos pendientes: "
        f"{len(grupos):,}"
    )

    for numero_grupo, (
        (
            placa,
            fecha_cita,
        ),
        grupo,
    ) in enumerate(
        grupos,
        start=1,
    ):

        print()
        print("-" * 72)

        print(
            f"Grupo "
            f"{numero_grupo}/"
            f"{len(grupos)}"
        )

        print(
            f"Placa       : {placa}"
        )

        print(
            f"Fecha       : {fecha_cita}"
        )

        fuentes = (
            grupo[
                "fuente"
            ]
            .dropna()
            .unique()
        )

        fuente = (
            fuentes[0]
            if len(fuentes)
            else ""
        )

        print(
            f"Evidencia   : {fuente}"
        )

        print()
        print(
            "Citas candidatas:"
        )

        indices = (
            grupo.index.tolist()
        )

        for posicion, indice in enumerate(
            indices,
            start=1,
        ):

            fila = resultado.loc[
                indice
            ]

            fecha_hora = fila[
                "fecha_hora_cita_lima"
            ]

            if pd.notna(
                fecha_hora
            ):

                fecha_hora_texto = (
                    fecha_hora.strftime(
                        "%d/%m/%Y %H:%M"
                    )
                )

            else:

                fecha_hora_texto = ""

            fecha_creacion = fila[
                "fecha_creacion_lima"
            ]

            if pd.notna(
                fecha_creacion
            ):

                fecha_creacion_texto = (
                    fecha_creacion.strftime(
                        "%d/%m/%Y %H:%M"
                    )
                )

            else:

                fecha_creacion_texto = ""

            print()
            print(
                f"  {posicion}. "
                f"Cita #"
                f"{fila['appointment_number']}"
            )

            print(
                f"     Agente    : "
                f"{fila['agente']}"
            )

            print(
                f"     Cita      : "
                f"{fecha_hora_texto}"
            )

            print(
                f"     Creación  : "
                f"{fecha_creacion_texto}"
            )

            print(
                f"     Motivo    : "
                f"{fila['motivos']}"
            )

            print(
                f"     Origen    : "
                f"{fila['origen']}"
            )

            print(
                "     Call Center: "
                f"{'Sí' if fila['es_callcenter'] else 'No'}"
            )

        print()
        print(
            "  0. Dejar pendiente"
        )

        while True:

            respuesta = input(
                "\nSeleccione la cita que "
                "debe recibir la efectividad: "
            ).strip()

            if respuesta == "0":

                print(
                    "⚠️ Ambigüedad dejada "
                    "pendiente."
                )

                break

            if not respuesta.isdigit():

                print(
                    "Seleccione una opción válida."
                )

                continue

            posicion = int(
                respuesta
            )

            if not (
                1
                <= posicion
                <= len(indices)
            ):

                print(
                    "Seleccione una opción válida."
                )

                continue

            indice_ganador = (
                indices[
                    posicion - 1
                ]
            )

            indices_perdedores = [
                indice
                for indice in indices
                if indice
                != indice_ganador
            ]

            resultado.loc[
                indice_ganador,
                "estado_nivel_1",
            ] = "EFECTIVA_NIVEL_1"

            resultado.loc[
                indice_ganador,
                "criterio_asignacion",
            ] = "RESOLUCION_MANUAL"

            resultado.loc[
                indice_ganador,
                "es_ambigua",
            ] = False

            resultado.loc[
                indices_perdedores,
                "estado_nivel_1",
            ] = "SOLAPADA_NO_ASIGNADA"

            resultado.loc[
                indices_perdedores,
                "criterio_asignacion",
            ] = (
                "PRESENCIA_ASIGNADA_"
                "MANUALMENTE_A_OTRA_CITA"
            )

            resultado.loc[
                indices_perdedores,
                "es_ambigua",
            ] = False

            cita_elegida = resultado.loc[
                indice_ganador,
                "appointment_number",
            ]

            print(
                f"✅ Presencia asignada a "
                f"cita #{cita_elegida}"
            )

            break

    return resultado


def explorar_nivel_2(
    resultado: pd.DataFrame,
    presencias: pd.DataFrame,
    dias_exploracion: int,
) -> pd.DataFrame:
    """
    Explora posibles coincidencias Nivel 2 sin modificar
    todavía el estado oficial de las citas.

    Solo estudia citas que:
    - no tuvieron evidencia exacta, o
    - quedaron solapadas porque la presencia exacta fue
      asignada a otra cita.

    Las presencias utilizadas/reservadas por Nivel 1 se
    excluyen de la búsqueda.

    Una misma presencia todavía puede aparecer como candidata
    para varias citas durante esta exploración. Ese conflicto
    se identifica explícitamente y se resolverá cuando
    construyamos el matching Nivel 2 definitivo.
    """

    columnas_salida = [
        "id_cita",
        "appointment_number",
        "placa_normalizada",
        "fecha_cita",
        "agente",
        "es_callcenter",
        "motivos",
        "estado_nivel_1",
        "presencia_id_candidata",
        "fecha_visita_candidata",
        "diferencia_dias",
        "distancia_absoluta",
        "fuente_candidata",
        "cantidad_presencias_en_ventana",
        "presencia_compartida",
    ]

    if resultado.empty or presencias.empty:
        return pd.DataFrame(
            columns=columnas_salida
        )

    # --------------------------------------------------------
    # PRESENCIAS RESERVADAS POR NIVEL 1
    #
    # Si existe una cita efectiva o una ambigüedad exacta
    # sobre placa/fecha, esa presencia no debe reutilizarse
    # para Nivel 2.
    # --------------------------------------------------------

    estados_que_reservan = {
        "EFECTIVA_NIVEL_1",
        "AMBIGUA_NIVEL_1",
        "SOLAPADA_NO_ASIGNADA",
    }

    grupos_reservados = (
        resultado.loc[
            resultado[
                "estado_nivel_1"
            ].isin(
                estados_que_reservan
            )
            &
            resultado[
                "fuente"
            ].notna(),
            [
                "placa_normalizada",
                "fecha_cita",
            ],
        ]
        .drop_duplicates()
        .copy()
    )

    if grupos_reservados.empty:

        ids_reservados = set()

    else:

        grupos_reservados[
            "presencia_id"
        ] = (
            grupos_reservados[
                "placa_normalizada"
            ].astype(str)
            +
            "|"
            +
            grupos_reservados[
                "fecha_cita"
            ].astype(str)
        )

        ids_reservados = set(
            grupos_reservados[
                "presencia_id"
            ]
        )

    presencias_disponibles = (
        presencias.loc[
            ~presencias[
                "presencia_id"
            ].isin(
                ids_reservados
            )
        ]
        .copy()
    )

    # --------------------------------------------------------
    # CITAS QUE NECESITAN SEGUNDA BÚSQUEDA
    # --------------------------------------------------------

    estados_explorables = {
        "SIN_EVIDENCIA",
        "SOLAPADA_NO_ASIGNADA",
    }

    citas_pendientes = (
        resultado.loc[
            resultado[
                "estado_nivel_1"
            ].isin(
                estados_explorables
            )
        ]
        .copy()
    )

    citas_pendientes = citas_pendientes.loc[
        citas_pendientes[
            "placa_normalizada"
        ].fillna(
            ""
        ).ne(
            ""
        )
        &
        citas_pendientes[
            "fecha_cita"
        ].notna()
    ].copy()

    registros = []

    # --------------------------------------------------------
    # BUSCAR LA PRESENCIA MÁS CERCANA DE CADA CITA
    # --------------------------------------------------------

    for fila in citas_pendientes.itertuples(
        index=False
    ):

        candidatas = (
            presencias_disponibles.loc[
                presencias_disponibles[
                    "placa_normalizada"
                ].eq(
                    fila.placa_normalizada
                )
            ]
            .copy()
        )

        if candidatas.empty:
            continue

        candidatas[
            "diferencia_dias"
        ] = candidatas[
            "fecha_visita"
        ].apply(
            lambda fecha:
                (
                    fecha
                    -
                    fila.fecha_cita
                ).days
        )

        candidatas = candidatas.loc[
            candidatas[
                "diferencia_dias"
            ].between(
                -dias_exploracion,
                dias_exploracion,
            )
        ].copy()

        if candidatas.empty:
            continue

        candidatas[
            "distancia_absoluta"
        ] = candidatas[
            "diferencia_dias"
        ].abs()

        # ----------------------------------------------------
        # ORDEN DIAGNÓSTICO
        #
        # 1. menor distancia absoluta
        # 2. ante empate, primero presencia posterior
        # 3. finalmente fecha cronológica
        # ----------------------------------------------------

        candidatas[
            "es_posterior"
        ] = candidatas[
            "diferencia_dias"
        ].ge(
            0
        )

        candidatas = candidatas.sort_values(
            [
                "distancia_absoluta",
                "es_posterior",
                "fecha_visita",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )

        mejor = candidatas.iloc[
            0
        ]

        registros.append(
            {
                "id_cita":
                    fila.id_cita,
                "appointment_number":
                    fila.appointment_number,
                "placa_normalizada":
                    fila.placa_normalizada,
                "fecha_cita":
                    fila.fecha_cita,
                "agente":
                    fila.agente,
                "es_callcenter":
                    fila.es_callcenter,
                "motivos":
                    fila.motivos,
                "estado_nivel_1":
                    fila.estado_nivel_1,
                "presencia_id_candidata":
                    mejor[
                        "presencia_id"
                    ],
                "fecha_visita_candidata":
                    mejor[
                        "fecha_visita"
                    ],
                "diferencia_dias":
                    int(
                        mejor[
                            "diferencia_dias"
                        ]
                    ),
                "distancia_absoluta":
                    int(
                        mejor[
                            "distancia_absoluta"
                        ]
                    ),
                "fuente_candidata":
                    mejor[
                        "fuente"
                    ],
                "cantidad_presencias_en_ventana":
                    len(
                        candidatas
                    ),
                "presencia_compartida":
                    False,
            }
        )

    exploracion = pd.DataFrame(
        registros,
        columns=columnas_salida,
    )

    if exploracion.empty:
        return exploracion

    # --------------------------------------------------------
    # IDENTIFICAR CUANDO DOS O MÁS CITAS QUIEREN UTILIZAR
    # LA MISMA PRESENCIA
    # --------------------------------------------------------

    conteo_presencias = (
        exploracion[
            "presencia_id_candidata"
        ]
        .value_counts()
    )

    ids_compartidos = set(
        conteo_presencias.loc[
            conteo_presencias > 1
        ].index
    )

    exploracion[
        "presencia_compartida"
    ] = exploracion[
        "presencia_id_candidata"
    ].isin(
        ids_compartidos
    )

    return exploracion




# ============================================================
# IMPRESIÓN
# ============================================================

def imprimir_exploracion_nivel_2(
    exploracion: pd.DataFrame,
    resultado: pd.DataFrame,
    dias_exploracion: int,
) -> None:
    """
    Imprime únicamente diagnóstico de Nivel 2.

    No modifica estados ni calcula todavía la efectividad
    definitiva.
    """

    print()
    print("=" * 72)
    print(
        "EXPLORACIÓN NIVEL 2 — "
        f"VENTANA ±{dias_exploracion} DÍAS"
    )
    print("=" * 72)

    pendientes = resultado.loc[
        resultado[
            "estado_nivel_1"
        ].isin(
            {
                "SIN_EVIDENCIA",
                "SOLAPADA_NO_ASIGNADA",
            }
        )
    ]

    print(
        f"Citas a explorar                : "
        f"{len(pendientes):,}"
    )

    if exploracion.empty:

        print(
            "Citas con presencia cercana      : 0"
        )

        print(
            f"Sin presencia en ±"
            f"{dias_exploracion} días       : "
            f"{len(pendientes):,}"
        )

        return

    citas_con_candidato = (
        exploracion[
            "id_cita"
        ].nunique()
    )

    sin_candidato = (
        len(pendientes)
        -
        citas_con_candidato
    )

    conflictos = int(
        exploracion[
            "presencia_compartida"
        ].sum()
    )

    presencias_compartidas = (
        exploracion.loc[
            exploracion[
                "presencia_compartida"
            ],
            "presencia_id_candidata",
        ]
        .nunique()
    )

    print(
        f"Citas con presencia cercana      : "
        f"{citas_con_candidato:,}"
    )

    print(
        f"Sin presencia en ±"
        f"{dias_exploracion} días       : "
        f"{sin_candidato:,}"
    )

    print(
        f"Citas involucradas en conflicto  : "
        f"{conflictos:,}"
    )

    print(
        f"Presencias compartidas           : "
        f"{presencias_compartidas:,}"
    )

    # ========================================================
    # DISTRIBUCIÓN POR DIFERENCIA DE DÍAS
    # ========================================================

    distribucion = (
        exploracion[
            "diferencia_dias"
        ]
        .value_counts()
        .sort_index()
        .rename_axis(
            "diferencia_dias"
        )
        .reset_index(
            name="citas"
        )
    )

    total = distribucion[
        "citas"
    ].sum()

    distribucion[
        "porcentaje"
    ] = (
        distribucion[
            "citas"
        ]
        /
        total
        *
        100
    ).round(
        1
    )

    print()
    print("-" * 72)
    print(
        "DISTRIBUCIÓN — FECHA VISITA MENOS FECHA CITA"
    )
    print("-" * 72)

    print(
        distribucion.to_string(
            index=False
        )
    )

    # ========================================================
    # POR AGENTE
    # ========================================================

    por_agente = (
        exploracion
        .groupby(
            [
                "agente",
                "es_callcenter",
            ],
            dropna=False,
        )
        .agg(
            citas_con_candidato=(
                "id_cita",
                "nunique",
            ),
            conflictos=(
                "presencia_compartida",
                "sum",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "es_callcenter",
                "citas_con_candidato",
            ],
            ascending=[
                False,
                False,
            ],
        )
    )

    print()
    print("-" * 72)
    print(
        "CANDIDATOS NIVEL 2 POR AGENTE"
    )
    print("-" * 72)

    print(
        por_agente.to_string(
            index=False
        )
    )

    # ========================================================
    # CONFLICTOS
    # ========================================================

    conflictos_df = (
        exploracion.loc[
            exploracion[
                "presencia_compartida"
            ]
        ]
        .sort_values(
            [
                "presencia_id_candidata",
                "fecha_cita",
                "appointment_number",
            ]
        )
    )

    if not conflictos_df.empty:

        print()
        print("-" * 72)
        print(
            "MUESTRA — PRESENCIAS NIVEL 2 "
            "DISPUTADAS POR VARIAS CITAS"
        )
        print("-" * 72)

        columnas = [
            "appointment_number",
            "placa_normalizada",
            "fecha_cita",
            "fecha_visita_candidata",
            "diferencia_dias",
            "agente",
            "motivos",
            "presencia_id_candidata",
        ]

        print(
            conflictos_df[
                columnas
            ]
            .head(
                30
            )
            .to_string(
                index=False
            )
        )


def imprimir_bloque(
    titulo: str,
    valores: list[
        tuple[str, int]
    ],
) -> None:

    print()
    print("=" * 72)
    print(titulo)
    print("=" * 72)

    for etiqueta, valor in valores:

        print(
            f"{etiqueta:<36}"
            f"{valor:>12,}"
        )


def imprimir_resultados(
    resumen_a: dict,
    resumen_b: dict,
    resumen_c: dict,
    presencias: pd.DataFrame,
    resultado: pd.DataFrame,
) -> None:

    # ========================================================
    # TABLA A
    # ========================================================

    imprimir_bloque(
        "TABLA A — CITAS",
        [
            (
                "Filas crudas",
                resumen_a[
                    "filas_raw"
                ],
            ),
            (
                "Citas únicas",
                resumen_a[
                    "citas_unicas"
                ],
            ),
            (
                "Citas eliminadas",
                resumen_a[
                    "eliminadas"
                ],
            ),
            (
                "Citas elegibles",
                resumen_a[
                    "elegibles"
                ],
            ),
            (
                "Elegibles sin placa",
                resumen_a[
                    "sin_placa"
                ],
            ),
        ],
    )

    # ========================================================
    # TABLA B
    # ========================================================

    imprimir_bloque(
        "TABLA B — COTIZACIONES",
        [
            (
                "Filas crudas",
                resumen_b[
                    "filas_raw"
                ],
            ),
            (
                "Documentos distintos",
                resumen_b[
                    "documentos"
                ],
            ),
            (
                "Presencias placa/fecha",
                resumen_b[
                    "presencias"
                ],
            ),
            (
                "Filas sin placa",
                resumen_b[
                    "sin_placa"
                ],
            ),
        ],
    )

    # ========================================================
    # TABLA C
    # ========================================================

    imprimir_bloque(
        "TABLA C — ÓRDENES",
        [
            (
                "Filas crudas",
                resumen_c[
                    "filas_raw"
                ],
            ),
            (
                "Órdenes distintas",
                resumen_c[
                    "ordenes"
                ],
            ),
            (
                "Presencias placa/fecha",
                resumen_c[
                    "presencias"
                ],
            ),
            (
                "Filas sin placa",
                resumen_c[
                    "sin_placa"
                ],
            ),
        ],
    )

    # ========================================================
    # PRESENCIAS
    # ========================================================

    solo_b = int(
        presencias[
            "fuente"
        ].eq(
            "COTIZACION"
        ).sum()
    )

    solo_c = int(
        presencias[
            "fuente"
        ].eq(
            "ORDEN"
        ).sum()
    )

    ambas = int(
        presencias[
            "fuente"
        ].eq(
            "COTIZACION_Y_ORDEN"
        ).sum()
    )

    imprimir_bloque(
        "PRESENCIAS B + C",
        [
            (
                "Solo cotización",
                solo_b,
            ),
            (
                "Solo orden",
                solo_c,
            ),
            (
                "Cotización + orden",
                ambas,
            ),
            (
                "Total placa/fecha",
                len(
                    presencias
                ),
            ),
        ],
    )

    # ========================================================
    # ESTADOS GENERALES
    # ========================================================

    conteo = (
        resultado[
            "estado_nivel_1"
        ]
        .value_counts()
        .to_dict()
    )

    imprimir_bloque(
        "EFECTIVIDAD — NIVEL 1 — UNIVERSO COMPLETO",
        [
            (
                "Efectivas",
                int(
                    conteo.get(
                        "EFECTIVA_NIVEL_1",
                        0,
                    )
                ),
            ),
            (
                "Solapadas no asignadas",
                int(
                    conteo.get(
                        "SOLAPADA_NO_ASIGNADA",
                        0,
                    )
                ),
            ),
            (
                "Ambiguas pendientes",
                int(
                    conteo.get(
                        "AMBIGUA_NIVEL_1",
                        0,
                    )
                ),
            ),
            (
                "Sin evidencia exacta",
                int(
                    conteo.get(
                        "SIN_EVIDENCIA",
                        0,
                    )
                ),
            ),
        ],
    )

    # ========================================================
    # UNIVERSO CALL CENTER
    # ========================================================

    callcenter = resultado.loc[
        resultado[
            "es_callcenter"
        ]
    ].copy()

    otros = resultado.loc[
        ~resultado[
            "es_callcenter"
        ]
    ].copy()

    imprimir_bloque(
        "UNIVERSO POR TIPO DE AGENTE",
        [
            (
                "Citas Call Center",
                len(
                    callcenter
                ),
            ),
            (
                "Citas otros agentes",
                len(
                    otros
                ),
            ),
            (
                "Total universo",
                len(
                    resultado
                ),
            ),
        ],
    )

    # ========================================================
    # RESUMEN POR AGENTE
    # ========================================================

    resumen_agentes = (
        resultado
        .groupby(
            [
                "agente",
                "es_callcenter",
            ],
            dropna=False,
        )
        .agg(
            citas=(
                "id_cita",
                "count",
            ),
            efectivas=(
                "estado_nivel_1",
                lambda serie:
                    (
                        serie
                        ==
                        "EFECTIVA_NIVEL_1"
                    ).sum(),
            ),
            solapadas=(
                "estado_nivel_1",
                lambda serie:
                    (
                        serie
                        ==
                        "SOLAPADA_NO_ASIGNADA"
                    ).sum(),
            ),
            pendientes_ambiguas=(
                "estado_nivel_1",
                lambda serie:
                    (
                        serie
                        ==
                        "AMBIGUA_NIVEL_1"
                    ).sum(),
            ),
            sin_evidencia=(
                "estado_nivel_1",
                lambda serie:
                    (
                        serie
                        ==
                        "SIN_EVIDENCIA"
                    ).sum(),
            ),
        )
        .reset_index()
    )

    resumen_agentes[
        "efectividad_pct"
    ] = (
        resumen_agentes[
            "efectivas"
        ]
        /
        resumen_agentes[
            "citas"
        ]
        *
        100
    ).round(
        1
    )

    resumen_agentes = (
        resumen_agentes
        .sort_values(
            [
                "es_callcenter",
                "citas",
            ],
            ascending=[
                False,
                False,
            ],
        )
    )

    print()
    print("=" * 72)
    print(
        "RESUMEN POR AGENTE — NIVEL 1"
    )
    print("=" * 72)

    print(
        resumen_agentes.to_string(
            index=False
        )
    )

    # ========================================================
    # DETALLE DE RESOLUCIONES
    # ========================================================

    decisiones = resultado.loc[
        resultado[
            "criterio_asignacion"
        ].ne(
            ""
        ),
        [
            "appointment_number",
            "placa_normalizada",
            "fecha_cita",
            "agente",
            "es_callcenter",
            "motivos",
            "estado_nivel_1",
            "criterio_asignacion",
            "fuente",
        ],
    ].copy()

    decisiones = decisiones.sort_values(
        [
            "fecha_cita",
            "placa_normalizada",
            "appointment_number",
        ]
    )

    print()
    print("=" * 72)
    print(
        "TRAZABILIDAD DE ASIGNACIONES NIVEL 1"
    )
    print("=" * 72)

    print(
        f"Registros con criterio: "
        f"{len(decisiones):,}"
    )

    # Solo mostramos manuales/solapadas para evitar
    # imprimir cientos de coincidencias exactas normales.
    especiales = decisiones.loc[
        decisiones[
            "criterio_asignacion"
        ].ne(
            "COINCIDENCIA_EXACTA"
        )
    ]

    if especiales.empty:

        print(
            "No existen decisiones especiales."
        )

    else:

        print()
        print(
            especiales.to_string(
                index=False
            )
        )

# ============================================================
# MAIN
# ============================================================

def main() -> None:

    argumentos = leer_argumentos()

    desde, hasta = validar_fechas(
        argumentos.desde,
        argumentos.hasta,
    )

    dias_exploracion = (
        argumentos.explorar_dias
    )

    # ========================================================
    # VENTANA DE PRESENCIAS
    #
    # La Tabla A conserva exclusivamente el período que
    # queremos evaluar.
    #
    # Las tablas B y C se consultan con una ventana ampliada
    # para poder estudiar llegadas anteriores/posteriores.
    # ========================================================

    desde_presencias = (
        desde
        -
        timedelta(
            days=dias_exploracion
        )
    )

    hasta_presencias = (
        hasta
        +
        timedelta(
            days=dias_exploracion
        )
    )

    print()
    print("=" * 72)
    print(
        "CGO CALL CENTER — "
        "DIAGNÓSTICO EFECTIVIDAD DATABRICKS"
    )
    print("=" * 72)

    print(
        f"Período de citas Lima : "
        f"{desde:%d/%m/%Y} "
        f"→ "
        f"{hasta:%d/%m/%Y} "
        "(fin exclusivo)"
    )

    print(
        f"Exploración Nivel 2   : "
        f"±{dias_exploracion} días"
    )

    print(
        f"Ventana B/C           : "
        f"{desde_presencias:%d/%m/%Y} "
        f"→ "
        f"{hasta_presencias:%d/%m/%Y} "
        "(fin exclusivo)"
    )

    # ========================================================
    # TABLA A — CITAS
    #
    # IMPORTANTE:
    # A se limita únicamente al período que estamos midiendo.
    # ========================================================

    print()
    print(
        "🐔 Consultando Tabla A — citas..."
    )

    citas_raw = obtener_citas(
        desde=desde,
        hasta=hasta,
    )

    citas, resumen_a = consolidar_citas(
        citas_raw
    )

    # ========================================================
    # TABLA B — COTIZACIONES
    #
    # Se amplía hacia atrás y adelante para poder localizar
    # presencias cercanas a las citas del período.
    # ========================================================

    print(
        "🐔 Consultando Tabla B — cotizaciones..."
    )

    cotizaciones_raw = obtener_cotizaciones(
        desde=desde_presencias,
        hasta=hasta_presencias,
    )

    cotizaciones, resumen_b = (
        consolidar_cotizaciones(
            cotizaciones_raw
        )
    )

    # ========================================================
    # TABLA C — ÓRDENES
    #
    # Misma ventana ampliada usada para cotizaciones.
    # ========================================================

    print(
        "🐔 Consultando Tabla C — órdenes..."
    )

    ordenes_raw = obtener_ordenes(
        desde=desde_presencias,
        hasta=hasta_presencias,
    )

    ordenes, resumen_c = consolidar_ordenes(
        ordenes_raw
    )

    # ========================================================
    # PRESENCIAS REALES
    #
    # B + C se consolidan a una única presencia por:
    #
    # placa + fecha
    # ========================================================

    presencias = construir_presencias(
        cotizaciones=cotizaciones,
        ordenes=ordenes,
    )

    # ========================================================
    # NIVEL 1
    #
    # Coincidencia exacta:
    #
    # misma placa
    # +
    # misma fecha cita / visita
    # ========================================================

    resultado = calcular_nivel_1(
        citas=citas,
        presencias=presencias,
        desde=desde,
        hasta=hasta,
    )

    # ========================================================
    # RESOLUCIÓN MANUAL
    #
    # Solo se ejecuta para conflictos que sobrevivieron
    # a las reglas automáticas.
    # ========================================================

    resultado = resolver_ambiguedades_terminal(
        resultado
    )

    # ========================================================
    # RESULTADOS NIVEL 1
    # ========================================================

    imprimir_resultados(
        resumen_a=resumen_a,
        resumen_b=resumen_b,
        resumen_c=resumen_c,
        presencias=presencias,
        resultado=resultado,
    )

    # ========================================================
    # EXPLORACIÓN NIVEL 2
    #
    # IMPORTANTE:
    #
    # Esta fase NO cambia todavía los estados oficiales.
    # Solo identifica posibles presencias cercanas y mide
    # su distribución temporal.
    # ========================================================

    exploracion_nivel_2 = explorar_nivel_2(
        resultado=resultado,
        presencias=presencias,
        dias_exploracion=dias_exploracion,
    )

    imprimir_exploracion_nivel_2(
        exploracion=exploracion_nivel_2,
        resultado=resultado,
        dias_exploracion=dias_exploracion,
    )

    # ========================================================
    # FIN
    # ========================================================

    print()
    print("=" * 72)
    print(
        "✅ DIAGNÓSTICO FINALIZADO — "
        "SOLO LECTURA"
    )
    print("=" * 72)

    print(
        "Nivel 1: calculado."
    )

    print(
        "Nivel 2: explorado, "
        "todavía no aplicado."
    )

    print()


if __name__ == "__main__":
    main()

