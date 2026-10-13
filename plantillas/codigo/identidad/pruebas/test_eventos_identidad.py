"""Eventos que `identidad` emite al bus (DISENO D.5.2): el mapeo, y su emisión real en la
misma transacción que la fila de intentos o acciones y que el cambio de negocio."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from django.test import Client

from identidad.adaptadores.entrada import composicion
from identidad.adaptadores.salida.modelos import AccionCuenta, IntentoIngreso, Usuario
from identidad.adaptadores.salida.registro import registro_de_accesos
from identidad.adaptadores.salida.repositorios import huella_de_correo
from identidad.aplicacion.eventos import eventos_de_accion, eventos_de_intento
from identidad.dominio.acceso import AccionDeCuenta, Factor, Motivo, Resultado
from identidad.pruebas.conftest import CONTRASENA, entrar
from nucleo.actor import Actor
from nucleo.adaptadores.modelos import EntregaOutbox, EventoOutbox
from nucleo.puertos import CATALOGO, EventoDeDominio, RegistroDeConsumidores
from nucleo.puertos.registro import obtener

AHORA = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
USUARIO = "11111111-1111-1111-1111-111111111111"
ADMIN = "22222222-2222-2222-2222-222222222222"
PROHIBIDOS = ("contrasena", "password", "secreto", "clave", "token", "correo", "ip")


def _accion(
    accion: AccionDeCuenta, detalle: dict[str, object] | None = None, *, por: str | None = ADMIN
) -> list[EventoDeDominio]:
    return eventos_de_accion(
        7,
        accion=accion,
        usuario_objetivo_id=USUARIO,
        hecha_por_id=por,
        momento=AHORA,
        detalle=detalle,
    )


def _nombres(eventos: list[EventoDeDominio]) -> list[str]:
    return [e.nombre for e in eventos]


# --- Mapeo de acciones (puro) ---


@pytest.mark.parametrize(
    ("accion", "esperado"),
    [
        (AccionDeCuenta.CAMBIO_DE_CONTRASENA, "ContrasenaCambiada"),
        (AccionDeCuenta.BLOQUEO, "CuentaBloqueada"),
        (AccionDeCuenta.DESBLOQUEO, "CuentaDesbloqueada"),
        (AccionDeCuenta.ENROLAMIENTO_SEGUNDO_FACTOR, "SegundoFactorEnrolado"),
        (AccionDeCuenta.REINICIO_SEGUNDO_FACTOR, "SegundoFactorReiniciado"),
        (AccionDeCuenta.RESTABLECIMIENTO_CONTRASENA, "ContrasenaTemporalEmitida"),
        (AccionDeCuenta.SESION_INICIADA, "SesionIniciada"),
    ],
)
def test_las_acciones_simples_producen_su_evento(accion: AccionDeCuenta, esperado: str) -> None:
    [evento] = _accion(accion)
    assert evento.nombre == esperado
    assert evento.payload["usuario_id"] == USUARIO
    assert evento.ocurrido_en == AHORA
    assert evento.agregado_id == USUARIO


def test_el_payload_de_cuenta_dice_quien_lo_hizo_y_es_nulo_si_fue_automatico() -> None:
    [manual] = _accion(AccionDeCuenta.DESBLOQUEO)
    assert manual.payload == {
        "usuario_id": USUARIO,
        "hecho_por": ADMIN,
        "motivo": "desbloqueo_por_administrador",
    }
    [automatico] = _accion(AccionDeCuenta.BLOQUEO, por=None)
    assert automatico.payload["hecho_por"] is None
    assert automatico.payload["motivo"] == "intentos_fallidos"


def test_los_cierres_de_sesion_solo_tienen_los_motivos_salida_y_tope_absoluto() -> None:
    [salida] = _accion(AccionDeCuenta.SESION_CERRADA_SALIDA, por=None)
    [tope] = _accion(AccionDeCuenta.SESION_CERRADA_TOPE_ABSOLUTO, por=None)
    emitidos = {salida.payload["motivo"], tope.payload["motivo"]}
    assert (
        emitidos == set(CATALOGO["SesionCerrada"].motivos_emitidos) == {"salida", "tope_absoluto"}
    )
    assert (salida.nombre, tope.nombre) == ("SesionCerrada", "SesionCerrada")


def test_el_alta_emite_usuario_cambiado_y_contrasena_temporal() -> None:
    eventos = _accion(AccionDeCuenta.ALTA, {"roles": ["auditor", "usuario"]})
    assert _nombres(eventos) == ["UsuarioCambiado", "ContrasenaTemporalEmitida"]
    assert eventos[0].payload["cambio"] == "alta"
    assert eventos[0].payload["roles"] == ["auditor", "usuario"]


def test_desactivar_a_cualquier_usuario_emite_usuario_desactivado() -> None:
    [evento] = _accion(AccionDeCuenta.DESACTIVACION, {"roles": ["auditor"]})
    assert evento.nombre == "UsuarioDesactivado"
    assert evento.payload == {"usuario_id": USUARIO, "hecho_por": ADMIN}


def test_reactivar_emite_usuario_cambiado() -> None:
    [evento] = _accion(AccionDeCuenta.REACTIVACION, {"roles": ["usuario"]})
    assert (evento.nombre, evento.payload["cambio"]) == ("UsuarioCambiado", "reactivacion")


def test_cambiar_los_roles_dice_los_de_antes_y_los_de_despues() -> None:
    [evento] = _accion(
        AccionDeCuenta.CAMBIO_DE_ROLES, {"antes": ["usuario"], "despues": ["auditor"]}
    )
    assert evento.nombre == "UsuarioCambiado"
    assert (evento.payload["cambio"], evento.payload["roles_antes"]) == ("roles", ["usuario"])
    assert evento.payload["roles_despues"] == ["auditor"]


def test_cambiar_los_datos_dice_que_campos_cambiaron() -> None:
    eventos = _accion(AccionDeCuenta.CAMBIO_DE_USUARIO, {"campos": ["nombre"]})
    assert _nombres(eventos) == ["UsuarioCambiado"]
    assert eventos[0].payload["campos"] == ["nombre"]


def test_cada_accion_de_cuenta_produce_al_menos_un_evento_valido_y_sin_datos_prohibidos() -> None:
    """Una acción nueva sin evento no pasa desapercibida; y ninguna carga lleva secretos."""
    for accion in AccionDeCuenta:
        eventos = _accion(accion, {"roles": ["usuario"]})
        assert eventos, accion
        for evento in eventos:
            assert evento.nombre in CATALOGO
            assert not {clave.lower() for clave in evento.payload} & set(PROHIBIDOS)


def test_el_evento_id_depende_de_la_fila_y_no_cambia() -> None:
    primero = _accion(AccionDeCuenta.ALTA, {"roles": ["usuario"]})
    segundo = _accion(AccionDeCuenta.ALTA, {"roles": ["usuario"]})
    assert [e.evento_id for e in primero] == [e.evento_id for e in segundo]
    assert len({e.evento_id for e in primero}) == 2
    otra_fila = eventos_de_accion(
        8,
        accion=AccionDeCuenta.CAMBIO_DE_CONTRASENA,
        usuario_objetivo_id=USUARIO,
        hecha_por_id=USUARIO,
        momento=AHORA,
    )
    assert otra_fila[0].evento_id not in {e.evento_id for e in primero}


# --- Mapeo de intentos (puro) ---


def _intento(
    motivo: Motivo, *, usuario: str | None = USUARIO, factor: Factor = Factor.CONTRASENA
) -> list[EventoDeDominio]:
    return eventos_de_intento(
        3,
        usuario_id=usuario,
        huella_correo="h" * 64,
        factor=factor,
        resultado=Resultado.CORRECTO if motivo is Motivo.CORRECTO else Resultado.FALLIDO,
        motivo=motivo,
        momento=AHORA,
    )


@pytest.mark.parametrize(
    ("motivo", "esperado"),
    [
        (Motivo.CORREO_INEXISTENTE, "credenciales"),
        (Motivo.CONTRASENA_INCORRECTA, "credenciales"),
        (Motivo.CAMBIO_DE_CONTRASENA_INCORRECTA, "credenciales"),
        (Motivo.USUARIO_DESACTIVADO, "desactivado"),
        (Motivo.CUENTA_BLOQUEADA, "bloqueada"),
        (Motivo.REQUIERE_SEGUNDO_FACTOR, "requiere_segundo_factor"),
        (Motivo.CODIGO_INVALIDO, "codigo_invalido"),
    ],
)
def test_un_intento_fallido_es_sesion_fallida_con_el_motivo_real(
    motivo: Motivo, esperado: str
) -> None:
    [evento] = _intento(motivo)
    assert evento.nombre == "SesionFallida"
    assert evento.payload["motivo"] == esperado
    assert evento.payload["usuario_id"] == USUARIO
    assert "huella_correo" not in evento.payload


def test_con_un_correo_inexistente_viaja_solo_la_huella_nunca_el_correo() -> None:
    [evento] = _intento(Motivo.CORREO_INEXISTENTE, usuario=None)
    assert evento.payload["usuario_id"] is None
    assert evento.payload["huella_correo"] == "h" * 64
    assert evento.agregado_id.startswith("huella:")
    assert "@" not in str(evento.payload)


def test_un_intento_correcto_no_emite_nada_porque_la_sesion_se_inicia_al_completar_el_ingreso() -> (
    None
):
    assert _intento(Motivo.CORRECTO) == []


def test_reusar_un_codigo_emite_sesion_fallida_y_codigo_segundo_factor_repetido() -> None:
    eventos = _intento(Motivo.CODIGO_REPETIDO, factor=Factor.CODIGO)
    assert _nombres(eventos) == ["SesionFallida", "CodigoSegundoFactorRepetido"]
    assert eventos[0].payload["motivo"] == "codigo_repetido"
    assert eventos[1].payload == {
        "usuario_id": USUARIO,
        "intento_id": 3,
        "ocurrido_en": AHORA.isoformat(),
    }


def test_un_codigo_invalido_no_emite_el_evento_de_repetido() -> None:
    assert _nombres(_intento(Motivo.CODIGO_INVALIDO, factor=Factor.CODIGO)) == ["SesionFallida"]


# --- Emisión real contra la base ---


def _publicados() -> list[tuple[str, dict[str, Any]]]:
    return [(e.nombre, e.payload) for e in EventoOutbox.objects.order_by("id")]


def _nombres_publicados() -> list[str]:
    return [nombre for nombre, _ in _publicados()]


@pytest.mark.django_db
def test_un_ingreso_con_contrasena_incorrecta_deja_la_fila_y_sesion_fallida(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    Client().post("/ingresar", {"correo": usuario.correo, "contrasena": "incorrecta-1234"})
    assert IntentoIngreso.objects.count() == 1
    [(nombre, payload)] = _publicados()
    assert nombre == "SesionFallida"
    assert payload["motivo"] == "credenciales"
    assert payload["usuario_id"] == str(usuario.id)
    assert usuario.correo not in str(payload)
    assert "ip" not in payload


@pytest.mark.django_db
def test_un_correo_inexistente_se_publica_con_su_huella(
    crear_usuario: Callable[..., Usuario],
) -> None:
    Client().post("/ingresar", {"correo": "nadie@empresa.example", "contrasena": "x" * 12})
    [(nombre, payload)] = _publicados()
    assert nombre == "SesionFallida"
    assert payload["usuario_id"] is None
    assert payload["huella_correo"] == huella_de_correo("nadie@empresa.example")
    assert "nadie@" not in str(payload)


@pytest.mark.django_db
def test_ingresar_y_salir_publican_sesion_iniciada_y_sesion_cerrada(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    cliente = Client()
    respuesta = cliente.post("/ingresar", {"correo": usuario.correo, "contrasena": CONTRASENA})
    assert respuesta.status_code == 302
    assert _nombres_publicados() == ["SesionIniciada"]
    assert AccionCuenta.objects.filter(accion="sesion_iniciada").count() == 1
    cliente.post("/salir")
    assert _publicados()[-1] == (
        "SesionCerrada",
        {"usuario_id": str(usuario.id), "motivo": "salida"},
    )


@pytest.mark.django_db
def test_cinco_contrasenas_incorrectas_publican_el_bloqueo(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    cliente = Client()
    for _ in range(5):
        cliente.post("/ingresar", {"correo": usuario.correo, "contrasena": "incorrecta-1234"})
    nombres = _nombres_publicados()
    assert nombres.count("SesionFallida") == 5
    assert nombres.count("CuentaBloqueada") == 1
    bloqueo = next(p for n, p in _publicados() if n == "CuentaBloqueada")
    assert bloqueo == {
        "usuario_id": str(usuario.id),
        "hecho_por": None,
        "motivo": "intentos_fallidos",
    }


@pytest.mark.django_db
def test_el_tope_absoluto_publica_sesion_cerrada_con_su_motivo(
    crear_usuario: Callable[..., Usuario], settings: Any
) -> None:
    usuario = crear_usuario()
    cliente = entrar(usuario)
    sesion = cliente.session
    sesion["iniciada_en"] = datetime(2020, 1, 1, tzinfo=UTC).isoformat()  # mas de 12 horas
    sesion.save()
    assert cliente.get("/").status_code == 302
    assert _publicados() == [
        ("SesionCerrada", {"usuario_id": str(usuario.id), "motivo": "tope_absoluto"})
    ]


@pytest.mark.django_db
def test_reusar_un_codigo_publica_los_dos_eventos_sin_el_codigo(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario(roles=("auditor",))
    registro_de_accesos().registrar_intento(
        correo_capturado=usuario.correo,
        usuario_id=str(usuario.id),
        factor=Factor.CODIGO,
        resultado=Resultado.FALLIDO,
        motivo=Motivo.CODIGO_REPETIDO,
        ip="203.0.113.5",
        momento=AHORA,
    )
    intento = IntentoIngreso.objects.get()
    publicados = _publicados()
    assert [n for n, _ in publicados] == ["SesionFallida", "CodigoSegundoFactorRepetido"]
    assert publicados[1][1] == {
        "usuario_id": str(usuario.id),
        "intento_id": intento.pk,
        "ocurrido_en": AHORA.isoformat(),
    }
    assert "203.0.113.5" not in str(publicados)
    assert usuario.correo not in str(publicados)


@pytest.mark.django_db
def test_si_falla_la_publicacion_tampoco_queda_la_fila(
    crear_usuario: Callable[..., Usuario], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fila y evento van juntos: lo garantiza el adaptador, no quien llama."""
    usuario = crear_usuario()
    publicador = type(obtener_publicador())

    def falla(self: Any, evento: EventoDeDominio) -> None:
        raise RuntimeError("outbox caido")

    monkeypatch.setattr(publicador, "publicar", falla)
    with pytest.raises(RuntimeError):
        registro_de_accesos().registrar_accion(
            accion=AccionDeCuenta.CAMBIO_DE_CONTRASENA,
            usuario_objetivo_id=str(usuario.id),
            hecha_por_id=str(usuario.id),
            momento=AHORA,
        )
    assert AccionCuenta.objects.count() == 0


