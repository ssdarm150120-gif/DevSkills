"""Encabezados de seguridad que Django 5.2 no trae de serie (D.6.3)."""

from collections.abc import Callable

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse

# CSP estricta: todo solo del mismo origen; nada embebe a la aplicacion (frame-ancestors) ni carga
# plugins, y los formularios solo se envian a la propia aplicacion (`form-action`: no cae en
# `default-src`).
POLITICA_CSP = "; ".join(
    (
        "default-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    )
)


class EncabezadoCSPMiddleware:
    """Agrega `Content-Security-Policy` con `settings.CONTENT_SECURITY_POLICY` a cada respuesta.

    Respeta un encabezado ya puesto por la vista (para relajarlo de forma explicita y local),
    salvo que lo haya fijado VACIO: un `Content-Security-Policy:` en blanco no protege nada, asi
    que se trata como ausente y se aplica la politica del sitio.

    Responsabilidad unica: Django es el UNICO que emite `Content-Security-Policy` y
    `Strict-Transport-Security` en las respuestas de la aplicacion; nginx no los agrega (si lo
    hiciera, el navegador recibiria dos CSP y aplicaria la interseccion de ambas).

    Si `CONTENT_SECURITY_POLICY` existe pero esta vacia, falla con `ImproperlyConfigured` (al
    arrancar y en cada peticion): una CSP vacia desactivaria la proteccion sin avisar.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self._politica()  # falla rapido al cargar el middleware

    @staticmethod
    def _politica() -> str:
        politica = getattr(settings, "CONTENT_SECURITY_POLICY", POLITICA_CSP)
        if not isinstance(politica, str) or not politica.strip():
            raise ImproperlyConfigured(
                "CONTENT_SECURITY_POLICY esta vacia: define una politica o quita el middleware"
            )
        return politica

    def __call__(self, request: HttpRequest) -> HttpResponse:
        respuesta = self.get_response(request)
        if not respuesta.get("Content-Security-Policy", "").strip():
            respuesta["Content-Security-Policy"] = self._politica()
        return respuesta
