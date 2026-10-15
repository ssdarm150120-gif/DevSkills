"""Produccion y staging. Todo secreto sale del entorno; si falta, falla al arrancar."""

import os
import ssl
import warnings

from django.core.exceptions import ImproperlyConfigured

from configuracion import adaptadores, entorno
from configuracion.seguridad import POLITICA_CSP
from configuracion.settings.base import *

DEBUG = False
# clave de >= 50 caracteres distinta de la de dev; hosts explicitos (sin `*` ni vacio).
SECRET_KEY = entorno.secret_key_de_produccion(entorno.requerida("SECRET_KEY"))
# llave propia para la huella HMAC del correo; obligatoria, fuerte y distinta de SECRET_KEY.
APP_LLAVE_HUELLA = entorno.llave_de_huella_de_produccion(entorno.requerida("APP_LLAVE_HUELLA"))
if APP_LLAVE_HUELLA == SECRET_KEY:
    raise ImproperlyConfigured("APP_LLAVE_HUELLA debe ser distinta de SECRET_KEY")
# llave que cifra el secreto del segundo factor. Obligatoria, fuerte y
# distinta de SECRET_KEY y de APP_LLAVE_HUELLA: si una se filtra, no compromete a las otras.
APP_LLAVE_SEGUNDO_FACTOR = entorno.llave_segundo_factor_de_produccion(
    entorno.requerida("APP_LLAVE_SEGUNDO_FACTOR")
)
if APP_LLAVE_SEGUNDO_FACTOR in (SECRET_KEY, APP_LLAVE_HUELLA):
    raise ImproperlyConfigured(
        "APP_LLAVE_SEGUNDO_FACTOR debe ser distinta de SECRET_KEY y de APP_LLAVE_HUELLA"
    )
ALLOWED_HOSTS = entorno.hosts_permitidos_de_produccion(entorno.requerida("ALLOWED_HOSTS"))

# D.6.3: la aplicacion se conecta con un rol SIN ownership (solo DML). Las credenciales de los roles
# que administran o migran el esquema (`DATABASE_MIGRACIONES_URL`, `DATABASE_ADMIN_URL`,
# `APP_MIGRACIONES_PASSWORD`) solo existen en el proceso del paso `migrar`; si llegaran al proceso
# web o al worker, un fallo de la aplicacion podria alterar el esquema o crear roles.
for _variable_de_otro_rol in (
    "DATABASE_MIGRACIONES_URL",
    "DATABASE_ADMIN_URL",
    "APP_MIGRACIONES_PASSWORD",
):
    if os.environ.get(_variable_de_otro_rol, "").strip():
        raise ImproperlyConfigured(
            f"{_variable_de_otro_rol} no debe estar definida en el proceso de la aplicacion: "
            "las credenciales de administracion y de migraciones son solo del paso `migrar` (D.6.3)"
        )
# DISENO D.1.4: en produccion la aplicacion se niega a arrancar con un adaptador falso (ver
# `configuracion/adaptadores.py` para la unica excepcion, el Compose de desarrollo en localhost).
APP_ADAPTADORES = adaptadores.elegir_en_produccion(ALLOWED_HOSTS)

DATABASES = {
    "default": entorno.parsear_url_base_de_datos(
        entorno.sin_marcador_de_ejemplo("DATABASE_URL", entorno.requerida("DATABASE_URL"))
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = 60

CELERY_BROKER_URL = entorno.sin_marcador_de_ejemplo("REDIS_URL", entorno.requerida("REDIS_URL"))

# TLS hacia la base y hacia Redis. La base entra por `DATABASE_URL` (`?sslmode=verify-full`) y
# Redis por `REDIS_URL` con esquema `rediss://`. Con `APP_EXIGIR_TLS_DATOS=true` la aplicacion se
# niega a arrancar si alguno de los dos viaja en claro. Por defecto no se exige: el Compose del
# proyecto los comunica por una red interna de Docker; con una base o un Redis administrados (otro
# host) SI debe exigirse. Ver el README del codigo, seccion "TLS hacia la base y Redis".
if entorno.booleana("APP_EXIGIR_TLS_DATOS", False):
    entorno.exigir_tls_en_datos(DATABASES["default"], CELERY_BROKER_URL)
if CELERY_BROKER_URL.lower().startswith("rediss://"):
    # `rediss://` cifra el canal; Celery pide ademas verificar el certificado del servidor.
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
# Sesiones en Redis: se pierden si Redis se reinicia sin persistencia, y el usuario vuelve
# a ingresar. El prefijo `app` separa sus claves de las de Celery.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CELERY_BROKER_URL,
        "KEY_PREFIX": "app",
    }
}

