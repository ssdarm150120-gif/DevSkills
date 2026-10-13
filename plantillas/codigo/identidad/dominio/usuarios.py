"""Datos de un usuario interno y sus reglas de alta y edicion (RF de gestion de usuarios).

Python puro. Reglas: el correo corporativo es valido y unico (la unicidad la decide el repositorio),
el nombre es obligatorio y legible, y hay al menos un rol del catalogo.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from identidad.dominio.acceso import correo_valido, normalizar_correo
from identidad.dominio.roles import CATALOGO_DE_ROLES

# Regla heredada del proyecto de referencia: el correo es solo ASCII. Antes de la arroba, letras sin
# acento, numeros, punto, guion y guion bajo; el dominio, etiquetas ASCII separadas por punto.
_CORREO = re.compile(
    r"^[a-z0-9_-]+(?:\.[a-z0-9_-]+)*"  # sin punto al inicio, al final ni dos seguidos
    r"@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
# Categorias Unicode que un nombre no puede llevar: control, formato (invisibles), separadores de
# linea y de parrafo, uso privado y sustitutos sueltos.
_CATEGORIAS_PROHIBIDAS_EN_NOMBRE = frozenset({"Cc", "Cf", "Zl", "Zp", "Co", "Cs"})
LONGITUD_MAXIMA_NOMBRE = 150

MENSAJE_CORREO_INVALIDO = (
    "El correo no es válido. Solo se aceptan letras sin acento, números, punto, guion y guion "
    "bajo antes de la arroba, y un dominio con letras sin acento, números, guiones y puntos "
    "(sin acentos, ñ ni espacios; sin punto al inicio ni al final de cada parte ni dos puntos "
    "seguidos; máximo 254 caracteres)"
)
MENSAJE_CORREO_REPETIDO = "Ya existe un usuario con ese correo"
MENSAJE_ULTIMO_ADMINISTRADOR = "Debe quedar al menos un administrador activo"


class UsuarioInvalido(ValueError):
    """Los datos del usuario no cumplen las reglas; el mensaje se le muestra al Administrador."""


@dataclass(frozen=True, slots=True)
class DatosDeUsuario:
    """Los datos ya validados y normalizados de un usuario."""

    correo: str
    nombre: str
    roles: frozenset[str]


def correo_corporativo_valido(correo_normalizado: str) -> bool:
    """Correo ASCII ya normalizado (minusculas): algo@dominio.tld de hasta 254 caracteres."""
    return correo_valido(correo_normalizado) and _CORREO.fullmatch(correo_normalizado) is not None


def validar_correo(correo: str) -> str:
    # Lo escrito debe ser ASCII ANTES de pasar a minusculas: `lower()` vuelve "K" (signo Kelvin,
    # U+212A) una "k" comun, y un caracter que no es ASCII no debe colarse por esa conversion.
    normalizado = normalizar_correo(correo)
    if not correo.isascii() or not correo_corporativo_valido(normalizado):
        raise UsuarioInvalido(MENSAJE_CORREO_INVALIDO)
    return normalizado


def validar_nombre(nombre: str) -> str:
    limpio = unicodedata.normalize("NFKC", nombre).strip()
    if not limpio:
        raise UsuarioInvalido("El nombre es obligatorio")
    if len(limpio) > LONGITUD_MAXIMA_NOMBRE:
        raise UsuarioInvalido(f"El nombre admite hasta {LONGITUD_MAXIMA_NOMBRE} caracteres")
    if any(unicodedata.category(c) in _CATEGORIAS_PROHIBIDAS_EN_NOMBRE for c in limpio):
        raise UsuarioInvalido("El nombre no puede llevar caracteres de control ni invisibles")
    return limpio


def validar_roles(roles: Iterable[str]) -> frozenset[str]:
    """Al menos un rol, todos del catalogo; un usuario puede tener varios."""
    elegidos = frozenset(roles)
    if not elegidos:
        raise UsuarioInvalido("Elige al menos un rol")
    desconocidos = sorted(elegidos - set(CATALOGO_DE_ROLES))
    if desconocidos:
        raise UsuarioInvalido(f"Rol desconocido: {', '.join(desconocidos)}")
    return elegidos


def validar_datos(
    *,
    correo: str,
    nombre: str,
    roles: Iterable[str],
) -> DatosDeUsuario:
    """Valida los datos de un alta o de una edicion; lanza `UsuarioInvalido` con el primer error."""
    roles_validos = validar_roles(roles)
    return DatosDeUsuario(
        correo=validar_correo(correo),
        nombre=validar_nombre(nombre),
        roles=roles_validos,
    )
