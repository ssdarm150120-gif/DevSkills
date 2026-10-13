"""Alta de un Administrador desde el servidor (DISENO D.6.3, "Alta inicial").

    python manage.py crear_administrador correo@empresa.example

Es la unica via fuera de la interfaz: sin ella nadie podria ingresar la primera vez. Genera una
contrasena temporal que se muestra UNA sola vez (solo se guarda su hash) y que el Administrador debe
cambiar en su primer ingreso. El alta queda en el registro de acciones.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import IntegrityError, transaction

from identidad.adaptadores.entrada import composicion
from identidad.aplicacion.crear_administrador import AltaInvalida


class Command(BaseCommand):
    help = "Crea un Administrador con una contraseña temporal (alta inicial desde el servidor)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("correo", help="Correo corporativo del Administrador")

    def handle(self, *args: Any, **opciones: Any) -> None:
        # Todo el caso de uso (alta + registro de la accion) en UNA transaccion: si algo falla no
        # queda un usuario sin su registro ni un registro sin su usuario.
        try:
            with transaction.atomic():
                _, temporal = composicion.crear_administrador()(opciones["correo"])
        except AltaInvalida as error:
            raise CommandError(str(error)) from error
        except IntegrityError as error:  # alta simultanea del mismo correo
            raise CommandError("Ya existe un usuario con ese correo") from error
        self.stdout.write(f"Administrador creado: {opciones['correo'].strip().lower()}")
        self.stdout.write(f"Contraseña temporal (se muestra una sola vez): {temporal}")
        self.stdout.write("Debe cambiarla en su primer ingreso.")
