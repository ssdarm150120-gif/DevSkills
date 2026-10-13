"""Iniciar sesion de forma segura: sus 9 escenarios Gherkin (pytest-bdd).

Corren contra la aplicacion completa (cliente HTTP de Django y PostgreSQL), con los adaptadores
reales de `identidad`: son la prueba de aceptacion de la historia.
"""

import re
import socket
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.hashers import check_password
from django.test import Client
from pytest_bdd import given, parsers, scenario, then, when

from identidad.adaptadores.salida.modelos import AccionCuenta, IntentoIngreso, Usuario
from identidad.pruebas.conftest import CONTRASENA, RelojAdelantable
from nucleo.pruebas.aislamiento import Aislamiento

# pytest-bdd resuelve los pasos al ejecutar el test: la base se prepara desde antes.
pytestmark = pytest.mark.django_db

FEATURE = "identidad/pruebas/ingreso.feature"
MENSAJE_GENERICO = "Correo o contraseña incorrectos"
CORREO = "ana@empresa.example"
ROLES_SENSIBLES = ["administrador", "auditor", "auditor", "auditor", "auditor"]


@pytest.fixture
def ctx() -> dict[str, Any]:
    """Estado compartido entre los pasos de un escenario."""
    return {}


def _ingresar(cliente: Client, correo: str, contrasena: str, **extra: Any) -> Any:
    return cliente.post("/ingresar", {"correo": correo, "contrasena": contrasena}, **extra)


# --- 1. Ingreso correcto ----------------------------------------------------------------------


@scenario(FEATURE, "Ingreso correcto")
def test_ingreso_correcto() -> None: ...


@given("que tengo un rol que no exige segundo factor")
def _rol_sin_segundo_factor(crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]) -> None:
    ctx["usuario"] = crear_usuario(roles=("usuario", "usuario"))


@when("ingreso mi correo corporativo y mi contraseña correctos")
def _ingreso_correcto(cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["respuesta"] = _ingresar(cliente, "  ANA@Empresa.Example ", CONTRASENA)


@then("entro a la aplicación con los permisos de mis roles")
def _entro(cliente: Client, ctx: dict[str, Any]) -> None:
    assert ctx["respuesta"].status_code == 302
    assert ctx["respuesta"]["Location"] == "/"
    inicio = cliente.get("/")
    assert inicio.status_code == 200
    # El `Actor` que reciben los casos de uso lleva exactamente los roles del usuario.
    actor = inicio.wsgi_request.actor  # type: ignore[attr-defined]
    assert actor.roles == frozenset({"usuario"})
    assert actor.id == str(ctx["usuario"].id)
    contenido = inicio.content.decode()
    assert "usuario" in contenido
    assert "usuario" in contenido


@then("el ingreso queda registrado")
def _ingreso_registrado(ctx: dict[str, Any]) -> None:
    intento = IntentoIngreso.objects.get()
    assert (intento.resultado, intento.motivo, intento.factor) == (
        "correcto",
        "correcto",
        "contrasena",
    )
    assert intento.usuario_id == ctx["usuario"].id


# --- 2. No se revela si el correo existe ------------------------------------------------------


@scenario(FEATURE, "No se revela si el correo existe")
def test_no_se_revela_si_el_correo_existe() -> None: ...


@when("intento ingresar con un correo que no existe")
def _correo_inexistente(
    cliente: Client, crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]
) -> None:
    crear_usuario()
    ctx["inexistente"] = _ingresar(cliente, "nadie@empresa.example", CONTRASENA)


@then(parsers.parse('veo "{mensaje}"'))
def _veo(mensaje: str, ctx: dict[str, Any]) -> None:
    respuesta = ctx.get("inexistente") or ctx["respuesta"]
    assert mensaje in respuesta.content.decode()


@then("es el mismo mensaje que al ingresar un correo existente con una contraseña incorrecta")
def _mismo_mensaje(cliente: Client, ctx: dict[str, Any]) -> None:
    existente = _ingresar(cliente, CORREO, "contraseña-equivocada")
    inexistente = ctx["inexistente"]
    assert existente.status_code == inexistente.status_code == 200
    assert MENSAJE_GENERICO in existente.content.decode()

    # Misma pagina salvo el correo que el usuario escribio (que se conserva para reintentar).
    def _sin_variables(pagina: str, correo: str) -> str:
        sin_token = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", pagina)
        return sin_token.replace(correo, "X")

    assert _sin_variables(existente.content.decode(), CORREO) == _sin_variables(
        inexistente.content.decode(), "nadie@empresa.example"
    )


