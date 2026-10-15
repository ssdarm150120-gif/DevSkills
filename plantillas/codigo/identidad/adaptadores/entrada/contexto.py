"""Variables comunes de las plantillas."""

from django.conf import settings
from django.http import HttpRequest


def contexto_de_la_aplicacion(request: HttpRequest) -> dict[str, str]:
    return {
        "nombre_aplicacion": settings.APP_NOMBRE_APLICACION,
        "idioma_html": settings.LANGUAGE_CODE,
    }
