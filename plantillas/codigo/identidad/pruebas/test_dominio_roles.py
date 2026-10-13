"""Catalogo de roles y segundo factor (DISENO D.2.3 y D.6.3)."""

import pytest

from identidad.dominio.roles import (
    ADMINISTRADOR,
    AUDITOR,
    CATALOGO_DE_ROLES,
    ROLES_CON_SEGUNDO_FACTOR,
    USUARIO,
    exige_segundo_factor,
)

SENSIBLES = {ADMINISTRADOR, AUDITOR}


def test_el_catalogo_trae_los_roles_del_esqueleto() -> None:
    assert set(CATALOGO_DE_ROLES) == {ADMINISTRADOR, AUDITOR, USUARIO}


def test_el_catalogo_no_tiene_repetidos_ni_valores_vacios() -> None:
    assert len(set(CATALOGO_DE_ROLES)) == len(CATALOGO_DE_ROLES)
    assert all(rol and rol == rol.strip().lower() for rol in CATALOGO_DE_ROLES)


def test_exigen_segundo_factor_los_roles_sensibles() -> None:
    assert frozenset(SENSIBLES) == ROLES_CON_SEGUNDO_FACTOR


def test_el_usuario_no_exige_segundo_factor() -> None:
    assert USUARIO not in ROLES_CON_SEGUNDO_FACTOR
    assert not exige_segundo_factor([USUARIO])


def test_los_roles_con_segundo_factor_pertenecen_al_catalogo() -> None:
    assert ROLES_CON_SEGUNDO_FACTOR.issubset(CATALOGO_DE_ROLES)


@pytest.mark.parametrize("rol", sorted(SENSIBLES))
def test_un_rol_sensible_basta_para_exigir_el_segundo_factor(rol: str) -> None:
    assert exige_segundo_factor([rol])
    assert exige_segundo_factor([USUARIO, rol])


def test_un_usuario_sin_roles_no_exige_segundo_factor() -> None:
    assert not exige_segundo_factor([])
