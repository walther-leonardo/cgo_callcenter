from __future__ import annotations

from playwright.sync_api import sync_playwright

from renovar_sesion_cloudtalk import abrir_cloudtalk


# ============================================================
# CONFIGURACIÓN
# ============================================================

CDP_URL = "http://127.0.0.1:9333"

URL_CLOUDTALK = (
    "https://dashboard.cloudtalk.io/menu/dashboard"
    "?pageIndex=1"
    "&agentIds=147645"
    "&agentIds=251589"
    "&duration=0%20day"
)

FILAS_A_REVISAR = 5


# ============================================================
# HELPERS
# ============================================================

def atributos_elemento(locator) -> dict:
    """
    Devuelve todos los atributos HTML del primer elemento
    representado por el locator.
    """

    return locator.evaluate(
        """
        element => {
            const attrs = {};

            for (const attr of element.attributes) {
                attrs[attr.name] = attr.value;
            }

            return attrs;
        }
        """
    )


def atributos_relevantes_descendientes(fila) -> list[dict]:
    """
    Busca dentro de la fila elementos que podrían contener
    identificadores, enlaces u otros metadatos útiles.
    """

    return fila.evaluate(
        """
        row => {
            const resultados = [];

            for (const element of row.querySelectorAll('*')) {
                const attrs = {};

                for (const attr of element.attributes) {

                    const nombre = attr.name.toLowerCase();

                    if (
                        nombre === 'id' ||
                        nombre === 'href' ||
                        nombre === 'name' ||
                        nombre === 'value' ||
                        nombre === 'title' ||
                        nombre === 'aria-label' ||
                        nombre.startsWith('data-')
                    ) {
                        attrs[attr.name] = attr.value;
                    }
                }

                if (Object.keys(attrs).length > 0) {
                    resultados.push({
                        tag: element.tagName,
                        atributos: attrs,
                    });
                }
            }

            return resultados;
        }
        """
    )


# ============================================================
# DIAGNÓSTICO
# ============================================================

def diagnosticar_ids() -> None:

    print()
    print("=" * 72)
    print("CGO CALL CENTER — BÚSQUEDA DE ID DE LLAMADA")
    print("=" * 72)

    abrir_cloudtalk()

    with sync_playwright() as playwright:

        browser = playwright.chromium.connect_over_cdp(
            CDP_URL
        )

        if not browser.contexts:
            raise RuntimeError(
                "No se encontró un contexto de Chrome."
            )

        context = browser.contexts[0]

        paginas = [
            page
            for page in context.pages
            if "cloudtalk" in page.url.lower()
        ]

        if not paginas:
            raise RuntimeError(
                "No se encontró una pestaña de CloudTalk."
            )

        page = paginas[0]

        print()
        print("🔄 Abriendo página de llamadas...")

        page.goto(
            URL_CLOUDTALK,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        filas = page.locator(
            "tbody tr"
        )

        filas.first.wait_for(
            state="attached",
            timeout=30_000,
        )

        cantidad = filas.count()

        print(
            f"✅ Filas encontradas: {cantidad}"
        )

        limite = min(
            FILAS_A_REVISAR,
            cantidad,
        )

        for indice in range(limite):

            fila = filas.nth(indice)

            print()
            print("=" * 72)
            print(
                f"FILA #{indice + 1}"
            )
            print("=" * 72)

            print()
            print("Texto:")
            print(
                fila.inner_text()
            )

            print()
            print("Atributos del <tr>:")

            atributos_fila = atributos_elemento(
                fila
            )

            if atributos_fila:
                for clave, valor in atributos_fila.items():
                    print(
                        f"  {clave} = {valor}"
                    )
            else:
                print(
                    "  (sin atributos relevantes)"
                )

            print()
            print("Atributos relevantes internos:")

            descendientes = (
                atributos_relevantes_descendientes(
                    fila
                )
            )

            if not descendientes:
                print(
                    "  (ninguno encontrado)"
                )

            for elemento in descendientes:

                print(
                    f"  <{elemento['tag']}> "
                    f"{elemento['atributos']}"
                )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    diagnosticar_ids()