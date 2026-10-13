"""Pruebas automatizadas (pytest) y CI.

La base de datos real la inyecta `conftest.py`: `DATABASE_URL` en CI o un PostgreSQL 16 embebido
(pgserver) en local. Redis se reemplaza con fakeredis y Celery corre en modo eager.
"""

from configuracion import adaptadores, entorno
from configuracion.settings.base import *

DEBUG = False
SECRET_KEY = "pruebas-no-es-secreto"  # noqa: S105  # nosec B105
ALLOWED_HOSTS = ["testserver", "localhost"]

DATABASES = {
    "default": entorno.parsear_url_base_de_datos(
        # Inalcanzable a proposito (TLD reservado .invalid, RFC 2606): si `conftest.py` no inyecta
        # la base real, la prueba falla en vez de conectarse al PostgreSQL de otro (puerto 5432).
        entorno.texto("DATABASE_URL", "postgres://app:app@pruebas.invalid:5432/app")
    )
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # rapido, solo pruebas

CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Las pruebas siempre usan los adaptadores falsos, sin importar el entorno de quien las corre.
APP_ADAPTADORES = adaptadores.falsos()
