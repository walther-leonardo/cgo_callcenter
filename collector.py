from __future__ import annotations

from datetime import datetime

from config import CLEARMECHANIC_FILE
from database import (
    get_connection,
    inicializar_base,
)
from procesamiento import cargar_clearmechanic


def registrar_snapshot() -> int:
    """
    Lee el Excel actual y registra una fotografía completa
    de ClearMechanic en SQLite.
    """

    if not CLEARMECHANIC_FILE.exists():
        raise FileNotFoundError(
            "No encontré el archivo:\n"
            f"{CLEARMECHANIC_FILE}\n\n"
            "Guarda la exportación como "
            "'inbox/clearmechanic.xlsx'."
        )

    df = cargar_clearmechanic(
        CLEARMECHANIC_FILE
    )

    fecha_hora_corte = datetime.now()

    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO snapshots (
                fecha_hora_corte,
                archivo_origen,
                cantidad_citas
            )
            VALUES (?, ?, ?)
            """,
            (
                fecha_hora_corte.isoformat(
                    timespec="seconds"
                ),
                CLEARMECHANIC_FILE.name,
                len(df),
            ),
        )

        snapshot_id = (
            cursor.lastrowid
        )

        registros = []

        for fila in df.itertuples(
            index=False
        ):

            registros.append(
                (
                    snapshot_id,
                    fila.id_cita,
                    fila.estatus_cita,
                    fila.motivo_visita,
                    (
                        fila.fecha_programada.isoformat()
                        if fila.fecha_programada
                        is not None
                        else None
                    ),
                    fila.hora_programada,
                    fila.origen_cita,
                    fila.persona_agenda,
                    (
                        fila.fecha_creacion.isoformat()
                        if fila.fecha_creacion
                        is not None
                        and not
                        getattr(
                            fila.fecha_creacion,
                            "isnat",
                            False,
                        )
                        else None
                    ),
                    fila.nombre,
                    fila.celular,
                    fila.asesor_servicio,
                    fila.modelo,
                    fila.placa,
                    (
                        float(
                            fila.kilometraje
                        )
                        if fila.kilometraje
                        == fila.kilometraje
                        else None
                    ),
                )
            )

        conn.executemany(
            """
            INSERT INTO citas_snapshot (
                snapshot_id,
                id_cita,
                estatus_cita,
                motivo_visita,
                fecha_programada,
                hora_programada,
                origen_cita,
                persona_agenda,
                fecha_creacion,
                nombre,
                celular,
                asesor_servicio,
                modelo,
                placa,
                kilometraje
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            registros,
        )

        conn.commit()

    return snapshot_id


def main() -> None:

    print()
    print("=" * 64)
    print("CGO CALL CENTER — REGISTRO DE SNAPSHOT")
    print("=" * 64)

    inicializar_base()

    snapshot_id = (
        registrar_snapshot()
    )

    print(
        f"✅ Snapshot #{snapshot_id} registrado correctamente."
    )

    print()


if __name__ == "__main__":
    main()