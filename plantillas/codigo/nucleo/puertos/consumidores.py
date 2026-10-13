"""Registro de consumidores de eventos (DISENO D.5.1). Python puro.

Cada módulo suscribe a sus consumidores desde la raíz de composición (`configuracion`), con un
nombre estable: el outbox lleva una entrega por (evento, consumidor), así que un consumidor que
falla se reintenta sin repetir la entrega a los demás. El manejador debe ser IDEMPOTENTE: la entrega
es al menos una vez, y procesar dos veces el mismo `evento_id` no puede tener efecto.

Un evento sin ningún consumidor suscrito es válido: se guarda y no genera entregas.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from nucleo.puertos.catalogo_eventos import CATALOGO
from nucleo.puertos.eventos import EventoDeDominio, EventoDesconocido

Manejador = Callable[[EventoDeDominio], None]
LARGO_MAXIMO_NOMBRE = 80


class ConsumidorRepetido(Exception):
    """Ya hay un consumidor con ese nombre."""


@dataclass(frozen=True, slots=True)
class Suscripcion:
    consumidor: str
    eventos: frozenset[str] | None  # None: todos los eventos (auditoría)
    manejador: Manejador

    def recibe(self, nombre_del_evento: str) -> bool:
        return self.eventos is None or nombre_del_evento in self.eventos


class RegistroDeConsumidores:
    def __init__(self) -> None:
        self._suscripciones: dict[str, Suscripcion] = {}

    def suscribir(
        self, consumidor: str, manejador: Manejador, *, eventos: Iterable[str] | None = None
    ) -> None:
        """Suscribe al consumidor a esos eventos (a todos si `eventos` es `None`).

        Solo recibe los eventos que se publiquen DESPUÉS: las entregas se crean al publicar, una por
        cada consumidor suscrito en ese momento. Un evento ya publicado sin ese consumidor no se
        reentrega al suscribirlo tarde (lo que hace falta de antes, como la carga única de
        `auditoria`, se carga desde su fuente). Por eso los consumidores se suscriben al
        arrancar, desde `configuracion`.
        """
        if not consumidor or len(consumidor) > LARGO_MAXIMO_NOMBRE:
            raise ValueError("el nombre del consumidor es obligatorio y de hasta 80 caracteres")
        if consumidor in self._suscripciones:
            raise ConsumidorRepetido(f"el consumidor {consumidor!r} ya está suscrito")
        nombres = None if eventos is None else frozenset(eventos)
        for nombre in nombres or ():
            if nombre not in CATALOGO:
                raise EventoDesconocido(f"{nombre!r} no está en el catálogo de eventos (D.5.2)")
        self._suscripciones[consumidor] = Suscripcion(consumidor, nombres, manejador)

    def de_evento(self, nombre_del_evento: str) -> tuple[Suscripcion, ...]:
        """Los consumidores que reciben ese evento, en orden de suscripción."""
        return tuple(s for s in self._suscripciones.values() if s.recibe(nombre_del_evento))

    def por_nombre(self, consumidor: str) -> Suscripcion | None:
        return self._suscripciones.get(consumidor)

    def retirar(self, consumidor: str) -> None:
        """Quita una suscripción (la usan las pruebas para no dejar consumidores de otra prueba)."""
        self._suscripciones.pop(consumidor, None)

    def nombres(self) -> frozenset[str]:
        return frozenset(self._suscripciones)
