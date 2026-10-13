"""`dominio/` solo importa stdlib pura, `nucleo` y su propio modulo (prueba AST).

`dominio-puro` de import-linter depende de lo que este INSTALADO (`requests` solo se detecta si es
una dependencia) y no puede nombrar modulos sueltos de la stdlib (`socket`, `subprocess`, `ssl`).
Esta prueba invierte el criterio: LISTA BLANCA (`IMPORTS_PERMITIDOS_EN_DOMINIO`), asi que lo
desconocido falla. Los imports relativos quedan dentro del propio modulo y se aceptan.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from configuracion.modulos import MODULO_NUCLEO, MODULOS_HEXAGONALES
from herramientas.contratos_importlinter import IMPORTS_PERMITIDOS_EN_DOMINIO, RAIZ_SRC


def imports_no_permitidos(codigo: str, modulo: str) -> list[str]:
    """Imports de `codigo` (un archivo de `<modulo>/dominio/`) fuera de la lista blanca."""
    permitidos = IMPORTS_PERMITIDOS_EN_DOMINIO | {MODULO_NUCLEO, modulo}
    hallazgos: list[str] = []
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import):
            nombres = [alias.name for alias in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0:
            nombres = [nodo.module or ""]
        else:
            continue
        hallazgos += [
            f"linea {nodo.lineno}: {nombre}"
            for nombre in nombres
            if nombre.split(".")[0] not in permitidos
        ]
    return hallazgos


def archivos_de_dominio(raiz: Path) -> Iterator[tuple[str, Path]]:
    for modulo in MODULOS_HEXAGONALES:
        for ruta in sorted((raiz / modulo / "dominio").rglob("*.py")):
            yield modulo, ruta


def test_hay_dominios_que_vigilar() -> None:
    assert len({modulo for modulo, _ in archivos_de_dominio(RAIZ_SRC)}) == len(MODULOS_HEXAGONALES)


def test_ningun_dominio_importa_algo_fuera_de_la_lista_blanca() -> None:
    hallazgos = {
        str(ruta.relative_to(RAIZ_SRC)): usos
        for modulo, ruta in archivos_de_dominio(RAIZ_SRC)
        if (usos := imports_no_permitidos(ruta.read_text(encoding="utf-8"), modulo))
    }
    assert not hallazgos, f"dominio/ solo admite stdlib pura, nucleo y su modulo: {hallazgos}"


@pytest.mark.parametrize(
    "codigo",
    [
        "import requests",
        "import socket",
        "import subprocess",
        "import ssl",
        "import os",
        "import os.path",
        "from pathlib import Path",
        "import io",
        "import http.client",
        "from urllib.request import urlopen",
        "import sqlite3",
        "from django.db import models",
        "import redis",
        "from identidad.dominio import Usuario",
        "from identidad import api_publica",
    ],
)
def test_el_detector_rechaza_imports_con_io_o_de_otros_modulos(codigo: str) -> None:
    assert imports_no_permitidos(codigo, "auditoria")


@pytest.mark.parametrize(
    "codigo",
    [
        "import decimal",
        "from decimal import Decimal",
        "from __future__ import annotations",
        "import datetime as dt; from zoneinfo import ZoneInfo",
        "from dataclasses import dataclass; from enum import Enum; from typing import Final",
        "from collections.abc import Iterable",
        "from nucleo.actor import Actor",
        "from auditoria.dominio.registro import Registro",
        "from . import registro; from .registro import Registro",
    ],
)
def test_el_detector_acepta_stdlib_pura_nucleo_y_el_propio_modulo(codigo: str) -> None:
    assert imports_no_permitidos(codigo, "auditoria") == []


def test_la_lista_blanca_no_incluye_io() -> None:
    io = {"socket", "subprocess", "ssl", "os", "pathlib", "io", "http", "urllib", "sqlite3"}
    assert not io & IMPORTS_PERMITIDOS_EN_DOMINIO


def test_la_prueba_falla_ante_un_intruso_en_un_dominio_real(tmp_path: Path) -> None:
    intruso = tmp_path / "auditoria" / "dominio" / "_tmp.py"
    intruso.parent.mkdir(parents=True)
    intruso.write_text(
        "import requests" + chr(10) + "import socket" + chr(10) + "import decimal" + chr(10),
        encoding="utf-8",
    )
    [(modulo, ruta)] = list(archivos_de_dominio(tmp_path))
    assert imports_no_permitidos(ruta.read_text(encoding="utf-8"), modulo) == [
        "linea 1: requests",
        "linea 2: socket",
    ]
