"""Aviso al dueno de la cuenta por un intento de reusar un codigo del segundo factor.

DISENO D.3.10. Python puro. La fecha y la hora que se muestran son las del intento MAS RECIENTE,
en la zona horaria configurada de la aplicacion; el aviso no lleva nada mas del intento (ni la IP ni
la huella del correo): quien lo hizo no es asunto de quien lo lee.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

MENSAJE_AVISO_REUSO = (
    "Alguien intentó usar un código tuyo ya utilizado el {momento}; "
    "si no fuiste tú, cambia tu contraseña y avisa al administrador"
)
# `%Z` es la abreviatura de la zona EN ESE INSTANTE (CDT/CST, EDT/EST; o el desplazamiento, `-05`,
# si la zona no tiene letras): sin ella la hora repetida al terminar el horario de verano (01:30
# ocurre dos veces) seria ambigua.
FORMATO_DEL_MOMENTO = "%d/%m/%Y %H:%M:%S %Z"


@dataclass(frozen=True, slots=True)
class IntentoDeReuso:
    """Un intento de reuso ya registrado: su id (el orden en que llegaron) y su momento."""

    id: int
    ocurrido_en: datetime


@dataclass(frozen=True, slots=True)
class AvisoDeReuso:
    """Lo que se le muestra al usuario: el momento del intento mas reciente y su zona horaria."""

    ocurrido_en: datetime  # con zona horaria (UTC): el `ocurrido_en` del intento
    zona: ZoneInfo

    def __post_init__(self) -> None:
        if self.ocurrido_en.tzinfo is None:
            raise ValueError("el momento del intento debe llevar zona horaria")

    @property
    def momento_local(self) -> str:
        """`12/10/2026 14:35:07 CST (America/Mexico_City)`: dia/mes/anio, hora de 24, abreviatura
        de la zona en ese instante y la zona usada. `01/11/2026 01:30:00 EDT` y `... 01:30:00 EST`
        son dos instantes distintos y se distinguen."""
        local = self.ocurrido_en.astimezone(self.zona)
        return f"{local.strftime(FORMATO_DEL_MOMENTO)} ({self.zona.key})"

    @property
    def mensaje(self) -> str:
        return MENSAJE_AVISO_REUSO.format(momento=self.momento_local)