@then("el intento queda registrado")
def _intento_registrado(ctx: dict[str, Any]) -> None:
    motivos = set(IntentoIngreso.objects.values_list("motivo", flat=True))
    esperados = ctx.get("motivos_esperados")
    if esperados is None:
        esperados = {"correo_inexistente", "contrasena_incorrecta"}
    assert esperados <= motivos
    assert set(IntentoIngreso.objects.values_list("resultado", flat=True)) == {"fallido"}


# --- 3. Bloqueo por intentos fallidos ---------------------------------------------------------


@scenario(FEATURE, "Bloqueo por intentos fallidos")
def test_bloqueo_por_intentos_fallidos() -> None: ...


@when("fallo la contraseña 5 veces seguidas")
def _cinco_fallos(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    reloj: RelojAdelantable,
    ctx: dict[str, Any],
) -> None:
    ctx["usuario"] = crear_usuario()
    for _ in range(5):
        assert MENSAJE_GENERICO in _ingresar(cliente, CORREO, "mala").content.decode()


@then("la cuenta se bloquea 15 minutos y el intento queda registrado")
def _bloqueada(cliente: Client, reloj: RelojAdelantable, ctx: dict[str, Any]) -> None:
    usuario = Usuario.objects.get(pk=ctx["usuario"].pk)
    restante = usuario.bloqueada_hasta - reloj.ahora()  # type: ignore[operator]
    assert timedelta(minutes=14, seconds=50) < restante <= timedelta(minutes=15)
    assert (
        AccionCuenta.objects.filter(accion="bloqueo", usuario_objetivo_id=usuario.id).count() == 1
    )
    assert IntentoIngreso.objects.filter(motivo="contrasena_incorrecta").count() == 5
    # Bloqueada: ni la contrasena correcta entra, y el mensaje es el mismo (no revela el bloqueo).
    respuesta = _ingresar(cliente, CORREO, CONTRASENA)
    assert MENSAJE_GENERICO in respuesta.content.decode()
    assert IntentoIngreso.objects.filter(motivo="cuenta_bloqueada").count() == 1
    # Cumplidos los 15 minutos vuelve a entrar.
    reloj.adelantar(minutes=15, seconds=1)
    assert _ingresar(cliente, CORREO, CONTRASENA).status_code == 302


@then("el bloqueo aplica a la cuenta, sin importar desde dónde se intente")
def _bloqueo_por_cuenta(crear_usuario: Callable[..., Usuario], reloj: RelojAdelantable) -> None:
    otra = crear_usuario(correo="luis@empresa.example")
    desde_aqui, desde_otra_ip = Client(REMOTE_ADDR="10.1.1.1"), Client(REMOTE_ADDR="10.2.2.2")
    for _ in range(5):
        _ingresar(desde_aqui, "luis@empresa.example", "mala")
    respuesta = _ingresar(desde_otra_ip, "luis@empresa.example", CONTRASENA)
    assert MENSAJE_GENERICO in respuesta.content.decode()
    assert Usuario.objects.get(pk=otra.pk).bloqueada_hasta is not None


# --- 4. Falla cerrado para los roles que exigen segundo factor --------------------------------


