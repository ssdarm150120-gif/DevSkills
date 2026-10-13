"""Aislamiento del registro de puertos para PRUEBAS (H4, H5).

Vive aquí y no en `nucleo/puertos/registro.py` a propósito: el registro de producción no ofrece
ninguna forma de vaciarse ni de reemplazar un adaptador, y este helper (que toca el estado interno)
solo lo importan las pruebas. Es el único camino para reemplazar un adaptador ya conectado.

    with Aislamiento():
        registro.conectar(PuertoDeEjemplo, AdaptadorFalso())
"""

from nucleo.puertos import registro
from nucleo.puertos.consumidores import RegistroDeConsumidores
from nucleo.puertos.eventos import FabricaDePublicadores

# El bus de eventos no es un adaptador externo que las pruebas quieran reemplazar: el registro de
# accesos de `identidad` lo necesita en cada accion. Sobrevive al vaciado salvo que se pida lo
# contrario.
_BUS = (FabricaDePublicadores, RegistroDeConsumidores)


def suscripciones_actuales() -> frozenset[str]:
    """Los consumidores suscritos ahora (vacío si el bus no está conectado)."""
    consumidores = registro._conectados.get(RegistroDeConsumidores)
    return (
        consumidores.nombres() if isinstance(consumidores, RegistroDeConsumidores) else frozenset()
    )


def retirar_suscripciones_nuevas(previas: frozenset[str]) -> None:
    """Quita los consumidores que una prueba suscribió y no estaban antes (no se fugan)."""
    consumidores = registro._conectados.get(RegistroDeConsumidores)
    if isinstance(consumidores, RegistroDeConsumidores):
        for nombre in consumidores.nombres() - previas:
            consumidores.retirar(nombre)


class Aislamiento:
    """Vacía el registro al entrar y, al salir, deja conectado lo que había (para pruebas).

    Conserva el bus de eventos (fábrica de publicadores y consumidores); `con_bus=False` lo vacía
    también. Los consumidores que se suscriban adentro se retiran al salir.
    """

    def __init__(self, *, con_bus: bool = True) -> None:
        self._con_bus = con_bus

    def __enter__(self) -> None:
        self._previos = dict(registro._conectados)
        self._suscripciones = suscripciones_actuales()
        registro._conectados.clear()
        if self._con_bus:
            registro._conectados.update({p: a for p, a in self._previos.items() if p in _BUS})

    def __exit__(self, *excepcion: object) -> None:
        if self._con_bus:  # el bus siguió conectado adentro: sus suscripciones nuevas se retiran
            retirar_suscripciones_nuevas(self._suscripciones)
        registro._conectados.clear()
        registro._conectados.update(self._previos)
