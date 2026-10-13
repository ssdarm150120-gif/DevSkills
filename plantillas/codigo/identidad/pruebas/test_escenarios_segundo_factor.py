"""Usar el segundo factor para los roles sensibles: sus 7 escenarios Gherkin (pytest-bdd).

Corren contra la aplicacion completa (cliente HTTP de Django, PostgreSQL y el adaptador TOTP real
conectado al arrancar). Los codigos se calculan como lo hace una aplicacion de codigos: con el
secreto y la hora, a partir de lo que la pantalla le muestra al usuario.
"""

import base64
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.test import Client
from pytest_bdd import given, parsers, scenario, then, when

from identidad.adaptadores.entrada import composicion
from identidad.adaptadores.entrada.codigo_qr import trazo_del_qr
from identidad.adaptadores.salida.modelos import (
    AccionCuenta,
    IntentoIngreso,
    Rol,
    SegundoFactor,
    Usuario,
    UsuarioRol,
)
from identidad.adaptadores.salida.segundo_factor import codigo_del_paso, uri_de_enrolamiento
from identidad.dominio.segundo_factor import paso_de
from identidad.pruebas.conftest import CONTRASENA, RelojAdelantable
from nucleo.actor import Actor

pytestmark = pytest.mark.django_db

FEATURE = "identidad/pruebas/segundo_factor.feature"
CORREO = "ana@empresa.example"
ROLES_SENSIBLES = ["administrador", "auditor", "auditor", "auditor", "auditor"]
MENSAJE_GENERICO = "Correo o contraseña incorrectos"

# Secreto elegido (se busco una vez) para que a las 12:00:10 UTC del 9 de octubre de 2026 su codigo
# sea exactamente 123456: el escenario "Un codigo no se acepta dos veces" nombra ese codigo.
SECRETO_DEL_123456 = bytes.fromhex("808a236ab0b1784de1e71df18480051d72446a22")
INSTANTE_DEL_123456 = datetime(2026, 10, 9, 12, 0, 10, tzinfo=UTC)

Callable_registrar = Callable[..., bytes]


@pytest.fixture
def ctx() -> dict[str, Any]:
    """Estado compartido entre los pasos de un escenario."""
    return {}


def _ingresar(cliente: Client, correo: str = CORREO, contrasena: str = CONTRASENA) -> Any:
    return cliente.post("/ingresar", {"correo": correo, "contrasena": contrasena})


def _codigo(cliente: Client, codigo: str, ruta: str = "/ingresar/codigo") -> Any:
    return cliente.post(ruta, {"codigo": codigo})


def _codigo_vigente(secreto: bytes, reloj: RelojAdelantable | None = None) -> str:
    ahora = reloj.ahora() if reloj else datetime.now(UTC)
    return codigo_del_paso(secreto, paso_de(ahora))


def _clave_en(pagina: str) -> str:
    """La clave que la pantalla de enrolamiento le muestra al usuario."""
    coincidencia = re.search(r'<code id="clave">([^<]+)</code>', pagina)
    assert coincidencia, "la pantalla de enrolamiento no muestra la clave"
    return coincidencia.group(1)


def _secreto_de(clave: str) -> bytes:
    sin_espacios = clave.replace(" ", "")
    return base64.b32decode(sin_espacios + "=" * (-len(sin_espacios) % 8))


def _sin_sesion(cliente: Client) -> None:
    assert "_auth_user_id" not in cliente.session
    inicio = cliente.get("/")
    assert inicio.status_code == 302
    assert "_auth_user_id" not in cliente.session


# --- 1. Segundo factor para roles sensibles ---------------------------------------------------


