from __future__ import annotations

import shutil

from datetime import date
from pathlib import Path

import requests

from dateutil.relativedelta import relativedelta
from playwright.sync_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

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

BROWSER_PROFILE = (
    PROJECT_ROOT
    / "browser_profile"
)

CUSTOM_REPORTS_URL = (
    f"{BASE_URL}/dashboard/reports/customreports"
)

# Durante pruebas lo dejamos visible.
# Cuando esté estable cambiaremos a True.
HEADLESS = False


# ============================================================
# VALIDACIONES
# ============================================================

def validar_configuracion() -> None:
    """
    Prepara las carpetas necesarias para la automatización.
    """

    TEMP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    BROWSER_PROFILE.mkdir(
        parents=True,
        exist_ok=True,
    )

def validar_sesion(
    page: Page,
) -> None:
    """
    Comprueba si ClearMechanic mantiene una sesión autenticada.

    La autenticación se conserva mediante browser_profile/.
    No utiliza auth/clearmechanic.json.
    """

    url_actual = page.url.lower()

    campo_email = page.locator(
        '[data-test-id="email__input"]'
    )

    campo_password = page.locator(
        '[data-test-id="password__input"]'
    )

    login_visible = False

    try:
        login_visible = (
            campo_email.is_visible()
            or campo_password.is_visible()
        )
    except Exception:
        login_visible = False

    if (
        "/dashboard/login" in url_actual
        or login_visible
    ):
        raise RuntimeError(
            "La sesión de ClearMechanic no está activa.\n\n"
            "Ejecuta:\n"
            "    py .\\renovar_sesion.py\n\n"
            "Haz login manualmente y, cuando estés dentro del "
            "Dashboard, vuelve a la terminal y presiona ENTER."
        )

# ============================================================
# NAVEGACIÓN
# ============================================================

def abrir_reportes(
    page: Page,
) -> None:
    """
    Abre directamente la pantalla de Reportes personalizables.

    Evitamos navegar por:
        Menú > Análisis > Reportes

    porque ya conocemos la URL estable del módulo.
    """

    page.goto(
        CUSTOM_REPORTS_URL,
        wait_until="domcontentloaded",
    )

    page.wait_for_timeout(
        2000
    )

    validar_sesion(
        page
    )

    print(
        f"   URL actual: {page.url}"
    )

    if "/dashboard/reports/customreports" not in page.url:
        raise RuntimeError(
            "ClearMechanic no llegó a Reportes personalizables. "
            f"URL actual: {page.url}"
        )

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


def obtener_boton_visible(
    locator,
):
    """
    Devuelve el primer elemento visible dentro de un locator.
    """

    for indice in range(
        locator.count()
    ):

        candidato = locator.nth(
            indice
        )

        try:

            if candidato.is_visible():
                return candidato

        except Exception:
            continue

    return None


def seleccionar_dia_calendario(
    page: Page,
    fecha: date,
) -> None:
    """
    Selecciona un día dentro del calendario actualmente visible.
    """

    calendario_visible = (
        page.locator('[role="grid"]:visible')
        .last
    )

    calendario_visible.wait_for(
        state="visible",
        timeout=10_000,
    )

    candidatos = calendario_visible.get_by_role(
        "gridcell",
        name=str(fecha.day),
        exact=True,
    )

    total = candidatos.count()

    if total == 0:
        raise RuntimeError(
            f"No se encontró el día {fecha.day} "
            "en el calendario visible."
        )

    # Elegimos la primera celda visible y habilitada.
    for indice in range(total):

        candidato = candidatos.nth(
            indice
        )

        try:

            if (
                candidato.is_visible()
                and candidato.is_enabled()
            ):
                candidato.click()
                return

        except Exception:
            continue

    raise RuntimeError(
        f"No se pudo seleccionar el día {fecha.day}."
    )


def seleccionar_fecha_inicio(
    page: Page,
    fecha_inicio: date,
) -> None:
    """
    Selecciona la fecha inicial.
    """

    boton_inicio = (
        page.get_by_role(
            "button",
            name="Choose date",
        )
        .nth(0)
    )

    boton_inicio.click()

    page.wait_for_timeout(
        300
    )

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
    Selecciona la fecha final.

    Navega por meses usando únicamente el calendario visible.
    """

    boton_fin = (
        page.get_by_role(
            "button",
            name="Choose date",
        )
        .nth(1)
    )

    boton_fin.click()

    page.wait_for_timeout(
        300
    )

    meses = diferencia_meses(
        fecha_origen=fecha_inicio,
        fecha_destino=fecha_fin,
    )

    if meses > 0:

        for _ in range(meses):

            botones_siguiente = (
                page.get_by_role(
                    "button",
                    name="Next month",
                )
            )

            boton_siguiente = obtener_boton_visible(
                botones_siguiente
            )

            if boton_siguiente is None:
                raise RuntimeError(
                    "No se encontró el botón visible "
                    "'Next month'."
                )

            boton_siguiente.click()

            page.wait_for_timeout(
                250
            )

    elif meses < 0:

        for _ in range(
            abs(meses)
        ):

            botones_anterior = (
                page.get_by_role(
                    "button",
                    name="Previous month",
                )
            )

            boton_anterior = obtener_boton_visible(
                botones_anterior
            )

            if boton_anterior is None:
                raise RuntimeError(
                    "No se encontró el botón visible "
                    "'Previous month'."
                )

            boton_anterior.click()

            page.wait_for_timeout(
                250
            )

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
    Selecciona el reporte personalizable utilizado por CGO.

    Evitamos buscar simplemente un botón llamado "Open",
    porque Material UI utiliza ese texto también en algunos
    controles internos del calendario.
    """

    # ========================================================
    # ABRIR SELECTOR DE REPORTES
    # ========================================================

    boton_selector = page.locator(
        'button[title="Open"]'
    )

    boton_selector.wait_for(
        state="visible",
        timeout=10_000,
    )

    boton_selector.click()

    page.wait_for_timeout(
        300
    )

    # ========================================================
    # SELECCIONAR "reporte CGO"
    # ========================================================

    opcion_reporte = page.get_by_text(
        NOMBRE_REPORTE,
        exact=True,
    )

    opcion_reporte.wait_for(
        state="visible",
        timeout=10_000,
    )

    opcion_reporte.click()

    page.wait_for_timeout(
        700
    )

    # ========================================================
    # VALIDAR QUE EL REPORTE QUEDÓ SELECCIONADO
    # ========================================================

    boton_descarga = page.get_by_role(
        "button",
        name="Descargar reporte",
        exact=True,
    )

    boton_descarga.wait_for(
        state="visible",
        timeout=15_000,
    )

    print(
        f"   Reporte seleccionado: {NOMBRE_REPORTE}"
    )

