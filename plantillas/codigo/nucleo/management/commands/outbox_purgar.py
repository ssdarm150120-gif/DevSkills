"""Borra del outbox los eventos que ya cumplieron los 30 días de retención.

    python manage.py outbox_purgar [--dry-run]

Solo se borran eventos despachados (todas sus entregas `entregada`, o sin entregas) de hace más de
30 días; un evento con una entrega en `error` o `pendiente` no se borra nunca solo. `--dry-run`
cuenta sin borrar. `beat` la corre una vez al día (`nucleo.purgar_outbox`).
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from nucleo.adaptadores.purga import purgar


class Command(BaseCommand):
    help = "Purga del outbox: borra los eventos despachados de hace más de 30 días."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Cuenta sin borrar.")

    def handle(self, *args: Any, **opciones: Any) -> None:
        resumen = purgar(dry_run=opciones["dry_run"])
        if resumen.dry_run:
            self.stdout.write(f"Eventos que se borrarían: {resumen.candidatos}")
        else:
            self.stdout.write(f"Eventos borrados: {resumen.borrados}")
