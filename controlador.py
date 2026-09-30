from __future__ import annotations

import json
import os
import subprocess
import sys

from datetime import datetime, time
from pathlib import Path


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

DATA_DIR = PROJECT_ROOT / "data"

ESTADO_PATH = (
    DATA_DIR
    / "controlador_estado.json"
)

LOCK_PATH = (
    DATA_DIR
    / "controlador.lock"
)


# ------------------------------------------------------------
# HORARIOS OPERATIVOS
#
# weekday():
#   0 = lunes
#   1 = martes
#   2 = miércoles
#   3 = jueves
#   4 = viernes
#   5 = sábado
#   6 = domingo
# ------------------------------------------------------------

HORARIOS = {
    0: {
        "activo": True,
        "inicio": time(8, 0),
        "fin": time(19, 0),
        "inicio_intensivo": time(17, 0),
    },
    1: {
        "activo": True,
        "inicio": time(8, 0),
        "fin": time(19, 0),
        "inicio_intensivo": time(17, 0),
    },
    2: {
        "activo": True,
        "inicio": time(8, 0),
        "fin": time(19, 0),
        "inicio_intensivo": time(17, 0),
    },
    3: {
        "activo": True,
        "inicio": time(8, 0),
        "fin": time(19, 0),
        "inicio_intensivo": time(17, 0),
    },
    4: {
        "activo": True,
        "inicio": time(8, 0),
        "fin": time(19, 0),
        "inicio_intensivo": time(17, 0),
    },
    6: {
        "activo": True,
        "inicio": time(8, 0),
        "fin": time(18, 0),
        "inicio_intensivo": time(12, 0),
    },
    5: {
        "activo": False,
        "inicio": None,
        "fin": None,
        "inicio_intensivo": None,
    },
}


# ------------------------------------------------------------
# FUENTES
#
# Cada fuente puede tener su propia frecuencia.
#
# En el futuro podremos agregar aquí:
#   cloudtalk
#   whaticket
#   telefonos
# ------------------------------------------------------------

FUENTES = {
    "clearmechanic": {
        "activo": True,
        "script": "actualizador.py",
        "intervalo_normal": 5,
        "intervalo_intensivo": 3,
    },
}


# ============================================================
# ESTADO
# ============================================================

def cargar_estado() -> dict:
    """
    Recupera la fecha/hora de la última actualización exitosa
    de cada fuente.
    """

    if not ESTADO_PATH.exists():
        return {}

    try:

        with ESTADO_PATH.open(
            "r",
            encoding="utf-8",
        ) as archivo:

            return json.load(
                archivo
            )

    except (
        json.JSONDecodeError,
        OSError,
    ):

        return {}


