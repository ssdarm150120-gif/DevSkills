"""Tareas de Celery de `nucleo` (DISENO, D.6.1).

`despachar_outbox` la dispara `beat` cada pocos segundos y la atiende `worker-outbox`, una cola
propia: un pico de tareas pesadas no frena la entrega de eventos. Dos corridas a la vez son
seguras (cada entrega se toma con `SKIP LOCKED`).

Tiempo máximo: `soft_time_limit` (el trabajo se interrumpe con `SoftTimeLimitExceeded`; lo ya
entregado queda, lo demás sigue pendiente) y `time_limit` (el proceso se mata) son la red de
seguridad ENCIMA de los límites de sentencia del despachador. Una entrega a medias se revierte y se
reintenta.

`acks_late` NO se activa a propósito: la entrega vive en PostgreSQL (no en el mensaje de Celery) y
cada una es una transacción, así que si el worker cae lo pendiente lo toma la siguiente corrida de
`beat`; reentregar el mensaje de Celery no agregaría garantía alguna.

`purgar_outbox` corre una vez al día en la cola por defecto (no en `outbox`, para no ocupar al
despachador).
"""

from celery import shared_task

from nucleo.adaptadores.despachador import Despachador
from nucleo.adaptadores.purga import purgar
from nucleo.puertos import FabricaDePublicadores, RegistroDeConsumidores
from nucleo.puertos.registro import obtener

NOMBRE_DE_LA_TAREA = "nucleo.despachar_outbox"
NOMBRE_DE_LA_PURGA = "nucleo.purgar_outbox"
COLA = "outbox"
LIMITE_SUAVE_SEGUNDOS = 240
LIMITE_DURO_SEGUNDOS = 300


def construir_despachador() -> Despachador:
    consumidores = obtener(RegistroDeConsumidores)
    return Despachador(consumidores, obtener(FabricaDePublicadores).de("nucleo"))


@shared_task(
    name=NOMBRE_DE_LA_TAREA,
    ignore_result=True,
    soft_time_limit=LIMITE_SUAVE_SEGUNDOS,
    time_limit=LIMITE_DURO_SEGUNDOS,
)
def despachar_outbox() -> dict[str, int]:
    """Entrega las entregas vencidas del outbox. Devuelve el resumen de la corrida."""
    resumen = construir_despachador().procesar_lote()
    return {
        "entregadas": resumen.entregadas,
        "reintentos": resumen.reintentos,
        "errores": resumen.errores,
    }


@shared_task(
    name=NOMBRE_DE_LA_PURGA,
    ignore_result=True,
    soft_time_limit=LIMITE_SUAVE_SEGUNDOS,
    time_limit=LIMITE_DURO_SEGUNDOS,
)
def purgar_outbox() -> dict[str, int]:
    """Borra del outbox lo despachado hace más de 30 días (retención)."""
    resumen = purgar()
    return {"candidatos": resumen.candidatos, "borrados": resumen.borrados}
