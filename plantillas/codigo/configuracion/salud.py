"""`/salud` (DISENO D.6.4): responde 200 si el proceso `web` esta vivo. No toca la base de datos."""

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe


@require_safe  # GET y HEAD: los balanceadores y `curl -I` consultan con HEAD
def salud(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"estado": "ok"})