def obtener_publicador() -> Any:
    from nucleo.puertos import FabricaDePublicadores

    return obtener(FabricaDePublicadores).de("identidad")


def _intento_fallido() -> None:
    registro_de_accesos().registrar_intento(
        correo_capturado="ana@empresa.example",
        usuario_id=None,
        factor=Factor.CONTRASENA,
        resultado=Resultado.FALLIDO,
        motivo=Motivo.CORREO_INEXISTENTE,
        ip="203.0.113.5",
        momento=AHORA,
    )


@pytest.mark.django_db
def test_si_falla_la_publicacion_de_un_intento_tampoco_queda_la_fila_del_intento(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemela de la de acciones: la transaccion la abre el adaptador, no quien llama."""

    def falla(self: Any, evento: EventoDeDominio) -> None:
        raise RuntimeError("outbox caido")

    monkeypatch.setattr(type(obtener_publicador()), "publicar", falla)
    with pytest.raises(RuntimeError):
        _intento_fallido()
    assert IntentoIngreso.objects.count() == 0


@pytest.mark.django_db
def test_la_fila_del_intento_y_su_evento_quedan_juntos_o_ninguno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si el evento se alcanza a escribir y despues algo falla, la fila tambien se revierte.

    Es la atomicidad "al reves" del intento: ejercer un fallo de la fila ANTES de publicar no prueba
    nada (el evento ni se intenta), asi que esa prueba trivial se elimino.
    """
    publicar_original = type(obtener_publicador()).publicar

    def publica_y_falla(self: Any, evento: EventoDeDominio) -> None:
        publicar_original(self, evento)
        raise RuntimeError("falla despues de escribir el evento")

    monkeypatch.setattr(type(obtener_publicador()), "publicar", publica_y_falla)
    with pytest.raises(RuntimeError):
        _intento_fallido()
    assert (IntentoIngreso.objects.count(), EventoOutbox.objects.count()) == (0, 0)


def test_identidad_no_puede_publicar_un_evento_de_otro_modulo() -> None:
    from nucleo.puertos import EmisorNoAutorizado

    ajeno = EventoDeDominio(
        nombre="PurgaEjecutada",  # es de `nucleo`
        agregado_id="p-1",
        ocurrido_en=AHORA,
        payload={"categoria": "c", "cantidad": 1},
    )
    with pytest.raises(EmisorNoAutorizado, match="identidad"):
        obtener_publicador().publicar(ajeno)


@pytest.mark.django_db
def test_si_se_escribe_el_evento_de_una_accion_y_despues_algo_falla_no_queda_la_fila_ni_el_evento(
    crear_usuario: Callable[..., Usuario], monkeypatch: pytest.MonkeyPatch
) -> None:
    """La fila de la accion se escribe primero; el fallo llega DESPUES de escribir el evento."""
    usuario = crear_usuario()
    publicar_original = type(obtener_publicador()).publicar

    def publica_y_falla(self: Any, evento: EventoDeDominio) -> None:
        publicar_original(self, evento)
        raise RuntimeError("falla despues de escribir el evento")

    monkeypatch.setattr(type(obtener_publicador()), "publicar", publica_y_falla)
    with pytest.raises(RuntimeError):
        registro_de_accesos().registrar_accion(
            accion=AccionDeCuenta.BLOQUEO,
            usuario_objetivo_id=str(usuario.id),
            hecha_por_id=None,
            momento=AHORA,
        )
    assert (AccionCuenta.objects.count(), EventoOutbox.objects.count()) == (0, 0)


# --- Casos de uso de la gestión de usuarios, con la base real ---


@pytest.fixture
def admin(crear_usuario: Callable[..., Usuario]) -> tuple[Usuario, Actor]:
    usuario = crear_usuario(
        correo="admin@empresa.example", nombre="Admin", roles=("administrador",)
    )
    return usuario, Actor.de(str(usuario.id), ["administrador"])


@pytest.mark.django_db
def test_dar_de_alta_publica_en_la_misma_transaccion_que_el_alta(
    admin: tuple[Usuario, Actor],
) -> None:
    _, actor = admin
    creado = composicion.crear_usuario()(
        actor, correo="nuevo@empresa.example", nombre="Nuevo", roles=["usuario"]
    )
    assert _nombres_publicados() == ["UsuarioCambiado", "ContrasenaTemporalEmitida"]
    payloads = " ".join(str(p) for _, p in _publicados())
    assert creado.correo not in payloads
    assert "temporal" not in payloads.replace("ContrasenaTemporalEmitida", "")


@pytest.mark.django_db
def test_si_el_alta_falla_a_medias_no_queda_ningun_evento(
    admin: tuple[Usuario, Actor], monkeypatch: pytest.MonkeyPatch
) -> None:
    from identidad.adaptadores.salida.repositorios import RepositorioCuentasDjango

    _, actor = admin
    original = RepositorioCuentasDjango.crear

    def crear_y_fallar(self: Any, **datos: Any) -> Any:
        original(self, **datos)
        raise RuntimeError("falla despues de crear la cuenta")

    monkeypatch.setattr(RepositorioCuentasDjango, "crear", crear_y_fallar)
    with pytest.raises(RuntimeError):
        composicion.crear_usuario()(
            actor,
            correo="otro@empresa.example",
            nombre="Otro",
            roles=["usuario"],
        )
    assert not Usuario.objects.filter(correo="otro@empresa.example").exists()
    assert EventoOutbox.objects.count() == 0


@pytest.mark.django_db
def test_desactivar_publica_usuario_desactivado(
    admin: tuple[Usuario, Actor], crear_usuario: Callable[..., Usuario]
) -> None:
    _, actor = admin
    ana = crear_usuario(correo="ana@empresa.example", roles=("usuario",))
    composicion.desactivar_usuario()(actor, str(ana.id))
    assert _publicados() == [
        ("UsuarioDesactivado", {"usuario_id": str(ana.id), "hecho_por": actor.id}),
    ]


@pytest.mark.django_db
def test_cambiar_los_roles_publica_usuario_cambiado(
    admin: tuple[Usuario, Actor], crear_usuario: Callable[..., Usuario]
) -> None:
    _, actor = admin
    ana = crear_usuario(correo="ana@empresa.example", nombre="Ana", roles=("usuario",))
    composicion.editar_usuario()(actor, str(ana.id), nombre="Ana", roles=["auditor"])
    publicados = dict(_publicados())
    assert publicados["UsuarioCambiado"]["roles_antes"] == ["usuario"]
    assert publicados["UsuarioCambiado"]["roles_despues"] == ["auditor"]


@pytest.mark.django_db
def test_desbloquear_restablecer_y_reiniciar_publican_eventos_de_cuenta(
    admin: tuple[Usuario, Actor], crear_usuario: Callable[..., Usuario]
) -> None:
    _, actor = admin
    objetivo = crear_usuario(correo="fin@empresa.example", nombre="Fin", roles=("auditor",))
    composicion.desbloquear_cuenta()(actor, str(objetivo.id))
    composicion.restablecer_contrasena()(actor, str(objetivo.id))
    composicion.reiniciar_segundo_factor()(actor, str(objetivo.id))
    assert _nombres_publicados() == [
        "CuentaDesbloqueada",
        "ContrasenaTemporalEmitida",
        "SegundoFactorReiniciado",
    ]


@pytest.mark.django_db
def test_con_un_consumidor_suscrito_el_evento_se_entrega_y_sin_el_queda_sin_entregas(
    admin: tuple[Usuario, Actor], crear_usuario: Callable[..., Usuario]
) -> None:
    _, actor = admin
    registro = obtener(RegistroDeConsumidores)
    ana = crear_usuario(correo="ana@empresa.example", roles=("usuario",))
    composicion.desactivar_usuario()(actor, str(ana.id))
    assert EntregaOutbox.objects.count() == 0  # sin consumidores: el evento ya esta despachado
    registro.suscribir("de-prueba-identidad", lambda e: None, eventos=["UsuarioDesactivado"])
    try:
        otro = crear_usuario(correo="luis@empresa.example", roles=("usuario",))
        composicion.desactivar_usuario()(actor, str(otro.id))
    finally:
        registro.retirar("de-prueba-identidad")
    assert list(EntregaOutbox.objects.values_list("consumidor", "evento__nombre")) == [
        ("de-prueba-identidad", "UsuarioDesactivado")
    ]


def test_las_cargas_de_los_eventos_de_identidad_estan_en_el_catalogo_con_emisor_identidad() -> None:
    emitidos = {
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
    }
    assert {CATALOGO[n].emisores for n in emitidos} == {("identidad",)}