def guardar_estado(
    estado: dict,
) -> None:
    """
    Guarda el estado del controlador.
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with ESTADO_PATH.open(
        "w",
        encoding="utf-8",
    ) as archivo:

        json.dump(
            estado,
            archivo,
            indent=4,
            ensure_ascii=False,
        )


# ============================================================
# HORARIO
# ============================================================

def obtener_configuracion_horaria(
    ahora: datetime,
) -> dict | None:
    """
    Devuelve la configuración correspondiente al día actual.

    Si el día está deshabilitado o estamos fuera del horario
    operativo, devuelve None.
    """

    configuracion = HORARIOS.get(
        ahora.weekday()
    )

    if not configuracion:
        return None

    if not configuracion["activo"]:
        return None

    hora_actual = ahora.time()

    if not (
        configuracion["inicio"]
        <= hora_actual
        <= configuracion["fin"]
    ):
        return None

    return configuracion


def obtener_intervalo(
    ahora: datetime,
    fuente: dict,
    horario: dict,
) -> int:
    """
    Determina la frecuencia aplicable según la hora actual.
    """

    if (
        ahora.time()
        >= horario["inicio_intensivo"]
    ):
        return int(
            fuente[
                "intervalo_intensivo"
            ]
        )

    return int(
        fuente[
            "intervalo_normal"
        ]
    )


# ============================================================
# CONTROL DE FRECUENCIA
# ============================================================

def corresponde_actualizar(
    ahora: datetime,
    ultima_ejecucion: datetime | None,
    intervalo_minutos: int,
) -> bool:
    """
    Indica si ya transcurrió el intervalo necesario.
    """

    if ultima_ejecucion is None:
        return True

    minutos_transcurridos = (
        ahora
        -
        ultima_ejecucion
    ).total_seconds() / 60

    return (
        minutos_transcurridos
        >= intervalo_minutos
    )


# ============================================================
# BLOQUEO DE EJECUCIÓN
# ============================================================

def adquirir_lock() -> bool:
    """
    Evita que existan dos controladores ejecutándose
    simultáneamente.
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:

        descriptor = os.open(
            LOCK_PATH,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY,
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as archivo:

            archivo.write(
                str(
                    os.getpid()
                )
            )

        return True

    except FileExistsError:
        return False


def liberar_lock() -> None:
    """
    Elimina el bloqueo al terminar la ejecución.
    """

    if LOCK_PATH.exists():
        LOCK_PATH.unlink()


# ============================================================
# EJECUCIÓN DE FUENTES
# ============================================================

def ejecutar_fuente(
    nombre: str,
    configuracion: dict,
) -> bool:
    """
    Ejecuta el script correspondiente a una fuente.

    Devuelve True solamente si terminó correctamente.
    """

    script = (
        PROJECT_ROOT
        / configuracion["script"]
    )

    if not script.exists():
        raise FileNotFoundError(
            f"No existe el script de la fuente "
            f"{nombre}: {script}"
        )

    print()
    print("=" * 68)

    print(
        f"ACTUALIZANDO FUENTE: "
        f"{nombre.upper()}"
    )

    print("=" * 68)

    resultado = subprocess.run(
        [
            sys.executable,
            str(script),
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )

    if resultado.returncode != 0:

        print()
        print(
            f"❌ {nombre}: actualización fallida."
        )

        return False

    print()
    print(
        f"✅ {nombre}: actualización completada."
    )

    return True


# ============================================================
# ORQUESTADOR
# ============================================================

def ejecutar_controlador() -> None:
    """
    Decide qué fuentes deben actualizarse en esta ejecución.
    """

    ahora = datetime.now()

    print()
    print("=" * 68)
    print("CGO CALL CENTER — CONTROLADOR")
    print("=" * 68)

    print(
        f"Fecha/hora: "
        f"{ahora:%d/%m/%Y %H:%M:%S}"
    )

    horario = obtener_configuracion_horaria(
        ahora
    )

    if horario is None:

        print(
            "⏸️ Fuera del horario operativo."
        )

        return

    estado = cargar_estado()

    fuentes_ejecutadas = 0

    for nombre, configuracion in FUENTES.items():

        if not configuracion["activo"]:
            continue

        intervalo = obtener_intervalo(
            ahora=ahora,
            fuente=configuracion,
            horario=horario,
        )

        ultima_ejecucion_texto = (
            estado
            .get(nombre, {})
            .get(
                "ultima_ejecucion_exitosa"
            )
        )

        ultima_ejecucion = None

        if ultima_ejecucion_texto:

            try:

                ultima_ejecucion = (
                    datetime.fromisoformat(
                        ultima_ejecucion_texto
                    )
                )

            except ValueError:
                ultima_ejecucion = None

        if not corresponde_actualizar(
            ahora=ahora,
            ultima_ejecucion=ultima_ejecucion,
            intervalo_minutos=intervalo,
        ):

            print(
                f"⏭️ {nombre}: "
                f"todavía no corresponde "
                f"(cada {intervalo} min)."
            )

            continue

        exito = ejecutar_fuente(
            nombre=nombre,
            configuracion=configuracion,
        )

        if not exito:
            continue

        estado.setdefault(
            nombre,
            {}
        )

        estado[
            nombre
        ][
            "ultima_ejecucion_exitosa"
        ] = datetime.now().isoformat(
            timespec="seconds"
        )

        guardar_estado(
            estado
        )

        fuentes_ejecutadas += 1

    if fuentes_ejecutadas == 0:

        print()
        print(
            "ℹ️ No había fuentes pendientes "
            "de actualización."
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    if not adquirir_lock():

        print()
        print(
            "⏭️ Ya existe una actualización "
            "en ejecución."
        )

        return

    try:

        ejecutar_controlador()

    finally:

        liberar_lock()


if __name__ == "__main__":
    main()