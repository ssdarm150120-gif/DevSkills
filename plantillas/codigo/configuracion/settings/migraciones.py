"""Migraciones de esquema (D.6.3): el UNICO proceso que usa el rol dueno del esquema.

    DJANGO_SETTINGS_MODULE=configuracion.settings.migraciones python manage.py migrate

La aplicacion (`web`, `worker`) corre con `configuracion.settings.prod` y un rol SIN ownership
(`DATABASE_URL`: solo SELECT/INSERT/UPDATE/DELETE). Las migraciones necesitan crear esquemas y
tablas, asi que corren aparte, con el rol de migraciones (`DATABASE_MIGRACIONES_URL`), en un paso
que termina antes de que arranque la aplicacion. No es un entorno de servicio: no atiende
peticiones ni tiene Redis ni `ALLOWED_HOSTS`.
"""

from configuracion import entorno
from configuracion.settings.base import *

DEBUG = False
SECRET_KEY = entorno.secret_key_de_produccion(entorno.requerida("SECRET_KEY"))
ALLOWED_HOSTS: list[str] = []

DATABASES = {
    "default": entorno.parsear_url_base_de_datos(
        entorno.sin_marcador_de_ejemplo(
            "DATABASE_MIGRACIONES_URL", entorno.requerida("DATABASE_MIGRACIONES_URL")
        )
    )
}