@pytest.fixture(params=ROLES_SENSIBLES)
def rol_sensible(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@scenario(FEATURE, "Falla cerrado para los roles que exigen segundo factor")
def test_falla_cerrado_para_los_roles_que_exigen_segundo_factor(rol_sensible: str) -> None: ...


@given("que tengo un rol que exige segundo factor (Administrador o Auditor)")
def _rol_sensible(crear_usuario: Callable[..., Usuario], rol_sensible: str) -> None:
    crear_usuario(roles=(rol_sensible,))


@pytest.fixture
def sin_segundo_factor() -> Iterator[None]:
    """El puerto del segundo factor sin adaptador: la red de seguridad del falla cerrado (
    conecto el adaptador real; esto lo desconecta mientras dura la prueba)."""
    with Aislamiento():
        yield


@given("el segundo factor todavía no está disponible o no lo he completado")
def _segundo_factor_no_disponible(sin_segundo_factor: None) -> None:
    from identidad.aplicacion.puertos import VerificadorSegundoFactor
    from nucleo.puertos.registro import PuertoSinAdaptador, obtener

    with pytest.raises(PuertoSinAdaptador):
        obtener(VerificadorSegundoFactor)


@when("ingreso mi correo y mi contraseña correctos")
def _ingreso_de_rol_sensible(cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["respuesta"] = _ingresar(cliente, CORREO, CONTRASENA)
    ctx["motivos_esperados"] = {"requiere_segundo_factor"}


@then("no entro a la aplicación")
def _no_entro(cliente: Client, ctx: dict[str, Any]) -> None:
    assert ctx["respuesta"].status_code == 403
    assert "_auth_user_id" not in cliente.session
    inicio = cliente.get("/")
    assert inicio.status_code == 302
    assert inicio["Location"].startswith("/ingresar")


# --- 5. Sesion inactiva -----------------------------------------------------------------------


@scenario(FEATURE, "Sesión inactiva")
def test_sesion_inactiva() -> None: ...


@when("paso 3 horas sin actividad")
def _tres_horas_sin_actividad(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    reloj: RelojAdelantable,
    ctx: dict[str, Any],
) -> None:
    crear_usuario()
    _ingresar(cliente, CORREO, CONTRASENA)
    assert cliente.get("/").status_code == 200
    ctx["reloj"] = reloj


@then("la sesión se cierra y tengo que volver a ingresar")
def _sesion_cerrada(cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["reloj"].adelantar(hours=3, seconds=1)
    respuesta = cliente.get("/")
    assert respuesta.status_code == 302
    assert respuesta["Location"].startswith("/ingresar")


@then(
    "mientras tenga actividad y no se cumpla la duración máxima, la sesión no se cierra por "
    "inactividad"
)
def _con_actividad_no_se_cierra(
    crear_usuario: Callable[..., Usuario], reloj: RelojAdelantable
) -> None:
    activo = Client()
    crear_usuario(correo="luis@empresa.example")
    _ingresar(activo, "luis@empresa.example", CONTRASENA)
    for _ in range(3):  # 3 x 2h59 = casi 9 horas, y nunca 3 horas seguidas sin actividad
        reloj.adelantar(hours=2, minutes=59)
        assert activo.get("/").status_code == 200


# --- 5b. Duracion maxima de la sesion -------------------------------------------------------------


@scenario(FEATURE, "Duración máxima de la sesión")
def test_duracion_maxima_de_la_sesion() -> None: ...


@given("que ingresé hace 12 horas y seguí trabajando sin interrupciones")
def _ingrese_hace_12_horas(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    reloj: RelojAdelantable,
    ctx: dict[str, Any],
) -> None:
    ctx["usuario"] = crear_usuario()
    _ingresar(cliente, CORREO, CONTRASENA)
    # Una peticion cada 2h59 (nunca 3 horas sin actividad) hasta cumplir las 12 horas menos 4 min.
    for _ in range(4):
        reloj.adelantar(hours=2, minutes=59)
        assert cliente.get("/").status_code == 200
    reloj.adelantar(minutes=4)  # 12 horas exactas desde el ingreso
    ctx["reloj"] = reloj


@when("hago una petición")
def _hago_una_peticion(cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["respuesta"] = cliente.get("/")


@then("la sesión se cierra y vuelvo a la pantalla de ingreso")
def _vuelvo_al_ingreso(cliente: Client, ctx: dict[str, Any]) -> None:
    respuesta = ctx["respuesta"]
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar")
    assert "_auth_user_id" not in cliente.session  # la sesion se destruyo
    assert AccionCuenta.objects.filter(
        accion="sesion_cerrada_tope_absoluto", usuario_objetivo_id=ctx["usuario"].id
    ).exists()
    ctx["reloj"].adelantar(minutes=1)
    assert cliente.get("/").status_code == 302  # y no hay forma de seguir con la misma sesion


# --- 6. Contrasena robusta --------------------------------------------------------------------


@scenario(FEATURE, "Contraseña robusta")
def test_contrasena_robusta() -> None: ...


@when("defino mi contraseña")
def _defino_mi_contrasena(
    cliente: Client, crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]
) -> None:
    crear_usuario()
    _ingresar(cliente, CORREO, CONTRASENA)
    ctx["cliente"] = cliente


def _cambiar(cliente: Client, nueva: str) -> Any:
    return cliente.post(
        "/cuenta/contrasena", {"actual": CONTRASENA, "nueva": nueva, "confirmar": nueva}
    )


@then(
    "debe tener al menos 12 caracteres y no puede estar en la lista de contraseñas filtradas "
    "incluida en el sistema"
)
def _politica(ctx: dict[str, Any]) -> None:
    cliente = ctx["cliente"]
    corta = _cambiar(cliente, "abcdefghij1")  # 11 caracteres
    assert corta.status_code == 422
    assert "al menos 12 caracteres" in corta.content.decode()
    filtrada = _cambiar(cliente, "qwerty123456")  # esta en la lista empaquetada
    assert filtrada.status_code == 422
    assert "listas de contraseñas filtradas" in filtrada.content.decode()
    assert _cambiar(cliente, "abcdefghij12-Luna").status_code == 302  # 12+ y no filtrada


@then("la validación no envía la contraseña a ningún servicio externo")
def _sin_red(monkeypatch: pytest.MonkeyPatch, ctx: dict[str, Any]) -> None:
    llamadas: list[object] = []

    def _prohibido(*args: object, **kwargs: object) -> None:
        llamadas.append(args)
        raise AssertionError("la validación abrió una conexión de red")

    monkeypatch.setattr(socket.socket, "connect", _prohibido)
    monkeypatch.setattr(socket, "create_connection", _prohibido)
    respuesta = ctx["cliente"].post(
        "/cuenta/contrasena",
        {"actual": "abcdefghij12-Luna", "nueva": "1q2w3e4r5t6y", "confirmar": "1q2w3e4r5t6y"},
    )
    assert respuesta.status_code in (302, 422)
    assert llamadas == []


# --- 7. Contrasena temporal en el primer ingreso ----------------------------------------------


@scenario(FEATURE, "Contraseña temporal en el primer ingreso")
def test_contrasena_temporal_en_el_primer_ingreso() -> None: ...


@given("que el administrador me dio una contraseña temporal")
def _con_temporal(crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]) -> None:
    ctx["usuario"] = crear_usuario(debe_cambiar_contrasena=True)


@when("ingreso con ella")
def _ingreso_con_temporal(cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["respuesta"] = _ingresar(cliente, CORREO, CONTRASENA)


@then("lo único que puedo hacer es definir una contraseña nueva")
def _solo_definir(cliente: Client, ctx: dict[str, Any]) -> None:
    assert ctx["respuesta"]["Location"] == "/ingresar/contrasena"
    assert "_auth_user_id" not in cliente.session  # sin sesion completa
    for ruta in ("/", "/cuenta/contrasena"):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 302
        assert respuesta["Location"] == "/ingresar/contrasena"
    assert cliente.get("/ingresar/contrasena").status_code == 200
    # Una contrasena que no cumple la politica no la reemplaza.
    corta = cliente.post("/ingresar/contrasena", {"nueva": "corta", "confirmar": "corta"})
    assert corta.status_code == 422
    nueva = "frase-nueva-larga-42"
    definida = cliente.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    assert (definida.status_code, definida["Location"]) == (302, "/")
    assert cliente.get("/").status_code == 200
    ctx["nueva"] = nueva


@then("la contraseña temporal deja de servir")
def _temporal_ya_no_sirve(ctx: dict[str, Any]) -> None:
    assert MENSAJE_GENERICO in _ingresar(Client(), CORREO, CONTRASENA).content.decode()
    despues = _ingresar(Client(), CORREO, ctx["nueva"])
    assert (despues.status_code, despues["Location"]) == (302, "/")  # y ya no pide cambiarla
    usuario = Usuario.objects.get(pk=ctx["usuario"].pk)
    assert not usuario.debe_cambiar_contrasena
    assert not check_password(CONTRASENA, usuario.password)


# --- 8. Cambiar mi propia contrasena ----------------------------------------------------------


@scenario(FEATURE, "Cambiar mi propia contraseña")
def test_cambiar_mi_propia_contrasena() -> None: ...


@given("que inicié sesión")
def _inicie_sesion(
    cliente: Client, crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]
) -> None:
    ctx["usuario"] = crear_usuario()
    ctx["otra_sesion"] = Client()  # mi sesion en otro dispositivo
    for navegador in (cliente, ctx["otra_sesion"]):
        assert _ingresar(navegador, CORREO, CONTRASENA).status_code == 302
        assert navegador.get("/").status_code == 200


@when("proporciono mi contraseña actual y una nueva que cumple las reglas")
def _cambio(cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["nueva"] = "otra-frase-larga-77Sol"
    ctx["respuesta"] = cliente.post(
        "/cuenta/contrasena",
        {"actual": CONTRASENA, "nueva": ctx["nueva"], "confirmar": ctx["nueva"]},
    )


@then("mi contraseña cambia, mis demás sesiones se cierran y el cambio queda registrado")
def _cambio_completo(cliente: Client, ctx: dict[str, Any]) -> None:
    assert ctx["respuesta"].status_code == 302
    usuario = Usuario.objects.get(pk=ctx["usuario"].pk)
    assert check_password(ctx["nueva"], usuario.password)
    assert not check_password(CONTRASENA, usuario.password)
    assert cliente.get("/").status_code == 200  # la sesion actual se conserva
    cerrada = ctx["otra_sesion"].get("/")  # las demas se cierran
    assert cerrada.status_code == 302
    assert cerrada["Location"].startswith("/ingresar")
    accion = AccionCuenta.objects.get(accion="cambio_de_contrasena")
    assert (accion.usuario_objetivo_id, accion.hecha_por_id) == (usuario.id, usuario.id)
