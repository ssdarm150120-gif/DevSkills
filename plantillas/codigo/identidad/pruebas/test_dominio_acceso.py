"""Bloqueo por intentos fallidos (escenario "Bloqueo"): dominio puro."""

from datetime import UTC, datetime, timedelta

import pytest

from identidad.dominio.acceso import (
    DURACION_BLOQUEO,
    MAXIMO_DE_FALLOS,
    correo_valido,
    esta_bloqueada,
    etapa_pendiente_vencida,
    normalizar_correo,
    sesion_vencida,
    tras_fallo,
)

T0 = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def test_el_bloqueo_es_de_5_fallos_y_15_minutos() -> None:
    assert MAXIMO_DE_FALLOS == 5
    assert timedelta(minutes=15) == DURACION_BLOQUEO


def test_los_primeros_cuatro_fallos_solo_suman() -> None:
    fallos, hasta = 0, None
    for esperado in (1, 2, 3, 4):
        fallos, hasta = tras_fallo(fallos, hasta, T0)
        assert (fallos, hasta) == (esperado, None)


def test_el_quinto_fallo_bloquea_quince_minutos_y_reinicia_el_conteo() -> None:
    assert tras_fallo(4, None, T0) == (0, T0 + DURACION_BLOQUEO)


def test_un_fallo_dentro_del_bloqueo_no_lo_extiende_ni_suma() -> None:
    hasta = T0 + DURACION_BLOQUEO
    assert tras_fallo(0, hasta, T0 + timedelta(minutes=5)) == (0, hasta)


def test_cumplido_el_bloqueo_el_conteo_empieza_de_cero() -> None:
    hasta = T0 + DURACION_BLOQUEO
    despues = hasta + timedelta(seconds=1)
    assert tras_fallo(0, hasta, despues) == (1, None)


def test_el_bloqueo_termina_exactamente_a_los_quince_minutos() -> None:
    hasta = T0 + DURACION_BLOQUEO
    assert esta_bloqueada(hasta, hasta - timedelta(seconds=1))
    assert not esta_bloqueada(hasta, hasta)


def test_sin_fecha_la_cuenta_no_esta_bloqueada() -> None:
    assert not esta_bloqueada(None, T0)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Ana@Empresa.Example", "ana@empresa.example"),
        ("  ana@empresa.example  ", "ana@empresa.example"),
        ("ANA@EMPRESA.EXAMPLE", "ana@empresa.example"),
    ],
)
def test_el_correo_se_normaliza_sin_distinguir_mayusculas(texto: str, esperado: str) -> None:
    assert normalizar_correo(texto) == esperado


# --- Correo invalido, tope de la sesion y vigencia de la etapa pendiente --------------------------


def test_el_correo_largo_no_se_trunca() -> None:
    assert len(normalizar_correo("a" * 400)) == 400


@pytest.mark.parametrize(
    "correo", ["", "a\x00b@empresa.example", "a\r\n@empresa.example", "a\x7f@x.example", "a" * 255]
)
def test_un_correo_con_control_vacio_o_largo_no_es_valido(correo: str) -> None:
    assert not correo_valido(normalizar_correo(correo))


def test_un_correo_normal_o_de_254_caracteres_es_valido() -> None:
    assert correo_valido("ana@empresa.example")
    assert correo_valido("a" * 254)


def test_la_sesion_vence_a_las_12_horas_exactas() -> None:
    assert not sesion_vencida(T0, T0 + timedelta(hours=11, minutes=59, seconds=59))
    assert sesion_vencida(T0, T0 + timedelta(hours=12))


def test_una_sesion_sin_marca_de_ingreso_se_considera_vencida() -> None:
    assert sesion_vencida(None, T0)


def test_la_etapa_pendiente_vence_a_los_15_minutos() -> None:
    assert not etapa_pendiente_vencida(T0, T0 + timedelta(minutes=14, seconds=59))
    assert etapa_pendiente_vencida(T0, T0 + timedelta(minutes=15))
    assert etapa_pendiente_vencida(None, T0)
