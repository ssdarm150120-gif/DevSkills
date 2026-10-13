"""Puerto `Reloj` (DISENO D.1.4): el momento actual llega inyectado, nunca se lee del sistema."""

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Reloj(Protocol):
    def ahora(self) -> datetime:
        """El momento actual, con zona horaria."""
        ...
