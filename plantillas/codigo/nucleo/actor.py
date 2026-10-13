"""`Actor`: quien ejecuta un caso de uso (DISENO D.1.3 y D.5).

Los permisos se verifican en el caso de uso, pero ningun modulo importa `identidad`. El adaptador
de entrada (vista, webhook o tarea) resuelve al usuario con `identidad` y le pasa al caso de uso
este valor inmutable; el caso de uso decide con el. En las pruebas basta con construir un `Actor`.

Python puro: sin Django, sin ORM y sin ningun otro modulo del monolito. Aqui NO hay autenticacion
ni catalogo de roles: eso es de `identidad`. Un `Actor` solo transporta lo que ya fue resuelto.

Para extenderlo (por ejemplo, con el alcance de lectura que tu dominio necesite, como una cartera o
una sucursal), agrega el campo, validalo en `_validar` y pasalo en `__reduce__` y `__setstate__`:
asi `pickle` y `copy` siguen revalidando.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass


def _texto_no_vacio(valor: object, campo: str) -> str:
    # `type(...) is str` (no `isinstance`): una subclase de `str` puede redefinir `__eq__`,
    # `__hash__` o `strip` y hacerse pasar por otro valor al comparar roles o ids.
    if type(valor) is not str or not valor.strip():
        raise ValueError(f"Actor.{campo} debe ser un texto no vacio")
    return valor


def _normalizar_roles(roles: Iterable[object]) -> frozenset[str]:
    """Valida y normaliza los roles; siempre falla con `ValueError("Actor.roles ...")`.

    Un texto suelto (`"usuario"`) se rechaza: si no, se partiria en letras. `None` o elementos no
    hasheables darian `TypeError`, que se traduce al mismo `ValueError`.
    """
    if isinstance(roles, str):
        raise ValueError("Actor.roles debe ser un conjunto de roles, no un texto")
    try:
        elementos = frozenset(roles)
    except TypeError as error:
        raise ValueError(
            "Actor.roles debe ser un iterable de textos no vacios (hasheables), no "
            f"{type(roles).__name__}"
        ) from error
    return frozenset(_texto_no_vacio(rol, "roles") for rol in elementos)


def _validar(id: object, roles: object) -> frozenset[str]:
    """Validacion unica del `Actor` (constructor, `pickle`, `copy`); devuelve los roles."""
    _texto_no_vacio(id, "id")
    return _normalizar_roles(roles)  # type: ignore[arg-type]


def _reconstruir(id: str, roles: frozenset[str]) -> "Actor":
    return Actor(id=id, roles=roles)


@dataclass(frozen=True, slots=True)
class Actor:
    """Quien actua: su identificador y sus roles."""

    id: str
    roles: frozenset[str]

    def __post_init__(self) -> None:
        roles = _validar(self.id, self.roles)
        # `frozen=True` impide asignar: se normaliza con `object.__setattr__` (solo aqui).
        object.__setattr__(self, "roles", roles)

    @classmethod
    def de(cls, id: str, roles: Iterable[str]) -> "Actor":
        """Construye un `Actor` desde cualquier iterable de roles (lista, tupla, set).

        Un texto suelto (`"usuario"`) lanza `ValueError`: se pasa `["usuario"]`.
        """
        return cls(id=id, roles=_normalizar_roles(roles))

    def __reduce__(self) -> tuple[Callable[..., "Actor"], tuple[object, ...]]:
        """`pickle` y `copy` reconstruyen pasando por el constructor, o sea, revalidan.

        El `__setstate__` que genera `dataclass(slots=True)` asigna los campos sin validar: un
        pickle o una copia manipulados entrarian sin pasar por `__post_init__`.
        """
        return (_reconstruir, (self.id, self.roles))

    def __setstate__(self, estado: dict[str, object]) -> None:
        """Ruta directa (`actor.__setstate__(...)`): valida igual que el constructor."""
        roles = _validar(estado.get("id"), estado.get("roles"))
        object.__setattr__(self, "id", estado.get("id"))
        object.__setattr__(self, "roles", roles)

    def tiene_rol(self, rol: str) -> bool:
        """Verdadero si el actor tiene exactamente ese rol."""
        return rol in self.roles

    def tiene_algun_rol(self, *roles: str) -> bool:
        """Verdadero si el actor tiene al menos uno de los roles dados."""
        return not self.roles.isdisjoint(roles)
