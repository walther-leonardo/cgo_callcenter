from __future__ import annotations

from efectividad_reportes import (
    construir_distribucion_meta_diaria,
    calcular_comision_agente,
    CONFIG_METAS_2026,
    CONFIG_INCENTIVOS_2026,
)

from database import (
    inicializar_base,
    cargar_detalle_efectividad,
)


def main() -> None:
    inicializar_base()

    print()
    print("=" * 80)
    print("🐿️ TEST — DISTRIBUCIÓN DIARIA DE META")
    print("=" * 80)

    # ========================================================
    # 1. DISTRIBUCIÓN DIARIA
    # ========================================================

    meta_prueba = 501

    distribucion = construir_distribucion_meta_diaria(
        anio=2026,
        mes=11,
        meta_mensual=meta_prueba,
        feriados=[],
    )

    print()
    print(
        distribucion[
            [
                "etiqueta",
                "dia_semana",
                "peso",
                "meta_dia",
                "meta_acumulada",
            ]
        ].to_string(
            index=False
        )
    )

    total_meta = int(
        distribucion[
            "meta_dia"
        ].sum()
    )

    domingos_con_meta = distribucion.loc[
        distribucion[
            "es_domingo"
        ]
        &
        distribucion[
            "meta_dia"
        ].ne(0)
    ]

    print()
    print("-" * 80)
    print(
        f"Meta mensual esperada : {meta_prueba}"
    )
    print(
        f"Meta diaria acumulada  : {total_meta}"
    )

    assert (
        total_meta
        ==
        meta_prueba
    ), (
        "La distribución diaria no suma "
        "exactamente la meta mensual."
    )

    assert domingos_con_meta.empty, (
        "Existe al menos un domingo con meta."
    )

    print(
        "✅ Distribución mensual exacta."
    )

    print(
        "✅ Domingos con meta = 0."
    )

    # ========================================================
    # 2. PRUEBA CON FERIADO
    # ========================================================

    print()
    print("=" * 80)
    print("🐿️ TEST — REDISTRIBUCIÓN POR FERIADO")
    print("=" * 80)

    distribucion_feriado = (
        construir_distribucion_meta_diaria(
            anio=2026,
            mes=11,
            meta_mensual=meta_prueba,
            feriados=[
                "2026-11-20",
            ],
        )
    )

    fila_feriado = distribucion_feriado.loc[
        distribucion_feriado[
            "fecha"
        ].astype(str).eq(
            "2026-11-20"
        )
    ]

    print()
    print(
        distribucion_feriado[
            [
                "etiqueta",
                "es_feriado",
                "meta_dia",
            ]
        ].to_string(
            index=False
        )
    )

    assert int(
        fila_feriado.iloc[
            0
        ][
            "meta_dia"
        ]
    ) == 0

    assert int(
        distribucion_feriado[
            "meta_dia"
        ].sum()
    ) == meta_prueba

    print()
    print(
        "✅ Feriado con meta = 0."
    )

    print(
        "✅ Meta redistribuida sin perder "
        "el total mensual."
    )

    # ========================================================
    # 3. COMISIONES REALES SEGÚN DETALLE
    # ========================================================

    print()
    print("=" * 80)
    print("🐿️ TEST — COMISIONES")
    print("=" * 80)

    detalle = cargar_detalle_efectividad(
        anio=2026
    )

    if detalle.empty:

        print(
            "⚠️ No existen registros de efectividad "
            "persistidos. Se omite prueba de comisión."
        )

        return

    casos = [
        (
            "ROCIO",
            "Rocio Miranda Ausejo",
        ),
        (
            "BRENDA",
            "Brenda Montalvan Cornejo",
        ),
    ]

    for grupo, agente in casos:

        comision = calcular_comision_agente(
            detalle=detalle,
            anio=2026,
            mes=11,
            agente=agente,
            grupo_meta=grupo,
            configuracion_metas=
                CONFIG_METAS_2026,
            configuracion_incentivos=
                CONFIG_INCENTIVOS_2026,
        )

        print()
        print(
            f"{grupo}"
        )
        print(
            f"Meta                : "
            f"{comision['meta']}"
        )
        print(
            f"Resultado efectivo  : "
            f"{comision['resultado']}"
        )
        print(
            f"Cumplimiento        : "
            f"{comision['cumplimiento_pct']}%"
        )
        print(
            f"Factor incentivo    : "
            f"{comision['factor_incentivo_pct']}%"
        )
        print(
            f"Incentivo base       : "
            f"S/ {comision['incentivo_base']}"
        )
        print(
            f"Comisión calculada  : "
            f"S/ {comision['comision']}"
        )

    print()
    print("=" * 80)
    print(
        "✅ TEST DE EFECTIVIDAD DIARIA FINALIZADO"
    )
    print("=" * 80)


if __name__ == "__main__":
    main()