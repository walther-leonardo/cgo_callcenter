from __future__ import annotations

from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta
from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

AUTH_PATH = (
    PROJECT_ROOT
    / "auth"
    / "clearmechanic.json"
)

TEMP_DIR = (
    PROJECT_ROOT
    / "temp"
)

BASE_URL = (
    "https://hondapanasanisidro.clearmechanic.com"
)

DASHBOARD_URL = (
    f"{BASE_URL}/dashboard"
)

NOMBRE_REPORTE = "reporte CGO"

# Durante pruebas lo dejamos visible.
# Cuando esté estable cambiaremos a True.
HEADLESS = False


# ============================================================
# VALIDACIONES
# ============================================================

def validar_configuracion() -> None:
    """
    Verifica que exista la sesión guardada y prepara temp/.
    """

    if not AUTH_PATH.exists():
        raise FileNotFoundError(
            "No encontré la sesión de ClearMechanic:\n"
            f"{AUTH_PATH}\n\n"
            "Debes renovar la sesión con Playwright Codegen."
        )

    TEMP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def validar_sesion(
    page: Page,
) -> None:
    """
    Detecta si ClearMechanic redirigió nuevamente al login.

    No intenta resolver CAPTCHA ni ingresar credenciales.
    """

    esta_en_login = (
        "/dashboard/login"
        in page.url
    )

    campo_email = (
        page.locator(
            '[data-test-id="email__input"]'
        )
    )

    if (
        esta_en_login
        or campo_email.is_visible()
    ):
        raise RuntimeError(
            "La sesión de ClearMechanic expiró.\n\n"
            "Debes renovar manualmente "
            "'auth/clearmechanic.json'."
        )


# ============================================================
# NAVEGACIÓN
# ============================================================

def abrir_reportes(
    page: Page,
) -> None:
    """
    Navega desde Dashboard hasta Reportes personalizables.
    """

    page.goto(
        DASHBOARD_URL,
        wait_until="domcontentloaded",
    )

    page.wait_for_timeout(
        1500
    )

    validar_sesion(
        page
    )

    # --------------------------------------------------------
    # ANÁLISIS
    # --------------------------------------------------------

    page.get_by_role(
        "button",
        name="Análisis",
    ).click()

    # --------------------------------------------------------
    # REPORTES
    # --------------------------------------------------------

    page.get_by_role(
        "link",
        name="Reportes",
    ).click()

    page.wait_for_load_state(
        "domcontentloaded"
    )

    # --------------------------------------------------------
    # REPORTES PERSONALIZABLES
    # --------------------------------------------------------

    page.get_by_role(
        "tab",
        name="Reportes personalizables",
    ).click()


# ============================================================
# FECHAS
# ============================================================

def diferencia_meses(
    fecha_origen: date,
    fecha_destino: date,
) -> int:
    """
    Calcula cuántos meses hay que avanzar/retroceder
    en el calendario.
    """

    return (
        (
            fecha_destino.year
            -
            fecha_origen.year
        )
        * 12
        +
        fecha_destino.month
        -
        fecha_origen.month
    )


def seleccionar_dia_calendario(
    page: Page,
    fecha: date,
) -> None:
    """
    Selecciona el número de día visible en el calendario abierto.
    """

    page.get_by_role(
        "gridcell",
        name=str(
            fecha.day
        ),
        exact=True,
    ).click()


def seleccionar_fecha_inicio(
    page: Page,
    fecha_inicio: date,
) -> None:
    """
    Configura la fecha inicial.
    """

    boton_inicio = (
        page.get_by_role(
            "button",
            name="Choose date",
        )
        .nth(0)
    )

    boton_inicio.click()

    # En nuestra automatización inicial la fecha de inicio
    # será el día actual, por lo que normalmente no debemos
    # cambiar de mes.

    seleccionar_dia_calendario(
        page=page,
        fecha=fecha_inicio,
    )


