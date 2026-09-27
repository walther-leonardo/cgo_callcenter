from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parent

BROWSER_PROFILE = (
    PROJECT_ROOT
    / "browser_profile"
)

CLEARMECHANIC_URL = (
    "https://hondapanasanisidro.clearmechanic.com/dashboard"
)


def main() -> None:

    BROWSER_PROFILE.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 68)
    print("CGO CALL CENTER — RENOVAR SESIÓN CLEARMECHANIC")
    print("=" * 68)

    print()
    print(
        "Se abrirá Chromium usando el perfil del robot."
    )

    print(
        "Si ClearMechanic solicita login, ingresa manualmente "
        "y resuelve el CAPTCHA."
    )

    print()
    print(
        "Cuando hayas llegado al Dashboard, vuelve a esta "
        "terminal y presiona ENTER."
    )

    print(
        f"Perfil usado por renovar_sesion: "
        f"{BROWSER_PROFILE.resolve()}"
    )

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
                    "--disable-save-password-bubble",
                    "--password-store=basic",
                    "--disable-features=PasswordManagerOnboarding,PasswordLeakDetection",
                ],
            )
        )

        if context.pages:

            page = context.pages[0]

        else:

            page = context.new_page()

        page.goto(
            CLEARMECHANIC_URL,
            wait_until="domcontentloaded",
        )

        input(
            "\nPresiona ENTER cuando la sesión esté activa..."
        )

        print()
        print(
            f"URL actual: {page.url}"
        )

        context.close()

    print()
    print(
        "✅ Perfil de ClearMechanic guardado."
    )
    print()


if __name__ == "__main__":
    main()