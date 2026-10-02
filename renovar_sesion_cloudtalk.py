from __future__ import annotations

import subprocess
import time
from pathlib import Path

import requests


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

CHROME_PROFILE = (
    PROJECT_ROOT
    / "chrome_profile_cloudtalk"
)

CHROME_PATH = Path(
    r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)

REMOTE_DEBUGGING_PORT = 9333

CLOUDTALK_URL = (
    "https://dashboard.cloudtalk.io/menu/dashboard"
)

CDP_VERSION_URL = (
    f"http://127.0.0.1:"
    f"{REMOTE_DEBUGGING_PORT}"
    f"/json/version"
)


# ============================================================
# HELPERS
# ============================================================

def chrome_cloudtalk_esta_abierto() -> bool:
    """
    Comprueba si existe un Chrome escuchando en el puerto
    reservado para CloudTalk.
    """

    try:

        response = requests.get(
            CDP_VERSION_URL,
            timeout=2,
        )

        if response.status_code != 200:
            return False

        datos = response.json()

        navegador = str(
            datos.get(
                "Browser",
                "",
            )
        )

        return navegador.startswith(
            "Chrome/"
        )

    except (
        requests.RequestException,
        ValueError,
    ):
        return False


def esperar_chrome(
    timeout_segundos: int = 15,
) -> bool:
    """
    Espera hasta que Chrome exponga el puerto CDP.
    """

    inicio = time.time()

    while (
        time.time() - inicio
        < timeout_segundos
    ):

        if chrome_cloudtalk_esta_abierto():
            return True

        time.sleep(0.5)

    return False


# ============================================================
# ABRIR CLOUDTALK
# ============================================================

def abrir_cloudtalk() -> None:
    """
    Abre Google Chrome real con un perfil persistente
    exclusivo para CloudTalk.

    No utiliza Playwright para lanzar el navegador.
    """

    print()
    print("=" * 68)
    print("CGO CALL CENTER — CLOUDTALK")
    print("=" * 68)

    # --------------------------------------------------------
    # VALIDAR CHROME
    # --------------------------------------------------------

    if not CHROME_PATH.exists():

        raise FileNotFoundError(
            "No se encontró Google Chrome en:\n"
            f"{CHROME_PATH}"
        )

    CHROME_PROFILE.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # SI YA ESTÁ ABIERTO, NO CREAR OTRO
    # --------------------------------------------------------

    if chrome_cloudtalk_esta_abierto():

        print(
            "🟢 Chrome de CloudTalk ya está abierto."
        )

        print(
            f"Puerto CDP: {REMOTE_DEBUGGING_PORT}"
        )

        return

    # --------------------------------------------------------
    # ABRIR CHROME NORMAL
    # --------------------------------------------------------

    comando = [
        str(CHROME_PATH),

        (
            f"--remote-debugging-port="
            f"{REMOTE_DEBUGGING_PORT}"
        ),

        (
            f"--user-data-dir="
            f"{CHROME_PROFILE}"
        ),

        "--start-maximized",

        CLOUDTALK_URL,
    ]

    print(
        "🔄 Abriendo Google Chrome..."
    )

    print(
        f"Perfil: {CHROME_PROFILE}"
    )

    print(
        f"Puerto CDP: {REMOTE_DEBUGGING_PORT}"
    )

    subprocess.Popen(
        comando,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # --------------------------------------------------------
    # ESPERAR DISPONIBILIDAD
    # --------------------------------------------------------

    if not esperar_chrome():

        raise RuntimeError(
            "Chrome se abrió, pero el puerto CDP "
            f"{REMOTE_DEBUGGING_PORT} no respondió."
        )

    print()
    print(
        "✅ Chrome de CloudTalk abierto correctamente."
    )

    print(
        "✅ Remote Debugging disponible."
    )

    print()
    print(
        "Si CloudTalk solicita login, hazlo manualmente."
    )

    print(
        "La sesión quedará guardada en el perfil persistente."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    abrir_cloudtalk()