"""Adaptador del puerto `PublicadorDeEventos` sobre PostgreSQL (DISENO, D.5.1).

Guarda el evento y una entrega por cada consumidor suscrito, en la transacción en curso: si el
cambio de negocio se revierte, el evento también. Sin transacción abierta se niega a publicar
(`EventoFueraDeTransaccion`), porque el evento quedaría guardado aunque el cambio no.
"""

from django.db import IntegrityError, transaction

from nucleo.adaptadores.modelos import EntregaOutbox, EventoOutbox
from nucleo.adaptadores.reloj import RelojDelSistema
from nucleo.puertos.catalogo_eventos import CATALOGO
from nucleo.puertos.consumidores import RegistroDeConsumidores
from nucleo.puertos.entrega import EstadoDeEntrega
from nucleo.puertos.eventos import (
    EmisorNoAutorizado,
    EventoDeDominio,
    EventoFueraDeTransaccion,
    PublicadorDeEventos,
    emisor_autorizado,
)
from nucleo.puertos.reloj import Reloj


class PublicadorDeEventosDjango:
    """El publicador de UN módulo: solo publica los eventos que el catálogo le asigna (D.5.2)."""

    def __init__(
        self, consumidores: RegistroDeConsumidores, modulo: str, reloj: Reloj | None = None
    ) -> None:
        if not modulo:
            raise ValueError("el publicador necesita el nombre de su módulo")
        self._consumidores = consumidores
        self._modulo = modulo
        self._reloj = reloj or RelojDelSistema()

    def publicar(self, evento: EventoDeDominio) -> None:
        if not emisor_autorizado(evento, self._modulo):
            raise EmisorNoAutorizado(
                f"el módulo {self._modulo!r} no puede publicar {evento.nombre}: el emisor es "
                f"{', '.join(CATALOGO[evento.nombre].emisores)}"
            )
        if not transaction.get_connection().in_atomic_block:
            raise EventoFueraDeTransaccion(
                f"{evento.nombre} se publicó sin una transacción abierta: el evento debe ir en "
                "la misma transacción que el cambio de negocio"
            )
        ahora = self._reloj.ahora()
        try:
            with transaction.atomic():  # punto de guardado: un choque no rompe la transacción
                fila = EventoOutbox.objects.create(
                    evento_id=evento.evento_id,
                    nombre=evento.nombre,
                    version_esquema=evento.version_esquema,
                    agregado_id=evento.agregado_id,
                    ocurrido_en=evento.ocurrido_en,
                    registrado_en=ahora,
                    payload=dict(evento.payload),
                    id_correlacion=evento.id_correlacion,
                )
        except IntegrityError:
            # Mismo `evento_id`: ya estaba publicado (republicacion de historial). Sin efecto.
            if EventoOutbox.objects.filter(evento_id=evento.evento_id).exists():
                return
            raise
        EntregaOutbox.objects.bulk_create(
            EntregaOutbox(
                evento=fila,
                consumidor=suscripcion.consumidor,
                estado=EstadoDeEntrega.PENDIENTE.value,
                proximo_intento_en=ahora,
                creada_en=ahora,
            )
            for suscripcion in self._consumidores.de_evento(evento.nombre)
        )


class FabricaDePublicadoresDjango:
    """Entrega a cada módulo su publicador (lo conecta `configuracion`)."""

    def __init__(self, consumidores: RegistroDeConsumidores, reloj: Reloj | None = None) -> None:
        self._consumidores = consumidores
        self._reloj = reloj

    def de(self, modulo: str) -> PublicadorDeEventos:
        return PublicadorDeEventosDjango(self._consumidores, modulo, self._reloj)
