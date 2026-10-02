from __future__ import annotations

import hashlib
from datetime import datetime

import pandas as pd
import argparse

from database import (
    guardar_llamadas_cloudtalk,
    inicializar_base,
)
from extraer_cloudtalk import extraer_cloudtalk


# ============================================================
# CONFIGURACIÓN
# ============================================================

MESES_CLOUDTALK = {
    "Jan": "01",
    "Feb": "02",
    "Mar": "03",
    "Apr": "04",
    "May": "05",
    "Jun": "06",
    "Jul": "07",
    "Aug": "08",
    "Sep": "09",
    "Oct": "10",
    "Nov": "11",
    "Dec": "12",
}


# ============================================================
# NORMALIZACIÓN
# ============================================================

def duracion_a_segundos(
    valor,
) -> int:
    """
    Convierte HH:MM:SS a segundos.
    """

    if pd.isna(
        valor
    ):
        return 0

    texto = str(
        valor
    ).strip()

    partes = texto.split(
        ":"
    )

    if len(partes) != 3:
        return 0

    try:

        horas = int(
            partes[0]
        )

        minutos = int(
            partes[1]
        )

        segundos = int(
            partes[2]
        )

    except ValueError:
        return 0

    return (
        horas * 3600
        + minutos * 60
        + segundos
    )


def convertir_fecha_cloudtalk(
    fecha,
    hora,
) -> pd.Timestamp:
    """
    Convierte:
        01 Oct 2026
        17:25:35

    en un timestamp independiente del locale de Windows.
    """

    if pd.isna(
        fecha
    ) or pd.isna(
        hora
    ):
        return pd.NaT

    partes = str(
        fecha
    ).strip().split()

    if len(partes) != 3:
        return pd.NaT

    dia, mes_texto, anio = partes

    mes = MESES_CLOUDTALK.get(
        mes_texto
    )

    if not mes:
        return pd.NaT

    texto = (
        f"{anio}-{mes}-{dia.zfill(2)} "
        f"{str(hora).strip()}"
    )

    return pd.to_datetime(
        texto,
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )


def clasificar_llamada(
    tipo_llamada,
) -> tuple[str, str]:
    """
    Normaliza los tipos visibles en el Dashboard.

    Devuelve:
        (direccion, estado)
    """

    tipo = str(
        tipo_llamada
    ).strip().lower()

    mapa = {
        "inbound":
            (
                "ENTRANTE",
                "ATENDIDA",
            ),

        "outbound":
            (
                "SALIENTE",
                "CONECTADA",
            ),

        "missed outgoing call":
            (
                "SALIENTE",
                "NO_CONECTADA",
            ),

        "missed call":
            (
                "ENTRANTE",
                "PERDIDA",
            ),
    }

    return mapa.get(
        tipo,
        (
            "INDETERMINADO",
            "INDETERMINADO",
        ),
    )


def limpiar_agente(
    valor,
) -> tuple[str | None, str | None]:
    """
    Separa:

        Brenda Montalvan Cornejo via PA Posventa Autos

    en:

        agente       = Brenda Montalvan Cornejo
        canal_agente = PA Posventa Autos
    """

    if pd.isna(
        valor
    ):
        return (
            None,
            None,
        )

    texto = str(
        valor
    ).strip()

    if not texto:
        return (
            None,
            None,
        )

    if " via " not in texto:

        return (
            texto,
            None,
        )

    agente, canal = texto.split(
        " via ",
        maxsplit=1,
    )

    return (
        agente.strip(),
        canal.strip(),
    )


def generar_id_evento(
    fecha_hora,
    telefono_contacto,
    agente,
    tipo_llamada,
) -> str:
    """
    Genera un identificador determinístico para una llamada.

    La duración no forma parte de la identidad para permitir
    que pueda actualizarse posteriormente.
    """

    componentes = [
        ""
        if pd.isna(
            fecha_hora
        )
        else pd.Timestamp(
            fecha_hora
        ).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        ""
        if pd.isna(
            telefono_contacto
        )
        else str(
            telefono_contacto
        ).strip(),

        ""
        if pd.isna(
            agente
        )
        else str(
            agente
        ).strip(),

        ""
        if pd.isna(
            tipo_llamada
        )
        else str(
            tipo_llamada
        ).strip().lower(),
    ]

    texto = "|".join(
        componentes
    )

    return hashlib.sha256(
        texto.encode(
            "utf-8"
        )
    ).hexdigest()


