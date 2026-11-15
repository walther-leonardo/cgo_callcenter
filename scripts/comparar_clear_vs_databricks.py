from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd

from procesamiento import (
    cargar_clearmechanic,
    _normalizar_clave_celular,
    _normalizar_clave_placa,
)

from scripts.diagnostico_efectividad_databricks import (
    TABLA_CITAS,
    agregar_textos_unicos,
    consultar_databricks,
    convertir_booleano,
    limites_utc_desde_lima,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

ARCHIVO_CLEAR = (
    PROJECT_ROOT
    /
    "clear.xlsx"
)


def normalizar_id_cita(
    serie: pd.Series,
) -> pd.Series:
    """
    Convierte appointmentNumber / id_cita a entero nullable.
    """

    return pd.to_numeric(
        serie,
        errors="coerce",
    ).astype(
        "Int64"
    )


def normalizar_texto(
    valor,
) -> str:
    if pd.isna(valor):
        return ""

    return " ".join(
        str(valor)
        .strip()
        .upper()
        .split()
    )


def cargar_clear() -> pd.DataFrame:
    """
    Carga el archivo manual de ClearMechanic utilizando
    exactamente el mismo parser del proyecto.
    """

    if not ARCHIVO_CLEAR.exists():

        raise FileNotFoundError(
            "No encontré el archivo:\n"
            f"{ARCHIVO_CLEAR}"
        )

    df = cargar_clearmechanic(
        ARCHIVO_CLEAR
    )

    df[
        "id_cita"
    ] = normalizar_id_cita(
        df[
            "id_cita"
        ]
    )

    df[
        "placa_normalizada"
    ] = df[
        "placa"
    ].apply(
        _normalizar_clave_placa
    )

    df[
        "celular_normalizado"
    ] = df[
        "celular"
    ].apply(
        _normalizar_clave_celular
    )

    df[
        "estatus_normalizado"
    ] = df[
        "estatus_cita"
    ].apply(
        normalizar_texto
    )

    df[
        "es_cancelada_clear"
    ] = df[
        "estatus_normalizado"
    ].eq(
        "CANCELADA"
    )

    return df


def obtener_periodo() -> tuple:
    """
    Detecta el período directamente desde clear.xlsx.

    Se lee el Excel crudo para no depender de la conversión
    de fechas de cargar_clearmechanic(), ya que ClearMechanic
    puede exportar la fecha como:
    - datetime real de Excel;
    - serial numérico de Excel;
    - texto.
    """

    raw = pd.read_excel(
        ARCHIVO_CLEAR
    )

    columna_fecha = (
        "FECHA PROGRAMADA DE LA CITA"
    )

    if columna_fecha not in raw.columns:
        raise ValueError(
            "clear.xlsx no contiene la columna "
            f"'{columna_fecha}'."
        )

    serie = raw[
        columna_fecha
    ]

    # ========================================================
    # 1. INTENTAR FECHAS/DATETIME DIRECTAMENTE
    # ========================================================

    fechas = pd.to_datetime(
        serie,
        errors="coerce",
        dayfirst=True,
    )

    # ========================================================
    # 2. PARA LO QUE NO CONVIRTIÓ, INTENTAR SERIAL EXCEL
    # ========================================================

    faltantes = fechas.isna()

    if faltantes.any():

        numericos = pd.to_numeric(
            serie.loc[
                faltantes
            ],
            errors="coerce",
        )

        fechas_serial = pd.to_datetime(
            numericos,
            unit="D",
            origin="1899-12-30",
            errors="coerce",
        )

        fechas.loc[
            faltantes
        ] = fechas_serial

    fechas = fechas.dropna()

    if fechas.empty:
        raise ValueError(
            "clear.xlsx no contiene fechas programadas "
            "válidas incluso leyendo el Excel crudo."
        )

    desde = (
        fechas
        .min()
        .date()
    )

    hasta = (
        fechas
        .max()
        .date()
        +
        timedelta(
            days=1
        )
    )

    return (
        desde,
        hasta,
    )


def obtener_databricks(
    desde,
    hasta,
) -> pd.DataFrame:
    """
    Obtiene las citas de Databricks correspondientes al
    mismo período del archivo manual.
    """

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

    raw = consultar_databricks(
        consulta,
        {
            "desde_utc":
                desde_utc,

            "hasta_utc":
                hasta_utc,
        },
    )

    if raw.empty:
        return raw

    # ========================================================
    # CONSOLIDAR KEY_MERGE
    # ========================================================

    df = (
        raw
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
        )
    )

    df[
        "id_cita"
    ] = normalizar_id_cita(
        df[
            "appointmentNumber"
        ]
    )

    df[
        "is_deleted"
    ] = df[
        "isDeleted"
    ].apply(
        convertir_booleano
    )

    df[
        "placa_normalizada"
    ] = df[
        "licensePlate"
    ].apply(
        _normalizar_clave_placa
    )

    df[
        "celular_normalizado"
    ] = df[
        "mobile"
    ].apply(
        _normalizar_clave_celular
    )

    fecha_utc = pd.to_datetime(
        df[
            "startDate"
        ],
        errors="coerce",
        utc=True,
    )

    df[
        "fecha_hora_lima"
    ] = (
        fecha_utc
        .dt.tz_convert(
            "America/Lima"
        )
    )

    df[
        "fecha_programada_db"
    ] = (
        df[
            "fecha_hora_lima"
        ]
        .dt.date
    )

    df[
        "hora_programada_db"
    ] = (
        df[
            "fecha_hora_lima"
        ]
        .dt.strftime(
            "%H:%M"
        )
    )

    return df


