from __future__ import annotations

from pathlib import Path

from collector import registrar_snapshot
from database import inicializar_base
from downloader import descargar_clearmechanic
from metricas import (
    guardar_analitica_snapshot,
    mostrar_resumen_snapshot,
)


def eliminar_archivo_temporal(
    archivo: Path,
) -> None:
    """
    Elimina el Excel temporal únicamente después de que
    todo el procesamiento haya finalizado correctamente.
    """

    if archivo.exists():
        archivo.unlink()

        print(
            "🧹 Archivo temporal eliminado."
        )


def ejecutar_actualizacion() -> int:
    """
    Ejecuta el ciclo completo de actualización:

    ClearMechanic
        → descarga Excel
        → registra snapshot
        → calcula deltas y métricas
        → elimina archivo temporal
    """

    print()
    print("=" * 68)
    print("CGO CALL CENTER — ACTUALIZACIÓN AUTOMÁTICA")
    print("=" * 68)

    inicializar_base()

    print()
    print("1️⃣ Descargando información de ClearMechanic...")

    ruta_descargada = Path(
        descargar_clearmechanic()
    )

    print()
    print("2️⃣ Registrando snapshot en SQLite...")

    snapshot_id = registrar_snapshot(
        archivo=ruta_descargada
    )

    print(
        f"✅ Snapshot #{snapshot_id} registrado correctamente."
    )

    print()
    print("3️⃣ Calculando deltas e indicadores...")

    guardar_analitica_snapshot(
        snapshot_id
    )

    print(
        "✅ Deltas e indicadores guardados correctamente."
    )

    print()
    print("4️⃣ Resumen del corte:")

    mostrar_resumen_snapshot(
        snapshot_id
    )

    print()
    print("5️⃣ Limpiando archivo temporal...")

    eliminar_archivo_temporal(
        ruta_descargada
    )

    print()
    print("=" * 68)
    print(
        f"✅ ACTUALIZACIÓN COMPLETADA — SNAPSHOT #{snapshot_id}"
    )
    print("=" * 68)
    print()

    return snapshot_id


def main() -> None:
    """
    Punto de entrada del actualizador.
    """

    try:

        ejecutar_actualizacion()

    except Exception as exc:

        print()
        print("=" * 68)
        print("❌ ACTUALIZACIÓN NO COMPLETADA")
        print("=" * 68)
        print()
        print(
            f"{type(exc).__name__}: {exc}"
        )
        print()
        print(
            "El archivo temporal, si llegó a descargarse, "
            "se conserva para diagnóstico."
        )
        print()

        raise


if __name__ == "__main__":
    main()