"""Retención del outbox (decisión del Product Owner 2026-10-12).

Un evento se borra solo a los `PLAZO_DE_RETENCION` (30 días) de despachado, y SOLO si todas sus
entregas están `entregada` o no tiene entregas. Un evento con una entrega en `error` o `pendiente`
no se borra nunca solo: alguien tiene que verla.

La aplicación no tiene UPDATE ni DELETE sobre `nucleo.evento_outbox`: el borrado lo hace la función
`nucleo.purgar_eventos_outbox` (SECURITY DEFINER, del rol de migraciones), que además se niega a
borrar nada más reciente que 30 días aunque se le pida. Borra por lotes (entregas primero y luego el
evento, en una sola sentencia) y toma cada lote con SKIP LOCKED, así que no frena al despachador.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import connection
from django.db.models import Exists, OuterRef, Q, QuerySet

from nucleo.adaptadores.modelos import EntregaOutbox, EventoOutbox
from nucleo.adaptadores.reloj import RelojDelSistema
from nucleo.puertos.reloj import Reloj

registro = logging.getLogger("nucleo.outbox")

PLAZO_DE_RETENCION = timedelta(days=30)  # el mismo plazo está fijo en la función de la base
# Margen de seguridad que se suma al plazo al calcular el corte: la función de la base rechaza un
# corte de menos de 30 días medidos con SU reloj, y el reloj de la aplicación puede ir adelantado
# unos milisegundos (o minutos) respecto al de PostgreSQL. Sin margen la purga fallaría todos los
# días con un desfase. Tolera hasta una hora de desfase; el costo es borrar una hora más tarde.
MARGEN_DE_RELOJ = timedelta(hours=1)
TAMANO_DE_LOTE = 500
MAXIMO_DE_LOTES = 200  # tope por corrida: 100 000 eventos; la siguiente corrida sigue


@dataclass(frozen=True, slots=True)
class ResumenDePurga:
    candidatos: int  # lo que se borraría (en `--dry-run`) o lo que había al empezar
    borrados: int
    dry_run: bool


def _candidatos(corte: datetime) -> QuerySet[EventoOutbox]:
    sin_despachar = EntregaOutbox.objects.filter(evento_id=OuterRef("pk")).filter(
        ~Q(estado="entregada") | Q(entregada_en__isnull=True) | Q(entregada_en__gt=corte)
    )
    return EventoOutbox.objects.filter(registrado_en__lte=corte).filter(~Exists(sin_despachar))


def purgar(
    reloj: Reloj | None = None, *, dry_run: bool = False, lote: int = TAMANO_DE_LOTE
) -> ResumenDePurga:
    """Borra (o, con `dry_run`, solo cuenta) lo que ya cumplió la retención."""
    corte = (reloj or RelojDelSistema()).ahora() - PLAZO_DE_RETENCION - MARGEN_DE_RELOJ
    candidatos = _candidatos(corte).count()
    if dry_run:
        return ResumenDePurga(candidatos, 0, True)
    borrados = 0
    for _ in range(MAXIMO_DE_LOTES):
        with connection.cursor() as cursor:
            cursor.execute("SELECT nucleo.purgar_eventos_outbox(%s, %s)", [corte, lote])
            fila = cursor.fetchone()
        n = int(fila[0]) if fila else 0
        borrados += n
        if n < lote:
            break
    registro.info("outbox_purga candidatos=%d borrados=%d", candidatos, borrados)
    return ResumenDePurga(candidatos, borrados, False)