def comparar(
    clear: pd.DataFrame,
    db: pd.DataFrame,
) -> pd.DataFrame:
    """
    Une ambos mundos por número de cita.
    """

    clear_cmp = clear[
        [
            "id_cita",
            "estatus_cita",
            "es_cancelada_clear",
            "placa_normalizada",
            "celular_normalizado",
            "fecha_programada",
            "hora_programada",
            "persona_agenda",
            "motivo_visita",
        ]
    ].copy()

    clear_cmp = clear_cmp.rename(
        columns={
            "placa_normalizada":
                "placa_clear",

            "celular_normalizado":
                "celular_clear",

            "fecha_programada":
                "fecha_clear",

            "hora_programada":
                "hora_clear",

            "persona_agenda":
                "agente_clear",

            "motivo_visita":
                "motivo_clear",
        }
    )

    db_cmp = db[
        [
            "id_cita",
            "Key_merge",
            "status",
            "is_deleted",
            "placa_normalizada",
            "celular_normalizado",
            "fecha_programada_db",
            "hora_programada_db",
            "userWhoSchedule",
            "motivos",
        ]
    ].copy()

    db_cmp = db_cmp.rename(
        columns={
            "placa_normalizada":
                "placa_db",

            "celular_normalizado":
                "celular_db",

            "userWhoSchedule":
                "agente_db",

            "motivos":
                "motivo_db",
        }
    )

    resultado = clear_cmp.merge(
        db_cmp,
        on="id_cita",
        how="outer",
        indicator=True,
    )

    resultado[
        "es_cancelada_clear"
    ] = (
        resultado[
            "es_cancelada_clear"
        ]
        .fillna(False)
        .astype(bool)
    )

    resultado[
        "is_deleted"
    ] = (
        resultado[
            "is_deleted"
        ]
        .fillna(False)
        .astype(bool)
    )

    resultado[
        "coincide_placa"
    ] = (
        resultado[
            "placa_clear"
        ]
        ==
        resultado[
            "placa_db"
        ]
    )

    resultado[
        "coincide_celular"
    ] = (
        resultado[
            "celular_clear"
        ]
        ==
        resultado[
            "celular_db"
        ]
    )

    resultado[
        "coincide_agente"
    ] = (
        resultado[
            "agente_clear"
        ]
        .fillna("")
        .apply(
            normalizar_texto
        )
        ==
        resultado[
            "agente_db"
        ]
        .fillna("")
        .apply(
            normalizar_texto
        )
    )

    return resultado


