import os

from celery import Celery

# Sin `os.environ.setdefault("DJANGO_SETTINGS_MODULE", ...)`: este modulo se importa desde
# `configuracion/__init__.py`, es decir ANTES que `wsgi.py`/`asgi.py`, y un valor por defecto aqui
# les ganaria (produccion arrancaria con los settings de desarrollo). Cada punto de entrada define
# el suyo: manage.py (dev), wsgi/asgi (prod) y el worker de Celery (variable de entorno explicita).

# El nombre de la app sale de la configuracion (nada propio de una empresa en el codigo).
# No se usa `configuracion.entorno` aqui: este modulo se importa antes que los settings.
app = Celery(os.environ.get("APP_NOMBRE_CELERY", "").strip() or "app")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