def normalizar_cloudtalk(
    llamadas: pd.DataFrame,
) -> pd.DataFrame:
    """
    Transforma el resultado crudo del DOM en registros
    persistibles y analíticamente consistentes.
    """

    if llamadas.empty:
        return llamadas.copy()

    df = llamadas.copy()

    # --------------------------------------------------------
    # FECHA Y HORA
    # --------------------------------------------------------

    df[
        "fecha_hora"
    ] = [
        convertir_fecha_cloudtalk(
            fecha,
            hora,
        )
        for fecha, hora
        in zip(
            df["fecha"],
            df["hora"],
        )
    ]

    invalidas = df[
        "fecha_hora"
    ].isna()

    if invalidas.any():

        raise ValueError(
            "CloudTalk contiene registros cuya fecha/hora "
            "no pudo convertirse."
        )

    df[
        "fecha"
    ] = (
        df[
            "fecha_hora"
        ]
        .dt.strftime(
            "%Y-%m-%d"
        )
    )

    df[
        "hora"
    ] = (
        df[
            "fecha_hora"
        ]
        .dt.strftime(
            "%H:%M:%S"
        )
    )

    # --------------------------------------------------------
    # DURACIÓN
    # --------------------------------------------------------

    df[
        "duracion_segundos"
    ] = (
        df[
            "duracion"
        ]
        .apply(
            duracion_a_segundos
        )
        .astype(
            int
        )
    )

    # --------------------------------------------------------
    # DIRECCIÓN / ESTADO
    # --------------------------------------------------------

    clasificaciones = (
        df[
            "tipo_llamada"
        ]
        .apply(
            clasificar_llamada
        )
    )

    df[
        "direccion"
    ] = [
        valor[0]
        for valor
        in clasificaciones
    ]

    df[
        "estado"
    ] = [
        valor[1]
        for valor
        in clasificaciones
    ]

    # --------------------------------------------------------
    # AGENTE / CANAL
    # --------------------------------------------------------

    agentes = (
        df[
            "agente"
        ]
        .apply(
            limpiar_agente
        )
    )

    df[
        "agente"
    ] = [
        valor[0]
        for valor
        in agentes
    ]

    df[
        "canal_agente"
    ] = [
        valor[1]
        for valor
        in agentes
    ]

    # --------------------------------------------------------
    # ID DETERMINÍSTICO
    # --------------------------------------------------------

    df[
        "id_evento"
    ] = [
        generar_id_evento(
            fecha_hora=fecha_hora,
            telefono_contacto=telefono,
            agente=agente,
            tipo_llamada=tipo_llamada,
        )
        for (
            fecha_hora,
            telefono,
            agente,
            tipo_llamada,
        )
        in zip(
            df[
                "fecha_hora"
            ],
            df[
                "telefono_contacto"
            ],
            df[
                "agente"
            ],
            df[
                "tipo_llamada"
            ],
        )
    ]

    # --------------------------------------------------------
    # AUDITORÍA DE CARGA
    # --------------------------------------------------------

    ahora = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    df[
        "fecha_primera_carga"
    ] = ahora

    df[
        "fecha_ultima_carga"
    ] = ahora

    # --------------------------------------------------------
    # SQLITE
    # --------------------------------------------------------

    df[
        "fecha_hora"
    ] = (
        df[
            "fecha_hora"
        ]
        .dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    return df


# ============================================================
# RESUMEN
# ============================================================

def mostrar_resumen(
    llamadas: pd.DataFrame,
) -> None:

    print()
    print("=" * 72)
    print("RESUMEN CLOUDTALK")
    print("=" * 72)

    if llamadas.empty:

        print(
            "No existen llamadas."
        )

        return

    resumen = (
        llamadas
        .groupby(
            [
                "agente",
                "direccion",
                "estado",
            ],
            dropna=False,
        )
        .agg(
            llamadas=(
                "id_evento",
                "count",
            ),
            duracion_segundos=(
                "duracion_segundos",
                "sum",
            ),
        )
        .reset_index()
    )

    print(
        resumen.to_string(
            index=False
        )
    )


def leer_argumentos():
    """
    Argumentos de ejecución.

    Sin argumentos:
        procesa HOY.

    --periodo ayer:
        procesa AYER.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Actualizador operativo de CloudTalk."
        )
    )

    parser.add_argument(
        "--periodo",
        choices=[
            "hoy",
            "ayer",
        ],
        default="hoy",
        help=(
            "Período a extraer desde CloudTalk. "
            "Default: hoy."
        ),
    )

    return parser.parse_args()



# ============================================================
# MAIN
# ============================================================

def main(
    periodo: str = "hoy",
) -> None:

    print()
    print("=" * 72)
    print("CGO CALL CENTER — ACTUALIZADOR CLOUDTALK")
    print("=" * 72)

    inicializar_base()

    # --------------------------------------------------------
    # EXTRAER
    # --------------------------------------------------------

    llamadas_raw = (
        extraer_cloudtalk(
            periodo=periodo
        )
    )

    print()
    print(
        f"📞 Registros DOM extraídos: "
        f"{len(llamadas_raw)}"
    )

    if llamadas_raw.empty:

        print(
            "⚠️ CloudTalk no devolvió llamadas."
        )

        return

    # --------------------------------------------------------
    # NORMALIZAR
    # --------------------------------------------------------

    llamadas = normalizar_cloudtalk(
        llamadas_raw
    )

    tipos_desconocidos = (
        llamadas.loc[
            llamadas[
                "direccion"
            ].eq(
                "INDETERMINADO"
            ),
            "tipo_llamada",
        ]
        .dropna()
        .drop_duplicates()
        .tolist()
    )

    if tipos_desconocidos:

        print()
        print(
            "⚠️ Tipos de llamada todavía "
            "no clasificados:"
        )

        for tipo in tipos_desconocidos:

            print(
                f"   - {tipo}"
            )

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    nuevas, actualizadas = (
        guardar_llamadas_cloudtalk(
            llamadas
        )
    )

    print()
    print(
        f"✅ Llamadas nuevas: {nuevas}"
    )

    print(
        f"🔄 Llamadas existentes actualizadas: "
        f"{actualizadas}"
    )

    mostrar_resumen(
        llamadas
    )

    print()
    print("=" * 72)
    print("✅ CLOUDTALK ACTUALIZADO")
    print("=" * 72)


if __name__ == "__main__":

    argumentos = leer_argumentos()

    main(
        periodo=argumentos.periodo
    )