def imprimir_resumen(
    clear: pd.DataFrame,
    db: pd.DataFrame,
    comparacion: pd.DataFrame,
) -> None:

    print()
    print("=" * 76)
    print(
        "CLEARMECHANIC MANUAL VS DATABRICKS"
    )
    print("=" * 76)

    print(
        f"Registros Clear                   "
        f"{len(clear):>8,}"
    )

    print(
        f"Canceladas Clear                  "
        f"{int(clear['es_cancelada_clear'].sum()):>8,}"
    )

    print(
        f"Citas lógicas Databricks          "
        f"{len(db):>8,}"
    )

    print(
        f"isDeleted=True Databricks         "
        f"{int(db['is_deleted'].sum()):>8,}"
    )

    print()
    print("-" * 76)
    print(
        "COBERTURA POR NÚMERO DE CITA"
    )
    print("-" * 76)





    solo_databricks = comparacion.loc[
        comparacion[
            "_merge"
        ].eq(
            "right_only"
        )
    ].copy()

    print()
    print("-" * 76)
    print(
        "SOLO DATABRICKS — NO APARECEN EN CLEAR"
    )
    print("-" * 76)

    print(
        f"Total solo Databricks             "
        f"{len(solo_databricks):>8,}"
    )

    if not solo_databricks.empty:

        cantidad_deleted = int(
            solo_databricks[
                "is_deleted"
            ].astype(bool).sum()
        )

        cantidad_no_deleted = (
            len(solo_databricks)
            -
            cantidad_deleted
        )

        print(
            f"Con isDeleted=True                "
            f"{cantidad_deleted:>8,}"
        )

        print(
            f"Con isDeleted=False               "
            f"{cantidad_no_deleted:>8,}"
        )

        print()
        print(
            solo_databricks[
                [
                    "id_cita",
                    "status",
                    "is_deleted",
                    "placa_db",
                    "fecha_programada_db",
                    "hora_programada_db",
                    "agente_db",
                    "motivo_db",
                ]
            ]
            .sort_values(
                [
                    "is_deleted",
                    "id_cita",
                ],
                ascending=[
                    True,
                    True,
                ],
            )
            .to_string(
                index=False
            )
        )


    





    conteo_merge = (
        comparacion[
            "_merge"
        ]
        .value_counts()
    )

    print(
        f"En ambos                          "
        f"{int(conteo_merge.get('both', 0)):>8,}"
    )

    print(
        f"Solo Clear                        "
        f"{int(conteo_merge.get('left_only', 0)):>8,}"
    )

    print(
        f"Solo Databricks                   "
        f"{int(conteo_merge.get('right_only', 0)):>8,}"
    )

    # ========================================================
    # CANCELACIONES
    # ========================================================

    ambos = comparacion.loc[
        comparacion[
            "_merge"
        ].eq(
            "both"
        )
    ].copy()

    canceladas = ambos.loc[
        ambos[
            "es_cancelada_clear"
        ].fillna(
            False
        )
    ].copy()

    print()
    print("-" * 76)
    print(
        "CANCELADAS CLEAR → DATABRICKS"
    )
    print("-" * 76)

    print(
        f"Canceladas comparables            "
        f"{len(canceladas):>8,}"
    )

    print(
        f"Cancelada + isDeleted=True        "
        f"{int(canceladas['is_deleted'].fillna(False).sum()):>8,}"
    )

    print(
        f"Cancelada + isDeleted=False       "
        f"{int((~canceladas['is_deleted'].fillna(False)).sum()):>8,}"
    )

    # ========================================================
    # ACTIVAS
    # ========================================================

    activas = ambos.loc[
        ~ambos[
            "es_cancelada_clear"
        ].astype(bool)
    ].copy()

    print()
    print("-" * 76)
    print(
        "ACTIVAS CLEAR → DATABRICKS"
    )
    print("-" * 76)

    print(
        f"Activas comparables               "
        f"{len(activas):>8,}"
    )

    print(
        f"Activa + isDeleted=True           "
        f"{int(activas['is_deleted'].fillna(False).sum()):>8,}"
    )

    print(
        f"Activa + isDeleted=False          "
        f"{int((~activas['is_deleted'].fillna(False)).sum()):>8,}"
    )

    # ========================================================
    # STATUS DATABRICKS
    # ========================================================

    print()
    print("-" * 76)
    print(
        "STATUS DATABRICKS — CITAS COMPARABLES"
    )
    print("-" * 76)

    distribucion = (
        ambos[
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
        distribucion.to_string(
            index=False
        )
    )

    # ========================================================
    # DETALLE CANCELADAS
    # ========================================================

    if not canceladas.empty:

        print()
        print("-" * 76)
        print(
            "DETALLE DE CANCELADAS"
        )
        print("-" * 76)

        columnas = [
            "id_cita",
            "estatus_cita",
            "status",
            "is_deleted",
            "placa_clear",
            "placa_db",
            "agente_clear",
            "agente_db",
        ]

        print(
            canceladas[
                columnas
            ].to_string(
                index=False
            )
        )

    # ========================================================
    # INCONSISTENCIAS CLAVE
    # ========================================================

    inconsistencias = ambos.loc[
        ~(
            ambos[
                "coincide_placa"
            ]
            &
            ambos[
                "coincide_celular"
            ]
            &
            ambos[
                "coincide_agente"
            ]
        )
    ].copy()

    print()
    print("-" * 76)
    print(
        "INCONSISTENCIAS EN CAMPOS CLAVE"
    )
    print("-" * 76)

    print(
        f"Citas con alguna diferencia       "
        f"{len(inconsistencias):>8,}"
    )

    if not inconsistencias.empty:

        columnas = [
            "id_cita",
            "placa_clear",
            "placa_db",
            "celular_clear",
            "celular_db",
            "agente_clear",
            "agente_db",
        ]

        print()

        print(
            inconsistencias[
                columnas
            ]
            .head(
                50
            )
            .to_string(
                index=False
            )
        )


def main() -> None:

    clear = cargar_clear()

    desde, hasta = obtener_periodo()

    print()
    print(
        "🐿️ Período detectado en clear.xlsx:"
    )

    print(
        f"   {desde:%d/%m/%Y}"
        f" → "
        f"{hasta:%d/%m/%Y} "
        "(fin exclusivo)"
    )

    print()
    print(
        "🐔 Consultando Databricks..."
    )

    db = obtener_databricks(
        desde=desde,
        hasta=hasta,
    )

    comparacion = comparar(
        clear=clear,
        db=db,
    )

    imprimir_resumen(
        clear=clear,
        db=db,
        comparacion=comparacion,
    )

    print()
    print("=" * 76)
    print(
        "✅ COMPARACIÓN FINALIZADA — SOLO LECTURA"
    )
    print("=" * 76)


if __name__ == "__main__":
    main()