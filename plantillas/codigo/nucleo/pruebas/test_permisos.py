"""Matriz de permisos por rol: deniega por defecto y suma las capacidades de varios roles."""

from nucleo.actor import Actor
from nucleo.permisos import (
    ADMINISTRADOR,
    AUDITOR,
    CAPACIDADES_POR_ROL,
    DESCRIPCIONES,
    USUARIO,
    Capacidad,
    capacidades_de,
    puede,
)


def _actor(*roles: str) -> Actor:
    return Actor.de("u-1", roles)


def test_toda_capacidad_tiene_su_descripcion_para_la_pantalla() -> None:
    assert set(DESCRIPCIONES) == set(Capacidad)
    assert all(texto.strip() for texto in DESCRIPCIONES.values())


def test_toda_capacidad_la_tiene_algun_rol() -> None:
    concedidas = frozenset().union(*CAPACIDADES_POR_ROL.values())
    assert concedidas == frozenset(Capacidad)


def test_un_rol_desconocido_no_concede_nada() -> None:
    assert capacidades_de(_actor("inventado")) == frozenset()


def test_un_actor_sin_roles_no_puede_nada() -> None:
    assert not puede(_actor(), Capacidad.GESTIONAR_USUARIOS)


def test_solo_el_administrador_gestiona_usuarios() -> None:
    assert puede(_actor(ADMINISTRADOR), Capacidad.GESTIONAR_USUARIOS)
    assert not puede(_actor(AUDITOR), Capacidad.GESTIONAR_USUARIOS)
    assert not puede(_actor(USUARIO), Capacidad.GESTIONAR_USUARIOS)


def test_solo_el_rol_de_ejemplo_auditor_tiene_la_capacidad_de_ejemplo() -> None:
    # El esqueleto no trae bitacora: la capacidad es un ejemplo y el administrador NO la anuncia.
    assert puede(_actor(AUDITOR), Capacidad.CONSULTAR_BITACORA)
    assert not puede(_actor(ADMINISTRADOR), Capacidad.CONSULTAR_BITACORA)
    assert not puede(_actor(USUARIO), Capacidad.CONSULTAR_BITACORA)


def test_un_usuario_con_varios_roles_tiene_las_capacidades_de_todos() -> None:
    ambos = _actor(ADMINISTRADOR, USUARIO)
    assert capacidades_de(ambos) == capacidades_de(_actor(ADMINISTRADOR)) | capacidades_de(
        _actor(USUARIO)
    )
