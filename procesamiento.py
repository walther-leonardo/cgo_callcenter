from __future__ import annotations

import pandas as pd


COLUMNAS_REQUERIDAS = [
    "# CITA POR FECHA PROGRAMADA",
    "ESTATUS DE CITA",
    "MOTIVO DE VISITA",
    "FECHA PROGRAMADA DE LA CITA",
    "HORA PROGRAMADA DE LA CITA",
    "ORIGEN DE CITA",
    "PERSONA QUE AGENDA",
    "FECHA DE CREACIÓN DE LA CITA",
    "NOMBRE",
    "CELULAR",
    "ASESOR DE SERVICIO",
    "MODELO",
    "PLACAS",
    "KILOMETRAJE",
]


MAPEO_COLUMNAS = {
    "# CITA POR FECHA PROGRAMADA": "id_cita",
    "ESTATUS DE CITA": "estatus_cita",
    "MOTIVO DE VISITA": "motivo_visita",
    "FECHA PROGRAMADA DE LA CITA": "fecha_programada",
    "HORA PROGRAMADA DE LA CITA": "hora_programada",
    "ORIGEN DE CITA": "origen_cita",
    "PERSONA QUE AGENDA": "persona_agenda",
    "FECHA DE CREACIÓN DE LA CITA": "fecha_creacion",
    "NOMBRE": "nombre",
    "CELULAR": "celular",
    "ASESOR DE SERVICIO": "asesor_servicio",
    "MODELO": "modelo",
    "PLACAS": "placa",
    "KILOMETRAJE": "kilometraje",
}


def _convertir_fecha_excel(
    serie: pd.Series,
) -> pd.Series:
    """
    Convierte fechas exportadas por ClearMechanic.

    Soporta tanto:
    - serial Excel: 46288.833333
    - fechas ya interpretadas por pandas
    """

    resultado = pd.Series(
        pd.NaT,
        index=serie.index,
        dtype="datetime64[ns]",
    )

    numerico = pd.to_numeric(
        serie,
        errors="coerce",
    )

    mask_numerico = numerico.notna()

    resultado.loc[
        mask_numerico
    ] = pd.to_datetime(
        numerico.loc[
            mask_numerico
        ],
        unit="D",
        origin="1899-12-30",
        errors="coerce",
    )

    mask_restante = ~mask_numerico

    if mask_restante.any():
        resultado.loc[
            mask_restante
        ] = pd.to_datetime(
            serie.loc[
                mask_restante
            ],
            errors="coerce",
            dayfirst=True,
        )

    return resultado


def cargar_clearmechanic(
    archivo,
) -> pd.DataFrame:
    """
    Lee y normaliza una exportación de ClearMechanic.
    """

    df = pd.read_excel(
        archivo
    )

    faltantes = [
        columna
        for columna in COLUMNAS_REQUERIDAS
        if columna not in df.columns
    ]

    if faltantes:
        raise ValueError(
            "El archivo ClearMechanic no contiene "
            f"las columnas requeridas: {faltantes}"
        )

    df = df[
        COLUMNAS_REQUERIDAS
    ].copy()

    df = df.rename(
        columns=MAPEO_COLUMNAS
    )

    # --------------------------------------------------------
    # Eliminar fila "46 resultados", "51 resultados", etc.
    # --------------------------------------------------------

    df[
        "id_cita"
    ] = pd.to_numeric(
        df[
            "id_cita"
        ],
        errors="coerce",
    )

    df = df.loc[
        df[
            "id_cita"
        ].notna()
    ].copy()

    df[
        "id_cita"
    ] = (
        df[
            "id_cita"
        ]
        .astype(int)
    )

    # --------------------------------------------------------
    # Fechas
    # --------------------------------------------------------

    df[
        "fecha_programada_dt"
    ] = _convertir_fecha_excel(
        df[
            "fecha_programada"
        ]
    )

    df[
        "fecha_creacion"
    ] = _convertir_fecha_excel(
        df[
            "fecha_creacion"
        ]
    )

    # --------------------------------------------------------
    # ClearMechanic parece repetir el datetime completo en
    # FECHA PROGRAMADA y HORA PROGRAMADA.
    # Utilizamos fecha_programada_dt como fuente canónica.
    # --------------------------------------------------------

    df[
        "fecha_programada"
    ] = (
        df[
            "fecha_programada_dt"
        ]
        .dt.normalize()
    )

    df[
        "hora_programada"
    ] = (
        df[
            "fecha_programada_dt"
        ]
        .dt.strftime(
            "%H:%M"
        )
    )

    df = df.drop(
        columns=[
            "fecha_programada_dt",
        ]
    )

    # --------------------------------------------------------
    # Textos
    # --------------------------------------------------------

    columnas_texto = [
        "estatus_cita",
        "motivo_visita",
        "origen_cita",
        "persona_agenda",
        "nombre",
        "celular",
        "asesor_servicio",
        "modelo",
        "placa",
    ]

    for columna in columnas_texto:

        df[
            columna
        ] = (
            df[
                columna
            ]
            .astype("string")
            .str.strip()
        )

    df[
        "kilometraje"
    ] = pd.to_numeric(
        df[
            "kilometraje"
        ],
        errors="coerce",
    )

    # --------------------------------------------------------
    # Control: una cita por snapshot
    # --------------------------------------------------------

    duplicados = int(
        df[
            "id_cita"
        ]
        .duplicated()
        .sum()
    )

    if duplicados:
        raise ValueError(
            "El archivo contiene "
            f"{duplicados} IDs de cita duplicados."
        )

    return (
        df
        .sort_values(
            [
                "fecha_programada",
                "hora_programada",
            ]
        )
        .reset_index(
            drop=True
        )
    )