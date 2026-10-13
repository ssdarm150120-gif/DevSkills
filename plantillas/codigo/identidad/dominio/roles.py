"""Catalogo de roles internos y cuales exigen segundo factor (Clases de usuarios, RNF de
seguridad). Python puro.

El catalogo es la fuente unica: la migracion de datos del esquema `identidad` lo siembra y una
prueba verifica que ambos coincidan. Los roles se identifican con una clave estable en minusculas;
el nombre para mostrar es asunto de la interfaz.

El esqueleto trae tres roles: `administrador` (gestiona usuarios y exige segundo factor), `auditor`
(ejemplo de rol sensible: consulta la bitacora y exige segundo factor) y `usuario` (ejemplo de rol
sin segundo factor). Cada proyecto agrega los roles de su SRS con una migracion de
datos nueva (ver el README del codigo) y los suma aqui, en `nucleo.permisos` y en la prueba que
verifica que coincidan.
"""

from collections.abc import Iterable

ADMINISTRADOR = "administrador"
AUDITOR = "auditor"
USUARIO = "usuario"

CATALOGO_DE_ROLES: tuple[str, ...] = (ADMINISTRADOR, AUDITOR, USUARIO)

# Segundo factor obligatorio para estos roles (HU de segundo factor; el ingreso falla cerrado).
ROLES_CON_SEGUNDO_FACTOR: frozenset[str] = frozenset({ADMINISTRADOR, AUDITOR})


def exige_segundo_factor(roles: Iterable[str]) -> bool:
    """Verdadero si al menos uno de los roles exige segundo factor."""
    return not ROLES_CON_SEGUNDO_FACTOR.isdisjoint(roles)