def seleccionar_fecha_fin(
    page: Page,
    fecha_inicio: date,
    fecha_fin: date,
) -> None:
    """
    Configura la fecha final y navega por meses si es necesario.
    """

    boton_fin = (
        page.get_by_role(
            "button",
            name="Choose date",
        )
        .nth(1)
    )

    boton_fin.click()

    meses = diferencia_meses(
        fecha_origen=fecha_inicio,
        fecha_destino=fecha_fin,
    )

    if meses > 0:

        for _ in range(
            meses
        ):
            page.get_by_role(
                "button",
                name="Next month",
            ).click()

    elif meses < 0:

        for _ in range(
            abs(
                meses
            )
        ):
            page.get_by_role(
                "button",
                name="Previous month",
            ).click()

    seleccionar_dia_calendario(
        page=page,
        fecha=fecha_fin,
    )


# ============================================================
# REPORTE
# ============================================================

def abrir_reporte_cgo(
    page: Page,
) -> None:
    """
    Abre el reporte personalizable utilizado por CGO.
    """

    page.get_by_role(
        "button",
        name="Open",
    ).click()

    page.get_by_text(
        NOMBRE_REPORTE,
        exact=True,
    ).click()


# ============================================================
# DESCARGA
# ============================================================

def descargar_reporte(
    page: Page,
) -> Path:
    """
    Descarga el Excel y lo guarda temporalmente.

    Devuelve la ruta local del archivo.
    """

    with page.expect_download(
        timeout=60_000
    ) as download_info:

        page.get_by_role(
            "button",
            name="Descargar reporte",
        ).click()

    download = (
        download_info.value
    )

    timestamp = (
        date.today()
        .strftime(
            "%Y%m%d"
        )
    )

    nombre_archivo = (
        f"clearmechanic_{timestamp}_"
        f"{download.suggested_filename}"
    )

    ruta = (
        TEMP_DIR
        /
        nombre_archivo
    )

    download.save_as(
        ruta
    )

    return ruta


# ============================================================
# ORQUESTADOR
# ============================================================

def descargar_clearmechanic(
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
) -> Path:
    """
    Descarga automáticamente el reporte CGO de ClearMechanic.

    Por defecto:
        fecha_inicio = hoy
        fecha_fin    = hoy + 1 mes
    """

    validar_configuracion()

    if fecha_inicio is None:
        fecha_inicio = (
            date.today()
        )

    if fecha_fin is None:
        fecha_fin = (
            fecha_inicio
            +
            relativedelta(
                months=1
            )
        )

    print()
    print("=" * 68)
    print("CGO CALL CENTER — DESCARGA CLEARMECHANIC")
    print("=" * 68)

    print(
        "Rango: "
        f"{fecha_inicio:%d/%m/%Y}"
        " → "
        f"{fecha_fin:%d/%m/%Y}"
    )

    with sync_playwright() as playwright:

        browser = (
            playwright.chromium.launch(
                headless=HEADLESS
            )
        )

        context: BrowserContext = (
            browser.new_context(
                storage_state=str(
                    AUTH_PATH
                ),
                accept_downloads=True,
            )
        )

        page = (
            context.new_page()
        )

        try:

            print(
                "🔄 Abriendo ClearMechanic..."
            )

            abrir_reportes(
                page
            )

            print(
                "🟢 Sesión válida."
            )

            print(
                "🔄 Configurando fechas..."
            )

            seleccionar_fecha_inicio(
                page=page,
                fecha_inicio=fecha_inicio,
            )

            seleccionar_fecha_fin(
                page=page,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )

            print(
                "🔄 Abriendo reporte CGO..."
            )

            abrir_reporte_cgo(
                page
            )

            print(
                "🔄 Descargando Excel..."
            )

            ruta = descargar_reporte(
                page
            )

            print(
                "✅ Descarga completada:"
            )

            print(
                ruta
            )

            return ruta

        except PlaywrightTimeoutError as exc:

            raise RuntimeError(
                "ClearMechanic no respondió como se esperaba "
                "durante la automatización."
            ) from exc

        finally:

            context.close()
            browser.close()


# ============================================================
# EJECUCIÓN MANUAL
# ============================================================

def main() -> None:

    ruta = descargar_clearmechanic()

    print()
    print(
        "Archivo temporal listo para procesamiento:"
    )
    print(
        ruta
    )
    print()


if __name__ == "__main__":
    main()