"""Configuracion global de pytest.

Base de datos de las pruebas:
- Si existe `DATABASE_URL` (CI, servicio PostgreSQL 16), se usa esa.
- Si no, se levanta un PostgreSQL 16 embebido con `pgserver` en `.pgdata_pruebas/` (en la raiz
  del repositorio; solo local).
  NO se usa `.pgdata/`: ese es el servidor de desarrollo (`herramientas.base_local`) y el de
  pruebas se detiene al terminar la sesion; con el mismo directorio pytest apagaba el de dev
  Un directorio propio es mas simple y robusto que "detener solo lo que levante yo".
Redis se reemplaza con `fakeredis` y Celery corre en modo eager (ver settings de pruebas).

Varias sesiones de pytest pueden compartir el mismo servidor (el embebido o el de CI): cada una crea
su propia base de pruebas con un nombre unico (`herramientas.base_pruebas`) y no se pisan.
"""

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from configuracion.entorno import parsear_url_base_de_datos
from herramientas.base_local import DIRECTORIO_PGDATA_PRUEBAS
from herramientas.base_pruebas import nombre_unico


def _asegurar_zonas_horarias(pgserver_modulo: Any) -> None:
    """El wheel de pgserver para Windows no trae `share/timezone`: PostgreSQL rechaza `UTC`.

    Se copian las zonas del paquete `tzdata` (mismo formato TZif). No hace nada si ya existen.
    """
    import tzdata

    destino = Path(pgserver_modulo.__file__).parent / "pginstall/share/postgresql/timezone"
    if not destino.exists():
        shutil.copytree(Path(tzdata.__file__).parent / "zoneinfo", destino)


@pytest.fixture(scope="session")
def url_base_de_datos() -> Iterator[str]:
    url = os.environ.get("DATABASE_URL")
    if url:
        yield url
        return
    import pgserver  # dependencia solo de desarrollo local

    _asegurar_zonas_horarias(pgserver)
    servidor = pgserver.get_server(DIRECTORIO_PGDATA_PRUEBAS, cleanup_mode="stop")
    try:
        yield servidor.get_uri()
    finally:
        servidor.cleanup()


@pytest.fixture(scope="session")
def django_db_modify_db_settings(url_base_de_datos: str) -> None:
    """Apunta `DATABASES['default']` a la base elegida antes de crear la base de pruebas."""
    from django.conf import settings

    configuracion = parsear_url_base_de_datos(url_base_de_datos)
    base = settings.DATABASES["default"]
    base.update(configuracion)
    # Nombre unico por sesion: dos pytest sobre el mismo servidor no comparten `test_<base>`.
    base.setdefault("TEST", {})["NAME"] = nombre_unico(configuracion["NAME"])


@pytest.fixture
def redis_falso() -> Iterator[Any]:
    """Cliente Redis en memoria (fakeredis) para pruebas sin servidor Redis."""
    import fakeredis

    cliente = fakeredis.FakeRedis()
    yield cliente
    cliente.flushall()


@pytest.fixture(autouse=True)
def sin_consumidores_fugados() -> Iterator[None]:
    """Los consumidores que una prueba suscribe al bus no pasan a la siguiente."""
    from nucleo.pruebas.aislamiento import retirar_suscripciones_nuevas, suscripciones_actuales

    previas = suscripciones_actuales()
    yield
    retirar_suscripciones_nuevas(previas)
