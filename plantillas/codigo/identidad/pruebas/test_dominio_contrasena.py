"""Politica de contrasenas (escenario "Contrasena robusta")."""

import pytest

from identidad.dominio.contrasena import LONGITUD_MINIMA, validar_contrasena

FILTRADAS = frozenset({"contrasena1234", "qwertyuiopas"})


def test_la_longitud_minima_es_de_12_caracteres() -> None:
    assert LONGITUD_MINIMA == 12


def test_una_contrasena_larga_y_no_filtrada_es_valida() -> None:
    assert validar_contrasena("caballo-grapa-9Lunar", FILTRADAS) == ()


def test_exactamente_12_caracteres_es_valida() -> None:
    assert validar_contrasena("abcdefghij12", FILTRADAS) == ()


def test_con_11_caracteres_se_rechaza_por_corta() -> None:
    errores = validar_contrasena("abcdefghij1", FILTRADAS)
    assert errores == ("La contraseña debe tener al menos 12 caracteres",)


def test_una_contrasena_de_la_lista_filtrada_se_rechaza() -> None:
    errores = validar_contrasena("contrasena1234", FILTRADAS)
    assert errores == ("Esa contraseña aparece en listas de contraseñas filtradas",)


def test_la_comparacion_con_la_lista_no_distingue_mayusculas() -> None:
    assert validar_contrasena("QwertyUiopAs", FILTRADAS)


def test_corta_y_filtrada_reporta_los_dos_motivos() -> None:
    assert len(validar_contrasena("qwerty", frozenset({"qwerty"}))) == 2


@pytest.mark.parametrize("valor", ["", "            "])
def test_vacia_o_solo_espacios_no_cumple(valor: str) -> None:
    assert validar_contrasena(valor, FILTRADAS)


def test_los_espacios_de_los_bordes_no_cuentan_para_la_longitud() -> None:
    assert validar_contrasena("   abcde      ", FILTRADAS)


def test_un_valor_que_no_es_texto_se_rechaza() -> None:
    with pytest.raises(TypeError):
        validar_contrasena(None, FILTRADAS)  # type: ignore[arg-type]
