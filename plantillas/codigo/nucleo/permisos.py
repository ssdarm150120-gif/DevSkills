"""Matriz de permisos por rol (DISENO, ADR de la matriz de permisos). Python puro.

Sin Django, sin ORM y sin ningun otro modulo del monolito. Los modulos NO importan `identidad` (es
hoja del grafo, D.1.3): consultan aqui, con el `Actor` que les llega, que puede hacer cada quien. El
catalogo de roles y su alta son de `identidad`; este archivo repite solo los CODIGOS de los roles
(una prueba de `identidad` verifica que coincidan con su catalogo).

Cada capacidad nombra una accion o una cola que algun modulo ofrece; aqui solo se decide QUIEN la
tiene. Un usuario con varios roles tiene la union de las capacidades de todos. El permiso se sigue
verificando en el caso de uso de cada modulo, con `puede(actor, capacidad)`. Deniega por defecto: un
rol que no esta en la matriz no concede nada.

Como crece: cada historia que agrega una accion protegida agrega su `Capacidad`, su descripcion y
los roles que la tienen, tal como lo diga el SRS (2.3 Clases de usuarios y RF de administracion).
Si el SRS no nombra una accion para un rol, el rol no la tiene. Si tu dominio necesita un alcance
de lectura (por ejemplo, "cada quien ve solo su cartera"), modelalo aqui como una funcion pura sobre
el `Actor` y documentalo en un ADR.
"""

from enum import StrEnum

from nucleo.actor import Actor

# Codigos de los roles (iguales a los de `identidad.dominio.roles`).
ADMINISTRADOR = "administrador"
AUDITOR = "auditor"
USUARIO = "usuario"


class Capacidad(StrEnum):
    """Una accion o cola que se concede por rol."""

    GESTIONAR_USUARIOS = "gestionar_usuarios"  # alta, edicion, roles y recuperacion del acceso
    CONSULTAR_BITACORA = "consultar_bitacora"  # la consulta llega con el modulo `auditoria`


# Lo que ve el usuario en su inicio: la capacidad dicha con palabras ("colas y acciones").
DESCRIPCIONES: dict[Capacidad, str] = {
    Capacidad.GESTIONAR_USUARIOS: "Gestionar usuarios y roles",
    Capacidad.CONSULTAR_BITACORA: "Consultar la bitácora de auditoría",
}

CAPACIDADES_POR_ROL: dict[str, frozenset[Capacidad]] = {
    ADMINISTRADOR: frozenset({Capacidad.GESTIONAR_USUARIOS, Capacidad.CONSULTAR_BITACORA}),
    AUDITOR: frozenset({Capacidad.CONSULTAR_BITACORA}),
    # El rol de ejemplo `usuario` entra a la aplicacion y no tiene capacidades de administracion.
    USUARIO: frozenset(),
}


def capacidades_de(actor: Actor) -> frozenset[Capacidad]:
    """Union de las capacidades de los roles del actor (un rol desconocido no concede nada)."""
    return frozenset().union(*(CAPACIDADES_POR_ROL.get(rol, frozenset()) for rol in actor.roles))


def puede(actor: Actor, capacidad: Capacidad) -> bool:
    return capacidad in capacidades_de(actor)
