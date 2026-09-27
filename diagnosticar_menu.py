from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

BROWSER_PROFILE = (
    PROJECT_ROOT
    / "browser_profile"
)

URL = (
    "https://hondapanasanisidro.clearmechanic.com/dashboard/orders"
)


# ============================================================
# HELPERS
# ============================================================

def leer_atributo(
    locator,
    atributo: str,
) -> str:
    """
    Lee un atributo HTML sin detener el diagnóstico
    si el elemento no lo contiene.
    """

    try:
        valor = locator.get_attribute(
            atributo
        )

        return (
            valor.strip()
            if valor
            else ""
        )

    except Exception:
        return ""


def leer_texto(
    locator,
) -> str:
    """
    Obtiene texto visible del elemento.
    """

    try:
        texto = locator.inner_text(
            timeout=1000
        )

        return (
            texto.strip()
            .replace(
                "\n",
                " | ",
            )
        )

    except Exception:
        return ""


def mostrar_elementos(
    page,
    selector: str,
    titulo: str,
) -> None:
    """
    Lista elementos visibles y sus atributos útiles
    para construir selectores robustos.
    """

    print()
    print("=" * 90)
    print(titulo)
    print("=" * 90)

    elementos = page.locator(
        selector
    )

    total = elementos.count()

    encontrados = 0

    for indice in range(
        total
    ):

        elemento = elementos.nth(
            indice
        )

        try:

            if not elemento.is_visible():
                continue

        except Exception:
            continue

        encontrados += 1

        texto = leer_texto(
            elemento
        )

        aria_label = leer_atributo(
            elemento,
            "aria-label",
        )

        title = leer_atributo(
            elemento,
            "title",
        )

        data_test_id = leer_atributo(
            elemento,
            "data-test-id",
        )

        class_name = leer_atributo(
            elemento,
            "class",
        )

        print()
        print(
            f"[{indice}]"
        )

        print(
            f"  texto        : {texto!r}"
        )

        print(
            f"  aria-label   : {aria_label!r}"
        )

        print(
            f"  title        : {title!r}"
        )

        print(
            f"  data-test-id : {data_test_id!r}"
        )

        print(
            f"  class        : {class_name[:180]!r}"
        )

    if encontrados == 0:

        print(
            "No se encontraron elementos visibles."
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print("=" * 90)
    print("CGO CALL CENTER — DIAGNÓSTICO MENÚ CLEARMECHANIC")
    print("=" * 90)

    with sync_playwright() as playwright:

        context = (
            playwright.chromium.launch_persistent_context(
                user_data_dir=str(
                    BROWSER_PROFILE
                ),
                headless=False,
                viewport=None,
                args=[
                    "--start-maximized",
                ],
            )
        )

        if context.pages:
            page = context.pages[0]

        else:
            page = context.new_page()

        page.goto(
            URL,
            wait_until="domcontentloaded",
        )

        page.wait_for_timeout(
            2500
        )

        print()
        print(
            f"URL actual: {page.url}"
        )

        print()
        print("=" * 90)
        print("INSPECCIÓN DEL PRIMER BOTÓN")
        print("=" * 90)

        boton_menu = page.locator("button").nth(0)

        print()
        print(
            "HTML:"
        )

        print(
            boton_menu.inner_html()
        )

        print()
        print("=" * 90)
        print("SVG / ICONOS VISIBLES")
        print("=" * 90)

        svgs = page.locator(
            "svg"
        )

        for indice in range(
            svgs.count()
        ):

            svg = svgs.nth(
                indice
            )

            try:

                if not svg.is_visible():
                    continue

            except Exception:
                continue

            data_testid = (
                svg.get_attribute(
                    "data-testid"
                )
                or ""
            )

            aria_label = (
                svg.get_attribute(
                    "aria-label"
                )
                or ""
            )

            print(
                f"[{indice}] "
                f"data-testid={data_testid!r} "
                f"aria-label={aria_label!r}"
            )

        mostrar_elementos(
            page=page,
            selector="button",
            titulo="BOTONES VISIBLES",
        )

        mostrar_elementos(
            page=page,
            selector="a",
            titulo="ENLACES VISIBLES",
        )

        print()
        print("=" * 90)
        print(
            "Deja el navegador abierto mientras revisas "
            "la información de la terminal."
        )
        print("=" * 90)

        input(
            "\nPresiona ENTER para cerrar..."
        )

        context.close()


if __name__ == "__main__":
    main()