# ============================================================
# DESCARGA
# ============================================================

def descargar_reporte(
    page: Page,
) -> Path:
    """
    Genera el reporte en ClearMechanic y descarga el Excel
    directamente desde la URL firmada entregada por el servidor.

    La descarga HTTP queda desacoplada de Chromium, por lo que
    puede completarse aunque ClearMechanic cierre la página o
    el contexto del navegador después de generar el archivo.
    """

    context = page.context

    print(
        f"   Página antes de descargar: "
        f"{'ABIERTA' if not page.is_closed() else 'CERRADA'}"
    )

    def al_cerrar_pagina() -> None:
        print(
            "   ⚠️ EVENTO: ClearMechanic cerró la página."
        )

    def al_cerrar_contexto() -> None:
        print(
            "   ⚠️ EVENTO: Se cerró el contexto del navegador."
        )

    page.on(
        "close",
        al_cerrar_pagina,
    )

    context.on(
        "close",
        al_cerrar_contexto,
    )

    boton_descarga = page.get_by_role(
        "button",
        name="Descargar reporte",
        exact=True,
    )

    boton_descarga.wait_for(
        state="visible",
        timeout=15_000,
    )

    print(
        "   Click en Descargar reporte..."
    )

    with page.expect_download(
        timeout=60_000
    ) as download_info:

        boton_descarga.click()

    download = download_info.value

    nombre_archivo = (
        download.suggested_filename
    )

    url_descarga = (
        download.url
    )

    print(
        "   ✅ Evento Download recibido."
    )

    print(
        f"   Nombre sugerido: "
        f"{nombre_archivo}"
    )

    if not url_descarga:
        raise RuntimeError(
            "ClearMechanic generó el evento de descarga, "
            "pero no proporcionó una URL válida."
        )

    print(
        "   ✅ URL de descarga capturada."
    )

    ruta_destino = (
        TEMP_DIR
        / nombre_archivo
    )

    print(
        "   🔄 Descargando archivo desde AWS..."
    )

    try:

        with requests.get(
            url_descarga,
            stream=True,
            timeout=(15, 120),
        ) as response:

            response.raise_for_status()

            with ruta_destino.open(
                "wb"
            ) as archivo:

                for bloque in response.iter_content(
                    chunk_size=1024 * 1024
                ):

                    if bloque:
                        archivo.write(
                            bloque
                        )

    except Exception:

        if ruta_destino.exists():
            ruta_destino.unlink()

        raise

    if (
        not ruta_destino.exists()
        or ruta_destino.stat().st_size == 0
    ):
        raise RuntimeError(
            "La descarga terminó, pero el archivo resultante "
            "no existe o está vacío."
        )

    tamano_mb = (
        ruta_destino.stat().st_size
        /
        (1024 * 1024)
    )

    print(
        f"   ✅ Archivo descargado correctamente."
    )

    print(
        f"   Ruta: {ruta_destino}"
    )

    print(
        f"   Tamaño: {tamano_mb:.2f} MB"
    )

    return ruta_destino

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

    print(
        f"Perfil usado por downloader: "
        f"{BROWSER_PROFILE.resolve()}"
    )

    with sync_playwright() as playwright:

        context = (
            playwright.chromium.launch_persistent_context(
                user_data_dir=str(
                    BROWSER_PROFILE
                ),
                headless=HEADLESS,
                accept_downloads=True,
                viewport=None,
                args=(
                    [
                        "--start-maximized",
                        "--disable-save-password-bubble",
                        "--password-store=basic",
                        "--disable-features=PasswordManagerOnboarding,PasswordLeakDetection",
                    ]
                    if not HEADLESS
                    else []
                ),
            )
        )

        if context.pages:

            page = context.pages[0]

        else:

            page = context.new_page()

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

            try:
                context.close()

            except PlaywrightError as exc:

                if "Target page, context or browser has been closed" not in str(exc):
                    raise

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