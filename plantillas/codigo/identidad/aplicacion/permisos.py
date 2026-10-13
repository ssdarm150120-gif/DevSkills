"""Permisos de (DISENO D.5.6): solo el Administrador gestiona usuarios.

Se verifican en cada caso de uso, no solo en la vista (D.5.6): pedir la ruta a mano con otro rol no
cambia nada. La fuente unica de "quien puede gestionar usuarios" es la matriz de `nucleo.permisos`.
"""

from collections.abc import Collection

from identidad.aplicacion.errores import ConflictoDeUsuario, PermisoDenegado
from identidad.aplicacion.puertos import Cuenta
from identidad.dominio.roles import ADMINISTRADOR
from identidad.dominio.usuarios import MENSAJE_ULTIMO_ADMINISTRADOR
from nucleo.actor import Actor
from nucleo.permisos import Capacidad, puede

MENSAJE_OTRO_ADMINISTRADOR = (
    "No puedes hacerlo sobre tu propia cuenta de Administrador: debe hacerlo otro administrador"
)
MENSAJE_PROPIA_CUENTA = "No puedes hacerlo sobre tu propia cuenta"


def exigir_administrador(actor: Actor) -> None:
    if not puede(actor, Capacidad.GESTIONAR_USUARIOS):
        raise PermisoDenegado


def exigir_otro_administrador(actor: Actor, objetivo: Cuenta) -> None:
    """Nadie restablece su contrasena ni reinicia su segundo factor como Administrador: lo hace
    otro."""
    if ADMINISTRADOR in objetivo.roles and objetivo.id == actor.id:
        raise PermisoDenegado(MENSAJE_OTRO_ADMINISTRADOR)


def exigir_que_quede_administrador(
    administradores_activos: Collection[str], objetivo_id: str
) -> None:
    """Siempre queda al menos un Administrador activo (decision del Product Owner).

    `administradores_activos` son los ids que devolvio `bloquear_administradores_activos()`: con
    sus filas bloqueadas, nadie mas puede quitarle el rol o desactivar al que quede.
    """
    if not any(id_ != objetivo_id for id_ in administradores_activos):
        raise ConflictoDeUsuario(MENSAJE_ULTIMO_ADMINISTRADOR)
