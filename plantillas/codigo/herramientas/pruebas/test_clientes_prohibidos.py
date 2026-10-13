"""`dominio-puro` cubre todo cliente de BD/HTTP que este en los requirements DIRECTOS.

import-linter solo acepta paquetes externos instalados, asi que `dominio-puro` no puede nombrar
por adelantado `requests` o `psycopg2`. Esta prueba cierra el hueco: si alguien agrega uno de esos
clientes a `requirements*.txt` y no lo suma a `EXTERNOS_PROHIBIDOS_EN_DOMINIO`, falla.
Las dependencias transitivas NO cuentan (solo lo que el proyecto declara).
"""

import configparser
import re
from pathlib import Path

import pytest

from herramientas.contratos_importlinter import (
    EXTERNOS_PROHIBIDOS_EN_DOMINIO,
    RAIZ_SRC,
    generar,
)

# Nombre de la distribucion (normalizado) -> paquetes que expone al importarse.
CLIENTES_BD_HTTP: dict[str, tuple[str, ...]] = {
    "psycopg": ("psycopg",),
    "psycopg2": ("psycopg2",),
    "psycopg2-binary": ("psycopg2",),
    "asyncpg": ("asyncpg",),
    "pg8000": ("pg8000",),
    "pymysql": ("pymysql",),
    "mysqlclient": ("MySQLdb",),
    "mysql-connector-python": ("mysql",),
    "aiomysql": ("aiomysql",),
    "pymssql": ("pymssql",),
    "pyodbc": ("pyodbc",),
    "hdbcli": ("hdbcli",),
    "cx-oracle": ("cx_Oracle",),
    "oracledb": ("oracledb",),
    "pymongo": ("pymongo",),
    "motor": ("motor",),
    "redis": ("redis",),
    "aioredis": ("aioredis",),
    "elasticsearch": ("elasticsearch",),
    "sqlalchemy": ("sqlalchemy",),
    "requests": ("requests",),
    "httpx": ("httpx",),
    "aiohttp": ("aiohttp",),
    "urllib3": ("urllib3",),
    "httplib2": ("httplib2",),
    "pycurl": ("pycurl",),
    "boto3": ("boto3", "botocore"),
    "botocore": ("botocore",),
    "aiobotocore": ("aiobotocore",),
}

_NOMBRE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def nombres_de_requirements(texto: str) -> set[str]:
    """Distribuciones declaradas en un requirements (sin extras ni versiones; `-r` se ignora)."""
    nombres: set[str] = set()
    for linea in texto.splitlines():
        sin_comentario = linea.split("#", 1)[0]
        if not sin_comentario.strip() or sin_comentario.lstrip().startswith("-"):
            continue
        if coincidencia := _NOMBRE.match(sin_comentario):
            nombres.add(re.sub(r"[-_.]+", "-", coincidencia.group(1)).lower())
    return nombres


def clientes_sin_cubrir(requirements: str, prohibidos: tuple[str, ...]) -> dict[str, list[str]]:
    """Cliente de BD/HTTP declarado -> paquetes suyos que `dominio-puro` NO prohibe."""
    faltantes: dict[str, list[str]] = {}
    for nombre in sorted(nombres_de_requirements(requirements) & CLIENTES_BD_HTTP.keys()):
        sin_cubrir = [p for p in CLIENTES_BD_HTTP[nombre] if p not in prohibidos]
        if sin_cubrir:
            faltantes[nombre] = sin_cubrir
    return faltantes


def _forbidden_modules_de_dominio_puro() -> tuple[str, ...]:
    config = configparser.ConfigParser()
    config.read_string(generar())
    bruto = config["importlinter:contract:dominio-puro"]["forbidden_modules"]
    return tuple(linea.strip() for linea in bruto.splitlines() if linea.strip())


def test_hay_requirements_que_revisar() -> None:
    assert sorted(p.name for p in RAIZ_SRC.glob("requirements*.txt")) == [
        "requirements-dev.txt",
        "requirements.txt",
    ]


@pytest.mark.parametrize("archivo", ["requirements.txt", "requirements-dev.txt"])
def test_clientes_bd_http_cubiertos(archivo: str) -> None:
    texto = (RAIZ_SRC / archivo).read_text(encoding="utf-8")
    assert clientes_sin_cubrir(texto, _forbidden_modules_de_dominio_puro()) == {}, (
        f"{archivo} declara un cliente de BD/HTTP que dominio-puro no prohibe: agregar su paquete "
        "a EXTERNOS_PROHIBIDOS_EN_DOMINIO (herramientas/contratos_importlinter.py) y regenerar"
    )


def test_los_clientes_ya_instalados_estan_en_el_contrato() -> None:
    # Hoy los directos son redis y psycopg[binary]: ambos deben estar prohibidos.
    prohibidos = _forbidden_modules_de_dominio_puro()
    assert {"redis", "psycopg"} <= set(prohibidos)
    assert set(prohibidos) == set(EXTERNOS_PROHIBIDOS_EN_DOMINIO)


# --- El detector muerde ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("linea", "esperado"),
    [
        ("requests>=2.31", {"requests": ["requests"]}),
        ("psycopg2-binary==2.9.9", {"psycopg2-binary": ["psycopg2"]}),
        ("psycopg2_binary", {"psycopg2-binary": ["psycopg2"]}),
        ("HTTPX[http2]>=0.27 ; python_version >= '3.12'", {"httpx": ["httpx"]}),
        ("mysqlclient", {"mysqlclient": ["MySQLdb"]}),
        ("boto3", {"boto3": ["boto3", "botocore"]}),
        ("aiohttp # cliente async", {"aiohttp": ["aiohttp"]}),
    ],
)
def test_el_detector_falla_ante_un_cliente_no_cubierto(
    linea: str, esperado: dict[str, list[str]]
) -> None:
    assert clientes_sin_cubrir(linea, EXTERNOS_PROHIBIDOS_EN_DOMINIO) == esperado


def test_el_detector_pasa_si_el_cliente_esta_en_la_lista() -> None:
    ampliada = (*EXTERNOS_PROHIBIDOS_EN_DOMINIO, "requests", "urllib3")
    assert clientes_sin_cubrir("requests\nurllib3==2.2", ampliada) == {}


def test_el_detector_ignora_lo_que_no_es_un_cliente_y_las_lineas_de_inclusion() -> None:
    texto = "-r requirements.txt\n# requests (comentario)\nDjango>=5.2\npytest>=8\n"
    assert clientes_sin_cubrir(texto, EXTERNOS_PROHIBIDOS_EN_DOMINIO) == {}


def test_las_dependencias_transitivas_no_cuentan() -> None:
    # `celery` arrastra `kombu`/`vine` y Django arrastra `sqlparse`; no estan declarados.
    assert nombres_de_requirements("celery>=5.4,<6\nDjango>=5.2") == {"celery", "django"}


def test_nombres_de_requirements_lee_los_archivos_reales() -> None:
    texto: Path = RAIZ_SRC / "requirements.txt"
    nombres = nombres_de_requirements(texto.read_text(encoding="utf-8"))
    assert {"django", "redis", "psycopg"} <= nombres
