from __future__ import annotations

from pathlib import Path

from database import get_connection


# ============================================================
# HELPERS
# ============================================================

def formato_bytes(
    cantidad: int,
) -> str:
    """
    Convierte bytes a una representación legible.
    """

    unidades = [
        "B",
        "KB",
        "MB",
        "GB",
    ]

    valor = float(
        cantidad
    )

    for unidad in unidades:

        if valor < 1024:
            return (
                f"{valor:,.2f} {unidad}"
            )

        valor /= 1024

    return (
        f"{valor:,.2f} TB"
    )


def obtener_ruta_base(
    conn,
) -> Path | None:
    """
    Obtiene desde SQLite la ruta física real
    de la base actualmente conectada.
    """

    fila = conn.execute(
        """
        PRAGMA database_list
        """
    ).fetchall()

    for registro in fila:

        nombre = registro[1]
        ruta = registro[2]

        if (
            nombre == "main"
            and ruta
        ):
            return Path(
                ruta
            ).resolve()

    return None


def listar_tablas(
    conn,
) -> list[str]:
    """
    Devuelve las tablas de usuario presentes
    en la base SQLite.
    """

    filas = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    return [
        fila[0]
        for fila in filas
    ]


def contar_registros(
    conn,
    tabla: str,
) -> int:
    """
    Cuenta las filas de una tabla.
    """

    resultado = conn.execute(
        f'SELECT COUNT(*) FROM "{tabla}"'
    ).fetchone()

    return int(
        resultado[0]
    )


def obtener_columnas(
    conn,
    tabla: str,
):
    """
    Obtiene estructura de columnas mediante PRAGMA.
    """

    return conn.execute(
        f'PRAGMA table_info("{tabla}")'
    ).fetchall()


def obtener_indices(
    conn,
    tabla: str,
):
    """
    Obtiene los índices asociados a una tabla.
    """

    return conn.execute(
        f'PRAGMA index_list("{tabla}")'
    ).fetchall()


def obtener_columnas_indice(
    conn,
    indice: str,
):
    """
    Obtiene las columnas que forman un índice.
    """

    return conn.execute(
        f'PRAGMA index_info("{indice}")'
    ).fetchall()


def obtener_foreign_keys(
    conn,
    tabla: str,
):
    """
    Obtiene claves foráneas declaradas.
    """

    return conn.execute(
        f'PRAGMA foreign_key_list("{tabla}")'
    ).fetchall()


# ============================================================
# DIAGNÓSTICO
# ============================================================

def main() -> None:

    print()
    print("=" * 90)
    print("CGO CALL CENTER — DIAGNÓSTICO DE ESQUEMA SQLITE")
    print("=" * 90)

    with get_connection() as conn:

        # ====================================================
        # BASE FÍSICA
        # ====================================================

        ruta_base = obtener_ruta_base(
            conn
        )

        print()
        print("BASE DE DATOS")
        print("-" * 90)

        if ruta_base is None:

            print(
                "Ruta física: no determinada"
            )

        else:

            print(
                f"Ruta física : {ruta_base}"
            )

            if ruta_base.exists():

                print(
                    "Tamaño      : "
                    f"{formato_bytes(ruta_base.stat().st_size)}"
                )

            else:

                print(
                    "Tamaño      : archivo no encontrado"
                )

        # ====================================================
        # TABLAS
        # ====================================================

        tablas = listar_tablas(
            conn
        )

        print()
        print("RESUMEN DE TABLAS")
        print("-" * 90)

        print(
            f"{'TABLA':<40}"
            f"{'FILAS':>15}"
        )

        print(
            "-" * 55
        )

        total_filas = 0

        for tabla in tablas:

            cantidad = contar_registros(
                conn=conn,
                tabla=tabla,
            )

            total_filas += cantidad

            print(
                f"{tabla:<40}"
                f"{cantidad:>15,}"
            )

        print(
            "-" * 55
        )

        print(
            f"{'TOTAL':<40}"
            f"{total_filas:>15,}"
        )

        # ====================================================
        # DETALLE POR TABLA
        # ====================================================

        for tabla in tablas:

            print()
            print("=" * 90)
            print(
                f"TABLA: {tabla}"
            )
            print("=" * 90)

            cantidad = contar_registros(
                conn=conn,
                tabla=tabla,
            )

            print(
                f"Filas: {cantidad:,}"
            )

            # -----------------------------------------------
            # COLUMNAS
            # -----------------------------------------------

            print()
            print("COLUMNAS")
            print("-" * 90)

            columnas = obtener_columnas(
                conn=conn,
                tabla=tabla,
            )

            print(
                f"{'CID':>4}  "
                f"{'COLUMNA':<35} "
                f"{'TIPO':<18} "
                f"{'NOT NULL':<10} "
                f"{'PK':<5}"
            )

            for columna in columnas:

                cid = columna[0]
                nombre = columna[1]
                tipo = columna[2]
                not_null = columna[3]
                pk = columna[5]

                print(
                    f"{cid:>4}  "
                    f"{nombre:<35} "
                    f"{tipo:<18} "
                    f"{str(bool(not_null)):<10} "
                    f"{str(bool(pk)):<5}"
                )

            # -----------------------------------------------
            # ÍNDICES
            # -----------------------------------------------

            print()
            print("ÍNDICES")
            print("-" * 90)

            indices = obtener_indices(
                conn=conn,
                tabla=tabla,
            )

            if not indices:

                print(
                    "(sin índices explícitos)"
                )

            else:

                for indice in indices:

                    nombre_indice = (
                        indice[1]
                    )

                    unico = bool(
                        indice[2]
                    )

                    columnas_indice = (
                        obtener_columnas_indice(
                            conn=conn,
                            indice=nombre_indice,
                        )
                    )

                    nombres_columnas = [
                        fila[2]
                        for fila
                        in columnas_indice
                    ]

                    print(
                        f"- {nombre_indice}"
                        f" | unique={unico}"
                        f" | columnas="
                        f"{', '.join(nombres_columnas)}"
                    )

            # -----------------------------------------------
            # FOREIGN KEYS
            # -----------------------------------------------

            print()
            print("FOREIGN KEYS")
            print("-" * 90)

            foreign_keys = (
                obtener_foreign_keys(
                    conn=conn,
                    tabla=tabla,
                )
            )

            if not foreign_keys:

                print(
                    "(sin foreign keys declaradas)"
                )

            else:

                for fk in foreign_keys:

                    print(
                        f"- {fk[3]} "
                        f"→ {fk[2]}.{fk[4]}"
                    )

        # ====================================================
        # TABLAS CLAVE — RELACIÓN SNAPSHOTS
        # ====================================================

        tablas_clave = [
            "snapshots",
            "citas_snapshot",
            "cambios_snapshot",
            "metricas_snapshot",
            "cloudtalk_llamadas",
        ]

        print()
        print("=" * 90)
        print("TABLAS CLAVE PARA PLAN B")
        print("=" * 90)

        tablas_existentes = set(
            tablas
        )

        for tabla in tablas_clave:

            if tabla not in tablas_existentes:

                print(
                    f"❌ {tabla:<30} no existe"
                )

                continue

            cantidad = contar_registros(
                conn=conn,
                tabla=tabla,
            )

            print(
                f"✅ {tabla:<30} "
                f"{cantidad:>12,} filas"
            )

    print()
    print("=" * 90)
    print("✅ DIAGNÓSTICO FINALIZADO — SOLO LECTURA")
    print("=" * 90)
    print()


if __name__ == "__main__":
    main()