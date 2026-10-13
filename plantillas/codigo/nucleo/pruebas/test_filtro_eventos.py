"""Filtro de datos sensibles del bus (DISENO D.5.2) contra las evasiones de la verificación final:
acentos, ancho completo, caracteres invisibles, separadores, camelCase, sinónimos, valores con forma
de correo o de teléfono, y el contrato de los eventos de configuración y exportación."""

from datetime import UTC, datetime
from typing import Any

import pytest

from nucleo.puertos import CATALOGO, EventoDeDominio, EventoInvalido

AHORA = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
BASE: dict[str, Any] = {"categoria": "c", "cantidad": 1}


def _purga(agregado: str = "a", correlacion: str = "", **payload: Any) -> EventoDeDominio:
    return EventoDeDominio(
        nombre="PurgaEjecutada",
        agregado_id=agregado,
        ocurrido_en=AHORA,
        payload={**BASE, **payload},
        id_correlacion=correlacion,
    )


def _con_clave(clave: str, valor: Any = "x") -> EventoDeDominio:
    return _purga(**{clave: valor})


EVASIONES = [
    # con acento
    "teléfono",
    "código",
    "número",
    "móvil",
    "contraseña",
    # sinónimos y variantes
    "movil",
    "celular",
    "phone",
    "mail",
    "e-mail",
    "e_mail",
    "E Mail",
    "eMail",
    "passwd",
    "pwd",
    "apikey",
    "api_key",
    "api-key",
    "apiKey",
    "authorization",
    "cookie",
    "session_id",
    "sesion_id",
    "sessionId",
    "csrf",
    "csrf_token",
    "totp",
    "otp",
    # ancho completo y caracteres invisibles
    "ＣＯＲＲＥＯ",
    "ｔｅｌｅｆｏｎｏ",
    "cor​reo",  # espacio de ancho cero
    "cor­reo",  # guion suave
    "código",  # `o` + acento combinante
    "tele‍fono",  # unidor de ancho cero
    # mayúsculas y camelCase
    "CORREO",
    "codigoSegundoFactor",
    "numeroCelular",
]


@pytest.mark.parametrize("clave", EVASIONES)
def test_cada_evasion_de_la_clave_se_rechaza(clave: str) -> None:
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _con_clave(clave)
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _con_clave("anidado", {clave: 1})


LEGITIMAS = [
    "huella_correo",
    "HuellaCorreo",
    "usuario_id",
    "hecho_por",
    "tipo",
    "descripcion",
    "estado",
    "terminacion_anterior",
    "terminacion_nueva",
    "ocurrido_en",
    "intento_id",
    "participantes",
    "campos",
]


@pytest.mark.parametrize("clave", LEGITIMAS)
def test_las_claves_legitimas_del_catalogo_no_se_prohiben_por_parecerse(clave: str) -> None:
    valor = "1234" if "terminacion" in clave else "x"
    assert _con_clave(clave, valor).payload[clave] == valor


def test_una_terminacion_solo_admite_hasta_cuatro_caracteres() -> None:
    assert _con_clave("terminacion_nueva", None).payload["terminacion_nueva"] is None
    for demasiado in ("12345", "5512345678", 5512345678, ["1234"]):
        with pytest.raises(EventoInvalido, match="terminación"):
            _con_clave("terminacion_nueva", demasiado)


@pytest.mark.parametrize(
    "valor",
    [
        "ana@empresa.example",
        "ana＠empresa.example",  # arroba de ancho completo
        "ＡＮＡ@ＮＯＲＪＡＬ.ＥＸＡＭＰＬＥ",
        "ana@nor​jal.example",  # espacio de ancho cero
        "contacto: ana@empresa.example.",
        "+5215512345678",
        "+52 55 1234 5678",
        "+52-55-1234-5678",
        "+52 (55) 1234.5678",
        "＋５２１５５１２３４５６７８",  # ancho completo
        "llamar al +1 415 555 0132 mañana",
    ],
)
def test_un_valor_con_forma_de_correo_o_de_telefono_se_rechaza_en_cualquier_lugar(
    valor: str,
) -> None:
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _con_clave("nota", valor)
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _con_clave("lista", [{"x": valor}])
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _purga(agregado=valor[:60])
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _purga(correlacion=valor)
    with pytest.raises(EventoInvalido, match="nunca viaja"):  # tambien como CLAVE
        _con_clave(valor, 1)


@pytest.mark.parametrize(
    "valor",
    [
        "2026-10-12T12:00:00+00:00",
        "2026-10-12T12:00:00.123456+00:00",
        "00000000-0000-0000-0000-000000000001",
        "@usuario sin dominio",
        "+52 solo siete: 1234567",
        "OC-2026-0001",
        "h" * 64,
    ],
)
def test_los_valores_legitimos_pasan(valor: str) -> None:
    assert _con_clave("nota", valor).payload["nota"] == valor


# --- Terminaciones: los ultimos 4 caracteres de un dato si viajan ---


def test_una_terminacion_viaja_y_el_dato_completo_no() -> None:
    assert _purga(telefono_terminacion="5678").payload["telefono_terminacion"] == "5678"
    for completo in ("+5215512345678", "5512345678"):
        with pytest.raises(EventoInvalido):
            _purga(telefono_terminacion=completo)
    with pytest.raises(EventoInvalido, match="nunca viaja"):  # la clave `telefono` no se admite
        _purga(telefono_terminacion="5678", telefono="x")


# --- ConfiguracionCambiada y ExportacionRealizada ---


def _evento(nombre: str, **payload: Any) -> EventoDeDominio:
    return EventoDeDominio(nombre=nombre, agregado_id="x", ocurrido_en=AHORA, payload=payload)


def test_configuracion_cambiada_exige_quien_y_que_cambio() -> None:
    assert _evento("ConfiguracionCambiada", usuario_id="u", clave="zona_horaria").payload["clave"]
    assert _evento("ConfiguracionCambiada", usuario_id="u", seccion="seguridad").payload["seccion"]
    for incompleto in ({}, {"usuario_id": "u"}, {"clave": "zona_horaria"}):
        with pytest.raises(EventoInvalido):
            _evento("ConfiguracionCambiada", **incompleto)


def test_exportacion_realizada_exige_quien_que_y_filtros_sin_datos_personales() -> None:
    ok = _evento("ExportacionRealizada", usuario_id="u", tipo="usuarios", filtros={"activo": "si"})
    assert ok.payload["filtros"] == {"activo": "si"}
    assert _evento("ExportacionRealizada", usuario_id="u", reporte="r", filtros={}).payload
    for incompleto in ({"usuario_id": "u", "filtros": {}}, {"usuario_id": "u", "tipo": "p"}):
        with pytest.raises(EventoInvalido):
            _evento("ExportacionRealizada", **incompleto)
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _evento(
            "ExportacionRealizada",
            usuario_id="u",
            tipo="p",
            filtros={"correo": "ana@empresa.example"},
        )
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _evento("ExportacionRealizada", usuario_id="u", tipo="p", filtros={"q": "+5215512345678"})


def test_el_emisor_de_esos_dos_eventos_sigue_siendo_cualquiera_con_su_comentario() -> None:
    assert CATALOGO["ConfiguracionCambiada"].emisores == ("*",)
    assert CATALOGO["ExportacionRealizada"].emisores == ("*",)
    from pathlib import Path

    fuente = (Path(__file__).parents[1] / "puertos" / "catalogo_eventos.py").read_text(
        encoding="utf-8"
    )
    assert "se enumeraran los" in fuente  # el comentario que explica por que `*`
