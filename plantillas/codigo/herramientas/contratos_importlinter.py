"""Genera `.importlinter` a partir del mapa de modulos (DISENO D.1.5).

Los contratos son repetitivos (uno por modulo), asi que no se escriben a mano: se generan desde
`configuracion.modulos` y una prueba verifica que `.importlinter` este sincronizado.

    python -m herramientas.contratos_importlinter --escribir
"""

import argparse
import sys
from collections.abc import Mapping, Sequence
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

from configuracion.modulos import (
    DEPENDENCIAS,
    MODULO_IDENTIDAD,
    MODULO_NUCLEO,
    MODULOS_HEXAGONALES,
)

RAIZ_SRC = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ_SRC / ".importlinter"

# Capas internas de un modulo que ningun otro modulo puede importar (solo `api_publica`).
INTERNOS = ("dominio", "aplicacion", "adaptadores", "pruebas", "apps")

# Lo que `dominio/` jamas puede importar: framework, ORM, red e IO. import-linter solo admite
# PAQUETES (no modulos sueltos como `socket`), por eso la lista de la biblioteca estandar es corta.
#
# LIMITE CONOCIDO: import-linter exige que cada paquete externo de `root_packages` este
# INSTALADO ("Could not find package ... in your Python path"). Por eso esta lista solo puede
# nombrar los clientes de BD/HTTP que YA estan en `requirements*.txt` (hoy: `redis` y `psycopg`);
# `psycopg2`, `requests`, `httpx`, etc. no se listan porque no estan instalados. AL INSTALAR uno
# de esos paquetes hay que agregar aqui su paquete de import y regenerar `.importlinter`
# (`python -m herramientas.contratos_importlinter --escribir`). Si se olvida, la prueba
# `test_clientes_bd_http_cubiertos` (herramientas/pruebas/test_clientes_prohibidos.py) falla.
#
# Esta lista NO es la garantia completa: import-linter no ve modulos sueltos de la stdlib (`socket`,
# `subprocess`, `ssl`, `os`...) ni los paquetes que no estan instalados. La garantia es la LISTA
# BLANCA de `IMPORTS_PERMITIDOS_EN_DOMINIO`, que vigila `herramientas/pruebas/test_dominio_puro.py`.
EXTERNOS_PROHIBIDOS_EN_DOMINIO = (
    "django",
    "rest_framework",
    "celery",
    "redis",
    "psycopg",
    "http",
    "urllib",
    "sqlite3",
)

# Lista BLANCA de lo unico que un modulo de `*/dominio/**` puede importar (ademas de `nucleo` y de
# su propio modulo): stdlib "pura" (calculo y estructuras de datos), SIN IO, red ni procesos.
# Lo que no esta aqui se rechaza (`socket`, `subprocess`, `ssl`, `os`, `pathlib`, `io`, `http`,
# `urllib`, `sqlite3`, `logging`, `threading`, `random`, `time`, `requests`...). Se vigila con la
# prueba AST `herramientas/pruebas/test_dominio_puro.py`, que no depende de lo que haya instalado.
#
# LIMITE CONOCIDO: la lista blanca controla QUE SE IMPORTA, no que atributos se usan. Con
# `import uuid; uuid.os.system(...)` la prueba AST solo ve `uuid` (permitido) y pasa. Tampoco ve
# `exec("import socket")` (el import va dentro de un string); eso lo cubre ruff S102 (uso de
# `exec`), que ya corre en CI. Cerrar lo primero exigiria analisis de flujo, fuera del alcance.
# `datetime` y `zoneinfo` se permiten porque el dominio razona con fechas y husos (el reloj lo
# inyecta el caso de uso; `datetime.now()` sin parametro es un descuido de revision, no de import).
IMPORTS_PERMITIDOS_EN_DOMINIO: frozenset[str] = frozenset(
    {
        "__future__",
        "abc",
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "fractions",
        "functools",
        "itertools",
        "math",
        "numbers",
        "operator",
        "re",
        "types",
        "typing",
        "unicodedata",
        "uuid",
        "zoneinfo",
    }
)


def _lista(valores: Sequence[str]) -> str:
    return "\n".join(f"    {valor}" for valor in valores)


def orden_sin_ciclos(
    modulos: Sequence[str], dependencias: Mapping[str, Sequence[str]]
) -> list[str]:
    """Modulos de arriba (los que dependen de otros) hacia abajo (los de los que dependen).

    Valida que `dependencias` solo nombre modulos conocidos y que no tenga ciclos (D.1.3).
    """
    desconocidos = {
        nombre for origen, destinos in dependencias.items() for nombre in (origen, *destinos)
    } - set(modulos)
    if desconocidos:
        raise ValueError(f"D.1.3 menciona modulos inexistentes: {sorted(desconocidos)}")
    grafo = {modulo: set(dependencias.get(modulo, ())) for modulo in modulos}
    try:
        return list(reversed(list(TopologicalSorter(grafo).static_order())))
    except CycleError as error:
        raise ValueError(f"D.1.3 no admite ciclos entre modulos: {error.args[1]}") from error


