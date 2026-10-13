"""Adaptadores de `identidad` contra PostgreSQL: modelo, catalogo, triggers, CSRF y comando."""

from collections.abc import Callable
from io import StringIO
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import IntegrityError, connection, transaction
from django.test import Client

from identidad.adaptadores.salida.modelos import (
    AccionCuenta,
    IntentoIngreso,
    Rol,
    Usuario,
    UsuarioRol,
)
from identidad.adaptadores.salida.repositorios import huella_de_correo
from identidad.dominio.roles import CATALOGO_DE_ROLES, ROLES_CON_SEGUNDO_FACTOR
from identidad.pruebas.conftest import CONTRASENA
from nucleo.actor import Actor
from nucleo.pruebas.aislamiento import Aislamiento

pytestmark = pytest.mark.django_db


def _actor(respuesta: Any) -> Actor | None:
    """El `Actor` que dejo el middleware en la peticion."""
    return respuesta.wsgi_request.actor  # type: ignore[attr-defined,no-any-return]


def test_el_modelo_de_usuario_es_el_de_identidad_sin_permisos_de_django() -> None:
    modelo = get_user_model()
    assert modelo is Usuario
    assert modelo.USERNAME_FIELD == "correo"
    assert not hasattr(modelo, "is_superuser")
    assert not hasattr(modelo, "has_perm")


def test_el_catalogo_sembrado_coincide_con_el_dominio() -> None:
    sembrados = {rol.codigo: rol.exige_segundo_factor for rol in Rol.objects.all()}
    assert set(sembrados) == set(CATALOGO_DE_ROLES)
    assert {codigo for codigo, exige in sembrados.items() if exige} == ROLES_CON_SEGUNDO_FACTOR


def test_el_correo_es_unico_sin_distinguir_mayusculas(
    crear_usuario: Callable[..., Usuario],
) -> None:
    crear_usuario(correo="ana@empresa.example")
    with pytest.raises(IntegrityError), transaction.atomic():
        crear_usuario(correo="ANA@Empresa.Example")


