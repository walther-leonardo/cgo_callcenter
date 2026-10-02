from pathlib import Path

import pandas as pd

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from renovar_sesion_cloudtalk import abrir_cloudtalk

from renovar_sesion_cloudtalk import abrir_cloudtalk


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

CDP_URL = "http://127.0.0.1:9333"

SALIDA_CSV = (
    PROJECT_ROOT
    / "temp"
    / "cloudtalk_llamadas_hoy.csv"
)

AGENTES = [
    147645,  # Rocío
    251589,  # Brenda
]

MAX_PAGINAS = 50

PERIODOS_CLOUDTALK = {
    "hoy": "0%20day",
    "ayer": "yesterday",
}

# ============================================================
# URL
# ============================================================

def construir_url(
    pagina: int,
    periodo: str = "hoy",
) -> str:
    """
    Construye la URL filtrada de CloudTalk.

    Períodos soportados:
        hoy
        ayer
    """

    if periodo not in PERIODOS_CLOUDTALK:

        raise ValueError(
            "Período CloudTalk no soportado: "
            f"{periodo!r}"
        )

    parametros_agentes = "&".join(
        f"agentIds={agente}"
        for agente in AGENTES
    )

    duracion = PERIODOS_CLOUDTALK[
        periodo
    ]

    return (
        "https://dashboard.cloudtalk.io/menu/dashboard"
        f"?pageIndex={pagina}"
        f"&{parametros_agentes}"
        f"&duration={duracion}"
    )


# ============================================================
# PARSEO
# ============================================================

def limpiar_lineas(
    texto: str,
) -> list[str]:
    """
    Convierte el contenido multilínea de una celda
    en una lista limpia de valores.
    """

    return [
        linea.strip()
        for linea in texto.splitlines()
        if linea.strip()
    ]


def parsear_fila(
    fila,
    pagina: int,
) -> dict:
    """
    Extrae los datos visibles de una fila de CloudTalk.

    Se trabaja por celdas para evitar depender de posiciones
    dentro del texto completo de la fila.
    """

    celdas = fila.locator("td")

    cantidad_celdas = celdas.count()

    if cantidad_celdas < 4:
        raise ValueError(
            "La fila no tiene la cantidad mínima "
            f"de celdas esperada: {cantidad_celdas}"
        )

    # --------------------------------------------------------
    # TIPO
    # --------------------------------------------------------

    tipo_lineas = limpiar_lineas(
        celdas.nth(0).inner_text()
    )

    tipo_llamada = (
        tipo_lineas[0]
        if len(tipo_lineas) >= 1
        else None
    )

    duracion = (
        tipo_lineas[1]
        if len(tipo_lineas) >= 2
        else None
    )

    # --------------------------------------------------------
    # CONTACTO
    # --------------------------------------------------------

    contacto_lineas = limpiar_lineas(
        celdas.nth(1).inner_text()
    )

    contacto = (
        contacto_lineas[0]
        if len(contacto_lineas) >= 1
        else None
    )

    telefono_contacto = (
        contacto_lineas[1]
        if len(contacto_lineas) >= 2
        else contacto
    )

    # --------------------------------------------------------
    # AGENTE
    # --------------------------------------------------------

    agente_lineas = limpiar_lineas(
        celdas.nth(2).inner_text()
    )

    # Puede existir una línea de iniciales:
    # BM / RD
    if (
        len(agente_lineas) >= 2
        and len(agente_lineas[0]) <= 3
    ):
        agente_lineas = agente_lineas[1:]

    agente_raw = (
        agente_lineas[0]
        if len(agente_lineas) >= 1
        else None
    )

    canal_agente = None
    agente = agente_raw

    if agente_raw and " via " in agente_raw:

        agente, canal_agente = (
            parte.strip()
            for parte in agente_raw.split(
                " via ",
                maxsplit=1,
            )
        )

    telefono_agente = (
        agente_lineas[1]
        if len(agente_lineas) >= 2
        else None
    )

    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    fecha_lineas = limpiar_lineas(
        celdas.nth(3).inner_text()
    )

    fecha = (
        fecha_lineas[0]
        if len(fecha_lineas) >= 1
        else None
    )

    hora = (
        fecha_lineas[1]
        if len(fecha_lineas) >= 2
        else None
    )

    return {
    "pagina":
        pagina,

    "tipo_llamada":
        tipo_llamada,

    "duracion":
        duracion,

    "contacto":
        contacto,

    "telefono_contacto":
        telefono_contacto,

    "agente":
        agente,

    "canal_agente":
        canal_agente,

    "telefono_agente":
        telefono_agente,

    "fecha":
        fecha,

    "hora":
        hora,
}