def generar(
    modulos: Sequence[str] = MODULOS_HEXAGONALES,
    nucleo: str = MODULO_NUCLEO,
    configuracion: str = "configuracion",
    externos: Sequence[str] = EXTERNOS_PROHIBIDOS_EN_DOMINIO,
    dependencias: Mapping[str, Sequence[str]] = DEPENDENCIAS,
    hoja: str = MODULO_IDENTIDAD,
) -> str:
    """Devuelve el contenido de `.importlinter` para los modulos dados."""
    orden = orden_sin_ciclos(modulos, dependencias)
    bloques: list[str] = [
        "# GENERADO: `python -m herramientas.contratos_importlinter --escribir`. No editar.\n"
        "[importlinter]\n"
        "root_packages =\n"
        f"{_lista([*modulos, nucleo, configuracion, *externos])}\n"
        "include_external_packages = True\n"
    ]

    # 1. Un modulo solo puede importar `api_publica` de otro (o el nucleo). Se prohibe CUALQUIER
    #    submodulo de otro modulo (`otro.*`: dominio, aplicacion, adaptadores, pero tambien un
    #    `otro.servicios` suelto) y se exime unicamente `otro.api_publica`. Una lista fija de
    #    internos dejaba pasar los modulos no listados.
    for modulo in modulos:
        prohibidos = [f"{otro}.*" for otro in modulos if otro != modulo]
        api_de_otros = [f"{modulo}.** -> {otro}.api_publica" for otro in modulos if otro != modulo]
        bloques.append(
            f"[importlinter:contract:aislamiento-{modulo}]\n"
            f"name = {modulo} solo usa la api_publica de otros modulos\n"
            "type = forbidden\n"
            f"source_modules =\n{_lista([modulo])}\n"
            f"forbidden_modules =\n{_lista(prohibidos)}\n"
            f"ignore_imports =\n{_lista(api_de_otros)}\n"
            "unmatched_ignore_imports_alerting = none\n"
            "allow_indirect_imports = True\n"
        )

    # 2. Solo las flechas del grafo D.1.3: cada modulo importa unicamente a los que tiene permitidos
    #    (siempre via `api_publica`, por el contrato anterior). Los imports indirectos no cuentan:
    #    si A -> B y B -> C, A no esta usando a C.
    for modulo in modulos:
        permitidos = set(dependencias.get(modulo, ()))
        vetados = [otro for otro in modulos if otro != modulo and otro not in permitidos]
        if not vetados:
            continue
        bloques.append(
            f"[importlinter:contract:dependencias-{modulo}]\n"
            f"name = {modulo} solo depende de las flechas permitidas en D.1.3\n"
            "type = forbidden\n"
            f"source_modules =\n{_lista([modulo])}\n"
            f"forbidden_modules =\n{_lista(vetados)}\n"
            "allow_indirect_imports = True\n"
        )

    # 2b. Hoja del grafo (D.1.3): ningun modulo ni el nucleo importa `hoja` (`identidad`), ni por
    #     la api_publica ni indirectamente. Los permisos llegan como un `Actor` de `nucleo`.
    if hoja in modulos:
        bloques.append(
            f"[importlinter:contract:nadie-importa-{hoja}]\n"
            f"name = ningun modulo importa {hoja}: los permisos llegan como un Actor de nucleo\n"
            "type = forbidden\n"
            f"source_modules =\n{_lista([*(m for m in modulos if m != hoja), nucleo])}\n"
            f"forbidden_modules =\n{_lista([hoja])}\n"
        )

    # 3. Sin ciclos: los modulos se ordenan de arriba (dependen de otros) a abajo; importar hacia
    #    arriba, directa o indirectamente, rompe el contrato.
    bloques.append(
        "[importlinter:contract:sin-ciclos]\n"
        "name = sin ciclos entre modulos (D.1.3)\n"
        "type = layers\n"
        f"layers =\n{_lista(orden)}\n"
    )

    # 4. `dominio/` y `nucleo.puertos` son Python puro: sin Django, ORM, red ni IO (ni por cadenas
    #    de imports). Los puertos (D.1.4) son los contratos que importan TODOS los modulos: si uno
    #    arrastrara Django, lo arrastraria a cada dominio.
    puros = [*(f"{modulo}.dominio" for modulo in modulos), f"{nucleo}.puertos"]
    bloques.append(
        "[importlinter:contract:dominio-puro]\n"
        f"name = dominio/ y {nucleo}.puertos no importan Django, ORM ni IO\n"
        "type = forbidden\n"
        f"source_modules =\n{_lista(puros)}\n"
        f"forbidden_modules =\n{_lista(externos)}\n"
    )

    # 5. Hexagonal: adaptadores -> aplicacion -> dominio (nunca al reves).
    bloques.append(
        "[importlinter:contract:capas-hexagonales]\n"
        "name = adaptadores -> aplicacion -> dominio dentro de cada modulo\n"
        "type = layers\n"
        f"containers =\n{_lista(modulos)}\n"
        "layers =\n    adaptadores\n    aplicacion\n    dominio\n"
    )

    # 6. El nucleo no conoce a los modulos, y los modulos no conocen la configuracion.
    bloques.append(
        "[importlinter:contract:nucleo-independiente]\n"
        "name = nucleo no depende de ningun modulo ni de la configuracion\n"
        "type = forbidden\n"
        f"source_modules =\n{_lista([nucleo])}\n"
        f"forbidden_modules =\n{_lista([*modulos, configuracion])}\n"
    )
    bloques.append(
        "[importlinter:contract:modulos-sin-configuracion]\n"
        "name = los modulos no importan la configuracion de Django\n"
        "type = forbidden\n"
        f"source_modules =\n{_lista(modulos)}\n"
        f"forbidden_modules =\n{_lista([configuracion])}\n"
    )
    return "\n".join(bloques)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--escribir", action="store_true", help="escribe .importlinter")
    args = parser.parse_args(argv)
    contenido = generar()
    if args.escribir:
        ARCHIVO.write_text(contenido, encoding="utf-8", newline="\n")
        print(f"Escrito {ARCHIVO}")
    else:
        # En bytes: el modo texto de Windows traduciria LF a CRLF y `diff` contra el archivo
        # (que siempre se guarda con LF, ver `.gitattributes`) fallaria sin diferencia real.
        sys.stdout.buffer.write(contenido.encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
