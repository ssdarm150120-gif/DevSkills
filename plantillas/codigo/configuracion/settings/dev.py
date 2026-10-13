"""Desarrollo local (Docker Compose o servicios locales). Los valores por defecto son SOLO dev."""

from configuracion import adaptadores, entorno
from configuracion.settings.base import *

DEBUG = True
SECRET_KEY = entorno.texto("SECRET_KEY", entorno.SECRET_KEY_DE_DESARROLLO)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# Sin valor por defecto: en `localhost:5432` puede haber OTRO PostgreSQL (el de otro sistema) y
# la aplicacion nunca debe apuntar ahi por accidente.
AYUDA_DATABASE_URL = (
    "En desarrollo no hay base por defecto. Opciones: (1) PostgreSQL embebido, sin instalar nada: "
    "`python -m herramientas.base_local` imprime la URL y la defines con "
    "`export DATABASE_URL=...` (bash) o `$env:DATABASE_URL = '...'` (PowerShell); "
    "(2) Docker Compose o tu propio PostgreSQL 16: `DATABASE_URL=postgres://usuario:clave@host:puerto/base`"
)
DATABASES = {
    "default": entorno.parsear_url_base_de_datos(
        entorno.requerida("DATABASE_URL", AYUDA_DATABASE_URL)
    )
}

CELERY_BROKER_URL = entorno.texto("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CELERY_BROKER_URL,
        "KEY_PREFIX": "app",
    }
}

# Adaptadores de los puertos compartidos (DISENO D.1.4, D.6.2): en desarrollo, los sistemas externos
# van simulados por defecto. Cada puerto se cambia con su variable `APP_ADAPTADOR_<PUERTO>`.
APP_ADAPTADORES = adaptadores.elegir_en_desarrollo()
