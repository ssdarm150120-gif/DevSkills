"""Reintenta entregas del outbox que quedaron en error.

    python manage.py outbox_reintentar --entrega 12
    python manage.py outbox_reintentar --evento <evento_id>
    python manage.py outbox_reintentar --consumidor auditoria

Hay que dar al menos un filtro. Las entregas vuelven a `pendiente` con los intentos en cero y el
despachador las toma en su siguiente corrida.
"""

from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from nucleo.adaptadores.despachador import reintentar


class Command(BaseCommand):
    help = "Reintenta entregas del outbox en estado de error."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--entrega", type=int, help="Id de la entrega.")
        parser.add_argument("--evento", help="evento_id (UUID) del evento.")
        parser.add_argument("--consumidor", help="Nombre del consumidor.")

    def handle(self, *args: Any, **opciones: Any) -> None:
        try:
            cantidad = reintentar(
                entrega_id=opciones["entrega"],
                evento_id=opciones["evento"],
                consumidor=opciones["consumidor"],
            )
        except (ValueError, ValidationError) as error:
            raise CommandError(str(error)) from None
        self.stdout.write(f"Entregas reprogramadas: {cantidad}")
