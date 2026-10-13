"""Adaptadores de salida del aviso por reuso de un codigo: la marca de visto y la zona."""

import uuid
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q

from identidad.adaptadores.salida.modelos import IntentoIngreso, Usuario
from identidad.aplicacion.errores import CuentaNoDisponible
from identidad.dominio.acceso import Motivo
from identidad.dominio.aviso_reuso import IntentoDeReuso


def _marca_de(usuario_id: str, *, bloquear: bool) -> int | None:
    try:
        identificador = uuid.UUID(usuario_id)
        usuarios = Usuario.objects.select_for_update() if bloquear else Usuario.objects
        # `select_for_update` FUERA de una transaccion lanza `TransactionManagementError`: sin el
        # bloqueo dos lecturas simultaneas mostrarian el mismo aviso, asi que falla en voz alta.
        marca: int | None = usuarios.values_list("aviso_reuso_visto_hasta_id", flat=True).get(
            pk=identificador
        )
        return marca
    except (ValueError, Usuario.DoesNotExist):
        raise CuentaNoDisponible from None


class AvisosDeReusoDjango:
    def marca(self, usuario_id: str) -> int | None:
        return _marca_de(usuario_id, bloquear=False)

    def bloquear_marca(self, usuario_id: str) -> int | None:
        return _marca_de(usuario_id, bloquear=True)

    def ultimo_intento_de_reuso(
        self, usuario_id: str, *, despues_de: int | None
    ) -> IntentoDeReuso | None:
        intentos = IntentoIngreso.objects.filter(
            usuario_id=uuid.UUID(usuario_id), motivo=Motivo.CODIGO_REPETIDO.value
        )
        if despues_de is not None:
            intentos = intentos.filter(pk__gt=despues_de)
        ultimo = intentos.order_by("-pk").values_list("pk", "ocurrido_en").first()
        return None if ultimo is None else IntentoDeReuso(id=ultimo[0], ocurrido_en=ultimo[1])

    def marcar_visto(self, usuario_id: str, *, hasta_id: int) -> None:
        # La condicion evita retroceder la marca aunque el bloqueo ya lo impida (defensa en
        # profundidad: una marca mayor nunca se pierde por un `hasta_id` menor).
        Usuario.objects.filter(pk=uuid.UUID(usuario_id)).filter(
            Q(aviso_reuso_visto_hasta_id__isnull=True) | Q(aviso_reuso_visto_hasta_id__lt=hasta_id)
        ).update(aviso_reuso_visto_hasta_id=hasta_id)


class ZonaHorariaDeConfiguracion:
    """La zona de `APP_ZONA_HORARIA` (validada al arrancar; por defecto `UTC`).

    Si el proyecto necesita una zona por usuario o por sede, este adaptador es lo unico que cambia.
    """

    def zona(self) -> ZoneInfo:
        return ZoneInfo(settings.APP_ZONA_HORARIA)
