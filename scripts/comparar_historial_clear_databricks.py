from __future__ import annotations

import re
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from scripts.diagnostico_efectividad_databricks import (
    TABLA_CITAS,
    consultar_databricks,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ZONA_LIMA = ZoneInfo("America/Lima")
ZONA_UTC = ZoneInfo("UTC")


ARCHIVOS = [
    {
        "mes": "SEPTIEMBRE",
        "archivo": PROJECT_ROOT / "clear_09.xlsx",
        "desde": date(2026, 9, 1),
        "hasta": date(2026, 10, 1),
    },
    {
        "mes": "OCTUBRE",
        "archivo": PROJECT_ROOT / "clear.xlsx",
        "desde": date(2026, 10, 1),
        "hasta": date(2026, 11, 1),
    },
    {
        "mes": "NOVIEMBRE",
        "archivo": PROJECT_ROOT / "clear_11.xlsx",
        "desde": date(2026, 11, 1),
        # 15/11 exclusivo = incluye hasta el 14/11.
        "hasta": date(2026, 11, 15),
    },
]


def normalizar_texto(valor) -> str:
    if pd.isna(valor):
        return ""

    return " ".join(
        str(valor)
        .strip()
        .upper()
        .split()
    )


def normalizar_placa(valor) -> str:
    texto = normalizar_texto(valor)

    return re.sub(
        r"[^A-Z0-9]",
        "",
        texto,
    )


def normalizar_id(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(
        serie,
        errors="coerce",
    ).astype("Int64")


def convertir_booleano(valor) -> bool:
    if isinstance(valor, bool):
        return valor

    if pd.isna(valor):
        return False

    return (
        str(valor)
        .strip()
        .lower()
        in {
            "true",
            "1",
            "yes",
            "si",
            "sí",
        }
    )


def limites_utc(
    desde: date,
    hasta: date,
) -> tuple[str, str]:

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
        .astimezone(ZONA_UTC)
        .replace(tzinfo=None)
    )

    hasta_utc = (
        hasta_lima
        .astimezone(ZONA_UTC)
        .replace(tzinfo=None)
    )

    return (
        desde_utc.strftime("%Y-%m-%d %H:%M:%S"),
        hasta_utc.strftime("%Y-%m-%d %H:%M:%S"),
    )


def cargar_excel(
    archivo: Path,
) -> pd.DataFrame:

    if not archivo.exists():
        raise FileNotFoundError(
            f"No encontré {archivo}"
        )

    df = pd.read_excel(
        archivo
    )

    columnas = {
        "# CITA POR FECHA PROGRAMADA": "id_cita",
        "ESTATUS DE CITA": "estatus_clear",
        "FECHA PROGRAMADA DE LA CITA": "fecha_clear",
        "HORA PROGRAMADA DE LA CITA": "hora_clear",
        "PLACAS": "placa_clear",
        "PERSONA QUE AGENDA": "agente_clear",
        "MOTIVO DE VISITA": "motivo_clear",
    }

    faltantes = [
        columna
        for columna in columnas
        if columna not in df.columns
    ]

    if faltantes:
        raise ValueError(
            f"{archivo.name} no contiene: "
            f"{faltantes}"
        )

    df = (
        df[
            list(columnas)
        ]
        .rename(
            columns=columnas
        )
        .copy()
    )

    df[
        "id_cita"
    ] = normalizar_id(
        df[
            "id_cita"
        ]
    )

    # Eliminar fila "XX resultados".
    df = df.loc[
        df[
            "id_cita"
        ].notna()
    ].copy()

    df[
        "estatus_normalizado"
    ] = df[
        "estatus_clear"
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

    df[
        "placa_normalizada_clear"
    ] = df[
        "placa_clear"
    ].apply(
        normalizar_placa
    )

    return df


def obtener_databricks(
    desde: date,
    hasta: date,
) -> pd.DataFrame:

    desde_utc, hasta_utc = limites_utc(
        desde=desde,
        hasta=hasta,
    )

    consulta = f"""
        SELECT
            Key_merge,
            appointmentNumber,
            licensePlate,
            userWhoSchedule,
            startDate,
            status,
            isDeleted,
            description

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
            "desde_utc": desde_utc,
            "hasta_utc": hasta_utc,
        },
    )

    if raw.empty:
        return raw

    # Una cita lógica por Key_merge.
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
            licensePlate=(
                "licensePlate",
                "first",
            ),
            userWhoSchedule=(
                "userWhoSchedule",
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
            motivo_db=(
                "description",
                lambda serie:
                    " | ".join(
                        sorted(
                            {
                                str(x).strip()
                                for x in serie
                                if pd.notna(x)
                                and str(x).strip()
                            }
                        )
                    ),
            ),
        )
    )

    df[
        "id_cita"
    ] = normalizar_id(
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
        "placa_normalizada_db"
    ] = df[
        "licensePlate"
    ].apply(
        normalizar_placa
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

    return df


def comparar_mes(
    mes: str,
    archivo: Path,
    desde: date,
    hasta: date,
) -> dict:

    print()
    print("=" * 88)
    print(
        f"{mes} — CLEARMECHANIC VS DATABRICKS"
    )
    print("=" * 88)

    clear = cargar_excel(
        archivo
    )

    db = obtener_databricks(
        desde=desde,
        hasta=hasta,
    )

    clear_cmp = clear[
        [
            "id_cita",
            "estatus_clear",
            "es_cancelada_clear",
            "placa_normalizada_clear",
            "agente_clear",
            "motivo_clear",
        ]
    ].copy()

    db_cmp = db[
        [
            "id_cita",
            "Key_merge",
            "status",
            "is_deleted",
            "placa_normalizada_db",
            "userWhoSchedule",
            "fecha_hora_lima",
            "motivo_db",
        ]
    ].copy()

    comparacion = clear_cmp.merge(
        db_cmp,
        on="id_cita",
        how="outer",
        indicator=True,
    )

    comparacion[
        "es_cancelada_clear"
    ] = (
        comparacion[
            "es_cancelada_clear"
        ]
        .fillna(False)
        .astype(bool)
    )

    comparacion[
        "is_deleted"
    ] = (
        comparacion[
            "is_deleted"
        ]
        .fillna(False)
        .astype(bool)
    )

    en_ambos = comparacion.loc[
        comparacion[
            "_merge"
        ].eq("both")
    ].copy()

    solo_clear = comparacion.loc[
        comparacion[
            "_merge"
        ].eq("left_only")
    ].copy()

    solo_db = comparacion.loc[
        comparacion[
            "_merge"
        ].eq("right_only")
    ].copy()

    canceladas_clear = clear.loc[
        clear[
            "es_cancelada_clear"
        ]
    ].copy()

    canceladas_comparables = (
        en_ambos.loc[
            en_ambos[
                "es_cancelada_clear"
            ]
        ]
        .copy()
    )

    solo_db_deleted = int(
        solo_db[
            "is_deleted"
        ].sum()
    )

    solo_db_activos = (
        len(solo_db)
        -
        solo_db_deleted
    )

    print(
        f"Registros Clear                    "
        f"{len(clear):>10,}"
    )

    print(
        f"Canceladas Clear                   "
        f"{len(canceladas_clear):>10,}"
    )

    print(
        f"Citas lógicas Databricks           "
        f"{len(db):>10,}"
    )

    print(
        f"isDeleted=True Databricks          "
        f"{int(db['is_deleted'].sum()):>10,}"
    )

    print()
    print("-" * 88)
    print(
        "COBERTURA"
    )
    print("-" * 88)

    print(
        f"En ambos                           "
        f"{len(en_ambos):>10,}"
    )

    print(
        f"Solo Clear                         "
        f"{len(solo_clear):>10,}"
    )

    print(
        f"Solo Databricks                    "
        f"{len(solo_db):>10,}"
    )

    print(
        f"  ↳ isDeleted=True                 "
        f"{solo_db_deleted:>10,}"
    )

    print(
        f"  ↳ isDeleted=False                "
        f"{solo_db_activos:>10,}"
    )

    print()
    print("-" * 88)
    print(
        "CANCELADAS DEL EXCEL"
    )
    print("-" * 88)

    print(
        f"Canceladas presentes en ambos      "
        f"{len(canceladas_comparables):>10,}"
    )

    if not canceladas_comparables.empty:

        cancelada_deleted = int(
            canceladas_comparables[
                "is_deleted"
            ].sum()
        )

        print(
            f"  ↳ isDeleted=True                 "
            f"{cancelada_deleted:>10,}"
        )

        print(
            f"  ↳ isDeleted=False                "
            f"{len(canceladas_comparables) - cancelada_deleted:>10,}"
        )

        print()
        print(
            canceladas_comparables[
                [
                    "id_cita",
                    "estatus_clear",
                    "status",
                    "is_deleted",
                    "placa_normalizada_clear",
                    "placa_normalizada_db",
                    "agente_clear",
                    "userWhoSchedule",
                ]
            ].to_string(
                index=False
            )
        )

    print()
    print("-" * 88)
    print(
        "STATUS DATABRICKS"
    )
    print("-" * 88)

    print(
        db[
            "status"
        ]
        .fillna("SIN_STATUS")
        .astype(str)
        .value_counts()
        .rename_axis("status")
        .reset_index(name="citas")
        .to_string(index=False)
    )

    # ========================================================
    # CASOS QUE EXPLICAN DIFERENCIAS
    # ========================================================

    if not solo_db.empty:

        print()
        print("-" * 88)
        print(
            "MUESTRA — SOLO DATABRICKS"
        )
        print("-" * 88)

        print(
            solo_db[
                [
                    "id_cita",
                    "status",
                    "is_deleted",
                    "placa_normalizada_db",
                    "fecha_hora_lima",
                    "userWhoSchedule",
                    "motivo_db",
                ]
            ]
            .sort_values(
                [
                    "is_deleted",
                    "id_cita",
                ]
            )
            .head(100)
            .to_string(index=False)
        )

    return {
        "mes": mes,
        "clear": len(clear),
        "canceladas_clear":
            len(canceladas_clear),
        "databricks":
            len(db),
        "deleted_db":
            int(
                db[
                    "is_deleted"
                ].sum()
            ),
        "ambos":
            len(en_ambos),
        "solo_clear":
            len(solo_clear),
        "solo_db":
            len(solo_db),
        "solo_db_deleted":
            solo_db_deleted,
        "solo_db_activo":
            solo_db_activos,
        "canceladas_comparables":
            len(canceladas_comparables),
        "canceladas_deleted":
            int(
                canceladas_comparables[
                    "is_deleted"
                ].sum()
            )
            if not canceladas_comparables.empty
            else 0,
    }


def main() -> None:

    resultados = []

    for configuracion in ARCHIVOS:

        resultado = comparar_mes(
            mes=configuracion[
                "mes"
            ],
            archivo=configuracion[
                "archivo"
            ],
            desde=configuracion[
                "desde"
            ],
            hasta=configuracion[
                "hasta"
            ],
        )

        resultados.append(
            resultado
        )

    resumen = pd.DataFrame(
        resultados
    )

    print()
    print()
    print("=" * 110)
    print(
        "RESUMEN COMPARATIVO — SEPTIEMBRE / OCTUBRE / NOVIEMBRE"
    )
    print("=" * 110)

    print(
        resumen.to_string(
            index=False
        )
    )

    print()
    print("=" * 110)
    print(
        "LECTURA DE LA HIPÓTESIS"
    )
    print("=" * 110)

    cerrados = resumen.loc[
        resumen[
            "mes"
        ].isin(
            [
                "SEPTIEMBRE",
                "OCTUBRE",
            ]
        )
    ]

    noviembre = resumen.loc[
        resumen[
            "mes"
        ].eq(
            "NOVIEMBRE"
        )
    ]

    meses_cerrados_sin_canceladas = bool(
        (
            cerrados[
                "canceladas_clear"
            ]
            ==
            0
        ).all()
    )

    noviembre_con_canceladas = bool(
        (
            noviembre[
                "canceladas_clear"
            ]
            >
            0
        ).any()
    )

    if (
        meses_cerrados_sin_canceladas
        and noviembre_con_canceladas
    ):

        print(
            "⚠️ Patrón compatible con la hipótesis:"
        )
        print(
            "los meses cerrados no muestran canceladas "
            "en el Excel, mientras el mes actual sí."
        )
        print()
        print(
            "Esto NO demuestra todavía por sí solo que "
            "ClearMechanic las elimine específicamente "
            "al cerrar el mes."
        )

    else:

        print(
            "El patrón observado no respalda de forma "
            "consistente la hipótesis de cierre mensual."
        )


if __name__ == "__main__":
    main()