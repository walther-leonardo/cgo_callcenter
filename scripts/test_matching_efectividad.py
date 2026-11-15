import pandas as pd

from matching_efectividad import (
    calcular_matching_efectividad,
)


def cita(
    id_cita,
    numero,
    fecha,
    agente="Brenda Montalvan Cornejo",
    motivo="Preventivo",
    hora="08:00",
):
    fecha_hora = pd.Timestamp(
        f"{fecha} {hora}",
        tz="America/Lima",
    )

    return {
        "id_cita":
            id_cita,

        "appointment_number":
            numero,

        "placa_normalizada":
            "ABC123",

        "fecha_cita":
            pd.Timestamp(
                fecha
            ).date(),

        "fecha_hora_cita_lima":
            fecha_hora,

        "fecha_creacion_lima":
            pd.Timestamp(
                fecha
            ),

        "agente":
            agente,

        "motivos":
            motivo,
    }


def presencia(
    nombre,
    fecha,
):
    return {
        "presencia_id": nombre,
        "placa_normalizada": "ABC123",
        "fecha_visita": pd.Timestamp(
            fecha
        ).date(),
        "fuente": "ORDEN",
    }


# ============================================================
# ESCENARIO 1
#
# F -> T = +7
# ============================================================

citas_1 = pd.DataFrame(
    [
        cita(
            "F",
            100,
            "2026-11-01",
        ),
    ]
)

presencias_1 = pd.DataFrame(
    [
        presencia(
            "T",
            "2026-11-08",
        ),
    ]
)

resultado_1 = calcular_matching_efectividad(
    citas_1,
    presencias_1,
)

print()
print("=" * 70)
print("ESCENARIO 1 — F + T")
print("=" * 70)
print(resultado_1.to_string(index=False))


# ============================================================
# ESCENARIO 2
#
# Aparece G.
#
# F -> T = +7 Nivel 3
# G -> T = +1 Nivel 2
#
# Debe ganar G.
# ============================================================

citas_2 = pd.DataFrame(
    [
        cita(
            "F",
            100,
            "2026-11-01",
        ),
        cita(
            "G",
            101,
            "2026-11-07",
        ),
    ]
)

resultado_2 = calcular_matching_efectividad(
    citas_2,
    presencias_1,
)

print()
print("=" * 70)
print("ESCENARIO 2 — APARECE G")
print("=" * 70)
print(resultado_2.to_string(index=False))


# ============================================================
# ESCENARIO 3
#
# Aparece U.
#
# F -> T = Nivel 3
# G -> U = Nivel 2
#
# Deben recuperarse DOS efectivas.
# ============================================================

presencias_3 = pd.DataFrame(
    [
        presencia(
            "T",
            "2026-11-08",
        ),
        presencia(
            "U",
            "2026-11-09",
        ),
    ]
)

resultado_3 = calcular_matching_efectividad(
    citas_2,
    presencias_3,
)

print()
print("=" * 70)
print("ESCENARIO 3 — APARECE U")
print("=" * 70)
print(resultado_3.to_string(index=False))


assert len(resultado_1) == 1

assert (
    resultado_1.iloc[0][
        "id_cita"
    ]
    ==
    "F"
)

assert (
    resultado_1.iloc[0][
        "nivel_efectividad"
    ]
    ==
    3
)


assert len(resultado_2) == 1

assert (
    resultado_2.iloc[0][
        "id_cita"
    ]
    ==
    "G"
)

assert (
    resultado_2.iloc[0][
        "nivel_efectividad"
    ]
    ==
    2
)


assert len(resultado_3) == 2

parejas = set(
    zip(
        resultado_3[
            "id_cita"
        ],
        resultado_3[
            "presencia_id"
        ],
    )
)

assert parejas == {
    (
        "F",
        "T",
    ),
    (
        "G",
        "U",
    ),
}

print()
print(
    "🐿️ TODAS LAS PRUEBAS DE MATCHING PASARON"
)


# ============================================================
# ESCENARIO 4
#
# REPROGRAMACIÓN MISMO DÍA
#
# Misma agente.
# Misma placa.
# Ambas Nivel 1.
#
# Debe ganar la cita con HORA PROGRAMADA MÁS TARDE.
# ============================================================

citas_4 = pd.DataFrame(
    [
        {
            "id_cita":
                "CVY027_31955",

            "appointment_number":
                31955,

            "placa_normalizada":
                "CVY027",

            "fecha_cita":
                pd.Timestamp(
                    "2026-11-03"
                ).date(),

            "fecha_hora_cita_lima":
                pd.Timestamp(
                    "2026-11-03 08:00:00",
                    tz="America/Lima",
                ),

            "fecha_creacion_lima":
                pd.Timestamp(
                    "2026-10-30 12:34:00",
                    tz="America/Lima",
                ),

            "agente":
                "Rocio Miranda Ausejo",

            "motivos":
                "PYP",
        },

        {
            "id_cita":
                "CVY027_32087",

            "appointment_number":
                32087,

            "placa_normalizada":
                "CVY027",

            "fecha_cita":
                pd.Timestamp(
                    "2026-11-03"
                ).date(),

            "fecha_hora_cita_lima":
                pd.Timestamp(
                    "2026-11-03 10:00:00",
                    tz="America/Lima",
                ),

            "fecha_creacion_lima":
                pd.Timestamp(
                    "2026-11-03 09:05:00",
                    tz="America/Lima",
                ),

            "agente":
                "Rocio Miranda Ausejo",

            "motivos":
                "Diagnostico",
        },
    ]
)

presencias_4 = pd.DataFrame(
    [
        {
            "presencia_id":
                "CVY027|2026-11-03",

            "placa_normalizada":
                "CVY027",

            "fecha_visita":
                pd.Timestamp(
                    "2026-11-03"
                ).date(),

            "fuente":
                "COTIZACION_Y_ORDEN",
        }
    ]
)

resultado_4 = calcular_matching_efectividad(
    citas_4,
    presencias_4,
)

print()
print("=" * 70)
print(
    "ESCENARIO 4 — REPROGRAMACIÓN MISMO DÍA"
)
print("=" * 70)

print(
    resultado_4.to_string(
        index=False
    )
)

assert len(
    resultado_4
) == 1

assert (
    resultado_4.iloc[0][
        "appointment_number"
    ]
    ==
    32087
)

assert (
    resultado_4.iloc[0][
        "nivel_efectividad"
    ]
    ==
    1
)

print()
print(
    "🐿️ REPROGRAMACIÓN MISMO DÍA VALIDADA"
)