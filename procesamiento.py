from __future__ import annotations

import re

import pandas as pd

from clasificaciones import (
    clasificar_canal_agenda,
    normalizar_persona_agenda,
)


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


def _normalizar_clave_texto(
    valor,
) -> str:
    """
    Normaliza texto exclusivamente para comparar citas.

    No modifica el valor original que se almacena.
    """

    if pd.isna(valor):
        return ""

    return " ".join(
        str(valor)
        .strip()
        .upper()
        .split()
    )


def _normalizar_clave_placa(
    valor,
) -> str:
    """
    Normaliza la placa para comparación.

    Ejemplos:
        ABC-123
        abc123
        ABC 123

    Todos se convierten en:
        ABC123
    """

    texto = _normalizar_clave_texto(
        valor
    )

    return re.sub(
        r"[^A-Z0-9]",
        "",
        texto,
    )


def _normalizar_clave_celular(
    valor,
) -> str:
    """
    Normaliza el celular conservando solamente dígitos.
    """

    if pd.isna(valor):
        return ""

    texto = str(
        valor
    ).strip()

    if texto.endswith(
        ".0"
    ):
        texto = texto[:-2]

    return re.sub(
        r"\D",
        "",
        texto,
    )


def _normalizar_estatus(
    valor,
) -> str:
    """
    Normaliza el estado para reglas operativas.
    """

    return _normalizar_clave_texto(
        valor
    )


def construir_vista_operativa_citas(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye la vista de citas que debe utilizar el
    seguimiento operativo de Call Center.

    El DataFrame original NO se modifica.

    REGLAS DE NEGOCIO
    -----------------
    1. Las citas con estatus CANCELADA no participan
       en métricas ni reportes operativos.

    2. Si existen varias citas activas con la misma:
       - placa
       - celular
       - fecha programada
       - hora programada
       - motivo de visita

       se contabiliza solamente una.

    3. Prioridad para resolver duplicados:
       a) una cita generada por CALL CENTER tiene prioridad;
       b) si existen varias de CALL CENTER, gana id_cita mayor;
       c) si no existe CALL CENTER, gana id_cita mayor.

    4. Si alguna parte fundamental de la clave está vacía,
       no se deduplica automáticamente para evitar falsos
       positivos.
    """

    if df.empty:
        return df.copy()

    columnas_requeridas = [
        "id_cita",
        "estatus_cita",
        "motivo_visita",
        "fecha_programada",
        "hora_programada",
        "persona_agenda",
        "celular",
        "placa",
    ]

    faltantes = [
        columna
        for columna in columnas_requeridas
        if columna not in df.columns
    ]

    if faltantes:
        raise ValueError(
            "No se puede construir la vista operativa. "
            f"Faltan columnas: {faltantes}"
        )

    resultado = df.copy()

    # ========================================================
    # 1. EXCLUIR CANCELADAS SOLO DE LA VISTA OPERATIVA
    #
    # Importante:
    # las Canceladas siguen existiendo en citas_snapshot y
    # citas_maestro. Aquí solo dejan de participar en KPIs.
    # ========================================================

    estatus = resultado[
        "estatus_cita"
    ].apply(
        _normalizar_estatus
    )

    resultado = resultado.loc[
        ~estatus.eq(
            "CANCELADA"
        )
    ].copy()

    if resultado.empty:
        return resultado

    # ========================================================
    # 2. CONSTRUIR CLAVES NORMALIZADAS
    # ========================================================

    resultado[
        "_clave_placa"
    ] = resultado[
        "placa"
    ].apply(
        _normalizar_clave_placa
    )

    resultado[
        "_clave_celular"
    ] = resultado[
        "celular"
    ].apply(
        _normalizar_clave_celular
    )

    resultado[
        "_clave_motivo"
    ] = resultado[
        "motivo_visita"
    ].apply(
        _normalizar_clave_texto
    )

    resultado[
        "_clave_fecha"
    ] = pd.to_datetime(
        resultado[
            "fecha_programada"
        ],
        errors="coerce",
    ).dt.normalize()

    resultado[
        "_clave_hora"
    ] = (
        resultado[
            "hora_programada"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # ========================================================
    # 3. IDENTIFICAR CALL CENTER UTILIZANDO LA CLASIFICACIÓN
    # YA EXISTENTE EN EL PROYECTO
    # ========================================================

    resultado[
        "_persona_canonica"
    ] = resultado[
        "persona_agenda"
    ].apply(
        normalizar_persona_agenda
    )

    resultado[
        "_canal_agenda"
    ] = resultado[
        "_persona_canonica"
    ].apply(
        clasificar_canal_agenda
    )

    resultado[
        "_es_callcenter"
    ] = resultado[
        "_canal_agenda"
    ].eq(
        "CALL CENTER"
    )

    # ========================================================
    # 4. SOLO DEDUPLICAR CUANDO TENEMOS CLAVE COMPLETA
    # ========================================================

    clave_completa = (
        resultado[
            "_clave_placa"
        ].ne("")
        &
        resultado[
            "_clave_celular"
        ].ne("")
        &
        resultado[
            "_clave_motivo"
        ].ne("")
        &
        resultado[
            "_clave_fecha"
        ].notna()
        &
        resultado[
            "_clave_hora"
        ].ne("")
    )

    candidatos = resultado.loc[
        clave_completa
    ].copy()

    sin_clave_completa = resultado.loc[
        ~clave_completa
    ].copy()

    # ========================================================
    # 5. RESOLVER DUPLICADOS
    #
    # Primero Call Center.
    # Después mayor id_cita.
    # ========================================================

    claves_grupo = [
        "_clave_placa",
        "_clave_celular",
        "_clave_fecha",
        "_clave_hora",
        "_clave_motivo",
    ]

    candidatos = candidatos.sort_values(
        claves_grupo
        +
        [
            "_es_callcenter",
            "id_cita",
        ],
        ascending=[
            True,
            True,
            True,
            True,
            True,
            False,
            False,
        ],
        kind="stable",
    )

    candidatos = (
        candidatos
        .drop_duplicates(
            subset=claves_grupo,
            keep="first",
        )
        .copy()
    )

    # ========================================================
    # 6. REUNIR LAS CITAS OPERATIVAS
    # ========================================================

    resultado = pd.concat(
        [
            candidatos,
            sin_clave_completa,
        ],
        ignore_index=True,
    )

    # ========================================================
    # 7. ELIMINAR COLUMNAS TEMPORALES
    # ========================================================

    columnas_control = [
        "_clave_placa",
        "_clave_celular",
        "_clave_motivo",
        "_clave_fecha",
        "_clave_hora",
        "_persona_canonica",
        "_canal_agenda",
        "_es_callcenter",
    ]

    resultado = resultado.drop(
        columns=columnas_control,
        errors="ignore",
    )

    # ========================================================
    # 8. ORDEN ESTABLE
    # ========================================================

    resultado = (
        resultado
        .sort_values(
            [
                "fecha_programada",
                "hora_programada",
                "id_cita",
            ],
            kind="stable",
        )
        .reset_index(
            drop=True
        )
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