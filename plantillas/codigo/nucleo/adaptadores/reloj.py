"""Adaptador del puerto `Reloj` (DISENO D.1.4): la hora del sistema, en UTC."""

from datetime import datetime

from django.utils import timezone


class RelojDelSistema:
    def ahora(self) -> datetime:
        return timezone.now()
