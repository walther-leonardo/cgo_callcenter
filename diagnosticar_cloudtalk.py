from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

DIAGNOSTICO_PATH = (
    PROJECT_ROOT
    / "temp"
    / "cloudtalk_dom.txt"
)

CDP_URL = "http://127.0.0.1:9333"

URL_CLOUDTALK = (
    "https://dashboard.cloudtalk.io/menu/dashboard"
    "?pageIndex=1"
    "&agentIds=147645"
    "&agentIds=251589"
    "&duration=0%20day"
)


# ============================================================
# DIAGNÓSTICO
# ============================================================

def diagnosticar_cloudtalk() -> None:
    """
    Abre directamente el dashboard filtrado de CloudTalk
    y analiza cómo está construida la tabla de llamadas.
    """

    DIAGNOSTICO_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 72)
    print("CGO CALL CENTER — DIAGNÓSTICO DOM CLOUDTALK")
    print("=" * 72)

    with sync_playwright() as playwright:

        browser = (
            playwright.chromium.connect_over_cdp(
                CDP_URL
            )
        )

        if not browser.contexts:
            raise RuntimeError(
                "No se encontró un contexto de Chrome."
            )

        context = browser.contexts[0]

        paginas = [
            pagina
            for pagina in context.pages
            if "cloudtalk" in pagina.url.lower()
        ]

        if not paginas:
            raise RuntimeError(
                "No se encontró una pestaña de CloudTalk."
            )

        page = paginas[0]

        print()
        print(
            "🔄 Abriendo filtros directos..."
        )

        page.goto(
            URL_CLOUDTALK,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        print(
            "⏳ Esperando que CloudTalk termine de renderizar..."
        )

        page.wait_for_timeout(
            8_000
        )

        print()
        print(
            f"URL final:\n{page.url}"
        )

        # ----------------------------------------------------
        # LOCALIZAR HISTORIAL
        # ----------------------------------------------------

        historial = page.get_by_text(
            "Historial de llamadas",
            exact=True,
        )

        print()
        print(
            "Historial de llamadas encontrado:",
            historial.count(),
        )

        # ----------------------------------------------------
        # PROBAR ESTRUCTURAS COMUNES
        # ----------------------------------------------------

        selectores = {
            "table":
                "table",

            "tbody tr":
                "tbody tr",

            "role=row":
                '[role="row"]',

            "role=rowgroup":
                '[role="rowgroup"]',

            "data-row":
                '[data-row]',
        }

        resultados = []

        print()
        print("=" * 72)
        print("ESTRUCTURAS ENCONTRADAS")
        print("=" * 72)

        for nombre, selector in selectores.items():

            elementos = page.locator(
                selector
            )

            cantidad = elementos.count()

            print(
                f"{nombre:<20}: {cantidad}"
            )

            resultados.append(
                f"{nombre}: {cantidad}"
            )

        # ----------------------------------------------------
        # TEXTO VISIBLE COMPLETO
        # ----------------------------------------------------

        body_texto = page.locator(
            "body"
        ).inner_text()

        with DIAGNOSTICO_PATH.open(
            "w",
            encoding="utf-8",
        ) as archivo:

            archivo.write(
                "=== ESTRUCTURAS ===\n"
            )

            archivo.write(
                "\n".join(
                    resultados
                )
            )

            archivo.write(
                "\n\n=== TEXTO VISIBLE ===\n\n"
            )

            archivo.write(
                body_texto
            )

        print()
        print(
            f"✅ Diagnóstico guardado en:\n"
            f"{DIAGNOSTICO_PATH}"
        )

        # ----------------------------------------------------
        # MUESTRA DE FILAS
        # ----------------------------------------------------

        filas = page.locator(
            'tbody tr'
        )

        if filas.count() > 0:

            print()
            print("=" * 72)
            print("MUESTRA DE FILAS")
            print("=" * 72)

            limite = min(
                filas.count(),
                5,
            )

            for indice in range(
                limite
            ):

                texto = (
                    filas
                    .nth(indice)
                    .inner_text()
                )

                print()
                print(
                    f"Fila #{indice + 1}:"
                )

                print(
                    texto
                )

        else:

            print()
            print(
                "ℹ️ No se detectaron filas con 'tbody tr'."
            )

            print(
                "Usaremos el archivo cloudtalk_dom.txt "
                "para identificar la estructura real."
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    diagnosticar_cloudtalk()