# Transporte y cookies (D.6.3). nginx termina TLS y reenvia `X-Forwarded-Proto`.
# Solo se CONFIA en ese encabezado si el despliegue lo declara (`CONFIAR_EN_PROXY_TLS`): cualquier
# cliente puede mandarlo, y fuera de nginx hacerle caso desactivaria la redireccion a HTTPS.
# Detras de nginx es seguro porque (1) nginx lo SOBRESCRIBE con el esquema real de la conexion y
# nunca reenvia el del cliente, y (2) `web` no publica puertos: solo nginx llega a el.
if entorno.booleana("CONFIAR_EN_PROXY_TLS", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# La IP del cliente (se guarda en cada intento de ingreso) la fija nginx en `X-Real-IP`; solo se
# confia en ella en el mismo caso que en `X-Forwarded-Proto`.
APP_IP_DESDE_PROXY = entorno.booleana("CONFIAR_EN_PROXY_TLS", False)
SECURE_SSL_REDIRECT = entorno.booleana("SECURE_SSL_REDIRECT", True)
# HSTS lo emite SOLO Django (nginx no): una sola fuente. El navegador recuerda el dominio y TODOS
# sus puertos; en una maquina de desarrollo (`localhost`) se acorta con HSTS_SEGUNDOS y se apagan
# `HSTS_SUBDOMINIOS` y `HSTS_PRELOAD` (ver `.env.ejemplo`). Por defecto rigen los de produccion.
SECURE_HSTS_SECONDS = entorno.entero("HSTS_SEGUNDOS", 31536000, minimo=1)
SECURE_HSTS_INCLUDE_SUBDOMAINS = entorno.booleana("HSTS_SUBDOMINIOS", True)
SECURE_HSTS_PRELOAD = entorno.booleana("HSTS_PRELOAD", True)
# Un transporte debil solo se admite si TODOS los hosts son de la propia maquina (desarrollo con
# Compose en localhost); en un servidor real la aplicacion se niega a arrancar.
_debilidades_de_transporte = entorno.debilidades_de_transporte(
    redireccion_https=SECURE_SSL_REDIRECT, hsts_segundos=SECURE_HSTS_SECONDS
)
if _debilidades_de_transporte:
    _detalle = "; ".join(_debilidades_de_transporte)
    if set(ALLOWED_HOSTS) <= adaptadores.HOSTS_DE_LA_MAQUINA:
        warnings.warn(
            f"Transporte debilitado, valido solo en la propia maquina: {_detalle}",
            RuntimeWarning,
            stacklevel=1,
        )
    else:
        raise ImproperlyConfigured(
            f"Transporte inseguro en un servidor real: {_detalle}. "
            f"Deja SECURE_SSL_REDIRECT en true y HSTS_SEGUNDOS >= {entorno.HSTS_MINIMO_SEGUNDOS}"
        )
SESSION_COOKIE_SECURE = True
# Prefijo `__Host-`: el navegador solo acepta la cookie si es Secure, de Path=/ y sin Domain,
# asi un subdominio no puede fijarla ni pisarla.
SESSION_COOKIE_NAME = "__Host-sessionid"
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_AGE = 3 * 60 * 60  # sesion de 3 horas (D.6.3)

# CSP estricta (D.6.3): middleware propio justo despues de SecurityMiddleware.
CONTENT_SECURITY_POLICY = POLITICA_CSP
MIDDLEWARE = [
    MIDDLEWARE[0],
    "configuracion.seguridad.EncabezadoCSPMiddleware",
    *MIDDLEWARE[1:],
]
