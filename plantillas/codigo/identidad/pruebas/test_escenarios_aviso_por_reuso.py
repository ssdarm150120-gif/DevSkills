"""Enterarme si alguien intento reusar mi codigo: sus 4 escenarios Gherkin (pytest-bdd).

Corren contra la aplicacion completa (cliente HTTP de Django, PostgreSQL y el adaptador TOTP real).
Quien intenta reusar el codigo es OTRA persona, en otro navegador y desde otra IP, con la
contrasena robada: el aviso lo ve el dueno en su siguiente ingreso completo.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.test import Client
from pytest_bdd import given, scenario, then, when

from identidad.adaptadores.salida.modelos import IntentoIngreso, Usuario
from identidad.adaptadores.salida.segundo_factor import codigo_del_paso
from identidad.dominio.segundo_factor import paso_de
from identidad.pruebas.conftest import CONTRASENA, RelojAdelantable
from nucleo.adaptadores.modelos import EventoOutbox

pytestmark = pytest.mark.django_db

FEATURE = "identidad/pruebas/aviso_por_reuso.feature"
CORREO = "ana@empresa.example"
IP_DEL_ATACANTE = "203.0.113.77"
# Las 12:00:10 UTC del 9 de octubre de 2026 son las 06:00:10 en la Ciudad de Mexico (UTC-6).
INSTANTE = datetime(2026, 10, 9, 12, 0, 10, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _zona_de_la_ciudad_de_mexico(settings: Any) -> None:
    """Las fechas esperadas de estas pruebas estan en la zona de la Ciudad de Mexico."""
    settings.APP_ZONA_HORARIA = "America/Mexico_City"


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


def _ingresar_con_codigo(cliente: Client, secreto: bytes, reloj: RelojAdelantable) -> Any:
    """Contrasena y codigo vigente: el ingreso completo. Devuelve la respuesta del codigo."""
    paso_uno = cliente.post("/ingresar", {"correo": CORREO, "contrasena": CONTRASENA})
    assert paso_uno["Location"] == "/ingresar/codigo"
    return cliente.post(
        "/ingresar/codigo", {"codigo": codigo_del_paso(secreto, paso_de(reloj.ahora()))}
    )


def _intento_ajeno(codigo_usado: str) -> Any:
    """Otra persona, con la contrasena robada, intenta con un codigo que ya se uso."""
    otro = Client(REMOTE_ADDR=IP_DEL_ATACANTE)
    paso_uno = otro.post("/ingresar", {"correo": CORREO, "contrasena": CONTRASENA})
    assert paso_uno["Location"] == "/ingresar/codigo"
    return otro.post("/ingresar/codigo", {"codigo": codigo_usado})


def _preparar_cuenta_con_un_codigo_reusado(
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    reloj: RelojAdelantable,
    ctx: dict[str, Any],
    intentos: int = 1,
) -> None:
    """El dueno ingresa con su codigo; despues alguien intenta (una o varias veces) con el mismo."""
    reloj.situar_en(INSTANTE)
    ctx["usuario"] = crear_usuario(roles=("auditor",))
    ctx["secreto"] = registrar_segundo_factor(ctx["usuario"], ahora=INSTANTE)
    usado = codigo_del_paso(ctx["secreto"], paso_de(reloj.ahora()))
    assert _ingresar_con_codigo(Client(), ctx["secreto"], reloj)["Location"] == "/"
    ctx["usado"] = usado
    ctx["momentos"] = []
    for _ in range(intentos):
        reloj.adelantar(seconds=5)
        ctx["momentos"].append(reloj.ahora())
        assert _intento_ajeno(usado).status_code == 422


def _volver_a_ingresar(cliente: Client, ctx: dict[str, Any], reloj: RelojAdelantable) -> None:
    reloj.adelantar(minutes=2)  # un paso de codigo nuevo, posterior al ya usado
    ctx["ingreso"] = _ingresar_con_codigo(cliente, ctx["secreto"], reloj)
    assert ctx["ingreso"]["Location"] == "/"


# --- 1. Aviso en el siguiente ingreso ----------------------------------------------------------


@scenario(FEATURE, "Aviso en el siguiente ingreso")
def test_aviso_en_el_siguiente_ingreso() -> None: ...


@given(
    "que alguien intentó entrar a mi cuenta con un código del segundo factor que ya se había usado"
)
def _alguien_intento_reusar(
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    reloj: RelojAdelantable,
    ctx: dict[str, Any],
) -> None:
    _preparar_cuenta_con_un_codigo_reusado(
        crear_usuario, registrar_segundo_factor, reloj, ctx, intentos=2
    )


@when("ingreso y completo mi segundo factor")
def _ingreso_y_completo(cliente: Client, reloj: RelojAdelantable, ctx: dict[str, Any]) -> None:
    _volver_a_ingresar(cliente, ctx, reloj)
    ctx["pagina"] = cliente.get("/")


@then("veo un aviso con la fecha y hora del intento")
def _veo_fecha_y_hora(ctx: dict[str, Any]) -> None:
    pagina = ctx["pagina"]
    assert pagina.status_code == 200
    contenido = pagina.content.decode()
    assert 'id="aviso-reuso"' in contenido
    # El intento MAS RECIENTE (el segundo, a las 12:00:20 UTC), en la hora de Mexico (UTC-6).
    # (el reloj sigue corriendo: los segundos exactos cambian en fracciones, no en el segundo)
    assert ctx["momentos"][-1].replace(microsecond=0) == datetime(
        2026, 10, 9, 12, 0, 20, tzinfo=UTC
    )
    assert "09/10/2026 06:00:20 CST (America/Mexico_City)" in contenido
    assert "06:00:15" not in contenido  # no el primero
    # Nada mas del intento: ni la IP de quien lo hizo ni su huella.
    assert IP_DEL_ATACANTE not in contenido
    assert "huella" not in contenido.lower()


@then("el aviso me indica que cambie mi contraseña y avise al administrador si no fui yo")
def _me_indica_que_actue(ctx: dict[str, Any]) -> None:
    contenido = ctx["pagina"].content.decode()
    assert "si no fuiste tú, cambia tu contraseña y avisa al administrador" in contenido
    assert 'href="/cuenta/contrasena"' in contenido


# --- 2. El aviso se muestra una sola vez -------------------------------------------------------


@scenario(FEATURE, "El aviso se muestra una sola vez")
def test_el_aviso_se_muestra_una_sola_vez() -> None: ...


@given("que ya vi el aviso de un intento de reuso")
def _ya_vi_el_aviso(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    reloj: RelojAdelantable,
    ctx: dict[str, Any],
) -> None:
    _preparar_cuenta_con_un_codigo_reusado(crear_usuario, registrar_segundo_factor, reloj, ctx)
    _volver_a_ingresar(cliente, ctx, reloj)
    assert 'id="aviso-reuso"' in cliente.get("/").content.decode()
    cliente.post("/salir")


@when("vuelvo a ingresar")
def _vuelvo_a_ingresar(cliente: Client, reloj: RelojAdelantable, ctx: dict[str, Any]) -> None:
    _volver_a_ingresar(cliente, ctx, reloj)
    ctx["pagina"] = cliente.get("/")


@then("no veo el aviso otra vez")
def _no_veo_el_aviso(cliente: Client, ctx: dict[str, Any]) -> None:
    assert ctx["pagina"].status_code == 200
    assert 'id="aviso-reuso"' not in ctx["pagina"].content.decode()
    # Ni recargando el inicio.
    assert "Alguien intentó" not in cliente.get("/").content.decode()


# --- 3. Sin intentos de reuso no hay aviso -----------------------------------------------------


@scenario(FEATURE, "Sin intentos de reuso no hay aviso")
def test_sin_intentos_de_reuso_no_hay_aviso() -> None: ...


@given("que nadie intentó reusar un código mío")
def _nadie_intento(
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    ctx: dict[str, Any],
) -> None:
    ctx["usuario"] = crear_usuario(roles=("auditor",))
    ctx["secreto"] = registrar_segundo_factor(ctx["usuario"])
    # Hay otros intentos registrados (la contrasena), pero ninguno de reuso.
    Client().post("/ingresar", {"correo": CORREO, "contrasena": CONTRASENA})
    assert not IntentoIngreso.objects.filter(motivo="codigo_repetido").exists()


@when("ingreso")
def _ingreso(cliente: Client, reloj: RelojAdelantable, ctx: dict[str, Any]) -> None:
    ctx["ingreso"] = _ingresar_con_codigo(cliente, ctx["secreto"], reloj)
    assert ctx["ingreso"]["Location"] == "/"
    ctx["pagina"] = cliente.get("/")


@then("no veo ningún aviso")
def _no_veo_ningun_aviso(ctx: dict[str, Any]) -> None:
    assert ctx["pagina"].status_code == 200
    contenido = ctx["pagina"].content.decode()
    assert 'id="aviso-reuso"' not in contenido
    assert "Alguien intentó" not in contenido
    assert 'role="alert"' not in contenido


# --- 4. El intento queda en la bitacora --------------------------------------------------------


@scenario(FEATURE, "El intento queda en la bitácora")
def test_el_intento_queda_en_la_bitacora() -> None: ...


@when("alguien intenta entrar con un código del segundo factor ya usado")
def _alguien_intenta_con_un_codigo_usado(
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    reloj: RelojAdelantable,
    ctx: dict[str, Any],
) -> None:
    reloj.situar_en(INSTANTE)
    ctx["usuario"] = crear_usuario(roles=("auditor",))
    ctx["secreto"] = registrar_segundo_factor(ctx["usuario"], ahora=INSTANTE)
    ctx["usado"] = codigo_del_paso(ctx["secreto"], paso_de(reloj.ahora()))
    assert _ingresar_con_codigo(Client(), ctx["secreto"], reloj)["Location"] == "/"
    reloj.adelantar(seconds=5)
    ctx["momento"] = reloj.ahora()
    ctx["respuesta"] = _intento_ajeno(ctx["usado"])


@then("el sistema lo rechaza")
def _el_sistema_lo_rechaza(ctx: dict[str, Any]) -> None:
    assert ctx["respuesta"].status_code == 422
    assert "Location" not in ctx["respuesta"]


@then("el intento queda en la bitácora de auditoría, visible para el administrador")
def _queda_en_la_bitacora(ctx: dict[str, Any]) -> None:
    # El registro de intentos es la bitacora de mientras no llegue su pantalla:
    # el intento queda con su motivo real, su IP y su momento, para el Administrador...
    intento = IntentoIngreso.objects.get(usuario_id=ctx["usuario"].id, motivo="codigo_repetido")
    assert (intento.factor, intento.resultado) == ("codigo", "fallido")
    assert intento.ip == IP_DEL_ATACANTE
    # (el reloj de la prueba sigue corriendo: el momento es el del intento, con unas decimas)
    assert timedelta(0) <= intento.ocurrido_en - ctx["momento"] < timedelta(seconds=5)
    # ...y llega al bus como `CodigoSegundoFactorRepetido`, SIN el codigo.
    evento = EventoOutbox.objects.get(nombre="CodigoSegundoFactorRepetido")
    assert evento.payload == {
        "usuario_id": str(ctx["usuario"].id),
        "intento_id": intento.pk,
        "ocurrido_en": intento.ocurrido_en.isoformat(),
    }
    assert ctx["usado"] not in str(evento.payload)
    # El rechazo cuenta como fallo del codigo: el aviso no cambio esa regla.
    assert Usuario.objects.get(pk=ctx["usuario"].pk).fallos_codigo == 1
