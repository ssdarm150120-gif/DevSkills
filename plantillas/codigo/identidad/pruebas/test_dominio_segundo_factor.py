"""Reglas puras del segundo factor TOTP (DISENO D.3.10)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from identidad.dominio.acceso import MAXIMO_DE_FALLOS, tras_fallo
from identidad.dominio.segundo_factor import (
    PASO_SEGUNDOS,
    TOLERANCIA_EN_PASOS,
    ResultadoCodigo,
    decidir_codigo,
    normalizar_codigo,
    paso_de,
    pasos_de_la_ventana,
)

AHORA = datetime(2026, 10, 9, 12, 0, 10, tzinfo=UTC)
PASO = paso_de(AHORA)


# --- Pasos de tiempo y ventana ------------------------------------------------------------------


def test_un_paso_dura_treinta_segundos() -> None:
    assert PASO_SEGUNDOS == 30
    assert paso_de(AHORA + timedelta(seconds=19)) == PASO  # 12:00:29, mismo paso
    assert paso_de(AHORA + timedelta(seconds=20)) == PASO + 1  # 12:00:30, el siguiente


def test_el_paso_no_depende_de_la_zona_horaria() -> None:
    en_mexico = AHORA.astimezone(timezone(timedelta(hours=-6)))
    assert paso_de(en_mexico) == PASO


def test_un_momento_sin_zona_horaria_se_rechaza() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        paso_de(datetime(2026, 10, 9, 12, 0, 10))


def test_la_ventana_acepta_el_paso_anterior_el_vigente_y_el_siguiente() -> None:
    assert TOLERANCIA_EN_PASOS == 1
    assert pasos_de_la_ventana(AHORA) == (PASO - 1, PASO, PASO + 1)


def test_la_ventana_esta_acotada_a_90_segundos() -> None:
    """El codigo no vale para siempre: 2 pasos atras o adelante ya no entran."""
    ventana = pasos_de_la_ventana(AHORA)
    assert PASO - 2 not in ventana
    assert PASO + 2 not in ventana
    assert (len(ventana) * PASO_SEGUNDOS) == 90


# --- Escritura del codigo ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("123456", "123456"),
        (" 123456 ", "123456"),
        ("123 456", "123456"),
        ("123-456", "123456"),
        ("000123", "000123"),  # los ceros a la izquierda cuentan
    ],
)
def test_normalizar_codigo_acepta_las_formas_que_muestran_las_aplicaciones(
    texto: str, esperado: str
) -> None:
    assert normalizar_codigo(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "12345",  # corto
        "1234567",  # largo
        "12345a",
        "١٢٣٤٥٦",  # digitos de otro alfabeto: \d los aceptaria, aqui no
        "123456\n123456",
        "12 34 56 78",
        "１２３４５６",  # digitos de ancho completo
    ],
)
def test_normalizar_codigo_rechaza_lo_que_no_es_un_codigo_de_6_digitos(texto: str) -> None:
    assert normalizar_codigo(texto) is None


# --- Decision: incorrecto, aceptado, repetido -------------------------------------------------


def test_sin_coincidencia_el_codigo_es_incorrecto() -> None:
    assert decidir_codigo([], None) == (ResultadoCodigo.INCORRECTO, None)
    assert decidir_codigo([], PASO) == (ResultadoCodigo.INCORRECTO, None)


def test_el_primer_codigo_se_acepta_y_guarda_su_paso() -> None:
    assert decidir_codigo([PASO], None) == (ResultadoCodigo.ACEPTADO, PASO)


def test_un_codigo_mas_nuevo_que_el_ultimo_aceptado_se_acepta() -> None:
    assert decidir_codigo([PASO + 1], PASO) == (ResultadoCodigo.ACEPTADO, PASO + 1)


def test_el_mismo_codigo_no_se_acepta_dos_veces_aunque_siga_vigente() -> None:
    """el paso ya aceptado se rechaza dentro de su vigencia."""
    assert decidir_codigo([PASO], PASO) == (ResultadoCodigo.REPETIDO, None)


def test_un_codigo_mas_viejo_que_el_ultimo_aceptado_tambien_es_repetido() -> None:
    """Aceptado el codigo del paso T+1, el de T (aun en la ventana) ya no sirve."""
    assert decidir_codigo([PASO - 1], PASO) == (ResultadoCodigo.REPETIDO, None)


def test_si_coincide_con_varios_pasos_se_guarda_el_mas_viejo_aun_no_usado() -> None:
    """Coincidencia doble (probabilidad de 1 en un millon): no se quema un paso futuro de mas."""
    assert decidir_codigo([PASO + 1, PASO], PASO - 1) == (ResultadoCodigo.ACEPTADO, PASO)
    assert decidir_codigo([PASO + 1, PASO], PASO) == (ResultadoCodigo.ACEPTADO, PASO + 1)


# --- Limite de intentos del codigo (el mismo `tras_fallo` que la contrasena) --------------------


def test_cinco_codigos_incorrectos_seguidos_bloquean_quince_minutos() -> None:
    fallos, hasta = 0, None
    for _ in range(MAXIMO_DE_FALLOS - 1):
        fallos, hasta = tras_fallo(fallos, hasta, AHORA)
        assert hasta is None
    fallos, hasta = tras_fallo(fallos, hasta, AHORA)
    assert hasta == AHORA + timedelta(minutes=15)
    assert fallos == 0  # el siguiente ciclo empieza limpio
