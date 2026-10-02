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

DATA_DIR = (
    PROJECT_ROOT
    / "data"
)

ESTADO_PATH = (
    DATA_DIR
    / "controlador_estado.json"
)

LOCK_PATH = (
    DATA_DIR
    / "controlador.lock"
)


# ============================================================
# HORARIOS OPERATIVOS
# ============================================================
#
# weekday():
#   0 = lunes
#   1 = martes
#   2 = miércoles
#   3 = jueves
#   4 = viernes
#   5 = sábado
#   6 = domingo
#
# Lunes a viernes:
#   08:00 - 19:00
#   intensivo desde 17:00
#
# Sábado:
#   08:00 - 13:00
#   intensivo desde 12:00
#
# Domingo:
#   inactivo
# ============================================================

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
    5: {
        "activo": True,
        "inicio": time(8, 0),
        "fin": time(13, 0),
        "inicio_intensivo": time(12, 0),
    },
    6: {
        "activo": False,
        "inicio": None,
        "fin": None,
        "inicio_intensivo": None,
    },
}


# ============================================================
# FUENTES
# ============================================================
#
# IMPORTANTE:
#
# El orden de este diccionario también define el orden de
# ejecución.
#
# 1. ClearMechanic
# 2. CloudTalk
#
# subprocess.run() es bloqueante, por lo que CloudTalk
# solamente podrá iniciar cuando ClearMechanic haya terminado.
# ============================================================

FUENTES = {
    "clearmechanic": {
        "activo": True,
        "script": "actualizador.py",
        "intervalo_normal": 5,
        "intervalo_intensivo": 3,
    },

    "cloudtalk": {
        "activo": True,
        "script": "actualizador_cloudtalk.py",
        "intervalo_normal": 5,
        "intervalo_intensivo": 3,
    },
}


# ============================================================
# ESTADO
# ============================================================

def cargar_estado() -> dict:
    """
    Recupera la fecha/hora de la última actualización
    exitosa de cada fuente.
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

    if not configuracion[
        "activo"
    ]:
        return None

    hora_actual = ahora.time()

    if not (
        configuracion[
            "inicio"
        ]
        <= hora_actual
        <= configuracion[
            "fin"
        ]
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
        >= horario[
            "inicio_intensivo"
        ]
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
    Ejecuta una fuente y espera hasta que termine.

    La ejecución es deliberadamente síncrona:
    no se inicia ninguna otra fuente mientras este
    subprocess siga activo.

    Devuelve True solamente si terminó correctamente.
    """

    script = (
        PROJECT_ROOT
        / configuracion[
            "script"
        ]
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

    inicio = datetime.now()

    print(
        f"🕐 Inicio: "
        f"{inicio:%H:%M:%S}"
    )

    resultado = subprocess.run(
        [
            sys.executable,
            str(
                script
            ),
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )

    fin = datetime.now()

    duracion_segundos = int(
        (
            fin
            -
            inicio
        ).total_seconds()
    )

    minutos, segundos = divmod(
        duracion_segundos,
        60,
    )

    print()

    if resultado.returncode != 0:

        print(
            f"❌ {nombre}: "
            f"actualización fallida."
        )

        print(
            f"⏱️ Duración: "
            f"{minutos}m {segundos:02d}s"
        )

        return False

    print(
        f"✅ {nombre}: "
        f"actualización completada."
    )

    print(
        f"⏱️ Duración: "
        f"{minutos}m {segundos:02d}s"
    )

    return True


# ============================================================
# ORQUESTADOR
# ============================================================

def ejecutar_controlador() -> None:
    """
    Decide qué fuentes deben actualizarse.

    Las fuentes se ejecutan secuencialmente.

    Nunca se ejecutan ClearMechanic y CloudTalk
    simultáneamente.
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

    horario = (
        obtener_configuracion_horaria(
            ahora
        )
    )

    if horario is None:

        print(
            "⏸️ Fuera del horario operativo."
        )

        return

    estado = cargar_estado()

    fuentes_ejecutadas = 0

    # --------------------------------------------------------
    # IMPORTANTE:
    #
    # Este loop es deliberadamente secuencial.
    #
    # ejecutar_fuente() usa subprocess.run(), que no retorna
    # hasta que el script de la fuente haya finalizado.
    # --------------------------------------------------------

    for nombre, configuracion in FUENTES.items():

        if not configuracion[
            "activo"
        ]:
            continue

        # Usamos la hora real antes de evaluar cada fuente.
        # Esto es importante porque la fuente anterior puede
        # haber demorado varios minutos.
        ahora_fuente = datetime.now()

        horario_fuente = (
            obtener_configuracion_horaria(
                ahora_fuente
            )
        )

        if horario_fuente is None:

            print()
            print(
                f"⏸️ {nombre}: "
                f"ya estamos fuera del horario operativo."
            )

            continue

        intervalo = obtener_intervalo(
            ahora=ahora_fuente,
            fuente=configuracion,
            horario=horario_fuente,
        )

        ultima_ejecucion_texto = (
            estado
            .get(
                nombre,
                {},
            )
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
            ahora=ahora_fuente,
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

        # ----------------------------------------------------
        # La hora guardada es la hora de FINALIZACIÓN.
        #
        # Esto evita que una fuente lenta vuelva a considerarse
        # vencida inmediatamente después de terminar.
        # ----------------------------------------------------

        fecha_fin = datetime.now()

        estado.setdefault(
            nombre,
            {},
        )

        estado[
            nombre
        ][
            "ultima_ejecucion_exitosa"
        ] = fecha_fin.isoformat(
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