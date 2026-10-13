"""Dos sesiones de pytest en paralelo no chocan en la base de pruebas."""

import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from django.db import connection

from herramientas.base_pruebas import LIMITE_IDENTIFICADOR_POSTGRESQL, nombre_unico

CODIGO = Path(__file__).resolve().parents[2]


def test_dos_sesiones_obtienen_nombres_distintos() -> None:
    assert nombre_unico("postgres") != nombre_unico("postgres")


def test_el_nombre_lleva_el_prefijo_de_django_el_pid_y_el_azar() -> None:
    assert nombre_unico("app", pid=4242, azar="abcd1234") == "test_app_4242_abcd1234"


def test_el_nombre_respeta_el_limite_de_postgresql_aunque_la_base_sea_larga() -> None:
    nombre = nombre_unico("x" * 200, pid=99999999, azar="abcd1234")
    assert len(nombre) == LIMITE_IDENTIFICADOR_POSTGRESQL
    assert nombre.endswith("_99999999_abcd1234")


def test_el_nombre_es_un_identificador_seguro() -> None:
    assert re.fullmatch(r"test_[a-z0-9_]+", nombre_unico("postgres"))


@pytest.mark.django_db
def test_esta_sesion_usa_una_base_de_pruebas_con_nombre_unico() -> None:
    nombre = connection.settings_dict["NAME"]
    assert nombre.startswith("test_")
    assert nombre != "test_postgres"  # el nombre que chocaba entre sesiones
    assert re.search(rf"_{os.getpid()}_[0-9a-f]{{8}}$", nombre)


def _sesion_de_pytest() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "configuracion/pruebas/test_esquemas_en_base.py",
        ],
        cwd=CODIGO,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


@pytest.mark.lento
def test_dos_sesiones_de_pytest_a_la_vez_sobre_el_mismo_servidor_pasan() -> None:
    """Antes de la segunda fallaba con `database "test_postgres" already exists`."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: _sesion_de_pytest(), range(2)))
    for resultado in resultados:
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        assert "1 passed" in resultado.stdout
