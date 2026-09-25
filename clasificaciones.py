from __future__ import annotations

import re

import pandas as pd


# ============================================================
# ASESORES — NORMALIZACIÓN Y SEDE
# ============================================================

ASESOR_ALIAS = {
    # --------------------------------------------------------
    # SAN ISIDRO
    # --------------------------------------------------------
    "Leonardo Castillo Renteria":        "Leonardo Castillo",
    "Leonardo Castillo":        "Leonardo Castillo",
    "Alexandra Behr":        "Alexandra Behr",
    "Angel Flores":        "Angel Flores",
    "Jorge Luis Gonzales Villar":        "Jorge Gonzales",
    "Jorge Gonzales":        "Jorge Gonzales",
    "José Rivera":        "Jose Rivera",
    "Jose Rivera":        "Jose Rivera",
    "Liliana Camargo":        "Liliana Camargo",
    "Sergio Huamán Herencia":        "Sergio Huaman Herencia",
    "Sergio Huaman Herencia":        "Sergio Huaman Herencia",
    "Darwin Lopez Gomez":        "Darwin Lopez",
    "Darwin Lopez":        "Darwin Lopez",

    # --------------------------------------------------------
    # SAN MIGUEL
    # --------------------------------------------------------
    "Carlos Alberto Manhualaya Tapia":        "Carlos Manhualaya",
    "Carlos Manhualaya":        "Carlos Manhualaya",
    "Jose Carlos Montes Coronel":        "Jose Carlos Montes",
    "José Carlos Montes Coronel":        "Jose Carlos Montes",
    "Jose Carlos Montes":        "Jose Carlos Montes",
    "Anthony Cardenas Martinez": "Anthony Cardenas" 
}


ASESOR_SEDE = {
    # --------------------------------------------------------
    # SAN ISIDRO
    # --------------------------------------------------------
    "Leonardo Castillo":        "SAN ISIDRO",
    "Alexandra Behr":        "SAN ISIDRO",
    "Angel Flores":        "SAN ISIDRO",
    "Jorge Gonzales":        "SAN ISIDRO",
    "Jose Rivera":        "SAN ISIDRO",
    "Liliana Camargo":        "SAN ISIDRO",
    "Sergio Huaman Herencia":        "SAN ISIDRO",
    "Darwin Lopez":        "SAN ISIDRO",
    # --------------------------------------------------------
    # SAN MIGUEL
    # --------------------------------------------------------
    "Carlos Manhualaya":        "SAN MIGUEL",
    "Jose Carlos Montes":        "SAN MIGUEL",
    "Anthony Cardenas":"SAN MIGUEL", 
}


# ============================================================
# PERSONA QUE AGENDA — NOMBRE CANÓNICO Y CANAL
# ============================================================

PERSONA_AGENDA_ALIAS = {
    # --------------------------------------------------------
    # CALL CENTER
    # --------------------------------------------------------
    "Brenda Montalvan Cornejo": "Brenda",
    "Rocio Miranda Ausejo": "Rocio",
    "Yesika Maria Castro": "Yesika",

    # --------------------------------------------------------
    # TALLER
    # --------------------------------------------------------
    # Los nombres del taller se irán agregando aquí
    # conforme identifiquemos variantes.
    #
    # Ejemplo:
    "Carlos Alberto Manhualaya Tapia": "Carlos Man.",
    "Yanina Astuhuaman Ninahuanca": "Yanina A.",
}


PERSONA_AGENDA_CANAL = {
    "Brenda": "CALL CENTER",
    "Rocio": "CALL CENTER",
    "Yesika": "CALL CENTER",
}



# ============================================================
# CLASIFICACIÓN DE SERVICIOS
# ============================================================
#
# IMPORTANTE:
# El orden sí importa.
#
# "Preventivo - 01K servicio" debe clasificarse como 01K y
# NO como Preventivo.
#
# ============================================================

REGLAS_SERVICIO = [
    {
        "tipo_servicio": "01K",
        "tipo_facturacion": "NO FACTURABLE",
        "patrones": [
            r"\b01K\b",
            r"\b1K\b",
            r"01K SERVICIO",
        ],
    },
    {
        "tipo_servicio": "Diagnóstico",
        "tipo_facturacion": "NO FACTURABLE",
        "patrones": [
            r"DIAGNOST",
        ],
    },
    {
        "tipo_servicio": "Preventivo",
        "tipo_facturacion": "FACTURABLE",
        "patrones": [
            r"PREVENTIVO",
            r"MANTENIMIENTO PREVENTIVO",
        ],
    },
    {
        "tipo_servicio": "Correctivo",
        "tipo_facturacion": "FACTURABLE",
        "patrones": [
            r"CORRECTIVO",
        ],
    },
    {
        "tipo_servicio": "Garantía",
        "tipo_facturacion": "FACTURABLE",
        "patrones": [
            r"GARANT",
            r"RECALL",
        ],
    },
    {
        "tipo_servicio": "PYP",
        "tipo_facturacion": "FACTURABLE",
        "patrones": [
            r"\bPYP\b",
            r"PLANCHADO",
            r"PINTURA",
            r"SINIESTRO",
        ],
    },
]