@pytest.fixture(params=ROLES_SENSIBLES)
def rol_sensible(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@scenario(FEATURE, "Segundo factor para roles sensibles")
def test_segundo_factor_para_roles_sensibles(rol_sensible: str) -> None: ...


@given("que tengo un rol que exige segundo factor (Administrador o Auditor)")
def _tengo_un_rol_sensible(
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable_registrar,
    rol_sensible: str,
    ctx: dict[str, Any],
) -> None:
    ctx["usuario"] = crear_usuario(roles=(rol_sensible,))
    ctx["secreto"] = registrar_segundo_factor(ctx["usuario"])  # ya tiene su aplicacion


@when("ingreso mi contraseña correcta")
def _ingreso_mi_contrasena(cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["respuesta"] = _ingresar(cliente)


@then("el sistema me pide un código de un segundo factor (aplicación autenticadora)")
def _me_pide_un_codigo(cliente: Client, ctx: dict[str, Any]) -> None:
    assert (ctx["respuesta"].status_code, ctx["respuesta"]["Location"]) == (
        302,
        "/ingresar/codigo",
    )
    pagina = cliente.get("/ingresar/codigo")
    assert pagina.status_code == 200
    contenido = pagina.content.decode()
    assert 'name="codigo"' in contenido
    assert "aplicación de códigos" in contenido
    # Aun con la contrasena correcta, el ingreso quedo registrado como correcto del factor 1.
    assert IntentoIngreso.objects.filter(
        usuario_id=ctx["usuario"].id, factor="contrasena", resultado="correcto"
    ).exists()


@then("sin ese código no se abre la sesión")
def _sin_ese_codigo_no_hay_sesion(cliente: Client) -> None:
    _sin_sesion(cliente)
    # Ni dejando el codigo vacio ni con uno que no es: la sesion sigue cerrada.
    for codigo in ("", "abcdef", "000000"):
        assert _codigo(cliente, codigo).status_code == 422
        _sin_sesion(cliente)
    # Y ninguna otra ruta de la aplicacion se abre mientras falta el codigo.
    for ruta in ("/", "/cuenta/contrasena", "/ingresar/enrolar", "/ingresar/contrasena"):
        respuesta = cliente.get(ruta)
        assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar/codigo")


# --- 2. Enrolamiento en el primer ingreso ------------------------------------------------------


@scenario(FEATURE, "Enrolamiento en el primer ingreso")
def test_enrolamiento_en_el_primer_ingreso() -> None: ...


@given("que tengo un rol que exige segundo factor y todavía no lo he registrado")
def _rol_sin_segundo_factor(crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]) -> None:
    ctx["usuario"] = crear_usuario(roles=("auditor",))
    assert not SegundoFactor.objects.filter(usuario=ctx["usuario"]).exists()


@then("el sistema me muestra un código QR y una clave para registrar mi aplicación de códigos")
def _me_muestra_qr_y_clave(cliente: Client, ctx: dict[str, Any]) -> None:
    assert (ctx["respuesta"].status_code, ctx["respuesta"]["Location"]) == (
        302,
        "/ingresar/enrolar",
    )
    pagina = cliente.get("/ingresar/enrolar")
    assert pagina.status_code == 200
    contenido = pagina.content.decode()
    ctx["clave"] = _clave_en(contenido)
    ctx["secreto"] = _secreto_de(ctx["clave"])
    assert len(ctx["secreto"]) == 20
    # El QR es un <svg> del servidor, y su trazo es el del URI que lleva ESA misma clave.
    uri = uri_de_enrolamiento(ctx["secreto"], CORREO)
    esperado = trazo_del_qr(uri)
    assert f'<path d="{esperado.trazo}"' in contenido
    assert f'viewBox="0 0 {esperado.lado} {esperado.lado}"' in contenido
    # Sin JavaScript, sin estilos en linea y sin imagen `data:`: la CSP estricta no se relaja.
    for prohibido in ("<script", "style=", "<style", "data:", "onload=", "<img"):
        assert prohibido not in contenido, prohibido
    # El secreto no se guarda en claro en la sesion ni en la base.
    assert ctx["clave"].replace(" ", "") not in str(dict(cliente.session))
    fila = SegundoFactor.objects.get(usuario=ctx["usuario"])
    assert ctx["clave"].replace(" ", "") not in fila.secreto_cifrado
    assert fila.confirmado_en is None  # todavia no esta confirmado


@then("el enrolamiento termina cuando capturo un código válido")
def _el_enrolamiento_termina(cliente: Client, ctx: dict[str, Any]) -> None:
    # Un codigo que no es no lo termina...
    incorrecto = _codigo(cliente, "000000", "/ingresar/enrolar")
    assert incorrecto.status_code == 422
    assert not SegundoFactor.objects.get(usuario=ctx["usuario"]).confirmado_en
    _sin_sesion(cliente)
    # ...y con el codigo valido de la aplicacion, si: entra y el segundo factor queda confirmado.
    valido = _codigo(cliente, _codigo_vigente(ctx["secreto"]), "/ingresar/enrolar")
    assert (valido.status_code, valido["Location"]) == (302, "/")
    assert cliente.get("/").status_code == 200
    fila = SegundoFactor.objects.get(usuario=ctx["usuario"])
    assert fila.confirmado_en is not None
    assert fila.ultimo_paso_aceptado is not None


@then("queda registrado")
def _queda_registrado(ctx: dict[str, Any]) -> None:
    accion = AccionCuenta.objects.get(accion="enrolamiento_segundo_factor")
    assert (accion.usuario_objetivo_id, accion.hecha_por_id) == (
        ctx["usuario"].id,
        ctx["usuario"].id,
    )
    intentos = IntentoIngreso.objects.filter(usuario_id=ctx["usuario"].id, factor="codigo")
    assert set(intentos.values_list("resultado", "motivo")) == {
        ("fallido", "codigo_invalido"),
        ("correcto", "correcto"),
    }
    # Nada de lo registrado lleva el secreto ni la clave.
    todo = str(list(AccionCuenta.objects.values())) + str(list(IntentoIngreso.objects.values()))
    assert ctx["clave"].replace(" ", "") not in todo


# --- 3. Codigo correcto ------------------------------------------------------------------------


@scenario(FEATURE, "Código correcto")
def test_codigo_correcto() -> None: ...


@given("que ya registré mi aplicación de códigos")
def _ya_registre_mi_aplicacion(
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable_registrar,
    ctx: dict[str, Any],
) -> None:
    ctx["usuario"] = crear_usuario(roles=("auditor", "usuario"))
    ctx["secreto"] = registrar_segundo_factor(ctx["usuario"])


@when("ingreso mi contraseña y el código vigente")
def _ingreso_contrasena_y_codigo(cliente: Client, ctx: dict[str, Any]) -> None:
    assert _ingresar(cliente)["Location"] == "/ingresar/codigo"
    ctx["respuesta"] = _codigo(cliente, _codigo_vigente(ctx["secreto"]))


@then("entro a la aplicación con los permisos de mis roles")
def _entro_con_mis_permisos(cliente: Client, ctx: dict[str, Any]) -> None:
    assert (ctx["respuesta"].status_code, ctx["respuesta"]["Location"]) == (302, "/")
    inicio = cliente.get("/")
    assert inicio.status_code == 200
    actor: Actor = inicio.wsgi_request.actor  # type: ignore[attr-defined]
    assert actor.roles == frozenset({"auditor", "usuario"})
    assert actor.id == str(ctx["usuario"].id)
    assert "iniciada_en" in cliente.session  # el tope de 12 horas cuenta desde ahora
    # El codigo se acepto UNA vez y quedo el registro del ingreso completo.
    assert IntentoIngreso.objects.filter(
        usuario_id=ctx["usuario"].id, factor="codigo", resultado="correcto"
    ).exists()


# --- 4. Limite de intentos del codigo ----------------------------------------------------------


@scenario(FEATURE, "Límite de intentos del código")
def test_limite_de_intentos_del_codigo() -> None: ...


@when("capturo 5 códigos incorrectos seguidos")
def _cinco_codigos_incorrectos(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable_registrar,
    reloj: RelojAdelantable,
    ctx: dict[str, Any],
) -> None:
    ctx["usuario"] = crear_usuario(roles=("administrador",))
    ctx["secreto"] = registrar_segundo_factor(ctx["usuario"])
    assert _ingresar(cliente)["Location"] == "/ingresar/codigo"
    bueno = _codigo_vigente(ctx["secreto"], reloj)
    malo = "000000" if bueno != "000000" else "000001"
    respuestas = [_codigo(cliente, malo) for _ in range(5)]
    ctx["respuestas"] = respuestas


@then("la cuenta se bloquea 15 minutos y los intentos quedan registrados")
def _bloqueada_y_registrada(cliente: Client, reloj: RelojAdelantable, ctx: dict[str, Any]) -> None:
    # Los cuatro primeros dejan reintentar; el quinto bloquea.
    assert [r.status_code for r in ctx["respuestas"]] == [422, 422, 422, 422, 403]
    assert "bloqueada 15 minutos" in ctx["respuestas"][-1].content.decode()
    usuario = Usuario.objects.get(pk=ctx["usuario"].pk)
    restante = usuario.bloqueada_hasta - reloj.ahora()  # type: ignore[operator]
    assert timedelta(minutes=14, seconds=50) < restante <= timedelta(minutes=15)
    # Contadores separados: el de la contrasena no se movio.
    assert usuario.fallos_contrasena == 0
    # Los cinco intentos y el bloqueo quedaron registrados.
    assert (
        IntentoIngreso.objects.filter(
            usuario_id=usuario.id, factor="codigo", motivo="codigo_invalido"
        ).count()
        == 5
    )
    assert (
        AccionCuenta.objects.filter(accion="bloqueo", usuario_objetivo_id=usuario.id).count() == 1
    )
    _sin_sesion(cliente)
    # Bloqueada: ni la contrasena y el codigo correctos entran, y el mensaje no cambia.
    otro = Client()
    respuesta = _ingresar(otro)
    assert MENSAJE_GENERICO in respuesta.content.decode()
    assert IntentoIngreso.objects.filter(motivo="cuenta_bloqueada").count() == 1
    # Cumplidos los 15 minutos vuelve a entrar con su contrasena y su codigo.
    reloj.adelantar(minutes=15, seconds=1)
    assert _ingresar(otro)["Location"] == "/ingresar/codigo"
    assert _codigo(otro, _codigo_vigente(ctx["secreto"], reloj)).status_code == 302
    assert otro.get("/").status_code == 200


# --- 5. Un codigo no se acepta dos veces -------------------------------------------------------


@scenario(FEATURE, "Un código no se acepta dos veces")
def test_un_codigo_no_se_acepta_dos_veces() -> None: ...


@given(parsers.parse('que ya ingresé con el código "{codigo}"'))
def _ya_ingrese_con_el_codigo(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable_registrar,
    reloj: RelojAdelantable,
    codigo: str,
    ctx: dict[str, Any],
) -> None:
    reloj.situar_en(INSTANTE_DEL_123456)
    ctx["usuario"] = crear_usuario(roles=("auditor",))
    registrar_segundo_factor(ctx["usuario"], SECRETO_DEL_123456, INSTANTE_DEL_123456)
    ctx["codigo"] = codigo
    assert _codigo_vigente(SECRETO_DEL_123456, reloj) == codigo == "123456"
    assert _ingresar(cliente)["Location"] == "/ingresar/codigo"
    assert _codigo(cliente, codigo)["Location"] == "/"
    assert cliente.get("/").status_code == 200


@when("alguien intenta ingresar con ese mismo código dentro de su vigencia")
def _alguien_repite_el_codigo(reloj: RelojAdelantable, ctx: dict[str, Any]) -> None:
    ctx["intentos"] = []
    # A los 2, 20 y 45 s del primer ingreso (12:00:12, 12:00:30 y 12:00:55): el codigo es del paso
    # de las 12:00:00 y el paso siguiente todavia lo tiene en su ventana.
    for segundos in (2, 18, 25):
        reloj.adelantar(seconds=segundos)
        otro = Client()  # otra persona, otro navegador, con la contrasena robada
        assert _ingresar(otro)["Location"] == "/ingresar/codigo"
        ctx["intentos"].append((otro, _codigo(otro, ctx["codigo"])))


@then("el sistema lo rechaza")
def _el_sistema_lo_rechaza(ctx: dict[str, Any]) -> None:
    for otro, respuesta in ctx["intentos"]:
        assert respuesta.status_code == 422
        assert "_auth_user_id" not in otro.session
        assert otro.get("/").status_code == 302
    repetidos = IntentoIngreso.objects.filter(
        usuario_id=ctx["usuario"].id, factor="codigo", motivo="codigo_repetido"
    )
    assert repetidos.count() == 3
    # Y el rechazo cuenta como fallo del codigo.
    assert Usuario.objects.get(pk=ctx["usuario"].pk).fallos_codigo == 3


# --- 6. Rol sensible asignado despues ----------------------------------------------------------


@scenario(FEATURE, "Rol sensible asignado después")
def test_rol_sensible_asignado_despues() -> None: ...


@given(parsers.parse('que el administrador me asignó el rol "{rol}"'))
def _me_asignaron_un_rol_sensible(
    crear_usuario: Callable[..., Usuario], rol: str, ctx: dict[str, Any]
) -> None:
    usuario = crear_usuario(roles=("usuario",))
    previo = Client()
    assert _ingresar(previo)["Location"] == "/"  # antes entraba solo con la contrasena
    UsuarioRol.objects.create(
        usuario=usuario,
        rol=Rol.objects.get(codigo=rol.lower()),
        asignado_en=datetime.now(UTC),
    )
    ctx["usuario"] = usuario


@when("vuelvo a ingresar")
def _vuelvo_a_ingresar(cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["respuesta"] = _ingresar(cliente)


@then("tengo que enrolar mi segundo factor antes de entrar")
def _tengo_que_enrolar(cliente: Client, ctx: dict[str, Any]) -> None:
    assert (ctx["respuesta"].status_code, ctx["respuesta"]["Location"]) == (
        302,
        "/ingresar/enrolar",
    )
    _sin_sesion(cliente)
    secreto = _secreto_de(_clave_en(cliente.get("/ingresar/enrolar").content.decode()))
    # Solo entra al confirmar con un codigo valido.
    assert _codigo(cliente, _codigo_vigente(secreto), "/ingresar/enrolar")["Location"] == "/"
    assert cliente.get("/").status_code == 200


# --- 7. Reinicio por el administrador ----------------------------------------------------------


@scenario(FEATURE, "Reinicio por el administrador")
def test_reinicio_por_el_administrador() -> None: ...


@given("que el administrador reinició mi segundo factor porque perdí mi dispositivo")
def _el_administrador_reinicio_mi_segundo_factor(
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable_registrar,
    ctx: dict[str, Any],
) -> None:
    usuario = crear_usuario(roles=("auditor",))
    ctx["secreto_anterior"] = registrar_segundo_factor(usuario)
    ctx["usuario"] = usuario
    sesion_abierta = Client()  # su sesion en el dispositivo perdido
    assert _ingresar(sesion_abierta)["Location"] == "/ingresar/codigo"
    assert _codigo(sesion_abierta, _codigo_vigente(ctx["secreto_anterior"]))["Location"] == "/"
    assert sesion_abierta.get("/").status_code == 200
    ctx["sesion_abierta"] = sesion_abierta
    # La pantalla de administracion es de: aqui se ejecuta el caso de uso, sin interfaz.
    otro_admin = crear_usuario(correo="root@empresa.example", roles=("administrador",))
    actor = Actor.de(str(otro_admin.id), ["administrador"])
    assert composicion.reiniciar_segundo_factor()(actor, str(usuario.id)) is True


@then("mi registro anterior ya no sirve y tengo que enrolarme de nuevo")
def _mi_registro_anterior_ya_no_sirve(cliente: Client, ctx: dict[str, Any]) -> None:
    assert (ctx["respuesta"].status_code, ctx["respuesta"]["Location"]) == (
        302,
        "/ingresar/enrolar",
    )
    assert not SegundoFactor.objects.filter(usuario=ctx["usuario"]).exists() or not (
        SegundoFactor.objects.get(usuario=ctx["usuario"]).confirmado_en
    )
    # El codigo de su aplicacion anterior ya no sirve para enrolarse...
    viejo = _codigo(cliente, _codigo_vigente(ctx["secreto_anterior"]), "/ingresar/enrolar")
    assert viejo.status_code == 422
    _sin_sesion(cliente)
    # ...ni su sesion abierta en el dispositivo perdido (el sello cambio).
    assert ctx["sesion_abierta"].get("/").status_code == 302
    # Se enrola con un secreto NUEVO.
    nuevo = _secreto_de(_clave_en(cliente.get("/ingresar/enrolar").content.decode()))
    assert nuevo != ctx["secreto_anterior"]
    assert _codigo(cliente, _codigo_vigente(nuevo), "/ingresar/enrolar")["Location"] == "/"
    assert AccionCuenta.objects.filter(
        accion="reinicio_segundo_factor", usuario_objetivo_id=ctx["usuario"].id
    ).exists()
