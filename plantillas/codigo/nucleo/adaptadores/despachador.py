"""Despachador del outbox (DISENO, D.5.1, D.4.3).

Toma de una en una las entregas `pendiente` ya vencidas con `SELECT ... FOR UPDATE SKIP LOCKED`
(dos despachadores a la vez nunca toman la misma), corre al consumidor y deja el resultado en la
MISMA transaccion que lo que el consumidor haya escrito:

* Si el consumidor tiene exito, la entrega queda `entregada`.
* Si falla, las escrituras del consumidor se revierten (punto de guardado), se cuenta el intento y
  se programa el siguiente con espera creciente. Agotados los reintentos, o si el error dice que no
  es reintentable, queda en `error`: visible en `estado_de_la_cola` y reintentable a mano, sin
  perderse, y se publica `ErrorIntegracionRegistrado` (D.5.2).
* Si el proceso se cae a media entrega, la transaccion se revierte y la entrega sigue `pendiente`:
  se entrega de nuevo (al menos una vez), por eso los consumidores son idempotentes.

* `SoftTimeLimitExceeded` no se trata como fallo del consumidor: se re-lanza y la entrega en
  curso queda `pendiente` tal como estaba.
* Un evento que no se puede leer (nombre fuera del catalogo, carga invalida) es un "veneno": su
  entrega va directo a `error` (`no_reintentable`, solo el NOMBRE de la excepcion) y la cola sigue
  con las demas entregas de la misma corrida.

Tiempo maximo. El candado de la entrega dura lo que tarde el consumidor, asi que la transaccion
corre con `statement_timeout` (30 s por defecto) y `lock_timeout` (5 s) de PostgreSQL, y la tarea de
Celery (`nucleo/tasks.py`) lleva `soft_time_limit` y `time_limit` como red de seguridad. Un
consumidor que excede el limite de una sentencia falla con un error reintentable: se revierte lo
suyo, la entrega queda `pendiente` con su espera y las demas entregas siguen. Un consumidor que
llama a un servicio EXTERNO debe poner su propio limite de tiempo: los limites de PostgreSQL no
cortan una llamada de red.

Los logs llevan ids y nombres, nunca la carga util ni el mensaje de la excepcion (podria traer
datos personales).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from celery.exceptions import SoftTimeLimitExceeded
from django.db import connection, transaction
from django.db.models import Count, Min, Q

from nucleo.adaptadores.modelos import EntregaOutbox, EventoOutbox
from nucleo.adaptadores.reloj import RelojDelSistema
from nucleo.puertos.consumidores import RegistroDeConsumidores
from nucleo.puertos.entrega import DecisionTrasFallo, EstadoDeEntrega, PoliticaDeReintentos
from nucleo.puertos.eventos import EventoDeDominio, PublicadorDeEventos
from nucleo.puertos.reloj import Reloj

registro = logging.getLogger("nucleo.outbox")

ORIGEN_DEL_ERROR = "despachador_outbox"
MAXIMO_POR_CORRIDA = 100
LIMITE_DE_SENTENCIA = timedelta(seconds=30)
LIMITE_DE_BLOQUEO = timedelta(seconds=5)


@dataclass(frozen=True, slots=True)
class ResumenDeCorrida:
    entregadas: int = 0
    reintentos: int = 0
    errores: int = 0

    @property
    def total(self) -> int:
        return self.entregadas + self.reintentos + self.errores


def evento_de(fila: EventoOutbox) -> EventoDeDominio:
    return EventoDeDominio(
        nombre=fila.nombre,
        agregado_id=fila.agregado_id,
        ocurrido_en=fila.ocurrido_en,
        payload=fila.payload,
        evento_id=fila.evento_id,
        version_esquema=fila.version_esquema,
        id_correlacion=fila.id_correlacion,
    )


class Despachador:
    def __init__(
        self,
        consumidores: RegistroDeConsumidores,
        publicador: PublicadorDeEventos,
        reloj: Reloj | None = None,
        politica: PoliticaDeReintentos | None = None,
        limite_de_sentencia: timedelta = LIMITE_DE_SENTENCIA,
        limite_de_bloqueo: timedelta = LIMITE_DE_BLOQUEO,
    ) -> None:
        self._limite_de_sentencia = limite_de_sentencia
        self._limite_de_bloqueo = limite_de_bloqueo
        self._consumidores = consumidores
        self._publicador = publicador
        self._reloj = reloj or RelojDelSistema()
        self._politica = politica or PoliticaDeReintentos()

    def procesar_una(self) -> str | None:
        """Procesa la siguiente entrega vencida. Devuelve `entregada`, `reintento` o `error`; o
        `None` si no hay ninguna lista (o todas las listas las tiene otro despachador)."""
        propios = self._consumidores.nombres()
        if not propios:
            return None
        with transaction.atomic():
            with connection.cursor() as cursor:  # valen solo dentro de esta transaccion
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true), "
                    "set_config('lock_timeout', %s, true)",
                    [
                        f"{int(self._limite_de_sentencia.total_seconds() * 1000)}ms",
                        f"{int(self._limite_de_bloqueo.total_seconds() * 1000)}ms",
                    ],
                )
            ahora = self._reloj.ahora()
            entrega = (
                EntregaOutbox.objects.select_for_update(skip_locked=True)
                .filter(
                    estado=EstadoDeEntrega.PENDIENTE.value,
                    proximo_intento_en__lte=ahora,
                    consumidor__in=propios,
                )
                .order_by("proximo_intento_en", "id")
                .first()
            )
            if entrega is None:
                return None
            fila = EventoOutbox.objects.get(pk=entrega.evento_id)
            suscripcion = self._consumidores.por_nombre(entrega.consumidor)
            if suscripcion is None:  # no pasa: la consulta filtra por `consumidor__in=propios`
                raise RuntimeError("consumidor sin suscripcion")
            intentos = entrega.intentos + 1
            try:
                # Leer el evento es parte de la entrega: un veneno no frena a la cola.
                evento = evento_de(fila)
            except SoftTimeLimitExceeded:
                raise
            except Exception as error:
                return self._tras_fallo(entrega, fila, intentos, error, ahora, ilegible=True)
            try:
                with transaction.atomic():  # punto de guardado: lo del consumidor se revierte
                    suscripcion.manejador(evento)
            except SoftTimeLimitExceeded:
                # El limite suave de Celery debe interrumpir DE VERDAD (hereda de `Exception`): se
                # revierte la entrega en curso, que queda `pendiente` (sin contar el intento), y la
                # corrida termina en lugar de seguir hasta el limite duro.
                raise
            except Exception as error:  # cualquier fallo del consumidor se reintenta o se registra
                return self._tras_fallo(entrega, fila, intentos, error, ahora)
            entrega.estado = EstadoDeEntrega.ENTREGADA.value
            entrega.intentos = intentos
            entrega.ultimo_intento_en = ahora
            entrega.entregada_en = ahora
            entrega.ultimo_error = ""
            entrega.save(
                update_fields=[
                    "estado",
                    "intentos",
                    "ultimo_intento_en",
                    "entregada_en",
                    "ultimo_error",
                ]
            )
            return "entregada"

    def _tras_fallo(
        self,
        entrega: EntregaOutbox,
        fila: EventoOutbox,
        intentos: int,
        error: Exception,
        ahora: datetime,
        *,
        ilegible: bool = False,
    ) -> str:
        if ilegible:
            decision = DecisionTrasFallo(False, timedelta(0), "no_reintentable")
        else:
            decision = self._politica.decidir(intentos, error)
        entrega.intentos = intentos
        entrega.ultimo_intento_en = ahora
        entrega.ultimo_error = type(error).__name__[:120]
        if decision.reintentar:
            entrega.proximo_intento_en = ahora + decision.espera
            entrega.save(
                update_fields=[
                    "intentos",
                    "ultimo_intento_en",
                    "ultimo_error",
                    "proximo_intento_en",
                ]
            )
            registro.warning(
                "outbox_reintento consumidor=%s evento=%s nombre=%s intentos=%d error=%s",
                entrega.consumidor,
                fila.evento_id,
                fila.nombre,
                intentos,
                entrega.ultimo_error,
            )
            return "reintento"
        entrega.estado = EstadoDeEntrega.ERROR.value
        entrega.save(update_fields=["estado", "intentos", "ultimo_intento_en", "ultimo_error"])
        registro.error(
            "outbox_error consumidor=%s evento=%s nombre=%s intentos=%d error=%s motivo=%s",
            entrega.consumidor,
            fila.evento_id,
            fila.nombre,
            intentos,
            entrega.ultimo_error,
            decision.motivo,
        )
        if fila.nombre != "ErrorIntegracionRegistrado":  # un fallo del aviso no genera otro aviso
            self._publicador.publicar(
                EventoDeDominio(
                    nombre="ErrorIntegracionRegistrado",
                    agregado_id=f"entrega:{entrega.pk}",
                    ocurrido_en=ahora,
                    payload={
                        "origen": ORIGEN_DEL_ERROR,
                        "codigo": decision.motivo,
                        "mensaje": (
                            f"La entrega de {fila.nombre} al consumidor {entrega.consumidor} "
                            "quedó en error"
                        ),
                        "id_correlacion": fila.id_correlacion or str(fila.evento_id),
                        "evento_id": str(fila.evento_id),
                        "consumidor": entrega.consumidor,
                        "error": entrega.ultimo_error,
                    },
                )
            )
        return "error"

    def procesar_lote(self, maximo: int = MAXIMO_POR_CORRIDA) -> ResumenDeCorrida:
        """Procesa hasta `maximo` entregas vencidas, una transaccion cada una."""
        conteo = {"entregada": 0, "reintento": 0, "error": 0}
        for _ in range(maximo):
            resultado = self.procesar_una()
            if resultado is None:
                break
            conteo[resultado] += 1
        resumen = ResumenDeCorrida(conteo["entregada"], conteo["reintento"], conteo["error"])
        if resumen.total:
            registro.info(
                "outbox_corrida entregadas=%d reintentos=%d errores=%d",
                resumen.entregadas,
                resumen.reintentos,
                resumen.errores,
            )
        return resumen


@dataclass(frozen=True, slots=True)
class EstadoDeLaCola:
    """Lo que hay que mirar para ver atrasos y errores (sin carga util ni datos personales)."""

    pendientes: int
    en_reintento: int  # pendientes que ya fallaron al menos una vez
    en_error: int
    entregadas: int
    atraso_segundos: int  # cuanto lleva esperando la entrega vencida mas antigua (0 si no hay)
    por_consumidor: dict[str, dict[str, int]] = field(default_factory=dict)


def estado_de_la_cola(reloj: Reloj | None = None) -> EstadoDeLaCola:
    ahora = (reloj or RelojDelSistema()).ahora()
    totales = EntregaOutbox.objects.aggregate(
        pendientes=Count("id", filter=Q(estado=EstadoDeEntrega.PENDIENTE.value)),
        en_reintento=Count("id", filter=Q(estado=EstadoDeEntrega.PENDIENTE.value, intentos__gt=0)),
        en_error=Count("id", filter=Q(estado=EstadoDeEntrega.ERROR.value)),
        entregadas=Count("id", filter=Q(estado=EstadoDeEntrega.ENTREGADA.value)),
        mas_antigua=Min(
            "proximo_intento_en",
            filter=Q(estado=EstadoDeEntrega.PENDIENTE.value, proximo_intento_en__lte=ahora),
        ),
    )
    atraso = (
        0
        if totales["mas_antigua"] is None
        else max(0, int((ahora - totales["mas_antigua"]).total_seconds()))
    )
    por_consumidor: dict[str, dict[str, int]] = {}
    for consumidor, estado, cantidad in (
        EntregaOutbox.objects.values_list("consumidor", "estado")
        .annotate(cantidad=Count("id"))
        .order_by("consumidor", "estado")
    ):
        por_consumidor.setdefault(consumidor, {})[estado] = cantidad
    return EstadoDeLaCola(
        pendientes=totales["pendientes"],
        en_reintento=totales["en_reintento"],
        en_error=totales["en_error"],
        entregadas=totales["entregadas"],
        atraso_segundos=atraso,
        por_consumidor=por_consumidor,
    )


def entregas_en_error(limite: int = 50) -> list[EntregaOutbox]:
    """Las entregas en error mas recientes (para decidir cuales reintentar)."""
    return list(
        EntregaOutbox.objects.filter(estado=EstadoDeEntrega.ERROR.value)
        .select_related("evento")
        .order_by("-ultimo_intento_en", "-id")[:limite]
    )


def reintentar(
    *,
    entrega_id: int | None = None,
    evento_id: str | None = None,
    consumidor: str | None = None,
    reloj: Reloj | None = None,
) -> int:
    """Vuelve a `pendiente`, con los intentos en cero, las entregas en error que coincidan.

    Hay que dar al menos un filtro: reintentar TODO por descuido no es una operacion segura.
    Devuelve cuantas entregas se reprogramaron.
    """
    if entrega_id is None and evento_id is None and consumidor is None:
        raise ValueError("indica entrega_id, evento_id o consumidor")
    filtro = EntregaOutbox.objects.filter(estado=EstadoDeEntrega.ERROR.value)
    if entrega_id is not None:
        filtro = filtro.filter(pk=entrega_id)
    if evento_id is not None:
        filtro = filtro.filter(evento__evento_id=evento_id)
    if consumidor is not None:
        filtro = filtro.filter(consumidor=consumidor)
    ahora = (reloj or RelojDelSistema()).ahora()
    cantidad = filtro.update(
        estado=EstadoDeEntrega.PENDIENTE.value,
        intentos=0,
        proximo_intento_en=ahora,
        ultimo_error="",
    )
    registro.info("outbox_reintento_manual entregas=%d", cantidad)
    return cantidad
