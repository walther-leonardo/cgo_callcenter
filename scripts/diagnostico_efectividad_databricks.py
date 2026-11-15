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
from clasificaciones import (
    clasificar_canal_agenda,
    normalizar_persona_agenda,
)
from matching_efectividad import (
    calcular_matching_efectividad,
)

# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ZONA_LIMA = ZoneInfo("America/Lima")
ZONA_UTC = ZoneInfo("UTC")


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


def normalizar_texto_clave(
    valor,
) -> str:
    """
    Normaliza texto exclusivamente para comparar citas.
    """

    if pd.isna(valor):
        return ""

    return " ".join(
        str(valor)
        .strip()
        .upper()
        .split()
    )


def normalizar_celular(
    valor,
) -> str:
    """
    Conserva únicamente los dígitos del celular.
    """

    if pd.isna(valor):
        return ""

    texto = str(
        valor
    ).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return re.sub(
        r"\D",
        "",
        texto,
    )


def es_status_cancelado(
    valor,
) -> bool:
    """
    Detecta estados de cancelación.

    Se utiliza 'CANCEL' como raíz para soportar valores como:
    CANCELADA / CANCELED / CANCELLED.

    La distribución real de status también se imprimirá
    para auditoría.
    """

    texto = normalizar_texto_clave(
        valor
    )

    return "CANCEL" in texto


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
            status,
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
            },
        )

    citas = citas_raw.copy()

    # ========================================================
    # VALIDAR KEY_MERGE
    # ========================================================

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

    # ========================================================
    # VALIDAR CONSISTENCIA INTERNA
    # ========================================================

    campos_criticos = [
        "appointmentNumber",
        "workshop_id",
        "licensePlate",
        "mobile",
        "startDate",
        "userWhoSchedule",
        "status",
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

        ids = cantidades.loc[
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

        raise ValueError(
            "Se encontraron Key_merge con "
            "campos críticos inconsistentes. "
            f"Muestra: {inconsistentes[:10]}"
        )

    # ========================================================
    # UNA FILA POR CITA LÓGICA
    # ========================================================

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
            status=(
                "status",
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

    # ========================================================
    # NORMALIZACIONES
    # ========================================================

    citas[
        "is_deleted"
    ] = citas[
        "isDeleted"
    ].apply(
        convertir_booleano
    )

    citas[
        "placa_normalizada"
    ] = citas[
        "placa"
    ].apply(
        normalizar_placa
    )

    citas[
        "telefono_normalizado"
    ] = citas[
        "telefono"
    ].apply(
        normalizar_celular
    )

    citas[
        "motivo_normalizado"
    ] = citas[
        "motivos"
    ].apply(
        normalizar_texto_clave
    )

    citas[
        "status_normalizado"
    ] = citas[
        "status"
    ].apply(
        normalizar_texto_clave
    )

    citas[
        "es_cancelada_status"
    ] = citas[
        "status"
    ].apply(
        es_status_cancelado
    )

    # ========================================================
    # FECHA/HORA CITA — UTC → LIMA
    # ========================================================

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

    # ========================================================
    # CREACIÓN — UTC → LIMA
    # ========================================================

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

    # ========================================================
    # CALL CENTER — FUENTE OFICIAL DEL PROYECTO
    # ========================================================

    citas[
        "agente_canonico"
    ] = citas[
        "agente"
    ].apply(
        normalizar_persona_agenda
    )

    citas[
        "canal_agenda"
    ] = citas[
        "agente_canonico"
    ].apply(
        clasificar_canal_agenda
    )

    citas[
        "es_callcenter"
    ] = citas[
        "canal_agenda"
    ].eq(
        "CALL CENTER"
    )

    resumen = {
        "filas_raw":
            len(citas_raw),

        "citas_unicas":
            len(citas),
    }

    return (
        citas,
        resumen,
    )


def construir_universo_operativo_citas(
    citas: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    dict,
    pd.DataFrame,
]:
    """
    Construye el universo de citas que puede participar
    en efectividad.

    Orden de reglas:
    1. excluir isDeleted;
    2. excluir status cancelado;
    3. deduplicar citas operativamente equivalentes;
    4. priorizar Call Center;
    5. si persiste empate, mayor appointment_number.

    Devuelve:
    - citas operativas;
    - resumen de auditoría;
    - detalle de citas excluidas/descartadas.
    """

    if citas.empty:

        return (
            citas.copy(),
            {
                "eliminadas_isdeleted": 0,
                "canceladas_status": 0,
                "antes_deduplicacion": 0,
                "grupos_duplicados": 0,
                "descartadas_duplicacion": 0,
                "ganadores_callcenter": 0,
                "ganadores_mayor_id": 0,
                "operativas": 0,
                "sin_placa": 0,
            },
            pd.DataFrame(),
        )

    base = citas.copy()

    auditoria = []

    # ========================================================
    # 1. ISDELETED
    # ========================================================

    eliminadas = base.loc[
        base[
            "is_deleted"
        ]
    ].copy()

    for fila in eliminadas.itertuples(
        index=False
    ):

        auditoria.append(
            {
                "id_cita":
                    fila.id_cita,

                "appointment_number":
                    fila.appointment_number,

                "placa":
                    fila.placa,

                "fecha_cita":
                    fila.fecha_cita,

                "agente":
                    fila.agente,

                "motivos":
                    fila.motivos,

                "status":
                    fila.status,

                "accion":
                    "EXCLUIDA",

                "criterio":
                    "IS_DELETED",

                "id_cita_ganadora":
                    None,
            }
        )

    base = base.loc[
        ~base[
            "is_deleted"
        ]
    ].copy()

    # ========================================================
    # 2. CANCELADAS
    # ========================================================

    canceladas = base.loc[
        base[
            "es_cancelada_status"
        ]
    ].copy()

    for fila in canceladas.itertuples(
        index=False
    ):

        auditoria.append(
            {
                "id_cita":
                    fila.id_cita,

                "appointment_number":
                    fila.appointment_number,

                "placa":
                    fila.placa,

                "fecha_cita":
                    fila.fecha_cita,

                "agente":
                    fila.agente,

                "motivos":
                    fila.motivos,

                "status":
                    fila.status,

                "accion":
                    "EXCLUIDA",

                "criterio":
                    "STATUS_CANCELADO",

                "id_cita_ganadora":
                    None,
            }
        )

    base = base.loc[
        ~base[
            "es_cancelada_status"
        ]
    ].copy()

    cantidad_antes_deduplicacion = len(
        base
    )

    # ========================================================
    # 3. CLAVE OPERATIVA
    # ========================================================

    base[
        "_clave_fecha_hora"
    ] = base[
        "fecha_hora_cita_lima"
    ]

    clave_completa = (
        base[
            "placa_normalizada"
        ].ne("")
        &
        base[
            "telefono_normalizado"
        ].ne("")
        &
        base[
            "motivo_normalizado"
        ].ne("")
        &
        base[
            "_clave_fecha_hora"
        ].notna()
    )

    candidatos = base.loc[
        clave_completa
    ].copy()

    incompletos = base.loc[
        ~clave_completa
    ].copy()

    claves_grupo = [
        "placa_normalizada",
        "telefono_normalizado",
        "_clave_fecha_hora",
        "motivo_normalizado",
    ]

    # ========================================================
    # 4. IDENTIFICAR GRUPOS DUPLICADOS
    # ========================================================

    tamanos = (
        candidatos
        .groupby(
            claves_grupo,
            dropna=False,
        )
        .size()
    )

    grupos_duplicados = int(
        (
            tamanos > 1
        ).sum()
    )

    candidatos[
        "_appointment_number_num"
    ] = pd.to_numeric(
        candidatos[
            "appointment_number"
        ],
        errors="coerce",
    )

    # Solo los grupos duplicados necesitan realmente
    # appointmentNumber para el desempate.
    claves_duplicadas = set(
        tamanos.loc[
            tamanos > 1
        ].index.tolist()
    )

    if claves_duplicadas:

        mascara_grupo_duplicado = (
            candidatos.apply(
                lambda fila:
                    (
                        fila[
                            "placa_normalizada"
                        ],
                        fila[
                            "telefono_normalizado"
                        ],
                        fila[
                            "_clave_fecha_hora"
                        ],
                        fila[
                            "motivo_normalizado"
                        ],
                    )
                    in claves_duplicadas,
                axis=1,
            )
        )

        invalidos = candidatos.loc[
            mascara_grupo_duplicado
            &
            candidatos[
                "_appointment_number_num"
            ].isna()
        ]

        if not invalidos.empty:

            raise ValueError(
                "Existen citas duplicadas cuyo "
                "appointmentNumber no puede convertirse "
                "a número. Muestra: "
                f"{invalidos['appointment_number'].head(10).tolist()}"
            )

    # ========================================================
    # 5. RESOLVER CADA GRUPO
    # ========================================================

    ganadores = []

    ganadores_callcenter = 0
    ganadores_mayor_id = 0

    for _, grupo in candidatos.groupby(
        claves_grupo,
        dropna=False,
        sort=False,
    ):

        if len(grupo) == 1:

            ganadores.append(
                grupo.iloc[0]
            )

            continue

        grupo = grupo.copy()

        cantidad_callcenter = int(
            grupo[
                "es_callcenter"
            ].sum()
        )

        if cantidad_callcenter > 0:

            elegibles_ganador = grupo.loc[
                grupo[
                    "es_callcenter"
                ]
            ].copy()

            criterio = (
                "PRIORIDAD_CALLCENTER"
            )

            ganadores_callcenter += 1

        else:

            elegibles_ganador = (
                grupo.copy()
            )

            criterio = (
                "MAYOR_APPOINTMENT_NUMBER"
            )

            ganadores_mayor_id += 1

        ganador = (
            elegibles_ganador
            .sort_values(
                "_appointment_number_num",
                ascending=False,
                kind="stable",
            )
            .iloc[0]
        )

        ganadores.append(
            ganador
        )

        perdedores = grupo.loc[
            grupo[
                "id_cita"
            ].ne(
                ganador[
                    "id_cita"
                ]
            )
        ]

        for fila in perdedores.itertuples(
            index=False
        ):

            auditoria.append(
                {
                    "id_cita":
                        fila.id_cita,

                    "appointment_number":
                        fila.appointment_number,

                    "placa":
                        fila.placa,

                    "fecha_cita":
                        fila.fecha_cita,

                    "agente":
                        fila.agente,

                    "motivos":
                        fila.motivos,

                    "status":
                        fila.status,

                    "accion":
                        "DESCARTADA",

                    "criterio":
                        criterio,

                    "id_cita_ganadora":
                        ganador[
                            "id_cita"
                        ],
                }
            )

    # ========================================================
    # 6. REUNIR GANADORES + CLAVES INCOMPLETAS
    # ========================================================

    if ganadores:

        ganadores_df = pd.DataFrame(
            ganadores
        )

    else:

        ganadores_df = candidatos.iloc[
            0:0
        ].copy()

    operativas = pd.concat(
        [
            ganadores_df,
            incompletos,
        ],
        ignore_index=True,
    )

    operativas = operativas.drop(
        columns=[
            "_clave_fecha_hora",
            "_appointment_number_num",
        ],
        errors="ignore",
    )

    operativas = (
        operativas
        .sort_values(
            [
                "fecha_hora_cita_lima",
                "appointment_number",
            ],
            kind="stable",
        )
        .reset_index(
            drop=True
        )
    )

    auditoria_df = pd.DataFrame(
        auditoria
    )

    resumen = {
        "eliminadas_isdeleted":
            len(eliminadas),

        "canceladas_status":
            len(canceladas),

        "antes_deduplicacion":
            cantidad_antes_deduplicacion,

        "grupos_duplicados":
            grupos_duplicados,

        "descartadas_duplicacion":
            (
                cantidad_antes_deduplicacion
                -
                len(operativas)
            ),

        "ganadores_callcenter":
            ganadores_callcenter,

        "ganadores_mayor_id":
            ganadores_mayor_id,

        "operativas":
            len(operativas),

        "sin_placa":
            int(
                operativas[
                    "placa_normalizada"
                ].eq(
                    ""
                ).sum()
            ),
    }

    return (
        operativas,
        resumen,
        auditoria_df,
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

    Recibe exclusivamente el universo operativo de citas.

    Reglas:
    - una presencia solo puede acreditar una cita;
    - una cita solo puede recibir una presencia;
    - se conserva todo el universo de agentes;
    - Call Center ya viene clasificado desde la fuente
      oficial del proyecto;
    - si varias citas válidas de la misma placa/fecha
      pertenecen al mismo agente y exactamente una es
      Preventivo, se prioriza Preventivo;
    - si persiste la ambigüedad, queda para decisión manual.
    """

    resultado = citas.copy()

    # ========================================================
    # VALIDACIÓN
    # ========================================================

    if (
        "es_callcenter"
        not in resultado.columns
    ):

        raise ValueError(
            "Las citas recibidas por calcular_nivel_1 "
            "no contienen 'es_callcenter'. "
            "Primero debe construirse el universo operativo."
        )

    # ========================================================
    # PERÍODO EVALUADO
    # ========================================================

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

    # ========================================================
    # EVIDENCIA
    # ========================================================

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

    # ========================================================
    # ESTADOS INICIALES
    # ========================================================

    resultado[
        "estado_nivel_1"
    ] = "SIN_EVIDENCIA"

    resultado[
        "criterio_asignacion"
    ] = ""

    resultado[
        "es_ambigua"
    ] = False

    candidatos = resultado.loc[
        resultado[
            "fuente"
        ].notna()
    ].copy()

    if candidatos.empty:
        return resultado

    # ========================================================
    # RESOLVER PRESENCIA POR PLACA + FECHA
    # ========================================================

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
        # UNA SOLA CITA
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
        # PRIORIDAD PERÍODO
        # ----------------------------------------------------

        grupo_periodo = grupo.loc[
            grupo[
                "en_periodo_evaluado"
            ]
        ]

        if len(grupo_periodo) == 1:

            indice_ganador = (
                grupo_periodo.index[0]
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
        # MISMO AGENTE + PREVENTIVO
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
        # AMBIGÜEDAD REAL
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


def construir_resultado_efectividad(
    citas: pd.DataFrame,
    matches: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combina el universo completo de citas operativas
    con los matches N1/N2/N3.

    Las citas sin presencia quedan identificadas
    explícitamente.
    """

    resultado = citas.copy()

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

    resultado[
        "estado_efectividad"
    ] = resultado[
        "estado_efectividad"
    ].fillna(
        "SIN_PRESENCIA"
    )

    resultado[
        "persona_creditada"
    ] = resultado[
        "persona_creditada"
    ].fillna(
        resultado[
            "agente"
        ]
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

    return resultado


def imprimir_resultado_matching(
    resultado: pd.DataFrame,
) -> None:
    """
    Imprime el resultado consolidado de efectividad
    N1 / N2 / N3.
    """

    print()
    print("=" * 88)
    print(
        "EFECTIVIDAD — MATCHING GLOBAL"
    )
    print("=" * 88)

    total = len(
        resultado
    )

    nivel_1 = int(
        resultado[
            "estado_efectividad"
        ].eq(
            "EFECTIVA_NIVEL_1"
        ).sum()
    )

    nivel_2 = int(
        resultado[
            "estado_efectividad"
        ].eq(
            "EFECTIVA_NIVEL_2"
        ).sum()
    )

    nivel_3 = int(
        resultado[
            "estado_efectividad"
        ].eq(
            "EFECTIVA_NIVEL_3"
        ).sum()
    )

    sin_presencia = int(
        resultado[
            "estado_efectividad"
        ].eq(
            "SIN_PRESENCIA"
        ).sum()
    )

    revision_manual = int(
        resultado[
            "requiere_revision_manual"
        ].sum()
    )

    efectivas = (
        nivel_1
        +
        nivel_2
        +
        nivel_3
    )

    porcentaje = (
        efectivas
        /
        total
        *
        100
        if total
        else 0
    )

    print(
        f"Citas operativas                  "
        f"{total:>10,}"
    )

    print(
        f"Efectivas Nivel 1                 "
        f"{nivel_1:>10,}"
    )

    print(
        f"Efectivas Nivel 2                 "
        f"{nivel_2:>10,}"
    )

    print(
        f"Efectivas Nivel 3                 "
        f"{nivel_3:>10,}"
    )

    print(
        f"Efectivas totales                 "
        f"{efectivas:>10,}"
    )

    print(
        f"Sin presencia                     "
        f"{sin_presencia:>10,}"
    )

    print(
        f"Requieren revisión manual         "
        f"{revision_manual:>10,}"
    )

    print(
        f"Efectividad total                 "
        f"{porcentaje:>9.1f}%"
    )

    # ========================================================
    # POR AGENTE
    # ========================================================

    resumen = (
        resultado
        .groupby(
            "agente",
            dropna=False,
        )
        .agg(
            citas=(
                "id_cita",
                "count",
            ),

            nivel_1=(
                "estado_efectividad",
                lambda s:
                    s.eq(
                        "EFECTIVA_NIVEL_1"
                    ).sum(),
            ),

            nivel_2=(
                "estado_efectividad",
                lambda s:
                    s.eq(
                        "EFECTIVA_NIVEL_2"
                    ).sum(),
            ),

            nivel_3=(
                "estado_efectividad",
                lambda s:
                    s.eq(
                        "EFECTIVA_NIVEL_3"
                    ).sum(),
            ),

            sin_presencia=(
                "estado_efectividad",
                lambda s:
                    s.eq(
                        "SIN_PRESENCIA"
                    ).sum(),
            ),

            revision_manual=(
                "requiere_revision_manual",
                "sum",
            ),
        )
        .reset_index()
    )

    resumen[
        "efectivas"
    ] = (
        resumen[
            "nivel_1"
        ]
        +
        resumen[
            "nivel_2"
        ]
        +
        resumen[
            "nivel_3"
        ]
    )

    resumen[
        "efectividad_pct"
    ] = (
        resumen[
            "efectivas"
        ]
        /
        resumen[
            "citas"
        ]
        *
        100
    ).round(
        1
    )

    resumen = resumen.sort_values(
        "citas",
        ascending=False,
    )

    print()
    print("-" * 88)
    print(
        "EFECTIVIDAD POR AGENTE"
    )
    print("-" * 88)

    print(
        resumen.to_string(
            index=False
        )
    )

    # ========================================================
    # REVISIONES
    # ========================================================

    revisar = resultado.loc[
        resultado[
            "requiere_revision_manual"
        ]
    ].copy()

    if not revisar.empty:

        print()
        print("-" * 88)
        print(
            "CASOS PARA REVISIÓN MANUAL"
        )
        print("-" * 88)

        columnas = [
            "appointment_number",
            "placa_normalizada",
            "fecha_cita",
            "agente",
            "motivos",
            "fecha_visita",
            "diferencia_dias",
            "nivel_efectividad",
            "presencia_id",
        ]

        print(
            revisar[
                columnas
            ]
            .to_string(
                index=False
            )
        )


def auditar_nivel_1_antiguo_vs_global(
    resultado_nivel_1: pd.DataFrame,
    matches_globales: pd.DataFrame,
) -> None:
    """
    Compara las citas consideradas efectivas Nivel 1
    por el método antiguo contra las asignadas como
    Nivel 1 por el matching global.

    Permite detectar:
    - N1 antiguo que dejó de ser N1;
    - N1 nuevo que antes no era efectivo;
    - presencia finalmente utilizada por la cita afectada.
    """

    print()
    print("=" * 96)
    print(
        "AUDITORÍA — NIVEL 1 ANTIGUO VS MATCHING GLOBAL"
    )
    print("=" * 96)

    antiguos = (
        resultado_nivel_1.loc[
            resultado_nivel_1[
                "estado_nivel_1"
            ].eq(
                "EFECTIVA_NIVEL_1"
            )
        ]
        .copy()
    )

    nuevos = (
        matches_globales.loc[
            matches_globales[
                "nivel_efectividad"
            ].eq(1)
        ]
        .copy()
    )

    ids_antiguos = set(
        antiguos[
            "id_cita"
        ]
    )

    ids_nuevos = set(
        nuevos[
            "id_cita"
        ]
    )

    perdieron_n1 = (
        ids_antiguos
        -
        ids_nuevos
    )

    ganaron_n1 = (
        ids_nuevos
        -
        ids_antiguos
    )

    print(
        f"N1 método antiguo                  "
        f"{len(ids_antiguos):>10,}"
    )

    print(
        f"N1 matching global                "
        f"{len(ids_nuevos):>10,}"
    )

    print(
        f"Antiguos N1 que dejaron de ser N1 "
        f"{len(perdieron_n1):>10,}"
    )

    print(
        f"Nuevos N1 no presentes antes      "
        f"{len(ganaron_n1):>10,}"
    )

    # ========================================================
    # ANTIGUOS N1 DESPLAZADOS
    # ========================================================

    if perdieron_n1:

        afectados = (
            antiguos.loc[
                antiguos[
                    "id_cita"
                ].isin(
                    perdieron_n1
                )
            ]
            .copy()
        )

        estado_final = (
            matches_globales[
                [
                    "id_cita",
                    "presencia_id",
                    "fecha_visita",
                    "diferencia_dias",
                    "nivel_efectividad",
                    "estado_efectividad",
                    "persona_creditada",
                ]
            ]
            .rename(
                columns={
                    "presencia_id":
                        "presencia_global",

                    "fecha_visita":
                        "fecha_visita_global",

                    "diferencia_dias":
                        "diferencia_global",

                    "nivel_efectividad":
                        "nivel_global",
                }
            )
        )

        afectados = afectados.merge(
            estado_final,
            on="id_cita",
            how="left",
        )

        print()
        print("-" * 96)
        print(
            "NIVEL 1 ANTIGUO QUE FUE DESPLAZADO"
        )
        print("-" * 96)

        columnas = [
            "appointment_number",
            "placa_normalizada",
            "fecha_cita",
            "agente",
            "motivos",
            "fuente",
            "presencia_global",
            "fecha_visita_global",
            "diferencia_global",
            "nivel_global",
        ]

        columnas = [
            columna
            for columna in columnas
            if columna in afectados.columns
        ]

        print(
            afectados[
                columnas
            ].to_string(
                index=False
            )
        )

    # ========================================================
    # NUEVOS N1
    # ========================================================

    if ganaron_n1:

        ganadores = (
            nuevos.loc[
                nuevos[
                    "id_cita"
                ].isin(
                    ganaron_n1
                )
            ]
            .copy()
        )

        print()
        print("-" * 96)
        print(
            "NUEVOS NIVEL 1 DEL MATCHING GLOBAL"
        )
        print("-" * 96)

        columnas = [
            "appointment_number",
            "placa_normalizada",
            "fecha_cita",
            "agente_original",
            "fecha_visita",
            "presencia_id",
        ]

        print(
            ganadores[
                columnas
            ].to_string(
                index=False
            )
        )


def imprimir_detalle_revisiones_matching(
    resultado_matching: pd.DataFrame,
    citas: pd.DataFrame,
    presencias: pd.DataFrame,
) -> None:
    """
    Para cada match marcado para revisión manual,
    reconstruye todas las citas de la misma placa que
    podían competir por esa presencia dentro de N1/N2/N3.

    Esta función es solo diagnóstica.
    """

    revisiones = resultado_matching.loc[
        resultado_matching[
            "requiere_revision_manual"
        ]
    ].copy()

    if revisiones.empty:
        return

    print()
    print("=" * 96)
    print(
        "DETALLE DE CONFLICTOS — REVISIÓN MANUAL"
    )
    print("=" * 96)

    for _, match in revisiones.iterrows():

        placa = match[
            "placa_normalizada"
        ]

        fecha_visita = pd.to_datetime(
            match[
                "fecha_visita"
            ]
        ).date()

        citas_placa = citas.loc[
            citas[
                "placa_normalizada"
            ].eq(
                placa
            )
        ].copy()

        registros = []

        for _, cita in citas_placa.iterrows():

            fecha_cita = pd.to_datetime(
                cita[
                    "fecha_cita"
                ]
            ).date()

            diferencia = (
                fecha_visita
                -
                fecha_cita
            ).days

            if diferencia == 0:
                nivel = 1

            elif (
                diferencia == -1
                or 1 <= diferencia <= 3
            ):
                nivel = 2

            elif (
                -4 <= diferencia <= -2
                or 4 <= diferencia <= 7
            ):
                nivel = 3

            else:
                continue

            registros.append(
                {
                    "appointment_number":
                        cita[
                            "appointment_number"
                        ],

                    "id_cita":
                        cita[
                            "id_cita"
                        ],

                    "placa":
                        placa,

                    "fecha_cita":
                        fecha_cita,

                    "fecha_visita":
                        fecha_visita,

                    "diferencia_dias":
                        diferencia,

                    "nivel":
                        nivel,

                    "agente":
                        cita[
                            "agente"
                        ],

                    "motivos":
                        cita[
                            "motivos"
                        ],

                    "fecha_creacion":
                        cita[
                            "fecha_creacion_lima"
                        ],

                    "es_match_actual":
                        (
                            cita[
                                "id_cita"
                            ]
                            ==
                            match[
                                "id_cita"
                            ]
                        ),
                }
            )

        detalle = pd.DataFrame(
            registros
        )

        if detalle.empty:
            continue

        detalle = detalle.sort_values(
            [
                "nivel",
                "diferencia_dias",
                "fecha_creacion",
                "appointment_number",
            ],
            kind="stable",
        )

        print()
        print(
            f"Presencia: "
            f"{match['presencia_id']}"
        )

        print(
            f"Ganador actual: "
            f"{match['appointment_number']} "
            f"— {match['agente_original']}"
        )

        print()

        print(
            detalle.to_string(
                index=False
            )
        )

def auditar_placa_matching(
    placa: str,
    citas: pd.DataFrame,
    presencias: pd.DataFrame,
    matches: pd.DataFrame,
) -> None:
    """
    Muestra todas las citas, todas las presencias y los matches
    finales de una placa.

    Sirve para entender redistribuciones del matching global.
    """

    placa = str(
        placa
    ).strip().upper()

    citas_placa = (
        citas.loc[
            citas[
                "placa_normalizada"
            ].eq(
                placa
            )
        ]
        .copy()
        .sort_values(
            [
                "fecha_cita",
                "appointment_number",
            ],
            kind="stable",
        )
    )

    presencias_placa = (
        presencias.loc[
            presencias[
                "placa_normalizada"
            ].eq(
                placa
            )
        ]
        .copy()
        .sort_values(
            "fecha_visita",
            kind="stable",
        )
    )

    matches_placa = (
        matches.loc[
            matches[
                "placa_normalizada"
            ].eq(
                placa
            )
        ]
        .copy()
        .sort_values(
            [
                "fecha_cita",
                "appointment_number",
            ],
            kind="stable",
        )
    )

    print()
    print("=" * 100)
    print(
        f"AUDITORÍA COMPLETA DE PLACA — {placa}"
    )
    print("=" * 100)

    # ========================================================
    # CITAS
    # ========================================================

    print()
    print("-" * 100)
    print("CITAS")
    print("-" * 100)

    if citas_placa.empty:

        print("Sin citas.")

    else:

        columnas = [
            "appointment_number",
            "id_cita",
            "fecha_cita",
            "fecha_creacion_lima",
            "agente",
            "motivos",
        ]

        print(
            citas_placa[
                columnas
            ].to_string(
                index=False
            )
        )

    # ========================================================
    # PRESENCIAS
    # ========================================================

    print()
    print("-" * 100)
    print("PRESENCIAS")
    print("-" * 100)

    if presencias_placa.empty:

        print("Sin presencias.")

    else:

        columnas = [
            "presencia_id",
            "fecha_visita",
            "fuente",
        ]

        columnas = [
            columna
            for columna in columnas
            if columna
            in presencias_placa.columns
        ]

        print(
            presencias_placa[
                columnas
            ].to_string(
                index=False
            )
        )

    # ========================================================
    # TODAS LAS COMBINACIONES POSIBLES
    # ========================================================

    print()
    print("-" * 100)
    print("COMBINACIONES VÁLIDAS N1 / N2 / N3")
    print("-" * 100)

    combinaciones = []

    for _, cita in citas_placa.iterrows():

        fecha_cita = pd.to_datetime(
            cita[
                "fecha_cita"
            ]
        ).date()

        for _, presencia in (
            presencias_placa.iterrows()
        ):

            fecha_visita = pd.to_datetime(
                presencia[
                    "fecha_visita"
                ]
            ).date()

            diferencia = (
                fecha_visita
                -
                fecha_cita
            ).days

            if diferencia == 0:
                nivel = 1

            elif (
                diferencia == -1
                or 1 <= diferencia <= 3
            ):
                nivel = 2

            elif (
                -4 <= diferencia <= -2
                or 4 <= diferencia <= 7
            ):
                nivel = 3

            else:
                continue

            combinaciones.append(
                {
                    "appointment_number":
                        cita[
                            "appointment_number"
                        ],

                    "fecha_cita":
                        fecha_cita,

                    "agente":
                        cita[
                            "agente"
                        ],

                    "motivos":
                        cita[
                            "motivos"
                        ],

                    "presencia_id":
                        presencia[
                            "presencia_id"
                        ],

                    "fecha_visita":
                        fecha_visita,

                    "diferencia_dias":
                        diferencia,

                    "nivel":
                        nivel,
                }
            )

    combinaciones_df = pd.DataFrame(
        combinaciones
    )

    if combinaciones_df.empty:

        print("Sin combinaciones válidas.")

    else:

        print(
            combinaciones_df
            .sort_values(
                [
                    "appointment_number",
                    "nivel",
                    "fecha_visita",
                ],
                kind="stable",
            )
            .to_string(
                index=False
            )
        )

    # ========================================================
    # MATCHING FINAL
    # ========================================================

    print()
    print("-" * 100)
    print("MATCHING FINAL")
    print("-" * 100)

    if matches_placa.empty:

        print("Ninguna cita terminó efectiva.")

    else:

        columnas = [
            "appointment_number",
            "agente_original",
            "fecha_cita",
            "presencia_id",
            "fecha_visita",
            "diferencia_dias",
            "nivel_efectividad",
            "estado_efectividad",
        ]

        print(
            matches_placa[
                columnas
            ].to_string(
                index=False
            )
        )

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


def imprimir_auditoria_universo(
    citas_logicas: pd.DataFrame,
    resumen_universo: dict,
    auditoria: pd.DataFrame,
) -> None:

    print()
    print("=" * 72)
    print(
        "UNIVERSO OPERATIVO DE CITAS"
    )
    print("=" * 72)

    valores = [
        (
            "Citas lógicas Key_merge",
            len(
                citas_logicas
            ),
        ),
        (
            "Excluidas isDeleted",
            resumen_universo[
                "eliminadas_isdeleted"
            ],
        ),
        (
            "Excluidas status cancelado",
            resumen_universo[
                "canceladas_status"
            ],
        ),
        (
            "Activas antes de deduplicar",
            resumen_universo[
                "antes_deduplicacion"
            ],
        ),
        (
            "Grupos duplicados operativos",
            resumen_universo[
                "grupos_duplicados"
            ],
        ),
        (
            "Citas descartadas duplicación",
            resumen_universo[
                "descartadas_duplicacion"
            ],
        ),
        (
            "Grupos ganados por Call Center",
            resumen_universo[
                "ganadores_callcenter"
            ],
        ),
        (
            "Grupos ganados por mayor ID",
            resumen_universo[
                "ganadores_mayor_id"
            ],
        ),
        (
            "Citas operativas finales",
            resumen_universo[
                "operativas"
            ],
        ),
        (
            "Operativas sin placa",
            resumen_universo[
                "sin_placa"
            ],
        ),
    ]

    for etiqueta, valor in valores:

        print(
            f"{etiqueta:<40}"
            f"{valor:>10,}"
        )

    # ========================================================
    # DISTRIBUCIÓN STATUS
    # ========================================================

    print()
    print("-" * 72)
    print(
        "DISTRIBUCIÓN STATUS — CITAS LÓGICAS"
    )
    print("-" * 72)

    distribucion_status = (
        citas_logicas[
            "status"
        ]
        .fillna(
            "SIN_STATUS"
        )
        .astype(str)
        .value_counts()
        .rename_axis(
            "status"
        )
        .reset_index(
            name="citas"
        )
    )

    print(
        distribucion_status.to_string(
            index=False
        )
    )

    # ========================================================
    # MUESTRA DE DESCARTES
    # ========================================================

    print()
    print("-" * 72)
    print(
        "AUDITORÍA DE CITAS EXCLUIDAS / DESCARTADAS"
    )
    print("-" * 72)

    if auditoria.empty:

        print(
            "No existen citas descartadas."
        )

        return

    columnas = [
        "appointment_number",
        "placa",
        "fecha_cita",
        "agente",
        "motivos",
        "status",
        "accion",
        "criterio",
        "id_cita_ganadora",
    ]

    print(
        auditoria[
            columnas
        ]
        .head(
            100
        )
        .to_string(
            index=False
        )
    )

    if len(auditoria) > 100:

        print()
        print(
            f"... mostrando 100 de "
            f"{len(auditoria):,} registros."
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
                "Filas crudas Databricks",
                resumen_a[
                    "filas_raw"
                ],
            ),
            (
                "Citas lógicas Key_merge",
                resumen_a[
                    "citas_unicas"
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

    citas_logicas, resumen_a = (
        consolidar_citas(
            citas_raw
        )
    )

    (
        citas,
        resumen_universo,
        auditoria_universo,
    ) = construir_universo_operativo_citas(
        citas_logicas
    )

    imprimir_auditoria_universo(
        citas_logicas=citas_logicas,
        resumen_universo=resumen_universo,
        auditoria=auditoria_universo,
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
    # MATCHING GLOBAL N1 / N2 / N3
    # ========================================================

    print()
    print(
        "🐿️ Calculando matching global "
        "Nivel 1 / Nivel 2 / Nivel 3..."
    )

    matches = calcular_matching_efectividad(
        citas=citas,
        presencias=presencias,
    )

    auditar_placa_matching(
        placa="DAQ057",
        citas=citas,
        presencias=presencias,
        matches=matches,
    )

    resultado_matching = (
        construir_resultado_efectividad(
            citas=citas,
            matches=matches,
        )
    )

    imprimir_resultado_matching(
        resultado_matching
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

    auditar_nivel_1_antiguo_vs_global(
        resultado_nivel_1=resultado,
        matches_globales=matches,
    )

    imprimir_detalle_revisiones_matching(
        resultado_matching=matches,
        citas=citas,
        presencias=presencias,
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