def esperar_historial(
    page,
    timeout_ms: int = 30_000,
) -> str:
    """
    Espera a que CloudTalk termine de renderizar el historial.

    Devuelve:
        "CON_DATOS"
            Si aparece al menos una fila.

        "VACIO"
            Si CloudTalk muestra explícitamente que no hay
            llamadas para los filtros seleccionados.

    Lanza TimeoutError únicamente si CloudTalk no llega
    a ninguno de los dos estados dentro del tiempo límite.
    """

    filas = page.locator(
        "tbody tr"
    )

    estado_vacio = page.get_by_text(
        "Tus llamadas aparecerán aquí.",
        exact=False,
    )

    intervalo_ms = 500

    tiempo_transcurrido = 0

    while tiempo_transcurrido < timeout_ms:

        # ----------------------------------------------------
        # CASO 1: EXISTEN LLAMADAS
        # ----------------------------------------------------

        if filas.count() > 0:

            return "CON_DATOS"

        # ----------------------------------------------------
        # CASO 2: CLOUDTALK CONFIRMA DÍA VACÍO
        # ----------------------------------------------------

        try:

            if (
                estado_vacio.count() > 0
                and estado_vacio.first.is_visible()
            ):

                return "VACIO"

        except PlaywrightError:
            pass

        # ----------------------------------------------------
        # ESPERAR SIGUIENTE COMPROBACIÓN
        # ----------------------------------------------------

        page.wait_for_timeout(
            intervalo_ms
        )

        tiempo_transcurrido += (
            intervalo_ms
        )

    raise PlaywrightTimeoutError(
        "CloudTalk no mostró llamadas ni confirmó "
        "un historial vacío dentro del tiempo esperado."
    )


def conectar_pagina_cloudtalk(
    playwright,
):
    """
    Garantiza que exista Chrome CloudTalk y devuelve
    una conexión CDP + contexto + pestaña utilizable.

    Si Chrome está cerrado, lo vuelve a abrir.
    Si Chrome está abierto pero no existe una pestaña
    CloudTalk, crea una nueva.
    """

    abrir_cloudtalk()

    browser = (
        playwright.chromium.connect_over_cdp(
            CDP_URL
        )
    )

    if not browser.contexts:

        raise RuntimeError(
            "Chrome está disponible, pero no existe "
            "ningún contexto de navegador."
        )

    context = browser.contexts[0]

    paginas_cloudtalk = [
        pagina
        for pagina in context.pages
        if "cloudtalk" in pagina.url.lower()
    ]

    if paginas_cloudtalk:

        page = paginas_cloudtalk[0]

    else:

        page = context.new_page()

    return (
        browser,
        context,
        page,
    )



# ============================================================
# EXTRACCIÓN
# ============================================================

