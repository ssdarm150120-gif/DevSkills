"""Arma el registro de accesos de `identidad` con sus eventos (DISENO D.5.2).

La fila (`IntentoIngreso` o `AccionCuenta`) y sus eventos se guardan en una sola transaccion que
abre este adaptador, no el llamador: el evento no puede quedar sin su fila ni la fila sin su
evento, venga la llamada de un caso de uso, del middleware o de una vista.
"""

from django.db import transaction

from identidad.adaptadores.salida.repositorios import RegistroDeAccesosDjango, huella_de_correo
from identidad.aplicacion.registro_con_eventos import RegistroDeAccesosConEventos
from nucleo.puertos import FabricaDePublicadores
from nucleo.puertos.registro import obtener


def registro_de_accesos() -> RegistroDeAccesosConEventos:
    return RegistroDeAccesosConEventos(
        RegistroDeAccesosDjango(),
        obtener(FabricaDePublicadores).de("identidad"),
        huella_de_correo,
        lambda: transaction.atomic(),
    )
