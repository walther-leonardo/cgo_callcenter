from __future__ import annotations

import pandas as pd

from database import get_connection


def cargar_snapshots_del_dia() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    """
    Obtiene el primer y el último snapshot del día más reciente registrado.
    """

    with get_connection() as conn:
        snapshots = pd.read_sql_query(
            """
            SELECT
                snapshot_id,
                fecha_hora_corte,
                archivo_origen,
                cantidad_citas
            FROM snapshots
            ORDER BY snapshot_id
            """,
            conn,
        )

        if snapshots.empty:
            raise ValueError("No hay snapshots registrados.")

        snapshots["fecha_hora_corte"] = pd.to_datetime(
            snapshots["fecha_hora_corte"],
            errors="coerce",
        )

        snapshots["fecha_corte"] = snapshots["fecha_hora_corte"].dt.date

        fecha_objetivo = snapshots["fecha_corte"].max()

        snapshots_dia = snapshots.loc[
            snapshots["fecha_corte"].eq(fecha_objetivo)
        ].copy()

        if snapshots_dia.empty:
            raise ValueError("No se encontraron snapshots del día objetivo.")

        primero_info = snapshots_dia.iloc[0].to_dict()
        ultimo_info = snapshots_dia.iloc[-1].to_dict()

        primero = pd.read_sql_query(
            """
            SELECT *
            FROM citas_snapshot
            WHERE snapshot_id = ?
            """,
            conn,
            params=[primero_info["snapshot_id"]],
        )

        ultimo = pd.read_sql_query(
            """
            SELECT *
            FROM citas_snapshot
            WHERE snapshot_id = ?
            """,
            conn,
            params=[ultimo_info["snapshot_id"]],
        )

    return primero, ultimo, primero_info, ultimo_info


def preparar_fechas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["fecha_programada"] = pd.to_datetime(
        df["fecha_programada"],
        errors="coerce",
    ).dt.normalize()

    df["fecha_creacion"] = pd.to_datetime(
        df["fecha_creacion"],
        errors="coerce",
    )

    return df


def construir_serie_agenda(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cuenta cuántas citas hay por fecha_programada.
    """

    base = (
        df.dropna(subset=["fecha_programada"])
        .groupby("fecha_programada", as_index=False)
        .agg(citas=("id_cita", "nunique"))
        .sort_values("fecha_programada")
    )

    return base


def comparar_inicio_vs_actual(
    inicio: pd.DataFrame,
    actual: pd.DataFrame,
) -> dict:
    """
    Compara el primer snapshot del día contra el último snapshot del día.
    """

    inicio = inicio.copy()
    actual = actual.copy()

    ids_inicio = set(inicio["id_cita"])
    ids_actual = set(actual["id_cita"])

    ids_nuevas = ids_actual - ids_inicio

    nuevas = actual.loc[
        actual["id_cita"].isin(ids_nuevas)
    ].copy()

    return {
        "nuevas": nuevas,
        "ids_inicio": ids_inicio,
        "ids_actual": ids_actual,
    }


def resumir_nuevas_por_bucket(
    nuevas: pd.DataFrame,
    fecha_base: pd.Timestamp,
) -> pd.DataFrame:
    """
    Resume nuevas citas por buckets operativos:
    HOY, MANANA, PASADO_MANANA_O_MAS
    """

    df = nuevas.copy()

    if df.empty:
        return pd.DataFrame(
            {
                "bucket": [
                    "HOY",
                    "MANANA",
                    "PASADO_MANANA_O_MAS",
                ],
                "nuevas": [0, 0, 0],
            }
        )

    df["dias_hasta_cita"] = (
        df["fecha_programada"] - fecha_base
    ).dt.days

    def clasificar(dias: float) -> str:
        if pd.isna(dias):
            return "SIN_FECHA"
        if dias <= 0:
            return "HOY"
        if dias == 1:
            return "MANANA"
        return "PASADO_MANANA_O_MAS"

    df["bucket"] = df["dias_hasta_cita"].apply(clasificar)

    resumen = (
        df.groupby("bucket", as_index=False)
        .agg(nuevas=("id_cita", "nunique"))
    )

    orden = pd.DataFrame(
        {
            "bucket": [
                "HOY",
                "MANANA",
                "PASADO_MANANA_O_MAS",
            ]
        }
    )

    resumen = orden.merge(
        resumen,
        on="bucket",
        how="left",
    )

    resumen["nuevas"] = resumen["nuevas"].fillna(0).astype(int)

    return resumen


def construir_lineas_inicio_vs_actual(
    inicio: pd.DataFrame,
    actual: pd.DataFrame,
) -> pd.DataFrame:
    """
    Devuelve una tabla con citas por fecha programada:
    - citas_inicio
    - citas_actual
    - delta
    """

    serie_inicio = construir_serie_agenda(inicio).rename(
        columns={"citas": "citas_inicio"}
    )

    serie_actual = construir_serie_agenda(actual).rename(
        columns={"citas": "citas_actual"}
    )

    comparativo = serie_inicio.merge(
        serie_actual,
        on="fecha_programada",
        how="outer",
    ).sort_values("fecha_programada")

    comparativo["citas_inicio"] = (
        comparativo["citas_inicio"].fillna(0).astype(int)
    )
    comparativo["citas_actual"] = (
        comparativo["citas_actual"].fillna(0).astype(int)
    )
    comparativo["delta"] = (
        comparativo["citas_actual"] - comparativo["citas_inicio"]
    )

    return comparativo


def main() -> None:
    print()
    print("=" * 72)
    print("CGO CALL CENTER — AGENDA DEL DÍA")
    print("=" * 72)

    inicio, actual, inicio_info, actual_info = cargar_snapshots_del_dia()

    inicio = preparar_fechas(inicio)
    actual = preparar_fechas(actual)

    resultado = comparar_inicio_vs_actual(
        inicio=inicio,
        actual=actual,
    )

    nuevas = resultado["nuevas"]

    fecha_base = pd.to_datetime(
        actual_info["fecha_hora_corte"]
    ).normalize()

    lineas = construir_lineas_inicio_vs_actual(
        inicio=inicio,
        actual=actual,
    )

    buckets = resumir_nuevas_por_bucket(
        nuevas=nuevas,
        fecha_base=fecha_base,
    )

    print()
    print("PRIMER CORTE DEL DÍA")
    print("-" * 72)
    print(
        f"Snapshot #{inicio_info['snapshot_id']} | "
        f"{inicio_info['fecha_hora_corte']} | "
        f"{inicio_info['cantidad_citas']} citas"
    )

    print()
    print("ÚLTIMO CORTE DEL DÍA")
    print("-" * 72)
    print(
        f"Snapshot #{actual_info['snapshot_id']} | "
        f"{actual_info['fecha_hora_corte']} | "
        f"{actual_info['cantidad_citas']} citas"
    )

    print()
    print("NUEVAS CITAS DEL DÍA")
    print("-" * 72)
    print(f"Nuevas desde inicio del día: {len(nuevas):,}")

    print()
    print("NUEVAS POR BUCKET")
    print("-" * 72)
    print(buckets.to_string(index=False))

    print()
    print("EVOLUCIÓN DE LA AGENDA")
    print("-" * 72)
    print(
        lineas[
            [
                "fecha_programada",
                "citas_inicio",
                "citas_actual",
                "delta",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()