def extraer_cloudtalk(
    periodo: str = "hoy",
) -> pd.DataFrame:
    """
    Extrae todas las páginas disponibles del historial
    de llamadas de hoy para Rocío y Brenda.

    La extracción es resiliente:
    si Chrome o la pestaña se cierran durante el proceso,
    intenta recuperar la sesión y continuar desde la
    misma página.
    """

    registros = []

    firmas_vistas = set()

    print()
    print("=" * 72)
    print("CGO CALL CENTER — EXTRACCIÓN CLOUDTALK")
    print("=" * 72)

    with sync_playwright() as playwright:

        (
            browser,
            context,
            page,
        ) = conectar_pagina_cloudtalk(
            playwright
        )

        # ----------------------------------------------------
        # RECORRER PÁGINAS
        # ----------------------------------------------------

        for numero_pagina in range(
            1,
            MAX_PAGINAS + 1,
        ):

            url = construir_url(
                pagina=numero_pagina,
                periodo=periodo,
            )

            pagina_extraida = False

            # ------------------------------------------------
            # REINTENTOS POR PÁGINA
            # ------------------------------------------------

            for intento in range(
                1,
                4,
            ):

                try:

                    print()
                    print(
                        f"🔄 Página {numero_pagina}..."
                    )
                    print(
                        f"Período: {periodo.upper()}"
                    )

                    if intento > 1:

                        print(
                            f"   ♻️ Reintento "
                            f"{intento}/3..."
                        )

                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )

                    print(
                        "   ⏳ Esperando historial "
                        "de llamadas..."
                    )

                    estado_historial = esperar_historial(
                        page=page,
                        timeout_ms=30_000,
                    )

                    # --------------------------------------------------------
                    # DÍA SIN LLAMADAS
                    # --------------------------------------------------------

                    if estado_historial == "VACIO":

                        print(
                            "   ℹ️ CloudTalk no tiene llamadas "
                            "para este período."
                        )

                        if numero_pagina == 1:

                            print(
                                "   ✅ Extracción válida: 0 llamadas."
                            )

                        else:

                            print(
                                "   ✅ Fin de paginación."
                            )

                        return pd.DataFrame(
                            registros
                        )


                    # --------------------------------------------------------
                    # DÍA CON LLAMADAS
                    # --------------------------------------------------------

                    filas = page.locator(
                        "tbody tr"
                    )

                    cantidad = filas.count()

                    print(
                        f"   Filas encontradas: {cantidad}"
                    )

                    if cantidad == 0:

                        raise RuntimeError(
                            "CloudTalk indicó que existen datos, "
                            "pero no se encontraron filas en el DOM."
                        )

                    # ----------------------------------------
                    # EVITAR PÁGINA REPETIDA
                    # ----------------------------------------

                    primera_fila = (
                        filas
                        .nth(0)
                        .inner_text()
                        .strip()
                    )

                    ultima_fila = (
                        filas
                        .nth(
                            cantidad - 1
                        )
                        .inner_text()
                        .strip()
                    )

                    firma = (
                        primera_fila,
                        ultima_fila,
                    )

                    if firma in firmas_vistas:

                        print(
                            "   ✅ CloudTalk repitió "
                            "la página anterior."
                        )

                        print(
                            "   Fin de paginación."
                        )

                        return pd.DataFrame(
                            registros
                        )

                    # ----------------------------------------
                    # EXTRAER FILAS DE LA PÁGINA
                    # ----------------------------------------

                    registros_pagina = []

                    for indice in range(
                        cantidad
                    ):

                        fila = filas.nth(
                            indice
                        )

                        registro = parsear_fila(
                            fila=fila,
                            pagina=numero_pagina,
                        )

                        registros_pagina.append(
                            registro
                        )

                    # Solo confirmamos página después de
                    # haber extraído todas sus filas.
                    registros.extend(
                        registros_pagina
                    )

                    firmas_vistas.add(
                        firma
                    )

                    pagina_extraida = True

                    # ----------------------------------------
                    # ÚLTIMA PÁGINA
                    # ----------------------------------------

                    if cantidad < 20:

                        print(
                            "   ✅ Última página "
                            "detectada."
                        )

                        return pd.DataFrame(
                            registros
                        )

                    break

                except (
                    PlaywrightError,
                    PlaywrightTimeoutError,
                ) as exc:

                    print()
                    print(
                        "   ⚠️ CloudTalk perdió la "
                        "pestaña o dejó de responder."
                    )

                    print(
                        f"   Detalle: "
                        f"{type(exc).__name__}"
                    )

                    if intento == 3:

                        raise RuntimeError(
                            "No fue posible recuperar "
                            f"CloudTalk en la página "
                            f"{numero_pagina} después "
                            "de 3 intentos."
                        ) from exc

                    print(
                        "   🔄 Recuperando Chrome "
                        "y sesión CloudTalk..."
                    )

                    (
                        browser,
                        context,
                        page,
                    ) = conectar_pagina_cloudtalk(
                        playwright
                    )

            if not pagina_extraida:

                raise RuntimeError(
                    "La extracción de CloudTalk "
                    f"quedó incompleta en la página "
                    f"{numero_pagina}."
                )

    return pd.DataFrame(
        registros
    )

# ============================================================
# MAIN
# ============================================================

def main() -> None:

    df = extraer_cloudtalk()

    print()
    print("=" * 72)
    print("RESULTADO")
    print("=" * 72)

    print(
        f"Registros extraídos: {len(df)}"
    )

    if df.empty:

        print(
            "⚠️ No se obtuvieron llamadas."
        )

        return

    SALIDA_CSV.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        SALIDA_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        df[
            [
                "tipo_llamada",
                "duracion",
                "agente",
                "fecha",
                "hora",
            ]
        ]
        .head(10)
        .to_string(
            index=False
        )
    )

    print()
    print(
        f"✅ Archivo generado:\n"
        f"{SALIDA_CSV}"
    )


if __name__ == "__main__":
    main()