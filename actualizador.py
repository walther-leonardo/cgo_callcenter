from __future__ import annotations

from pathlib import Path

from collector import registrar_snapshot
from database import inicializar_base
from downloader import descargar_clearmechanic
from metricas import (
    guardar_analitica_snapshot,
    mostrar_resumen_snapshot,
)
from retencion import aplicar_retencion_citas_snapshot


def eliminar_archivo_temporal(
    archivo: Path,
) -> None:
    """
    Elimina el Excel temporal únicamente después de que
    todo el procesamiento principal haya finalizado correctamente.
    """

    if archivo.exists():
        archivo.unlink()

        print(
            "🧹 Archivo temporal eliminado."
        )


def ejecutar_retencion_segura() -> None:
    """
    Ejecuta la retención de citas_snapshot como mantenimiento.

    Un fallo de retención no invalida una actualización
    que ya guardó correctamente snapshot, métricas y cambios.
    """

    try:

        resultado = (
            aplicar_retencion_citas_snapshot()
        )

        eliminadas = int(
            resultado[
                "filas_eliminadas"
            ]
        )

        restantes = int(
            resultado[
                "filas_restantes"
            ]
        )

        referencia = resultado[
            "snapshot_referencia"
        ]

        if eliminadas > 0:

            print(
                f"✅ Retención aplicada: "
                f"{eliminadas:,} filas eliminadas."
            )

            print(
                f"   Buffer actual: "
                f"{restantes:,} filas."
            )

            print(
                f"   Snapshot referencia: "
                f"#{referencia}"
            )

        else:

            print(
                "✅ Retención revisada: "
                "no existen filas antiguas "
                "por eliminar."
            )

    except Exception as exc:

        print()
        print(
            "⚠️ La actualización fue guardada, "
            "pero la retención automática no pudo ejecutarse."
        )

        print(
            f"   {type(exc).__name__}: {exc}"
        )

        print(
            "   El buffer se conservará intacto "
            "y podrá limpiarse en un siguiente ciclo."
        )


def ejecutar_actualizacion() -> int:
    """
    Ejecuta el ciclo completo de actualización:

    ClearMechanic
        → descarga Excel
        → registra snapshot
        → calcula deltas y métricas
        → aplica retención del buffer
        → muestra resumen
        → elimina archivo temporal
    """

    print()
    print("=" * 68)
    print("CGO CALL CENTER — ACTUALIZACIÓN AUTOMÁTICA")
    print("=" * 68)

    inicializar_base()

    print()
    print(
        "1️⃣ Descargando información de ClearMechanic..."
    )

    ruta_descargada = Path(
        descargar_clearmechanic()
    )

    print()
    print(
        "2️⃣ Registrando snapshot en SQLite..."
    )

    snapshot_id = registrar_snapshot(
        archivo=ruta_descargada
    )

    print(
        f"✅ Snapshot #{snapshot_id} registrado correctamente."
    )

    print()
    print(
        "3️⃣ Calculando deltas e indicadores..."
    )

    guardar_analitica_snapshot(
        snapshot_id
    )

    print(
        "✅ Deltas e indicadores guardados correctamente."
    )

    print()
    print(
        "4️⃣ Aplicando retención del buffer..."
    )

    ejecutar_retencion_segura()

    print()
    print(
        "5️⃣ Resumen del corte:"
    )

    mostrar_resumen_snapshot(
        snapshot_id
    )

    print()
    print(
        "6️⃣ Limpiando archivo temporal..."
    )

    eliminar_archivo_temporal(
        ruta_descargada
    )

    print()
    print("=" * 68)

    print(
        f"✅ ACTUALIZACIÓN COMPLETADA — "
        f"SNAPSHOT #{snapshot_id}"
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
        print(
            "❌ ACTUALIZACIÓN NO COMPLETADA"
        )
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