# ============================================================
# HELPERS
# ============================================================
def normalizar_asesor(
    asesor,
) -> str:
    """
    Convierte variantes del nombre del asesor
    a un nombre canónico.
    """

    if pd.isna(asesor):
        return "INDETERMINADO"

    asesor_limpio = str(
        asesor
    ).strip()

    return ASESOR_ALIAS.get(
        asesor_limpio,
        asesor_limpio,
    )

def normalizar_persona_agenda(
    persona,
) -> str:
    """
    Convierte el nombre original de PERSONA QUE AGENDA
    a un nombre canónico.

    Si todavía no existe un alias, conserva el nombre original.
    """

    if pd.isna(persona):
        return "INDETERMINADO"

    persona_limpia = str(
        persona
    ).strip()

    if not persona_limpia:
        return "INDETERMINADO"

    return PERSONA_AGENDA_ALIAS.get(
        persona_limpia,
        persona_limpia,
    )


def clasificar_canal_agenda(
    persona_canonica: str,
) -> str:
    """
    Clasifica quién agenda en CALL CENTER o TALLER.

    Regla temporal:
    Brenda, Rocio y Yesika pertenecen a CALL CENTER.
    Todo otro usuario válido pertenece a TALLER.
    """

    if (
        not persona_canonica
        or persona_canonica == "INDETERMINADO"
    ):
        return "INDETERMINADO"

    return PERSONA_AGENDA_CANAL.get(
        persona_canonica,
        "TALLER",
    )


def normalizar_texto(
    valor,
) -> str:
    """
    Convierte un valor a texto limpio para clasificación.
    """

    if pd.isna(valor):
        return ""

    return (
        str(valor)
        .strip()
        .upper()
    )


def clasificar_sede(
    asesor,
) -> str:
    """
    Devuelve la sede correspondiente al asesor normalizado.

    Si el asesor todavía no está clasificado,
    devuelve INDETERMINADO.
    """

    asesor_canonico = normalizar_asesor(
        asesor
    )

    return ASESOR_SEDE.get(
        asesor_canonico,
        "INDETERMINADO",
    )


def clasificar_servicio(
    motivo,
) -> tuple[str, str]:
    """
    Clasifica MOTIVO DE VISITA en:

        tipo_facturacion
        tipo_servicio

    Si no encuentra una regla conocida:
        INDETERMINADO / INDETERMINADO
    """

    texto = normalizar_texto(
        motivo
    )

    if not texto:
        return (
            "INDETERMINADO",
            "INDETERMINADO",
        )

    for regla in REGLAS_SERVICIO:

        for patron in regla[
            "patrones"
        ]:

            if re.search(
                patron,
                texto,
                flags=re.IGNORECASE,
            ):

                return (
                    regla[
                        "tipo_facturacion"
                    ],
                    regla[
                        "tipo_servicio"
                    ],
                )

    return (
        "INDETERMINADO",
        "INDETERMINADO",
    )


def enriquecer_clasificaciones(
    citas: pd.DataFrame,
) -> pd.DataFrame:
    """
    Agrega las clasificaciones necesarias para los reportes:

    - asesor_canonico
    - sede
    - tipo_facturacion
    - tipo_servicio
    """

    df = citas.copy()

    # --------------------------------------------------------
    # NORMALIZAR ASESOR
    # --------------------------------------------------------

    df[
        "asesor_canonico"
    ] = df[
        "asesor_servicio"
    ].apply(
        normalizar_asesor
    )

    # --------------------------------------------------------
    # ASIGNAR SEDE
    # --------------------------------------------------------

    df[
        "sede"
    ] = df[
        "asesor_canonico"
    ].apply(
        lambda asesor:
            ASESOR_SEDE.get(
                asesor,
                "INDETERMINADO",
            )
    )

    # --------------------------------------------------------
    # CLASIFICAR SERVICIO
    # --------------------------------------------------------

    clasificaciones = (
        df[
            "motivo_visita"
        ]
        .apply(
            clasificar_servicio
        )
    )

    df[
        "tipo_facturacion"
    ] = [
        resultado[0]
        for resultado
        in clasificaciones
    ]

    df[
        "tipo_servicio"
    ] = [
        resultado[1]
        for resultado
        in clasificaciones
    ]


    # --------------------------------------------------------
    # PERSONA QUE AGENDA
    # --------------------------------------------------------

    df[
        "persona_agenda_canonica"
    ] = df[
        "persona_agenda"
    ].apply(
        normalizar_persona_agenda
    )

    df[
        "canal_agenda"
    ] = df[
        "persona_agenda_canonica"
    ].apply(
        clasificar_canal_agenda
    )


    return df