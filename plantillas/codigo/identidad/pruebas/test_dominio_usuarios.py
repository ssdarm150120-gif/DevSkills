"""Reglas de alta y edicion de un usuario: dominio puro."""

import pytest

from identidad.dominio.roles import CATALOGO_DE_ROLES
from identidad.dominio.usuarios import (
    LONGITUD_MAXIMA_NOMBRE,
    UsuarioInvalido,
    correo_corporativo_valido,
    validar_correo,
    validar_datos,
    validar_nombre,
    validar_roles,
)


def _datos(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "correo": "Ana@Empresa.Example",
        "nombre": "Ana",
        "roles": ["usuario", "auditor"],
    }
    return {**base, **cambios}


def test_los_datos_validos_se_normalizan() -> None:
    datos = validar_datos(**_datos())  # type: ignore[arg-type]
    assert datos.correo == "ana@empresa.example"
    assert datos.nombre == "Ana"
    assert datos.roles == frozenset({"usuario", "auditor"})


# --- Correo --------------------------------------------------------------------------------------


@pytest.mark.parametrize("correo", ["ana@empresa.example", "a.b-c_9@sub.empresa.example"])
def test_un_correo_con_forma_de_correo_es_valido(correo: str) -> None:
    assert correo_corporativo_valido(correo)


@pytest.mark.parametrize(
    "correo",
    [
        "",
        "ana",
        "ana@",
        "@empresa.example",
        "ana@empresa",
        "ana empresa@x.com",
        "a@b@c.com",
        "ana@empresa.example\x00",
        "a" * 250 + "@x.com",
    ],
)
def test_un_correo_invalido_se_rechaza(correo: str) -> None:
    with pytest.raises(UsuarioInvalido, match="correo"):
        validar_correo(correo)


def test_el_correo_se_compara_sin_distinguir_mayusculas_ni_espacios_en_los_extremos() -> None:
    assert validar_correo("  ANA@Empresa.Example ") == "ana@empresa.example"


# --- Nombre -------------------------------------------------------------------------------------


def test_el_nombre_es_obligatorio_y_se_recorta() -> None:
    assert validar_nombre("  Ana López ") == "Ana López"
    for vacio in ("", "   "):
        with pytest.raises(UsuarioInvalido, match="obligatorio"):
            validar_nombre(vacio)


def test_el_nombre_tiene_un_maximo_y_no_admite_caracteres_de_control() -> None:
    assert validar_nombre("a" * LONGITUD_MAXIMA_NOMBRE)
    with pytest.raises(UsuarioInvalido, match="hasta"):
        validar_nombre("a" * (LONGITUD_MAXIMA_NOMBRE + 1))
    with pytest.raises(UsuarioInvalido, match="control"):
        validar_nombre("Ana\x00")
    with pytest.raises(UsuarioInvalido, match="control"):
        validar_nombre("Ana\nLopez")


# --- Roles ---------------------------------------------------------------------------------------


def test_un_usuario_puede_tener_varios_roles() -> None:
    assert validar_roles(["usuario", "auditor"]) == frozenset({"usuario", "auditor"})


def test_los_roles_repetidos_se_unifican() -> None:
    assert validar_roles(["usuario", "usuario"]) == frozenset({"usuario"})


def test_sin_roles_se_rechaza() -> None:
    with pytest.raises(UsuarioInvalido, match="al menos un rol"):
        validar_roles([])


def test_un_rol_fuera_del_catalogo_se_rechaza() -> None:
    with pytest.raises(UsuarioInvalido, match="inventado"):
        validar_roles(["usuario", "inventado"])


@pytest.mark.parametrize("rol", CATALOGO_DE_ROLES)
def test_cada_rol_del_catalogo_es_asignable(rol: str) -> None:
    assert validar_roles([rol]) == frozenset({rol})
