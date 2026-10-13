"""App de Django de `configuracion`: conecta los adaptadores a los puertos al arrancar."""

from django.apps import AppConfig
from django.conf import settings


class ConfiguracionConfig(AppConfig):
    name = "configuracion"
    verbose_name = "Configuracion"

    def ready(self) -> None:
        from configuracion import adaptadores

        # `settings.migraciones` no define adaptadores: el paso `migrar` no usa los puertos.
        elegidos = getattr(settings, "APP_ADAPTADORES", None)
        if elegidos is not None:
            adaptadores.conectar(elegidos)
            # El segundo factor se conecta con los demas adaptadores (no en `migrar`).
            adaptadores.conectar_segundo_factor()
            # El bus de eventos (publicador + consumidores) y su despachador por Celery.
            adaptadores.conectar_bus_de_eventos()
