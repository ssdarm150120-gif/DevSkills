"""Modelos de `nucleo` (DISENO D.2.3): el outbox de eventos (D.5.1)."""

from typing import Any, ClassVar

from django.db import models

from nucleo.adaptadores.esquemas import nombre_tabla
from nucleo.puertos.entrega import EstadoDeEntrega


def _opciones(enum: Any) -> list[tuple[str, str]]:
    return [(miembro.value, miembro.name) for miembro in enum]


class EventoOutbox(models.Model):
    """Un evento de dominio publicado (D.5.1). Se escribe en la MISMA transaccion que el cambio de
    negocio y no se modifica despues: el estado de la entrega vive en `EntregaOutbox`.

    `evento_id` es unico: publicar dos veces el mismo evento (por ejemplo, al republicar historial)
    no lo duplica. `payload` nunca lleva contrasenas, codigos ni numeros completos.
    """

    evento_id = models.UUIDField(unique=True)
    nombre = models.CharField(max_length=80)
    version_esquema = models.PositiveSmallIntegerField()
    agregado_id = models.CharField(max_length=64)
    ocurrido_en = models.DateTimeField()
    registrado_en = models.DateTimeField()
    payload = models.JSONField()
    id_correlacion = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = nombre_tabla("nucleo", "evento_outbox")
        indexes: ClassVar[list[Any]] = [
            models.Index(fields=["nombre", "ocurrido_en"], name="evento_outbox_nombre_fecha"),
        ]


class EntregaOutbox(models.Model):
    """La entrega de un evento a UN consumidor, con su estado y sus reintentos.

    El despachador toma las entregas `pendiente` vencidas con `FOR UPDATE SKIP LOCKED`: dos
    despachadores a la vez no toman la misma. `ultimo_error` guarda solo el NOMBRE de la excepcion,
    nunca su mensaje (podria traer datos personales).
    """

    evento = models.ForeignKey(EventoOutbox, on_delete=models.PROTECT, related_name="entregas")
    consumidor = models.CharField(max_length=80)
    estado = models.CharField(max_length=10, choices=_opciones(EstadoDeEntrega))
    intentos = models.PositiveSmallIntegerField(default=0)
    proximo_intento_en = models.DateTimeField()
    ultimo_error = models.CharField(max_length=120, blank=True, default="")
    ultimo_intento_en = models.DateTimeField(null=True, blank=True)
    entregada_en = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField()

    class Meta:
        db_table = nombre_tabla("nucleo", "entrega_outbox")
        constraints: ClassVar[list[Any]] = [
            models.UniqueConstraint(
                fields=["evento", "consumidor"], name="entrega_evento_consumidor_unica"
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=[e.value for e in EstadoDeEntrega]),
                name="entrega_estado_valido",
            ),
        ]
        indexes: ClassVar[list[Any]] = [
            # Lo que recorre el despachador: solo las pendientes, por vencimiento.
            models.Index(
                fields=["proximo_intento_en", "id"],
                condition=models.Q(estado=EstadoDeEntrega.PENDIENTE.value),
                name="entrega_outbox_pendientes",
            ),
            models.Index(
                fields=["consumidor", "estado"],
                name="entrega_consumidor_estado",
            ),
        ]
