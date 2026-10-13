"""Endurecimiento de (ronda 2): sesion, etapa pendiente, registro, llave y huella."""

import threading
from collections.abc import Callable
from datetime import timedelta
from io import StringIO
from typing import Any

import pytest
from django.contrib.auth.hashers import Argon2PasswordHasher, check_password
from django.core.management import CommandError, call_command
from django.db import connection, connections, transaction
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from identidad.adaptadores.entrada.middleware import CLAVE_ETAPA, CLAVE_INICIADA_EN
from identidad.adaptadores.salida import contrasenas as modulo_contrasenas
from identidad.adaptadores.salida.modelos import (
    AccionCuenta,
    IntentoIngreso,
    Rol,
    Usuario,
    UsuarioRol,
)
from identidad.adaptadores.salida.repositorios import (
    RegistroDeAccesosDjango,
    RepositorioCuentasDjango,
    huella_de_correo,
)
from identidad.dominio.acceso import normalizar_correo
from identidad.pruebas.conftest import CONTRASENA, RelojAdelantable
from nucleo.pruebas.aislamiento import Aislamiento

pytestmark = pytest.mark.django_db

CORREO = "ana@empresa.example"
GENERICO = "Correo o contraseña incorrectos"
ARGON2 = ["django.contrib.auth.hashers.Argon2PasswordHasher"]


def _ingresar(cliente: Client, correo: str = CORREO, contrasena: str = CONTRASENA) -> Any:
    return cliente.post("/ingresar", {"correo": correo, "contrasena": contrasena})


# --- 1. Tope absoluto de la sesion --------------------------------------------------


