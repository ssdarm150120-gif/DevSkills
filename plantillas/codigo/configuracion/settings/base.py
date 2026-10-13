"""Configuracion comun a todos los entornos. Lo que cambia por entorno va en dev/pruebas/prod."""

from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab

from configuracion import entorno
from configuracion.modulos import APPS_PROPIAS, MIGRATION_MODULES

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # .../codigo

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "rest_framework",
    # Conecta los adaptadores a los puertos al arrancar (raiz de composicion).
    "configuracion.apps.ConfiguracionConfig",
    *APPS_PROPIAS,
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Deja `request.actor` (un `Actor` de nucleo) y limita las etapas del ingreso (D.1.3, D.3.10).
    "identidad.adaptadores.entrada.middleware.ActorMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "configuracion.urls"
WSGI_APPLICATION = "configuracion.wsgi.application"
ASGI_APPLICATION = "configuracion.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Las plantillas viven en el adaptador de entrada de cada modulo (hexagonal).
        "DIRS": [BASE_DIR / "identidad" / "adaptadores" / "entrada" / "plantillas"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "identidad.adaptadores.entrada.contexto.contexto_de_la_aplicacion",
            ],
        },
    },
]

# Las migraciones de cada modulo viven en su adaptador de salida (ver nucleo.adaptadores.esquemas).
MIGRATION_MODULES = dict(MIGRATION_MODULES)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Fechas en UTC; la zona horaria se aplica solo al mostrar.
LANGUAGE_CODE = "es-mx"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Autenticacion (DISENO D.6.3): usuario propio de `identidad`, contrasenas Argon2.
AUTH_USER_MODEL = "identidad.Usuario"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
LOGIN_URL = "/ingresar"
LOGIN_REDIRECT_URL = "/"
# Nombre que se muestra en la interfaz. Va en configuracion y no en el codigo.
APP_NOMBRE_APLICACION = entorno.texto("APP_NOMBRE_APLICACION", "Aplicación")

# Sesion de 3 horas de INACTIVIDAD, no absolutas: cada peticion renueva el vencimiento.
# Las sesiones se guardan en la cache (Redis en dev y prod; memoria local en pruebas).
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_COOKIE_AGE = 3 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# Tope ABSOLUTO de la sesion desde el ingreso, ademas de la inactividad.
APP_SESION_DURACION_MAXIMA = timedelta(
    hours=entorno.entero("APP_SESION_DURACION_MAXIMA_HORAS", 12, minimo=1, maximo=72)
)
# Llave del HMAC de la huella del correo en el registro de intentos (distinta de SECRET_KEY).
# En produccion es obligatoria (prod.py); aqui solo tiene un valor local de desarrollo y pruebas.
APP_LLAVE_HUELLA = entorno.texto("APP_LLAVE_HUELLA", entorno.LLAVE_HUELLA_DE_DESARROLLO)
# Llave con que se CIFRA el secreto del segundo factor: distinta de
# SECRET_KEY y de APP_LLAVE_HUELLA. En produccion es obligatoria (prod.py); aqui solo tiene un valor
# local de desarrollo y pruebas.
APP_LLAVE_SEGUNDO_FACTOR = entorno.texto(
    "APP_LLAVE_SEGUNDO_FACTOR", entorno.LLAVE_SEGUNDO_FACTOR_DE_DESARROLLO
)
# Zona horaria con la que se muestran fechas y horas a los usuarios (se guarda en UTC y la zona se
# aplica solo al mostrar). Es configuracion y no codigo; se valida al arrancar.
APP_ZONA_HORARIA = entorno.zona_horaria(
    entorno.texto("APP_ZONA_HORARIA", "UTC"), variable="APP_ZONA_HORARIA"
)
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Encabezados de seguridad (D.6.3). Los de transporte se endurecen en prod.
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Celery (el broker se define por entorno).
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # Deniega por defecto (D.6.3): una vista nueva sin permisos explicitos NO queda abierta.
    # Los endpoints publicos (webhook, enlaces con token) deben declararlo con AllowAny.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

# Outbox de eventos (D.5.1, D.6.1): `beat` dispara el despachador cada pocos segundos y lo
# atiende `worker-outbox`, una cola propia. `expires` evita que se amontonen corridas si el
# worker se retrasa; dos corridas a la vez son seguras (SKIP LOCKED).
# `acks_late` no se activa: la entrega vive en PostgreSQL y su transaccion ya garantiza el reintento
# (ver `nucleo/tasks.py`). La purga (una vez al dia) va por la cola por defecto, no por `outbox`.
CELERY_TASK_ROUTES = {"nucleo.despachar_outbox": {"queue": "outbox"}}
CELERY_BEAT_SCHEDULE = {
    "despachar-outbox": {
        "task": "nucleo.despachar_outbox",
        "schedule": 5.0,
        "options": {"expires": 10},
    },
    # Retencion del outbox (30 dias): una vez al dia, de madrugada (hora UTC).
    "purgar-outbox": {
        "task": "nucleo.purgar_outbox",
        "schedule": crontab(hour=9, minute=30),
        "options": {"expires": 3600},
    },
}