def test_un_usuario_puede_tener_varios_roles_y_no_repetidos(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario(roles=("usuario", "auditor"))
    assert set(usuario.roles.values_list("codigo", flat=True)) == {"usuario", "auditor"}
    with pytest.raises(IntegrityError), transaction.atomic():
        UsuarioRol.objects.create(
            usuario=usuario, rol=Rol.objects.get(codigo="usuario"), asignado_en=usuario.creado_en
        )


@pytest.mark.parametrize("modelo", [IntentoIngreso, AccionCuenta])
def test_los_registros_son_de_solo_insercion(
    modelo: type, crear_usuario: Callable[..., Usuario]
) -> None:
    usuario = crear_usuario()
    fila: IntentoIngreso | AccionCuenta
    if modelo is IntentoIngreso:
        fila = IntentoIngreso.objects.create(
            usuario_id=usuario.id,
            huella_correo="h",
            factor="contrasena",
            resultado="correcto",
            motivo="correcto",
            ip="10.0.0.1",
            ocurrido_en=usuario.creado_en,
        )
    else:
        fila = AccionCuenta.objects.create(
            accion="alta", usuario_objetivo_id=usuario.id, ocurrido_en=usuario.creado_en
        )
    with pytest.raises(Exception, match="solo inserción"), transaction.atomic():
        modelo.objects.filter(pk=fila.pk).update(**{"ocurrido_en": usuario.creado_en})  # type: ignore[attr-defined]
    with pytest.raises(Exception, match="solo inserción"), transaction.atomic():
        fila.delete()


def test_el_registro_guarda_la_huella_del_correo_y_no_el_texto(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario()
    escrito_por_error = "una frase tecleada en el campo de correo"
    cliente.post("/ingresar", {"correo": escrito_por_error, "contrasena": "x"})
    intento = IntentoIngreso.objects.get()
    assert intento.huella_correo == huella_de_correo(escrito_por_error)
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM "identidad"."intento_ingreso"')
        assert escrito_por_error not in str(cursor.fetchall())


def test_la_huella_ignora_mayusculas_y_espacios() -> None:
    assert huella_de_correo(" Ana@Empresa.Example ") == huella_de_correo("ana@empresa.example")


def test_la_contrasena_se_guarda_con_hash_y_no_en_el_registro(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    assert CONTRASENA not in usuario.password


def test_el_post_de_ingreso_exige_csrf(crear_usuario: Callable[..., Usuario]) -> None:
    crear_usuario()
    estricto = Client(enforce_csrf_checks=True)
    datos = {"correo": "ana@empresa.example", "contrasena": CONTRASENA}
    sin_token = estricto.post("/ingresar", datos)
    assert sin_token.status_code == 403
    pagina = estricto.get("/ingresar")
    token = estricto.cookies["csrftoken"].value
    assert 'name="csrfmiddlewaretoken"' in pagina.content.decode()
    con_token = estricto.post("/ingresar", {**datos, "csrfmiddlewaretoken": token})
    assert con_token.status_code == 302


def test_salir_es_solo_post_y_cierra_la_sesion(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario()
    cliente.post("/ingresar", {"correo": "ana@empresa.example", "contrasena": CONTRASENA})
    assert cliente.get("/salir").status_code == 405
    assert cliente.get("/").status_code == 200
    assert cliente.post("/salir").status_code == 302
    assert cliente.get("/").status_code == 302


def test_un_usuario_desactivado_pierde_la_sesion_en_la_siguiente_peticion(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    usuario = crear_usuario()
    cliente.post("/ingresar", {"correo": "ana@empresa.example", "contrasena": CONTRASENA})
    assert cliente.get("/").status_code == 200
    Usuario.objects.filter(pk=usuario.pk).update(activo=False)
    assert cliente.get("/").status_code == 302


def test_un_cambio_de_roles_aplica_en_la_siguiente_peticion(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    usuario = crear_usuario(roles=("usuario",))
    cliente.post("/ingresar", {"correo": "ana@empresa.example", "contrasena": CONTRASENA})
    actor = _actor(cliente.get("/"))
    assert actor is not None
    assert actor.roles == frozenset({"usuario"})
    UsuarioRol.objects.create(
        usuario=usuario, rol=Rol.objects.get(codigo="auditor"), asignado_en=usuario.creado_en
    )
    actor = _actor(cliente.get("/"))
    assert actor is not None
    assert actor.roles == frozenset({"usuario", "auditor"})


def test_sin_sesion_completa_no_hay_actor(cliente: Client) -> None:
    assert _actor(cliente.get("/ingresar")) is None


def test_la_pagina_de_ingreso_no_trae_estilos_en_linea_y_su_css_se_sirve_aparte(
    cliente: Client,
) -> None:
    pagina = cliente.get("/ingresar").content.decode()
    assert "<style" not in pagina
    assert ' style="' not in pagina
    assert "<script" not in pagina
    css = cliente.get("/estilos/identidad.css")
    assert css.status_code == 200
    assert css["Content-Type"].startswith("text/css")
    assert b"prefers-color-scheme: dark" in b"".join(css.streaming_content)  # type: ignore[attr-defined]


def test_el_nombre_de_la_aplicacion_sale_de_la_configuracion(
    cliente: Client, settings: object
) -> None:
    settings.APP_NOMBRE_APLICACION = "Mi Empresa"  # type: ignore[attr-defined]
    assert "Mi Empresa" in cliente.get("/ingresar").content.decode()


def test_la_sesion_se_renueva_en_cada_peticion_y_la_cookie_no_la_lee_javascript(
    settings: object,
) -> None:
    assert settings.SESSION_COOKIE_AGE == 3 * 60 * 60  # type: ignore[attr-defined]
    assert settings.SESSION_SAVE_EVERY_REQUEST is True  # type: ignore[attr-defined]
    assert settings.SESSION_COOKIE_HTTPONLY is True  # type: ignore[attr-defined]


# --- Comando crear_administrador -----------------------------------------------------------------


def _correr(*argumentos: str) -> str:
    salida = StringIO()
    call_command("crear_administrador", *argumentos, stdout=salida)
    return salida.getvalue()


def test_crear_administrador_muestra_la_temporal_una_vez_y_guarda_solo_el_hash() -> None:
    salida = _correr("Root@Empresa.Example")
    temporal = salida.split("una sola vez): ")[1].splitlines()[0]
    usuario = Usuario.objects.get(correo="root@empresa.example")
    assert usuario.debe_cambiar_contrasena
    assert temporal not in usuario.password
    assert usuario.check_password(temporal)
    assert set(usuario.roles.values_list("codigo", flat=True)) == {"administrador"}
    accion = AccionCuenta.objects.get(accion="alta")
    assert (accion.usuario_objetivo_id, accion.hecha_por_id) == (usuario.id, None)
    assert temporal not in str(list(AccionCuenta.objects.values()))


def test_crear_administrador_rechaza_correo_repetido_e_invalido() -> None:
    _correr("root@empresa.example")
    with pytest.raises(CommandError, match="Ya existe"):
        _correr("ROOT@empresa.example")
    with pytest.raises(CommandError, match="no es válido"):
        _correr("sin-arroba")


def test_sin_adaptador_el_administrador_recien_creado_no_entra_falla_cerrado() -> None:
    """Red de seguridad: si el puerto del segundo factor no estuviera conectado, un rol
    sensible NO entra con solo la contrasena (ni siquiera llega al cambio de la temporal)."""
    salida = _correr("root@empresa.example")
    temporal = salida.split("una sola vez): ")[1].splitlines()[0]
    with Aislamiento():  # vacia el registro: no hay adaptador del segundo factor
        respuesta = Client().post(
            "/ingresar", {"correo": "root@empresa.example", "contrasena": temporal}
        )
    assert respuesta.status_code == 403
    assert "Tu rol requiere un segundo factor para ingresar" in respuesta.content.decode()


def test_con_el_adaptador_conectado_el_administrador_recien_creado_sigue_a_su_primera_etapa() -> (
    None
):
    """ya no se rechaza; sigue el cambio de la temporal y todavia NO hay sesion."""
    salida = _correr("root@empresa.example")
    temporal = salida.split("una sola vez): ")[1].splitlines()[0]
    cliente = Client()
    respuesta = cliente.post(
        "/ingresar", {"correo": "root@empresa.example", "contrasena": temporal}
    )
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar/contrasena")
    assert "_auth_user_id" not in cliente.session