def test_una_sesion_sin_iniciada_en_se_trata_como_vencida(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario()
    _ingresar(cliente)
    assert cliente.get("/").status_code == 200
    sesion = cliente.session  # una sesion anterior a esta regla: sin la marca de ingreso
    del sesion[CLAVE_INICIADA_EN]
    sesion.save()
    respuesta = cliente.get("/")
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar")
    assert "_auth_user_id" not in cliente.session


def test_el_ingreso_guarda_iniciada_en_al_completarse(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario()
    _ingresar(cliente)
    assert CLAVE_INICIADA_EN in cliente.session


def test_la_etapa_de_contrasena_temporal_no_guarda_iniciada_en(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario(debe_cambiar_contrasena=True)
    _ingresar(cliente)
    assert CLAVE_ETAPA in cliente.session
    assert CLAVE_INICIADA_EN not in cliente.session  # solo al COMPLETAR el ingreso


def test_el_tope_es_configurable_y_se_compara_con_el_reloj_inyectado(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    reloj: RelojAdelantable,
    settings: Any,
) -> None:
    settings.APP_SESION_DURACION_MAXIMA = timedelta(hours=5)
    crear_usuario()
    _ingresar(cliente)
    for _ in range(2):  # 2 x 2h30 = 5 horas, con actividad cada 2h30
        reloj.adelantar(hours=2, minutes=29)
        assert cliente.get("/").status_code == 200
    reloj.adelantar(hours=2)  # 6 horas desde el ingreso: pasa el tope de 5
    assert cliente.get("/").status_code == 302


def test_el_cierre_por_salida_queda_registrado(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    usuario = crear_usuario()
    _ingresar(cliente)
    cliente.post("/salir")
    assert AccionCuenta.objects.filter(
        accion="sesion_cerrada_salida", usuario_objetivo_id=usuario.id
    ).exists()


# --- sin `?next=` ----------------------------------------------------------------------


@pytest.mark.parametrize("ruta", ["/", "/cuenta/contrasena"])
def test_las_redirecciones_al_ingreso_no_emiten_next(cliente: Client, ruta: str) -> None:
    respuesta = cliente.get(ruta)
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar")
    assert "next" not in respuesta["Location"]


def test_ni_el_tope_ni_la_etapa_vencida_emiten_next(
    cliente: Client, crear_usuario: Callable[..., Usuario], reloj: RelojAdelantable
) -> None:
    crear_usuario(debe_cambiar_contrasena=True)
    _ingresar(cliente)
    reloj.adelantar(minutes=16)
    respuesta = cliente.get("/cuenta/contrasena")
    assert respuesta["Location"] == "/ingresar"


# --- etapa de la contrasena temporal -----------------------------------------------------


def _etapa(cliente: Client) -> dict[str, str]:
    return dict(cliente.session[CLAVE_ETAPA])


def test_la_etapa_guarda_usuario_sello_y_marca_de_tiempo(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    usuario = crear_usuario(debe_cambiar_contrasena=True)
    _ingresar(cliente)
    etapa = _etapa(cliente)
    assert etapa["usuario_id"] == str(usuario.id)
    assert etapa["sello"] == str(usuario.sello_sesion)
    assert etapa["creada_en"]


def test_la_etapa_expira_a_los_15_minutos(
    cliente: Client, crear_usuario: Callable[..., Usuario], reloj: RelojAdelantable
) -> None:
    crear_usuario(debe_cambiar_contrasena=True)
    _ingresar(cliente)
    reloj.adelantar(minutes=14, seconds=59)
    assert cliente.get("/ingresar/contrasena").status_code == 200
    reloj.adelantar(seconds=2)
    respuesta = cliente.post(
        "/ingresar/contrasena",
        {"nueva": "frase-nueva-larga-42", "confirmar": "frase-nueva-larga-42"},
    )
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar")
    assert "_auth_user_id" not in cliente.session
    assert Usuario.objects.get(correo=CORREO).debe_cambiar_contrasena  # no cambio nada


def test_sin_adaptador_si_cambian_los_roles_con_la_etapa_abierta_a_uno_sensible_no_entra(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    """Falla cerrado revalidado: sin segundo factor disponible, el cambio no se completa."""
    usuario = crear_usuario(debe_cambiar_contrasena=True, roles=("usuario",))
    _ingresar(cliente)
    UsuarioRol.objects.create(
        usuario=usuario, rol=Rol.objects.get(codigo="auditor"), asignado_en=usuario.creado_en
    )
    nueva = "frase-nueva-larga-42"
    with Aislamiento():  # el puerto del segundo factor sin adaptador
        respuesta = cliente.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    assert respuesta.status_code == 403
    assert "Tu rol requiere un segundo factor para ingresar" in respuesta.content.decode()
    assert "_auth_user_id" not in cliente.session
    assert CLAVE_ETAPA not in cliente.session
    assert Usuario.objects.get(pk=usuario.pk).debe_cambiar_contrasena  # la temporal sigue igual
    assert not check_password(nueva, Usuario.objects.get(pk=usuario.pk).password)
    assert IntentoIngreso.objects.filter(motivo="requiere_segundo_factor").count() == 1


def test_con_adaptador_si_cambian_los_roles_con_la_etapa_abierta_a_uno_sensible_va_al_enrolamiento(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    """el rol sensible asignado a medio ingreso no abre sesion; sigue el enrolamiento."""
    usuario = crear_usuario(debe_cambiar_contrasena=True, roles=("usuario",))
    _ingresar(cliente)
    UsuarioRol.objects.create(
        usuario=usuario, rol=Rol.objects.get(codigo="auditor"), asignado_en=usuario.creado_en
    )
    nueva = "frase-nueva-larga-42"
    respuesta = cliente.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar/enrolar")
    assert "_auth_user_id" not in cliente.session  # todavia sin sesion
    etapa = cliente.session[CLAVE_ETAPA]
    assert etapa["etapa"] == "enrolamiento_pendiente"
    assert etapa["sello"] == str(Usuario.objects.get(pk=usuario.pk).sello_sesion)  # el sello NUEVO


def test_si_reinician_la_temporal_con_la_etapa_abierta_no_entra(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    usuario = crear_usuario(debe_cambiar_contrasena=True)
    _ingresar(cliente)
    # El Administrador reinicia la temporal: cambia el hash y el sello.
    RepositorioCuentasDjango().guardar_contrasena(
        str(usuario.pk), "x", temporal=True, ahora=usuario.creado_en
    )
    nueva = "frase-nueva-larga-42"
    respuesta = cliente.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    assert respuesta.status_code == 200
    assert "Tu ingreso ya no es válido" in respuesta.content.decode()
    assert "_auth_user_id" not in cliente.session
    assert CLAVE_ETAPA not in cliente.session


def test_sin_cambios_la_etapa_si_se_completa_y_abre_sesion_con_iniciada_en(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario(debe_cambiar_contrasena=True)
    _ingresar(cliente)
    nueva = "frase-nueva-larga-42"
    respuesta = cliente.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/")
    assert CLAVE_INICIADA_EN in cliente.session


# --- y: comando crear_administrador -------------------------------------------------


def _alta(*argumentos: str) -> str:
    salida = StringIO()
    call_command("crear_administrador", *argumentos, stdout=salida)
    return salida.getvalue()


def test_el_alta_simultanea_del_mismo_correo_da_un_error_en_espanol_y_no_deja_restos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _alta("root@empresa.example")
    # Simula la carrera: la verificacion previa no ve al otro, y es la restriccion la que falla.
    monkeypatch.setattr(RepositorioCuentasDjango, "por_correo", lambda self, correo: None)
    with pytest.raises(CommandError, match="Ya existe un usuario con ese correo"):
        _alta("ROOT@empresa.example")
    assert Usuario.objects.count() == 1
    assert AccionCuenta.objects.filter(accion="alta").count() == 1


def test_si_falla_el_registro_de_la_accion_no_queda_el_usuario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _falla(self: object, **kwargs: object) -> None:
        raise RuntimeError("se cayo el registro")

    monkeypatch.setattr(RegistroDeAccesosDjango, "registrar_accion", _falla)
    with pytest.raises(RuntimeError):
        _alta("root@empresa.example")
    assert not Usuario.objects.filter(correo="root@empresa.example").exists()  # todo o nada


def test_el_alta_rechaza_un_correo_largo_o_con_control() -> None:
    with pytest.raises(CommandError, match="no es válido"):
        _alta("a" * 250 + "@empresa.example")
    with pytest.raises(CommandError, match="no es válido"):
        _alta("ro\x00ot@empresa.example")


# --- correo con NUL --------------------------------------------------------------


@pytest.mark.parametrize("correo", ["a\x00b@empresa.example", "a\r\nb@empresa.example", "a" * 300])
def test_un_correo_imposible_da_el_mensaje_generico_y_registra_el_intento(
    cliente: Client, crear_usuario: Callable[..., Usuario], correo: str
) -> None:
    crear_usuario()
    respuesta = _ingresar(cliente, correo=correo)
    assert respuesta.status_code == 200
    assert GENERICO in respuesta.content.decode()
    intento = IntentoIngreso.objects.get()
    assert (intento.motivo, intento.usuario_id) == ("correo_inexistente", None)
    assert intento.huella_correo == huella_de_correo(correo)  # la huella tampoco falla con NUL


def test_el_correo_con_nul_hace_el_mismo_trabajo_de_hash_que_uno_inexistente(
    cliente: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas: list[str] = []
    original = modulo_contrasenas.ServicioContrasenasDjango.verificar_ficticia

    def _espia(self: Any, contrasena: str) -> None:
        llamadas.append("x")
        original(self, contrasena)

    monkeypatch.setattr(modulo_contrasenas.ServicioContrasenasDjango, "verificar_ficticia", _espia)
    _ingresar(cliente, correo="a\x00b@empresa.example")
    _ingresar(cliente, correo="nadie@empresa.example")
    assert llamadas == ["x", "x"]


# --- llave propia de la huella -----------------------------------------------------------


def test_la_huella_usa_la_llave_propia_y_no_secret_key(settings: Any) -> None:
    antes = huella_de_correo(CORREO)
    settings.APP_LLAVE_HUELLA = "otra-llave-distinta-para-la-huella"
    assert huella_de_correo(CORREO) != antes
    settings.SECRET_KEY = "otra-secret-key-que-no-influye-en-la-huella"  # noqa: S105
    assert huella_de_correo(CORREO) == huella_de_correo(normalizar_correo(" ANA@Empresa.Example "))


# --- parametros sensibles ----------------------------------------------------------------


def _sensibles(respuesta: Any) -> tuple[str, ...]:
    """Parametros que `sensitive_post_parameters` marco para ocultar en los reportes de error."""
    return tuple(respuesta.wsgi_request.sensitive_post_parameters)


def test_las_tres_vistas_con_contrasenas_las_marcan_como_sensibles(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario()
    ingreso = _ingresar(cliente)
    assert _sensibles(ingreso) == ("contrasena",)
    propia = cliente.post("/cuenta/contrasena", {"actual": "x", "nueva": "y", "confirmar": "y"})
    assert _sensibles(propia) == ("actual", "nueva", "confirmar")
    temporal = Client()
    crear_usuario(correo="luis@empresa.example", debe_cambiar_contrasena=True)
    _ingresar(temporal, correo="luis@empresa.example")
    obligatoria = temporal.post("/ingresar/contrasena", {"nueva": "y", "confirmar": "y"})
    assert _sensibles(obligatoria) == ("nueva", "confirmar")


# --- cookie `__Host-` --------------------------------------------------------------------


def test_con_la_cookie_host_el_ingreso_sigue_funcionando(
    crear_usuario: Callable[..., Usuario],
) -> None:
    crear_usuario()
    with override_settings(
        SESSION_COOKIE_NAME="__Host-sessionid", SESSION_COOKIE_SECURE=True, SESSION_COOKIE_PATH="/"
    ):
        cliente = Client()
        respuesta = _ingresar(cliente)
        cookie = respuesta.cookies["__Host-sessionid"]
        assert (cookie["secure"], cookie["path"], cookie["domain"]) == (True, "/", "")
        assert cookie["httponly"]
        assert cliente.get("/").status_code == 200


# --- busqueda por Lower(correo) con el indice unico --------------------------------------


def test_la_busqueda_por_correo_usa_lower_y_el_indice_unico(
    crear_usuario: Callable[..., Usuario],
) -> None:
    crear_usuario(correo="ana@empresa.example")
    with CaptureQueriesContext(connection) as consultas:
        encontrada = RepositorioCuentasDjango().por_correo("ana@empresa.example")
    assert encontrada is not None
    sql_ejecutado = consultas.captured_queries[0]["sql"]  # la busqueda; despues vienen los roles
    assert 'LOWER("identidad"."usuario"."correo")' in sql_ejecutado
    assert "ILIKE" not in sql_ejecutado.upper().replace("LOWER", "")
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(
            'EXPLAIN SELECT 1 FROM "identidad"."usuario" WHERE LOWER(correo) = %s',
            ["ana@empresa.example"],
        )
        plan = " ".join(fila[0] for fila in cursor.fetchall())
    assert "usuario_correo_unico_sin_mayusculas" in plan


# --- Argon2 real, rotacion, invalidacion, no-store ---------------------------------------


@override_settings(PASSWORD_HASHERS=ARGON2)
def test_el_ingreso_funciona_con_argon2_real(crear_usuario: Callable[..., Usuario]) -> None:
    from django.contrib.auth.hashers import make_password

    usuario = crear_usuario()
    Usuario.objects.filter(pk=usuario.pk).update(password=make_password(CONTRASENA))
    assert Usuario.objects.get(pk=usuario.pk).password.startswith("argon2$argon2id$")
    cliente = Client()
    assert _ingresar(cliente).status_code == 302
    assert cliente.get("/").status_code == 200
    assert _ingresar(Client(), contrasena="mala").status_code == 200


def _hash_con_parametros_viejos(contrasena: str) -> str:
    viejo = Argon2PasswordHasher()
    viejo.time_cost = 1  # el vigente es 2
    return viejo.encode(contrasena, viejo.salt())


@override_settings(PASSWORD_HASHERS=ARGON2)
def test_con_parametros_viejos_el_hash_se_actualiza_al_ingresar_y_la_sesion_sigue_viva(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    viejo = _hash_con_parametros_viejos(CONTRASENA)
    Usuario.objects.filter(pk=usuario.pk).update(password=viejo)
    primera = Client()
    assert _ingresar(primera).status_code == 302
    actualizado = Usuario.objects.get(pk=usuario.pk)
    assert actualizado.password != viejo
    assert ",t=2," in actualizado.password  # parametros vigentes
    assert check_password(CONTRASENA, actualizado.password)
    sello = actualizado.sello_sesion
    # Otro rehash con la primera sesion abierta: no se cierra (el sello no cambia).
    Usuario.objects.filter(pk=usuario.pk).update(password=viejo)
    assert _ingresar(Client()).status_code == 302
    assert Usuario.objects.get(pk=usuario.pk).sello_sesion == sello
    assert primera.get("/").status_code == 200


def test_el_ingreso_rota_la_sesion(cliente: Client, crear_usuario: Callable[..., Usuario]) -> None:
    crear_usuario()
    previa = cliente.session
    previa["dato"] = "anonimo"
    previa.save()
    clave_anonima = cliente.session.session_key
    _ingresar(cliente)
    assert cliente.session.session_key != clave_anonima  # nueva clave: sin fijacion de sesion
    assert Client().get("/").status_code == 302


def test_cambiar_el_sello_invalida_todas_las_sesiones_del_usuario(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    sesiones = [Client(), Client(), Client()]
    for sesion in sesiones:
        assert _ingresar(sesion).status_code == 302
        assert sesion.get("/").status_code == 200
    RepositorioCuentasDjango().guardar_contrasena(
        str(usuario.pk), usuario.password, temporal=False, ahora=usuario.creado_en
    )
    assert [sesion.get("/").status_code for sesion in sesiones] == [302, 302, 302]


@pytest.mark.parametrize("ruta", ["/ingresar", "/cuenta/contrasena"])
def test_las_pantallas_con_credenciales_no_se_guardan_en_cache(
    cliente: Client, crear_usuario: Callable[..., Usuario], ruta: str
) -> None:
    crear_usuario()
    _ingresar(cliente)
    respuesta = cliente.get(ruta)
    assert "no-store" in respuesta["Cache-Control"]


def test_la_pagina_de_ingreso_y_el_inicio_tampoco(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    assert "no-store" in cliente.get("/ingresar")["Cache-Control"]
    crear_usuario()
    _ingresar(cliente)
    assert "no-store" in cliente.get("/")["Cache-Control"]


def test_el_conteo_del_bloqueo_no_pierde_intentos_concurrentes() -> None:
    """5 fallos a la vez deben bloquear UNA vez: la fila se bloquea (`select_for_update`)."""
    correo = "concurrente@empresa.example"
    creado: dict[str, Any] = {}
    errores: list[BaseException] = []

    def _crear() -> None:
        try:
            from datetime import UTC, datetime

            from django.contrib.auth.hashers import make_password

            creado["pk"] = Usuario.objects.create(
                correo=correo,
                password=make_password(CONTRASENA),
                creado_en=datetime.now(UTC),
            ).pk
        finally:
            connections.close_all()

    def _fallar(barrera: threading.Barrier) -> None:
        try:
            barrera.wait()
            _ingresar(Client(), correo=correo, contrasena="mala")
        except BaseException as error:
            errores.append(error)
        finally:
            connections.close_all()

    def _limpiar() -> None:
        # Los registros son de solo insercion: para borrar los de la prueba se apagan los
        # triggers un instante (la prueba corre con un rol con permiso, nunca la aplicacion).
        try:
            with connection.cursor() as cursor:
                for tabla in ("intento_ingreso", "accion_cuenta"):
                    cursor.execute(f'ALTER TABLE "identidad"."{tabla}" DISABLE TRIGGER USER')
                    cursor.execute(f'DELETE FROM "identidad"."{tabla}"')  # noqa: S608
                    cursor.execute(f'ALTER TABLE "identidad"."{tabla}" ENABLE TRIGGER USER')
                # Los eventos que publicaron esas filas.
                cursor.execute('DELETE FROM "nucleo"."entrega_outbox"')
                cursor.execute('DELETE FROM "nucleo"."evento_outbox"')
                cursor.execute('DELETE FROM "identidad"."usuario" WHERE correo = %s', [correo])
        finally:
            connections.close_all()

    hilo = threading.Thread(target=_crear)
    hilo.start()
    hilo.join()
    try:
        barrera = threading.Barrier(5)
        hilos = [threading.Thread(target=_fallar, args=(barrera,)) for _ in range(5)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        assert errores == []
        resultado: dict[str, Any] = {}

        def _leer() -> None:
            try:
                usuario = Usuario.objects.get(pk=creado["pk"])
                resultado["fallos"] = usuario.fallos_contrasena
                resultado["bloqueada"] = usuario.bloqueada_hasta
                resultado["bloqueos"] = AccionCuenta.objects.filter(accion="bloqueo").count()
                resultado["intentos"] = IntentoIngreso.objects.count()
            finally:
                connections.close_all()

        lector = threading.Thread(target=_leer)
        lector.start()
        lector.join()
        assert resultado["intentos"] == 5
        assert resultado["bloqueos"] == 1
        assert resultado["bloqueada"] is not None
        assert resultado["fallos"] == 0
    finally:
        limpiador = threading.Thread(target=_limpiar)
        limpiador.start()
        limpiador.join()


# --- y ----------------------------------------------------------------------------


def test_el_hash_ficticio_se_genera_al_arrancar_la_aplicacion() -> None:
    from django.apps import apps

    modulo_contrasenas.hash_ficticio.cache_clear()
    apps.get_app_config("identidad").ready()
    assert modulo_contrasenas.hash_ficticio.cache_info().currsize == 1


@pytest.mark.parametrize("tabla", ["intento_ingreso", "accion_cuenta"])
def test_los_registros_rechazan_truncate(tabla: str) -> None:
    with (
        pytest.raises(Exception, match="solo inserción"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(f'TRUNCATE "identidad"."{tabla}"')


def test_los_registros_siguen_rechazando_update_y_delete_por_fila(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    fila = AccionCuenta.objects.create(
        accion="alta", usuario_objetivo_id=usuario.id, ocurrido_en=usuario.creado_en
    )
    with pytest.raises(Exception, match="solo inserción"), transaction.atomic():
        AccionCuenta.objects.filter(pk=fila.pk).update(accion="bloqueo")
    with pytest.raises(Exception, match="solo inserción"), transaction.atomic():
        fila.delete()


# --- Ronda 3: todo cambio de contrasena rota el sello; no se refleja un correo invalido -----


def test_set_password_y_save_cierran_las_sesiones_abiertas(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    usuario = crear_usuario()
    _ingresar(cliente)
    assert cliente.get("/").status_code == 200
    sello = usuario.sello_sesion
    usuario.set_password("otra-frase-larga-77Sol")
    usuario.save()
    assert Usuario.objects.get(pk=usuario.pk).sello_sesion != sello
    assert cliente.get("/").status_code == 302


def test_changepassword_del_servidor_cierra_las_sesiones_abiertas(
    crear_usuario: Callable[..., Usuario], monkeypatch: pytest.MonkeyPatch
) -> None:
    crear_usuario()
    sesiones = [Client(), Client()]
    for sesion in sesiones:
        _ingresar(sesion)
        assert sesion.get("/").status_code == 200
    claves = iter(["otra-frase-larga-77Sol"] * 2)
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: next(claves))
    call_command("changepassword", CORREO, stdout=StringIO())
    assert [sesion.get("/").status_code for sesion in sesiones] == [302, 302]
    assert _ingresar(Client(), contrasena="otra-frase-larga-77Sol").status_code == 302


@override_settings(PASSWORD_HASHERS=ARGON2)
def test_el_rehash_por_actualizar_hash_no_rota_el_sello_y_la_sesion_sigue_en_200(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    usuario = crear_usuario()
    _ingresar(cliente)
    antes = Usuario.objects.get(pk=usuario.pk)
    RepositorioCuentasDjango().actualizar_hash(str(usuario.pk), _hash_con_parametros_viejos("x"))
    despues = Usuario.objects.get(pk=usuario.pk)
    assert despues.password != antes.password
    assert despues.sello_sesion == antes.sello_sesion
    assert cliente.get("/").status_code == 200


def test_guardar_contrasena_rota_el_sello_exactamente_una_vez(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    usuario = crear_usuario()
    _ingresar(cliente)
    antes = Usuario.objects.get(pk=usuario.pk).sello_sesion
    RepositorioCuentasDjango().guardar_contrasena(
        str(usuario.pk), usuario.password, temporal=False, ahora=usuario.creado_en
    )
    despues = Usuario.objects.get(pk=usuario.pk).sello_sesion
    assert despues != antes
    assert cliente.get("/").status_code == 302
    # Ingresar de nuevo con el sello nuevo funciona, y el rehash posterior no lo vuelve a mover.
    nuevo = Client()
    assert _ingresar(nuevo).status_code == 302
    assert Usuario.objects.get(pk=usuario.pk).sello_sesion == despues
    assert nuevo.get("/").status_code == 200


@pytest.mark.parametrize("correo", ["a\x00b@empresa.example", "a\x07b@empresa.example", "a" * 300])
def test_un_correo_invalido_no_se_refleja_en_el_formulario(
    cliente: Client, crear_usuario: Callable[..., Usuario], correo: str
) -> None:
    crear_usuario()
    pagina = _ingresar(cliente, correo=correo).content.decode()
    assert GENERICO in pagina
    assert 'name="correo"' in pagina
    assert 'value=""' in pagina
    assert "\x00" not in pagina
    assert "a" * 300 not in pagina


def test_un_correo_valido_si_se_conserva_para_reintentar(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario()
    pagina = _ingresar(cliente, correo="otra@empresa.example", contrasena="mala").content.decode()
    assert 'value="otra@empresa.example"' in pagina
