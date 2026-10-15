"""Desarrollo local (sin Docker, o con Docker Compose). Los valores por defecto son SOLO dev.

Docker NO es requisito: la base sale del PostgreSQL embebido (`python -m herramientas.base_local`)
y, sin `REDIS_URL`, Celery corre en modo local (las tareas se ejecutan en el mismo proceso, sin
worker) y la cache y las sesiones viven en la memoria del proceso. Con `REDIS_URL` (por ejemplo, el
Redis de Compose) se usan el broker y la cache reales, como en produccion.
"""

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

# Redis es OPCIONAL en desarrollo. Sin `REDIS_URL` no se apunta a ningun `localhost:6379` por
# accidente: Celery corre en modo local (eager, broker en memoria) y la cache es local al proceso.
# Los envios del outbox se despachan en la misma peticion; no hay worker ni beat, y para probar los
# reintentos reales se usa Compose.
_REDIS_URL = entorno.texto("REDIS_URL", "")
if _REDIS_URL:
    CELERY_BROKER_URL = _REDIS_URL
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CELERY_BROKER_URL,
            "KEY_PREFIX": "app",
        }
    }
else:
    CELERY_BROKER_URL = "memory://"
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Adaptadores de los puertos compartidos (DISENO D.1.4, D.6.2): en desarrollo, los sistemas externos
# van simulados por defecto. Cada puerto se cambia con su variable `APP_ADAPTADOR_<PUERTO>`.
APP_ADAPTADORES = adaptadores.elegir_en_desarrollo()
