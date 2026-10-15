"""HU de gestion de usuarios y roles: sus escenarios Gherkin (pytest-bdd).

Corren contra la aplicacion completa: el Administrador usa las pantallas por HTTP (sesion, CSRF,
casos de uso, PostgreSQL y adaptadores conectados al arrancar). Lo que pertenece a modulos que aun
no existen se prueba hasta el limite de `identidad` y se dice en cada paso.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.test import Client
from pytest_bdd import given, parsers, scenario, then, when

from identidad.adaptadores.entrada import composicion
from identidad.adaptadores.salida.modelos import AccionCuenta, SegundoFactor, Usuario
from identidad.aplicacion.errores import ConflictoDeUsuario
from identidad.pruebas.conftest import CONTRASENA
from identidad.pruebas.conftest import entrar as _entrar
from nucleo.actor import Actor
from nucleo.permisos import DESCRIPCIONES, Capacidad

pytestmark = pytest.mark.django_db

FEATURE = "identidad/pruebas/gestion_de_usuarios.feature"
CODIGOS = {
    "Administrador": "administrador",
    "Auditor": "auditor",
    "Usuario": "usuario",
}


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


def _alta(
    admin: Client,
    correo: str = "ana@empresa.example",
    nombre: str = "Ana",
    roles: tuple[str, ...] = ("usuario",),
) -> Any:
    return admin.post(
        "/admin/usuarios/nuevo",
        {
            "correo": correo,
            "nombre": nombre,
            "roles": list(roles),
        },
    )


def _temporal(respuesta: Any) -> str:
    coincidencia = re.search(
        r'<code id="contrasena-temporal">([^<]+)</code>', respuesta.content.decode()
    )
    assert coincidencia, "la pantalla no muestra la contraseña temporal"
    return coincidencia.group(1)


def _accion(nombre: str, objetivo: Usuario) -> AccionCuenta:
    return AccionCuenta.objects.filter(accion=nombre, usuario_objetivo_id=objetivo.id).latest("id")


def _por_correo(correo: str) -> Usuario:
    return Usuario.objects.get(correo=correo)


def _ingresar(correo: str, contrasena: str) -> Any:
    return Client().post("/ingresar", {"correo": correo, "contrasena": contrasena})


def _actor_de(usuario: Usuario) -> Actor:
    """El `Actor` que el middleware arma en la peticion siguiente (roles vigentes)."""
    respuesta = _entrar(usuario).get("/")
    return respuesta.wsgi_request.actor  # type: ignore[attr-defined,no-any-return]


# --- 1. Usuario con varios roles --------------------------------------------------------------


@scenario(FEATURE, "Usuario con varios roles")
def test_usuario_con_varios_roles() -> None: ...


@when(parsers.parse('creo a "Ana" con los roles "{uno}" y "{dos}"'))
def _crear_ana_con_dos_roles(
    admin_cliente: Client, ctx: dict[str, Any], uno: str, dos: str
) -> None:
    respuesta = _alta(admin_cliente, roles=(CODIGOS[uno], CODIGOS[dos]))
    assert respuesta.status_code == 200
    ctx["ana"] = _por_correo("ana@empresa.example")


@then("Ana ve las colas y las acciones de los dos roles")
def _ana_ve_los_dos_roles(ctx: dict[str, Any]) -> None:
    ana = ctx["ana"]
    assert {r.codigo for r in ana.roles.all()} == {"auditor", "usuario"}
    pagina = _entrar(ana).get("/").content.decode()
    assert DESCRIPCIONES[Capacidad.CONSULTAR_BITACORA] in pagina  # capacidad de ejemplo del Auditor
    assert "Auditor" in pagina or "auditor" in pagina
    assert "Administrar usuarios" not in pagina


# --- 2. Desactivar, no borrar -----------------------------------------------------------------


@scenario(FEATURE, "Desactivar, no borrar")
def test_desactivar_no_borrar() -> None: ...


@when("desactivo a un usuario que dejó la empresa")
def _desactivar(
    admin_cliente: Client, crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]
) -> None:
    usuario = crear_usuario(correo="juan@empresa.example", nombre="Juan", roles=("usuario",))
    ctx["usuario"] = usuario
    ctx["su_sesion"] = _entrar(usuario)
    assert ctx["su_sesion"].get("/").status_code == 200  # tenia sesion abierta
    AccionCuenta.objects.create(
        accion="alta",
        usuario_objetivo_id=usuario.id,
        hecha_por_id=usuario.id,
        ocurrido_en=datetime.now(UTC),
    )
    respuesta = admin_cliente.post(f"/admin/usuarios/{usuario.id}/desactivar")
    assert respuesta.status_code == 302


@then("ya no puede entrar")
def _ya_no_entra(ctx: dict[str, Any]) -> None:
    usuario = ctx["usuario"]
    assert ctx["su_sesion"].get("/").status_code == 302  # su sesion abierta cayo
    ingreso = _ingresar(usuario.correo, CONTRASENA)
    assert (
        ingreso.status_code == 200 and "Correo o contraseña incorrectos" in ingreso.content.decode()
    )
    usuario.refresh_from_db()
    assert usuario.activo is False


@then("sus acciones pasadas siguen en la bitácora con su nombre")
def _historia_intacta(ctx: dict[str, Any]) -> None:
    usuario = ctx["usuario"]
    assert Usuario.objects.filter(pk=usuario.pk, nombre="Juan").exists()  # no se borra
    assert AccionCuenta.objects.filter(hecha_por_id=usuario.id, accion="alta").exists()


@then("lo asignado a su nombre en otros modulos se libera por el bus de eventos")
def _lo_asignado_se_libera(ctx: dict[str, Any]) -> None:
    """PARCIAL: cada modulo decide que hacer con lo asignado al consumir `UsuarioDesactivado`.

    Aqui se verifica lo que `identidad` entrega para eso: la desactivacion queda registrada con sus
    roles, y de esa fila sale el evento en la misma transaccion (D.5.1).
    """
    registro = _accion("desactivacion", ctx["usuario"])
    assert registro.detalle == {"roles": ["usuario"]}
    assert registro.hecha_por_id is not None


# --- 3. Alta con correo corporativo y contrasena temporal -------------------------------------


@scenario(FEATURE, "Alta con correo corporativo y contraseña temporal")
def test_alta_con_correo_y_contrasena_temporal() -> None: ...


@when('doy de alta a "Ana" con su correo corporativo')
def _alta_de_ana(admin_cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["respuesta"] = _alta(admin_cliente)
    ctx["ana"] = _por_correo("ana@empresa.example")
    ctx["admin_usuario"] = _por_correo("admin@empresa.example")


@then("el sistema genera una contraseña temporal para entregársela")
def _genera_temporal(ctx: dict[str, Any]) -> None:
    respuesta = ctx["respuesta"]
    ctx["temporal"] = _temporal(respuesta)
    assert len(ctx["temporal"]) >= 12
    assert "no-store" in respuesta["Cache-Control"]
    assert "una sola vez" in respuesta.content.decode()
    assert ctx["ana"].check_password(ctx["temporal"])


@then("Ana tiene que cambiarla en su primer ingreso")
def _debe_cambiarla(ctx: dict[str, Any]) -> None:
    ingreso = _ingresar("ana@empresa.example", ctx["temporal"])
    assert (ingreso.status_code, ingreso["Location"]) == (302, "/ingresar/contrasena")


@then("el alta queda en la bitácora, sin guardar la contraseña")
def _alta_en_bitacora(ctx: dict[str, Any]) -> None:
    registro = _accion("alta", ctx["ana"])
    assert registro.hecha_por_id == ctx["admin_usuario"].id
    assert ctx["temporal"] not in repr(list(AccionCuenta.objects.values()))
    assert ctx["ana"].password != ctx["temporal"]  # solo el hash


def test_la_contrasena_temporal_se_ve_una_sola_vez(admin_cliente: Client) -> None:
    respuesta = _alta(admin_cliente)
    temporal = _temporal(respuesta)
    ana = _por_correo("ana@empresa.example")
    for ruta in (f"/admin/usuarios/{ana.id}", "/admin/usuarios"):
        assert temporal not in admin_cliente.get(ruta).content.decode()
    assert temporal not in str(dict(admin_cliente.session))


# --- 4. Correo repetido -----------------------------------------------------------------------


@scenario(FEATURE, "Correo repetido")
def test_correo_repetido() -> None: ...


@when("intento dar de alta a un usuario con un correo que ya tiene otro usuario")
def _correo_repetido(
    admin_cliente: Client, crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]
) -> None:
    crear_usuario(correo="ana@empresa.example")
    ctx["respuesta"] = _alta(admin_cliente, correo="ANA@Empresa.Example", nombre="Otra Ana")
    ctx["verificar_rechazo"] = _verificar_correo_repetido


@then("el sistema no lo permite")
def _no_lo_permite(ctx: dict[str, Any]) -> None:
    ctx["verificar_rechazo"](ctx)


def _verificar_correo_repetido(ctx: dict[str, Any]) -> None:
    assert ctx["respuesta"].status_code == 422
    assert "Ya existe un usuario con ese correo" in ctx["respuesta"].content.decode()
    assert Usuario.objects.filter(correo__iexact="ana@empresa.example").count() == 1


# --- 5. Restablecer la contrasena -------------------------------------------------------------


@scenario(FEATURE, "Restablecer la contraseña")
def test_restablecer_la_contrasena() -> None: ...


@given('que "Ana" olvidó su contraseña')
def _ana_olvido(
    admin_cliente: Client, crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]
) -> None:
    ctx["ana"] = crear_usuario(correo="ana@empresa.example", roles=("usuario",))
    ctx["admin"] = admin_cliente
    ctx["admin_usuario"] = _por_correo("admin@empresa.example")
    ctx["su_sesion"] = _entrar(ctx["ana"])


@when("restablezco su contraseña")
def _restablezco(ctx: dict[str, Any]) -> None:
    antes = datetime.now(UTC)
    ctx["respuesta"] = ctx["admin"].post(f"/admin/usuarios/{ctx['ana'].id}/restablecer")
    ctx["antes"] = antes


@then("su contraseña anterior deja de servir y recibe otra temporal que debe cambiar al ingresar")
def _anterior_ya_no_sirve(ctx: dict[str, Any]) -> None:
    assert _ingresar("ana@empresa.example", CONTRASENA).status_code == 200  # rechazada
    temporal = _temporal(ctx["respuesta"])
    assert temporal != CONTRASENA
    ingreso = _ingresar("ana@empresa.example", temporal)
    assert (ingreso.status_code, ingreso["Location"]) == (302, "/ingresar/contrasena")
    assert ctx["su_sesion"].get("/").status_code == 302  # sus sesiones abiertas cayeron
    ctx["temporal"] = temporal


@then("el restablecimiento queda en la bitácora con quién lo hizo, sobre qué usuario y cuándo")
def _restablecimiento_en_bitacora(ctx: dict[str, Any]) -> None:
    registro = _accion("restablecimiento_contrasena", ctx["ana"])
    assert registro.hecha_por_id == ctx["admin_usuario"].id
    assert registro.usuario_objetivo_id == ctx["ana"].id
    assert ctx["antes"] <= registro.ocurrido_en <= datetime.now(UTC)
    assert ctx["temporal"] not in repr(list(AccionCuenta.objects.values()))


# --- 6. Reiniciar el segundo factor -----------------------------------------------------------


@scenario(FEATURE, "Reiniciar el segundo factor")
def test_reiniciar_el_segundo_factor() -> None: ...


@given('que "Luis", auditor, perdió su dispositivo')
def _luis(
    admin_cliente: Client,
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    ctx: dict[str, Any],
) -> None:
    ctx["luis"] = crear_usuario(correo="luis@empresa.example", roles=("auditor",))
    registrar_segundo_factor(ctx["luis"])
    ctx["admin"] = admin_cliente
    ctx["su_sesion"] = _entrar(ctx["luis"])


@when("reinicio su segundo factor")
def _reinicio(ctx: dict[str, Any]) -> None:
    ctx["respuesta"] = ctx["admin"].post(
        f"/admin/usuarios/{ctx['luis'].id}/segundo-factor/reiniciar"
    )


@then("su registro anterior deja de servir y Luis se vuelve a enrolar en su siguiente ingreso")
def _luis_se_reenrola(ctx: dict[str, Any]) -> None:
    assert not SegundoFactor.objects.filter(usuario=ctx["luis"]).exists()
    assert ctx["su_sesion"].get("/").status_code == 302
    ingreso = _ingresar("luis@empresa.example", CONTRASENA)
    assert (ingreso.status_code, ingreso["Location"]) == (302, "/ingresar/enrolar")


@then("el reinicio queda en la bitácora")
def _reinicio_en_bitacora(ctx: dict[str, Any]) -> None:
    registro = _accion("reinicio_segundo_factor", ctx["luis"])
    assert registro.hecha_por_id == _por_correo("admin@empresa.example").id


# --- 7. Desbloquear una cuenta ---------------------------------------------------------------


@scenario(FEATURE, "Desbloquear una cuenta")
def test_desbloquear_una_cuenta() -> None: ...


@given('que la cuenta de "Ana" está bloqueada por 5 intentos fallidos')
def _ana_bloqueada(
    admin_cliente: Client, crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]
) -> None:
    ctx["ana"] = crear_usuario(correo="ana@empresa.example", roles=("usuario",))
    ctx["admin"] = admin_cliente
    for _ in range(5):
        _ingresar("ana@empresa.example", "incorrecta-Incorrecta-1")
    ctx["ana"].refresh_from_db()
    assert ctx["ana"].bloqueada_hasta is not None
    assert _ingresar("ana@empresa.example", CONTRASENA).status_code == 200  # ni la buena entra
    assert (
        "Desbloquear cuenta"
        in admin_cliente.get(f"/admin/usuarios/{ctx['ana'].id}").content.decode()
    )


@when("la desbloqueo")
def _desbloqueo(ctx: dict[str, Any]) -> None:
    ctx["admin"].post(f"/admin/usuarios/{ctx['ana'].id}/desbloquear")


@then("Ana puede ingresar sin esperar los 15 minutos")
def _ana_entra(ctx: dict[str, Any]) -> None:
    ingreso = _ingresar("ana@empresa.example", CONTRASENA)
    assert (ingreso.status_code, ingreso["Location"]) == (302, "/")


@then("el desbloqueo queda en la bitácora")
def _desbloqueo_en_bitacora(ctx: dict[str, Any]) -> None:
    assert _accion("desbloqueo", ctx["ana"]).hecha_por_id == _por_correo("admin@empresa.example").id


# --- 8. Sin autoservicio de recuperacion -----------------------------------------------------


@scenario(FEATURE, "Sin autoservicio de recuperación")
def test_sin_autoservicio_de_recuperacion() -> None: ...


@when("un usuario olvida su contraseña")
def _olvida(ctx: dict[str, Any]) -> None:
    ctx["pagina"] = Client().get("/ingresar").content.decode()


@then("la pantalla de ingreso no ofrece recuperarla por correo")
def _sin_recuperacion(ctx: dict[str, Any]) -> None:
    pagina = ctx["pagina"].lower()
    assert "recuperar" not in pagina and "restablecer" not in pagina
    assert "<a " not in pagina  # ningun enlace de recuperacion
    for ruta in ("/recuperar", "/ingresar/recuperar", "/cuenta/recuperar"):
        assert Client().get(ruta).status_code in (302, 404)


@then("le indica que la solicite al administrador")
def _indica_al_administrador(ctx: dict[str, Any]) -> None:
    assert "solicítala al administrador" in ctx["pagina"]


# --- 9. Un administrador no recupera su propia cuenta ----------------------------------------


@scenario(FEATURE, "Un administrador no recupera su propia cuenta")
def test_un_administrador_no_recupera_su_propia_cuenta() -> None: ...


@given('que tengo el rol "Administrador"')
def _soy_administrador(admin_cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["admin"] = admin_cliente
    ctx["yo"] = _por_correo("admin@empresa.example")
    ctx["hash"] = ctx["yo"].password


@when(
    "intento restablecer mi propia contraseña o reiniciar mi propio segundo factor desde la "
    "gestión de usuarios"
)
def _intento_lo_mio(ctx: dict[str, Any], registrar_segundo_factor: Callable[..., bytes]) -> None:
    registrar_segundo_factor(ctx["yo"])
    ctx["respuestas"] = [
        ctx["admin"].post(f"/admin/usuarios/{ctx['yo'].id}/restablecer"),
        ctx["admin"].post(f"/admin/usuarios/{ctx['yo'].id}/segundo-factor/reiniciar"),
    ]


@then("el sistema no lo permite y me indica que debe hacerlo otro administrador")
def _otro_administrador(ctx: dict[str, Any], crear_usuario: Callable[..., Usuario]) -> None:
    for respuesta in ctx["respuestas"]:
        assert respuesta.status_code == 403
        assert "otro administrador" in respuesta.content.decode()
    ctx["yo"].refresh_from_db()
    assert ctx["yo"].password == ctx["hash"]
    assert SegundoFactor.objects.filter(usuario=ctx["yo"]).exists()
    assert not AccionCuenta.objects.filter(
        accion__in=["restablecimiento_contrasena", "reinicio_segundo_factor"]
    ).exists()
    # La pantalla ni siquiera ofrece los botones sobre la propia cuenta.
    pagina = ctx["admin"].get(f"/admin/usuarios/{ctx['yo'].id}").content.decode()
    assert "Restablecer contraseña</button>" not in pagina
    # Otro administrador si puede.
    otro = _entrar(crear_usuario(correo="admin2@empresa.example", roles=("administrador",)))
    assert otro.post(f"/admin/usuarios/{ctx['yo'].id}/restablecer").status_code == 200


# --- 10. Un administrador cambia sus propios roles -------------------------------------------


@scenario(FEATURE, "Un administrador cambia sus propios roles")
def test_un_administrador_cambia_sus_propios_roles() -> None: ...


@when("me agrego o me quito otros roles")
def _me_agrego_y_me_quito_roles(ctx: dict[str, Any]) -> None:
    url = f"/admin/usuarios/{ctx['yo'].id}/editar"
    ctx["respuestas"] = [
        ctx["admin"].post(
            url,
            {"nombre": "Admin", "roles": ["administrador", "usuario"]},
        )
    ]
    ctx["roles_con_otro"] = {r.codigo for r in ctx["yo"].roles.all()}
    ctx["respuestas"].append(
        ctx["admin"].post(url, {"nombre": "Admin", "roles": ["administrador"]})
    )


@then("el cambio se aplica y queda en la bitácora")
def _cambio_propio_aplicado(ctx: dict[str, Any]) -> None:
    assert ctx["roles_con_otro"] == {"administrador", "usuario"}
    assert {r.codigo for r in ctx["yo"].roles.all()} == {"administrador"}
    cambios = AccionCuenta.objects.filter(
        accion="cambio_de_roles", usuario_objetivo_id=ctx["yo"].id
    )
    assert cambios.count() == 2
    assert all(c.hecha_por_id == ctx["yo"].id for c in cambios)
    # La propia sesion no se cae a mitad de la gestion (las demas si, por el sello).
    assert ctx["admin"].get("/admin/usuarios").status_code == 200


@then('no puedo quitarme el rol "Administrador" ni desactivarme')
def _no_puedo_quitarme_ni_desactivarme(ctx: dict[str, Any]) -> None:
    quitarme = ctx["admin"].post(
        f"/admin/usuarios/{ctx['yo'].id}/editar",
        {"nombre": "Admin", "roles": ["auditor"]},
    )
    desactivarme = ctx["admin"].post(f"/admin/usuarios/{ctx['yo'].id}/desactivar")
    assert (quitarme.status_code, desactivarme.status_code) == (403, 403)
    assert "otro administrador" in quitarme.content.decode()
    ctx["yo"].refresh_from_db()
    assert ctx["yo"].activo
    assert {r.codigo for r in ctx["yo"].roles.all()} == {"administrador"}


# --- 11. Siempre queda un administrador activo ------------------------------------------------


@scenario(FEATURE, "Siempre queda un administrador activo")
def test_siempre_queda_un_administrador_activo() -> None: ...


@given(
    "que desactivar a un administrador o quitarle el rol dejaría al sistema "
    "sin administradores activos"
)
def _dejaria_sin_administradores(
    crear_usuario: Callable[..., Usuario], ctx: dict[str, Any]
) -> None:
    """El unico camino es una carrera: el otro administrador acaba de ser desactivado por una
    peticion simultanea, y esta (ya autenticada) llega despues (la prueba con hilos esta en
    `test_gestion_usuarios_base.py`)."""
    ctx["ultimo"] = crear_usuario(correo="ultimo@empresa.example", roles=("administrador",))
    saliente = crear_usuario(
        correo="saliente@empresa.example", roles=("administrador",), activo=False
    )
    ctx["actor"] = Actor.de(str(saliente.id), ["administrador"])


@when("intento hacerlo")
def _intento_hacerlo(ctx: dict[str, Any]) -> None:
    objetivo = str(ctx["ultimo"].id)
    errores = []
    for intento in (
        lambda: composicion.desactivar_usuario()(ctx["actor"], objetivo),
        lambda: composicion.editar_usuario()(ctx["actor"], objetivo, nombre="U", roles=["auditor"]),
    ):
        with pytest.raises(ConflictoDeUsuario) as error:
            intento()
        errores.append(str(error.value))
    ctx["errores"] = errores


@then("el sistema no lo permite y me indica que debe quedar al menos un administrador activo")
def _debe_quedar_uno(ctx: dict[str, Any]) -> None:
    assert all("debe quedar al menos un administrador activo" in e.lower() for e in ctx["errores"])
    ctx["ultimo"].refresh_from_db()
    assert ctx["ultimo"].activo
    assert {r.codigo for r in ctx["ultimo"].roles.all()} == {"administrador"}
    assert not AccionCuenta.objects.exists()


# --- 12. Aviso de un solo administrador ---------------------------------------------------------


@scenario(FEATURE, "Aviso de un solo administrador")
def test_aviso_de_un_solo_administrador() -> None: ...


@given("que solo queda un administrador activo")
def _solo_un_administrador(admin_cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["admin"] = admin_cliente
    assert Usuario.objects.filter(activo=True, asignaciones__rol_id="administrador").count() == 1


@when("abro la gestión de usuarios")
def _abro_la_gestion(ctx: dict[str, Any]) -> None:
    ctx["pagina"] = ctx["admin"].get("/admin/usuarios").content.decode()


@then("veo un aviso que recomienda tener al menos dos administradores")
def _veo_el_aviso(ctx: dict[str, Any], crear_usuario: Callable[..., Usuario]) -> None:
    assert "Solo hay un administrador activo" in ctx["pagina"]
    assert "al menos dos" in " ".join(ctx["pagina"].split())  # el HTML parte la linea
    # Con dos administradores activos el aviso desaparece; con uno desactivado, vuelve.
    otro = crear_usuario(correo="otro-admin@empresa.example", roles=("administrador",))
    assert (
        "Solo hay un administrador activo"
        not in ctx["admin"].get("/admin/usuarios").content.decode()
    )
    ctx["admin"].post(f"/admin/usuarios/{otro.id}/desactivar")
    assert (
        "Solo hay un administrador activo" in ctx["admin"].get("/admin/usuarios").content.decode()
    )


# --- 13. Correo con caracteres no permitidos ------------------------------------------------------

CORREOS_NO_PERMITIDOS = [
    "josé@empresa.example",
    "peña@empresa.example",
    "ñandú@empresa.example",
    "ana@empresá.example",
    "ana+extra@empresa.example",
    "ana ruiz@empresa.example",
    "ana@empresa.example​",
    "ａｎａ@empresa.example",
]


@scenario(FEATURE, "Correo con caracteres no permitidos")
def test_correo_con_caracteres_no_permitidos() -> None: ...


@when(
    "intento dar de alta a un usuario con un correo que tiene acentos, "
    '"ñ" u otros caracteres no permitidos'
)
def _correos_no_permitidos(admin_cliente: Client, ctx: dict[str, Any]) -> None:
    ctx["respuestas"] = [_alta(admin_cliente, correo=correo) for correo in CORREOS_NO_PERMITIDOS]


@then("el sistema no lo permite y me indica qué caracteres se aceptan")
def _indica_que_se_acepta(ctx: dict[str, Any]) -> None:
    for respuesta in ctx["respuestas"]:
        assert respuesta.status_code == 422
        pagina = respuesta.content.decode()
        assert "letras sin acento, números, punto, guion y guion bajo" in pagina
    assert Usuario.objects.filter(activo=True).count() == 1  # solo el administrador de la prueba
    assert not AccionCuenta.objects.exists()


# --- Permisos y endurecimiento de las pantallas -----------------------------------------------

RUTAS_POST = [
    "desactivar",
    "reactivar",
    "restablecer",
    "segundo-factor/reiniciar",
    "desbloquear",
    "editar",
]


@pytest.mark.parametrize("rol", [r for r in CODIGOS.values() if r != "administrador"])
def test_quien_no_es_administrador_no_abre_ninguna_pantalla_ni_ejecuta_acciones(
    rol: str, crear_usuario: Callable[..., Usuario]
) -> None:
    objetivo = crear_usuario(correo="objetivo@empresa.example", roles=("usuario",))
    navegador = _entrar(crear_usuario(correo="x@empresa.example", roles=(rol,)))
    for ruta in ("/admin/usuarios", "/admin/usuarios/nuevo", f"/admin/usuarios/{objetivo.id}"):
        assert navegador.get(ruta).status_code == 403
    assert (
        navegador.post(
            "/admin/usuarios/nuevo",
            {"correo": "n@n.co", "nombre": "N", "roles": ["usuario"]},
        ).status_code
        == 403
    )
    for accion in RUTAS_POST:
        assert (
            navegador.post(
                f"/admin/usuarios/{objetivo.id}/{accion}", {"nombre": "X", "roles": ["usuario"]}
            ).status_code
            == 403
        )
    objetivo.refresh_from_db()
    assert objetivo.activo
    assert not Usuario.objects.filter(correo="n@n.co").exists()
    assert not AccionCuenta.objects.exists()


def test_sin_sesion_se_redirige_al_ingreso() -> None:
    respuesta = Client().get("/admin/usuarios")
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar")


def test_las_acciones_solo_aceptan_post_y_exigen_csrf(
    crear_usuario: Callable[..., Usuario],
) -> None:
    admin = crear_usuario(correo="admin@empresa.example", roles=("administrador",))
    objetivo = crear_usuario(correo="u@empresa.example", roles=("usuario",))
    navegador = Client(enforce_csrf_checks=True)
    navegador.force_login(admin)
    sesion = navegador.session
    sesion["iniciada_en"] = datetime.now(UTC).isoformat()
    sesion.save()
    assert navegador.get(f"/admin/usuarios/{objetivo.id}/desactivar").status_code == 405
    assert (
        navegador.post(f"/admin/usuarios/{objetivo.id}/desactivar").status_code == 403
    )  # sin token
    objetivo.refresh_from_db()
    assert objetivo.activo
    pagina = navegador.get(f"/admin/usuarios/{objetivo.id}")
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina.content.decode())
    assert token
    assert (
        navegador.post(
            f"/admin/usuarios/{objetivo.id}/desactivar", {"csrfmiddlewaretoken": token.group(1)}
        ).status_code
        == 302
    )


def test_las_pantallas_no_se_guardan_en_cache_y_no_llevan_javascript_en_linea(
    admin_cliente: Client,
) -> None:
    for ruta in ("/admin/usuarios", "/admin/usuarios/nuevo"):
        respuesta = admin_cliente.get(ruta)
        assert "no-store" in respuesta["Cache-Control"]
        cuerpo = respuesta.content.decode().lower()
        assert "<script" not in cuerpo and "style=" not in cuerpo and " onclick" not in cuerpo


def test_la_lista_muestra_estado_roles_y_la_pagina_de_otro_usuario_inexistente_da_404(
    admin_cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario(correo="a@n.co", nombre="Ana", roles=("usuario", "auditor"), activo=False)
    crear_usuario(correo="b@n.co", roles=("auditor",), debe_cambiar_contrasena=True)
    crear_usuario(
        correo="c@n.co",
        roles=("auditor",),
        bloqueada_hasta=datetime.now(UTC) + timedelta(minutes=9),
    )
    pagina = admin_cliente.get("/admin/usuarios").content.decode()
    for texto in ("Desactivado", "Contraseña temporal", "Bloqueada", "Auditor, Usuario", "a@n.co"):
        assert texto in pagina
    assert (
        admin_cliente.get("/admin/usuarios/00000000-0000-4000-8000-000000000000").status_code == 404
    )
    assert (
        admin_cliente.post(
            "/admin/usuarios/00000000-0000-4000-8000-000000000000/desactivar"
        ).status_code
        == 404
    )


def test_el_administrador_ve_el_enlace_de_administracion_y_los_demas_no(
    admin_cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    assert "Administrar usuarios" in admin_cliente.get("/").content.decode()
    assert (
        "Administrar usuarios"
        not in _entrar(crear_usuario(correo="k@n.co")).get("/").content.decode()
    )


def test_acciones_con_datos_invalidos_muestran_el_error_sin_romper(
    admin_cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    u = crear_usuario(correo="u@n.co", roles=("auditor",))
    base = f"/admin/usuarios/{u.id}"
    assert (
        "Elige al menos un rol"
        in admin_cliente.post(f"{base}/editar", {"nombre": "U"}, follow=True).content.decode()
    )
    assert (
        "El nombre es obligatorio"
        in admin_cliente.post(
            f"{base}/editar", {"nombre": " ", "roles": ["usuario"]}, follow=True
        ).content.decode()
    )


def test_editar_roles_cierra_sesiones_y_aplica_en_el_siguiente_ingreso(
    admin_cliente: Client,
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
) -> None:
    """Rol sensible asignado despues: el cambio de roles rota el sello de sesion."""
    luis = crear_usuario(correo="luis@n.co", roles=("usuario",))
    sesion = _entrar(luis)
    assert sesion.get("/").status_code == 200
    respuesta = admin_cliente.post(
        f"/admin/usuarios/{luis.id}/editar",
        {"nombre": "Luis", "roles": ["usuario", "auditor"]},
        follow=True,
    )
    assert "Sus sesiones se cerraron" in respuesta.content.decode()
    assert sesion.get("/").status_code == 302
    ingreso = _ingresar("luis@n.co", CONTRASENA)
    assert (ingreso.status_code, ingreso["Location"]) == (302, "/ingresar/enrolar")
    assert _accion("cambio_de_roles", luis).detalle == {
        "antes": ["usuario"],
        "despues": ["auditor", "usuario"],
    }


def test_editar_datos_sin_cambiar_roles_no_cierra_sesiones(
    admin_cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    u = crear_usuario(correo="u@n.co", nombre="U", roles=("usuario",))
    sesion = _entrar(u)
    admin_cliente.post(f"/admin/usuarios/{u.id}/editar", {"nombre": "Nuevo", "roles": ["usuario"]})
    u.refresh_from_db()
    assert u.nombre == "Nuevo"
    assert sesion.get("/").status_code == 200
    assert _accion("cambio_de_usuario", u).detalle["campos"] == ["nombre"]


def test_reactivar_desde_la_pantalla(
    admin_cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    juan = crear_usuario(correo="j@n.co", nombre="Juan", roles=("usuario",))
    admin_cliente.post(f"/admin/usuarios/{juan.id}/desactivar")
    assert "Reactivar usuario" in admin_cliente.get(f"/admin/usuarios/{juan.id}").content.decode()
    admin_cliente.post(f"/admin/usuarios/{juan.id}/reactivar")
    juan.refresh_from_db()
    assert juan.activo
