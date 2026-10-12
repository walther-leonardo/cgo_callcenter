from __future__ import annotations

import pandas as pd

from database import get_connection


def main() -> None:

    print()
    print("=" * 90)
    print("CGO CALL CENTER — AUDITORÍA TIMELINE HISTÓRICO")
    print("=" * 90)

    with get_connection() as conn:

        viejo = pd.read_sql_query(
            """
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

            ORDER BY id_cita
            """,
            conn,
        )

        nuevo = pd.read_sql_query(
            """
            SELECT
                id_cita,
                persona_agenda,
                origen_cita,
                nombre,
                celular,
                placa,
                modelo,
                fecha_detectada

            FROM citas_primera_deteccion

            ORDER BY id_cita
            """,
            conn,
        )

    columnas = [
        "id_cita",
        "persona_agenda",
        "origen_cita",
        "nombre",
        "celular",
        "placa",
        "modelo",
        "fecha_detectada",
    ]

    viejo = viejo[
        columnas
    ].copy()

    nuevo = nuevo[
        columnas
    ].copy()

    viejo = viejo.where(
        viejo.notna(),
        None,
    )

    nuevo = nuevo.where(
        nuevo.notna(),
        None,
    )

    ids_viejo = set(
        viejo["id_cita"]
    )

    ids_nuevo = set(
        nuevo["id_cita"]
    )

    faltan_nuevo = (
        ids_viejo
        -
        ids_nuevo
    )

    sobran_nuevo = (
        ids_nuevo
        -
        ids_viejo
    )

    comparacion = (
        viejo
        .merge(
            nuevo,
            on="id_cita",
            how="inner",
            suffixes=(
                "_viejo",
                "_nuevo",
            ),
        )
    )

    diferencias = []

    for fila in comparacion.itertuples(
        index=False
    ):

        for columna in columnas[1:]:

            anterior = getattr(
                fila,
                f"{columna}_viejo",
            )

            nuevo_valor = getattr(
                fila,
                f"{columna}_nuevo",
            )

            ambos_nulos = (
                pd.isna(anterior)
                and pd.isna(nuevo_valor)
            )

            if ambos_nulos:
                continue

            if str(anterior) != str(nuevo_valor):

                diferencias.append(
                    {
                        "id_cita":
                            fila.id_cita,

                        "campo":
                            columna,

                        "viejo":
                            anterior,

                        "nuevo":
                            nuevo_valor,
                    }
                )

    diferencias_df = pd.DataFrame(
        diferencias
    )

    print()
    print("CANTIDADES")
    print("-" * 90)

    print(
        f"Consulta histórica vieja : "
        f"{len(viejo):,}"
    )

    print(
        f"Primera detección nueva  : "
        f"{len(nuevo):,}"
    )

    print(
        f"Faltan en nueva tabla    : "
        f"{len(faltan_nuevo):,}"
    )

    print(
        f"Sobran en nueva tabla    : "
        f"{len(sobran_nuevo):,}"
    )

    print(
        f"Diferencias de campos    : "
        f"{len(diferencias_df):,}"
    )

    if not diferencias_df.empty:

        print()
        print("MUESTRA DE DIFERENCIAS")
        print("-" * 90)

        print(
            diferencias_df
            .head(30)
            .to_string(
                index=False
            )
        )

    paridad_ok = (
        len(viejo) == len(nuevo)
        and not faltan_nuevo
        and not sobran_nuevo
        and diferencias_df.empty
    )

    print()
    print("=" * 90)

    if paridad_ok:

        print(
            "✅ PARIDAD 100% — TIMELINE HISTÓRICO VALIDADO"
        )

    else:

        print(
            "⚠️ PARIDAD INCOMPLETA — REVISAR"
        )

    print("=" * 90)
    print()


if __name__ == "__main__":
    main()