"""Muestra el estado de la cola del outbox: pendientes, atraso y entregas en error.

    python manage.py outbox_estado [--errores]

No imprime la carga util de los eventos ni mensajes de error (podrian traer datos personales): solo
ids, nombres y conteos. Sale con codigo 1 si hay entregas en error, para poder usarlo en una sonda.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from nucleo.adaptadores.despachador import entregas_en_error, estado_de_la_cola


class Command(BaseCommand):
    help = "Estado de la cola del outbox (pendientes, atraso y entregas en error)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--errores", action="store_true", help="Lista las entregas en error.")

    def handle(self, *args: Any, **opciones: Any) -> None:
        estado = estado_de_la_cola()
        self.stdout.write(
            f"pendientes={estado.pendientes} en_reintento={estado.en_reintento} "
            f"en_error={estado.en_error} entregadas={estado.entregadas} "
            f"atraso_segundos={estado.atraso_segundos}"
        )
        for consumidor, estados in estado.por_consumidor.items():
            detalle = " ".join(f"{nombre}={cantidad}" for nombre, cantidad in estados.items())
            self.stdout.write(f"  {consumidor}: {detalle}")
        if opciones["errores"]:
            for entrega in entregas_en_error():
                self.stdout.write(
                    f"  error entrega={entrega.pk} evento={entrega.evento.evento_id} "
                    f"nombre={entrega.evento.nombre} consumidor={entrega.consumidor} "
                    f"intentos={entrega.intentos} error={entrega.ultimo_error}"
                )
        if estado.en_error:
            raise SystemExit(1)
