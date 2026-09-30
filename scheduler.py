from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from controlador import main as ejecutar_controlador


# ============================================================
# CONFIGURACIÓN
# ============================================================

INTERVALO_REVISION_MINUTOS = 1


# ============================================================
# JOB
# ============================================================

def revisar_actualizaciones() -> None:
    """
    Ejecuta una revisión del controlador.

    El controlador decide si corresponde actualizar alguna fuente.
    """

    print()
    print("=" * 68)
    print("CGO CALL CENTER — REVISIÓN PROGRAMADA")
    print("=" * 68)

    print(
        f"Hora revisión: "
        f"{datetime.now():%d/%m/%Y %H:%M:%S}"
    )

    try:

        ejecutar_controlador()

    except Exception as exc:

        print()
        print(
            f"❌ Error en revisión programada: "
            f"{type(exc).__name__}: {exc}"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    scheduler = BlockingScheduler()

    scheduler.add_job(
        revisar_actualizaciones,
        trigger="interval",
        minutes=INTERVALO_REVISION_MINUTOS,
        max_instances=1,
        coalesce=True,
        id="cgo_callcenter_controlador",
        replace_existing=True,
    )

    print()
    print("=" * 68)
    print("CGO CALL CENTER — SCHEDULER")
    print("=" * 68)

    print(
        f"Revisión cada "
        f"{INTERVALO_REVISION_MINUTOS} minuto(s)."
    )

    print(
        "Presiona CTRL+C para detener."
    )

    print()

    # Primera revisión inmediata al iniciar.
    revisar_actualizaciones()

    try:

        scheduler.start()

    except (
        KeyboardInterrupt,
        SystemExit,
    ):

        print()
        print(
            "🛑 Scheduler detenido."
        )


if __name__ == "__main__":
    main()