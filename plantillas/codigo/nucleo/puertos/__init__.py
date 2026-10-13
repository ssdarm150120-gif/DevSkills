"""Puertos que usan varios modulos (D.1.4). Python puro: sin Django ni ORM.

Los consumidores y los adaptadores importan solo estos contratos; `configuracion` conecta el
adaptador que corresponda al arrancar (`nucleo.puertos.registro`).

Para agregar un puerto compartido (por ejemplo, el de un sistema externo): define aqui su
`Protocol` con `@runtime_checkable`, sus valores como dataclasses inmutables y sus errores tipados;
escribe su adaptador falso y su prueba de contrato reutilizable en `nucleo/pruebas/contratos/`, y
conectalo en `configuracion/adaptadores.py`. El README del codigo trae la receta completa.
"""

from nucleo.puertos.catalogo_eventos import (
    CATALOGO,
    EVENTOS_AUDITABLES_MINIMOS,
    EspecificacionEvento,
)
from nucleo.puertos.consumidores import (
    ConsumidorRepetido,
    Manejador,
    RegistroDeConsumidores,
    Suscripcion,
)
from nucleo.puertos.entrega import DecisionTrasFallo, EstadoDeEntrega, PoliticaDeReintentos
from nucleo.puertos.eventos import (
    EmisorNoAutorizado,
    EventoDeDominio,
    EventoDesconocido,
    EventoFueraDeTransaccion,
    EventoInvalido,
    FabricaDePublicadores,
    PublicadorDeEventos,
    emisor_autorizado,
)
from nucleo.puertos.integracion import (
    ErrorDeIntegracion,
    ErrorTemporalDeIntegracion,
    LimiteDeSolicitudes,
    SolicitudRechazada,
)
from nucleo.puertos.reloj import Reloj

__all__ = [
    "CATALOGO",
    "EVENTOS_AUDITABLES_MINIMOS",
    "ConsumidorRepetido",
    "DecisionTrasFallo",
    "EmisorNoAutorizado",
    "ErrorDeIntegracion",
    "ErrorTemporalDeIntegracion",
    "EspecificacionEvento",
    "EstadoDeEntrega",
    "EventoDeDominio",
    "EventoDesconocido",
    "EventoFueraDeTransaccion",
    "EventoInvalido",
    "FabricaDePublicadores",
    "LimiteDeSolicitudes",
    "Manejador",
    "PoliticaDeReintentos",
    "PublicadorDeEventos",
    "RegistroDeConsumidores",
    "Reloj",
    "SolicitudRechazada",
    "Suscripcion",
    "emisor_autorizado",
]
