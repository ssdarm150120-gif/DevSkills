"""Política de entrega y reintentos del outbox (DISENO, D.4.3). Python puro.

Un consumidor que falla se reintenta con espera exponencial hasta `max_reintentos` veces (5 por
defecto: hasta 6 intentos en total) y después queda en estado de error, visible y sin perderse,
hasta que alguien lo reintente a mano. Un error que dice `reintentable = False` (por ejemplo, una
solicitud que el proveedor rechazó) va directo a error: reintentarlo no cambiaría nada. Un error que
trae `reintentar_en_segundos` (límite de solicitudes del proveedor) manda esa espera, no la
exponencial. Ver `nucleo.puertos.integracion`.

Una excepción que no dice nada (cualquier `Exception` sin el atributo `reintentable`) se trata como
REINTENTABLE: un fallo desconocido casi siempre es transitorio (red, bloqueo, tiempo agotado) y
perder la entrega por no reintentarla es peor que reintentarla cinco veces y dejarla en error.
"""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum


class EstadoDeEntrega(StrEnum):
    PENDIENTE = "pendiente"  # esperando su turno, o esperando el siguiente reintento
    ENTREGADA = "entregada"
    ERROR = "error"  # agotó los reintentos o no era reintentable: requiere atención


@dataclass(frozen=True, slots=True)
class DecisionTrasFallo:
    reintentar: bool
    espera: timedelta
    motivo: str  # `reintento`, `reintentos_agotados` o `no_reintentable`


@dataclass(frozen=True, slots=True)
class PoliticaDeReintentos:
    max_reintentos: int = 5
    espera_base: timedelta = timedelta(seconds=30)
    espera_maxima: timedelta = timedelta(hours=1)

    def __post_init__(self) -> None:
        if self.max_reintentos < 0 or self.espera_base <= timedelta(0):
            raise ValueError("la política de reintentos no es válida")
        if self.espera_maxima < self.espera_base:
            raise ValueError("espera_maxima no puede ser menor que espera_base")

    def decidir(self, intentos_hechos: int, error: BaseException) -> DecisionTrasFallo:
        """`intentos_hechos` cuenta el que acaba de fallar (el primero fallido vale 1)."""
        if not getattr(error, "reintentable", True):
            return DecisionTrasFallo(False, timedelta(0), "no_reintentable")
        if intentos_hechos > self.max_reintentos:
            return DecisionTrasFallo(False, timedelta(0), "reintentos_agotados")
        sugerida = getattr(error, "reintentar_en_segundos", None)
        if type(sugerida) is int and sugerida >= 0:
            espera = timedelta(seconds=sugerida)
        else:
            espera = self.espera_base * (2 ** (intentos_hechos - 1))
        return DecisionTrasFallo(True, min(espera, self.espera_maxima), "reintento")
