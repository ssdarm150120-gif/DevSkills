"""Contrato del bus de eventos sin base de datos (DISENO D.5.1, D.5.2): evento, catálogo, registro
de consumidores y política de reintentos."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from nucleo.puertos import (
    CATALOGO,
    EVENTOS_AUDITABLES_MINIMOS,
    ConsumidorRepetido,
    ErrorDeIntegracion,
    ErrorTemporalDeIntegracion,
    EventoDeDominio,
    EventoDesconocido,
    EventoInvalido,
    LimiteDeSolicitudes,
    PoliticaDeReintentos,
    RegistroDeConsumidores,
    SolicitudRechazada,
)

AHORA = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
PURGA = {"categoria": "mensajes", "cantidad": 3}


def _evento(nombre: str = "PurgaEjecutada", **cambios: object) -> EventoDeDominio:
    datos: dict[str, object] = {
        "nombre": nombre,
        "agregado_id": "purga-1",
        "ocurrido_en": AHORA,
        "payload": PURGA,
    }
    datos.update(cambios)
    return EventoDeDominio(**datos)  # type: ignore[arg-type]


# --- Evento ---


def test_un_evento_valido_toma_la_version_del_catalogo_y_un_id_propio() -> None:
    evento = _evento()
    assert evento.version_esquema == CATALOGO["PurgaEjecutada"].version_esquema == 1
    assert isinstance(evento.evento_id, UUID)
    assert _evento().evento_id != evento.evento_id


def test_un_nombre_fuera_del_catalogo_se_rechaza() -> None:
    with pytest.raises(EventoDesconocido):
        _evento("PedidoRegalado")


def test_faltar_un_campo_requerido_se_rechaza() -> None:
    with pytest.raises(EventoInvalido, match="cantidad"):
        _evento(payload={"categoria": "mensajes"})


@pytest.mark.parametrize(
    "prohibido",
    ["contrasena", "password", "secreto", "clave", "token", "codigo_totp", "correo", "Contrasena"],
)
def test_un_dato_que_nunca_viaja_se_rechaza_aunque_este_anidado(prohibido: str) -> None:
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _evento(payload={**PURGA, "extra": {prohibido: "x"}})
    with pytest.raises(EventoInvalido, match="nunca viaja"):
        _evento(payload={**PURGA, prohibido: "x"})


@pytest.mark.parametrize("valor", [datetime(2026, 1, 1, tzinfo=UTC), {1, 2}, object(), UUID(int=1)])
def test_el_payload_solo_admite_valores_de_json(valor: object) -> None:
    with pytest.raises(EventoInvalido, match="tipo no admitido"):
        _evento(payload={**PURGA, "extra": valor})


def test_las_claves_del_payload_son_texto() -> None:
    with pytest.raises(EventoInvalido, match="claves"):
        _evento(payload={**PURGA, "x": {1: "a"}})


def test_un_payload_enorme_se_rechaza() -> None:
    with pytest.raises(EventoInvalido, match="pasa de"):
        _evento(payload={**PURGA, "texto": "x" * 20_000})


def test_el_momento_debe_traer_zona_y_ser_utc() -> None:
    with pytest.raises(EventoInvalido, match="UTC"):
        _evento(ocurrido_en=datetime(2026, 10, 12, 12, 0))
    with pytest.raises(EventoInvalido, match="UTC"):
        _evento(ocurrido_en=datetime(2026, 10, 12, 12, 0, tzinfo=timezone(timedelta(hours=-6))))


def test_un_agregado_vacio_o_demasiado_largo_se_rechaza() -> None:
    for agregado in ("", "x" * 65):
        with pytest.raises(EventoInvalido, match="agregado_id"):
            _evento(agregado_id=agregado)


def test_una_version_de_esquema_invalida_se_rechaza() -> None:
    with pytest.raises(EventoInvalido, match="version_esquema"):
        _evento(version_esquema=-1)
    assert _evento(version_esquema=2).version_esquema == 2


def test_el_payload_del_evento_no_comparte_el_diccionario_de_quien_lo_creo() -> None:
    origen = dict(PURGA)
    evento = _evento(payload=origen)
    origen["cantidad"] = 99
    assert evento.payload["cantidad"] == 3


# --- Catálogo ---


def test_los_eventos_auditables_minimos_existen_en_el_catalogo() -> None:
    """, D.5.2: si falta alguno, el bus no puede registrarlo."""
    faltan = [nombre for nombre in EVENTOS_AUDITABLES_MINIMOS if nombre not in CATALOGO]
    assert faltan == []


def test_los_eventos_del_diseno_estan_en_el_catalogo_con_nombre_en_pasado() -> None:
    esperados = {
        "SesionIniciada",
        "SesionFallida",
        "SesionCerrada",
        "UsuarioCambiado",
        "UsuarioDesactivado",
        "CuentaBloqueada",
        "CuentaDesbloqueada",
        "ContrasenaTemporalEmitida",
        "ContrasenaCambiada",
        "SegundoFactorEnrolado",
        "SegundoFactorReiniciado",
        "CodigoSegundoFactorRepetido",
        "ErrorIntegracionRegistrado",
    }
    assert esperados <= set(CATALOGO)


def test_el_catalogo_deja_escrito_que_motivos_de_cierre_de_sesion_se_emiten_hoy() -> None:
    """D.3.10 y D.5.2 (1.13): `SesionCerrada` solo con `salida` y `tope_absoluto`."""
    especificacion = CATALOGO["SesionCerrada"]
    assert set(especificacion.motivos_emitidos) == {"salida", "tope_absoluto"}
    assert "inactividad" in especificacion.nota
    assert "sello" in especificacion.nota


def test_el_catalogo_dice_que_cambios_de_usuario_existen() -> None:
    assert set(CATALOGO["UsuarioCambiado"].motivos_emitidos) == {
        "alta",
        "datos",
        "roles",
        "reactivacion",
    }


def test_el_codigo_repetido_lleva_solo_ids_y_momento() -> None:
    assert CATALOGO["CodigoSegundoFactorRepetido"].campos == (
        "usuario_id",
        "intento_id",
        "ocurrido_en",
    )


def test_cada_especificacion_tiene_emisor_y_version_positiva() -> None:
    for nombre, especificacion in CATALOGO.items():
        assert especificacion.emisores, nombre
        assert especificacion.version_esquema >= 1, nombre


# --- Registro de consumidores ---


def test_un_consumidor_recibe_solo_los_eventos_a_los_que_se_suscribio() -> None:
    registro = RegistroDeConsumidores()
    registro.suscribir("uno", lambda evento: None, eventos=["PurgaEjecutada"])
    registro.suscribir("todos", lambda evento: None)
    assert [s.consumidor for s in registro.de_evento("PurgaEjecutada")] == ["uno", "todos"]
    assert [s.consumidor for s in registro.de_evento("SesionIniciada")] == ["todos"]
    assert registro.nombres() == {"uno", "todos"}


def test_un_evento_sin_consumidores_no_tiene_suscripciones() -> None:
    assert RegistroDeConsumidores().de_evento("PurgaEjecutada") == ()


def test_no_se_suscribe_dos_veces_el_mismo_consumidor_ni_a_un_evento_desconocido() -> None:
    registro = RegistroDeConsumidores()
    registro.suscribir("uno", lambda evento: None)
    with pytest.raises(ConsumidorRepetido):
        registro.suscribir("uno", lambda evento: None)
    with pytest.raises(EventoDesconocido):
        registro.suscribir("dos", lambda evento: None, eventos=["Inventado"])
    with pytest.raises(ValueError, match="nombre"):
        registro.suscribir("", lambda evento: None)


def test_se_busca_la_suscripcion_por_nombre() -> None:
    registro = RegistroDeConsumidores()
    registro.suscribir("uno", lambda evento: None)
    assert registro.por_nombre("uno") is not None
    assert registro.por_nombre("otro") is None


# --- Política de reintentos ---


def test_la_espera_se_duplica_en_cada_reintento_hasta_el_tope() -> None:
    politica = PoliticaDeReintentos(max_reintentos=5, espera_base=timedelta(seconds=30))
    esperas = [politica.decidir(n, RuntimeError()).espera.total_seconds() for n in range(1, 6)]
    assert esperas == [30, 60, 120, 240, 480]
    capada = PoliticaDeReintentos(max_reintentos=20, espera_maxima=timedelta(minutes=10))
    assert capada.decidir(15, RuntimeError()).espera == timedelta(minutes=10)


def test_agotados_los_cinco_reintentos_pasa_a_error() -> None:
    politica = PoliticaDeReintentos()
    assert politica.decidir(5, RuntimeError()).reintentar  # el quinto reintento aun se programa
    decision = politica.decidir(6, RuntimeError())
    assert (decision.reintentar, decision.motivo) == (False, "reintentos_agotados")


def test_un_error_no_reintentable_va_directo_a_error() -> None:
    decision = PoliticaDeReintentos().decidir(1, SolicitudRechazada("x"))
    assert (decision.reintentar, decision.motivo) == (False, "no_reintentable")
    assert not PoliticaDeReintentos().decidir(1, ErrorDeIntegracion("x")).reintentar


def test_un_error_temporal_de_mensajeria_se_reintenta() -> None:
    assert PoliticaDeReintentos().decidir(1, ErrorTemporalDeIntegracion("x")).reintentar


def test_el_limite_de_envios_manda_su_propia_espera() -> None:
    decision = PoliticaDeReintentos().decidir(3, LimiteDeSolicitudes("x", reintentar_en_segundos=7))
    assert decision.espera == timedelta(seconds=7)
    sin_espera = PoliticaDeReintentos().decidir(3, LimiteDeSolicitudes("x"))
    assert sin_espera.espera == timedelta(seconds=120)  # sin sugerencia, la exponencial


def test_la_espera_sugerida_no_pasa_del_tope() -> None:
    politica = PoliticaDeReintentos(espera_maxima=timedelta(minutes=1))
    decision = politica.decidir(1, LimiteDeSolicitudes("x", reintentar_en_segundos=3600))
    assert decision.espera == timedelta(minutes=1)


@pytest.mark.parametrize(
    "argumentos",
    [
        {"max_reintentos": -1},
        {"espera_base": timedelta(0)},
        {"espera_base": timedelta(hours=2)},
    ],
)
def test_una_politica_invalida_se_rechaza(argumentos: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"política|espera"):
        PoliticaDeReintentos(**argumentos)  # type: ignore[arg-type]


def test_una_excepcion_sin_clasificar_se_trata_como_reintentable() -> None:
    """un fallo desconocido casi siempre es transitorio; se reintenta, no se pierde."""
    assert PoliticaDeReintentos().decidir(1, KeyError("x")).reintentar
    assert not hasattr(KeyError("x"), "reintentable")
