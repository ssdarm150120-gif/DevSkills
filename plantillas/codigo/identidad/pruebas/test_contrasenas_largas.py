"""Tope de longitud ANTES de Argon2: una entrada enorme no llega al hasher."""

from typing import Any

import pytest

from identidad.adaptadores.salida import contrasenas as modulo
from identidad.adaptadores.salida.contrasenas import ServicioContrasenasDjango
from identidad.dominio.contrasena import LONGITUD_MAXIMA


@pytest.fixture
def espia_de_argon2(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Largos de las contrasenas que de verdad llegan a Django (hash o verificacion)."""
    llegadas: list[int] = []
    originales = (modulo.make_password, modulo.check_password)

    def _hash(contrasena: str, *args: Any, **kwargs: Any) -> str:
        llegadas.append(len(contrasena))
        return originales[0](contrasena, *args, **kwargs)

    def _verificar(contrasena: str, *args: Any, **kwargs: Any) -> bool:
        llegadas.append(len(contrasena))
        return originales[1](contrasena, *args, **kwargs)

    monkeypatch.setattr(modulo, "make_password", _hash)
    monkeypatch.setattr(modulo, "check_password", _verificar)
    return llegadas


def test_una_contrasena_en_el_limite_se_hashea_y_se_verifica(espia_de_argon2: list[int]) -> None:
    servicio = ServicioContrasenasDjango()
    contrasena = "a1" * (LONGITUD_MAXIMA // 2)
    resultado = servicio.hashear(contrasena)
    assert resultado != contrasena
    assert servicio.verificar(contrasena, resultado) is True
    assert espia_de_argon2 == [LONGITUD_MAXIMA, LONGITUD_MAXIMA]


def test_una_contrasena_enorme_no_llega_a_argon2(espia_de_argon2: list[int]) -> None:
    servicio = ServicioContrasenasDjango()
    hash_valido = servicio.hashear("clave-valida-de-prueba")
    espia_de_argon2.clear()
    enorme = "x" * 5_000_000
    assert servicio.verificar(enorme, hash_valido) is False
    servicio.verificar_ficticia(enorme)
    with pytest.raises(ValueError, match="largo máximo"):
        servicio.hashear(enorme)
    assert espia_de_argon2 == []


def test_una_contrasena_apenas_mas_larga_que_el_limite_tampoco_llega(
    espia_de_argon2: list[int],
) -> None:
    servicio = ServicioContrasenasDjango()
    assert servicio.verificar("x" * (LONGITUD_MAXIMA + 1), "argon2$no-importa") is False
    assert espia_de_argon2 == []
