"""Gestion de usuarios contra PostgreSQL: atomicidad, concurrencia y restricciones.

* Atomicidad: cada accion del Administrador es UNA transaccion (`composicion._atomico`); si falla
  el ultimo paso (el registro de la accion), no queda nada a medias.
* Concurrencia: dos peticiones simultaneas no pueden duplicar un correo ni dejar al sistema sin
  Administradores activos. Corren con hilos y conexiones reales (no caben en la transaccion de la
  prueba), igual que las del ingreso y del segundo factor.
* Restricciones de la base y la traduccion de cada `IntegrityError` a un error de dominio.
"""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from django.db import IntegrityError, OperationalError, connection, connections, transaction

from identidad.adaptadores.entrada import composicion
from identidad.adaptadores.entrada.middleware import actor_de
from identidad.adaptadores.salida.modelos import AccionCuenta, Rol, Usuario, UsuarioRol
from identidad.adaptadores.salida.repositorios import (
    RegistroDeAccesosDjango,
    RepositorioCuentasDjango,
)
from identidad.aplicacion.crear_administrador import AltaInvalida
from identidad.aplicacion.crear_usuario import UsuarioCreado
from identidad.aplicacion.errores import ConflictoDeUsuario
from identidad.dominio.acceso import AccionDeCuenta
from nucleo.actor import Actor

pytestmark = pytest.mark.django_db

AHORA = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def _usuario(correo: str, *roles: str, **campos: Any) -> Usuario:
    """Crea un usuario con roles; sirve dentro de la prueba y dentro de un hilo."""
    usuario = Usuario.objects.create(
        correo=correo,
        password="x",  # noqa: S106  # nosec B106  # no se usa para ingresar
        creado_en=AHORA,
        **campos,
    )
    for rol in Rol.objects.filter(codigo__in=roles):
        UsuarioRol.objects.create(usuario=usuario, rol=rol, asignado_en=AHORA)
    return usuario


def _actor(usuario: Usuario, *roles: str) -> Actor:
    return Actor.de(str(usuario.id), roles or ["administrador"])


class _Falla(Exception):
    """Fallo forzado del ultimo paso de una accion."""


@pytest.fixture
def fallar_registro(monkeypatch: pytest.MonkeyPatch) -> Callable[[AccionDeCuenta], None]:
    """Hace que `registrar_accion` falle para UNA accion; las demas se registran normal."""

    def _instalar(accion_que_falla: AccionDeCuenta) -> None:
        original = RegistroDeAccesosDjango.registrar_accion

        def registrar(
            self: RegistroDeAccesosDjango, *, accion: AccionDeCuenta, **resto: Any
        ) -> None:
            if accion is accion_que_falla:
                raise _Falla
            original(self, accion=accion, **resto)

        monkeypatch.setattr(RegistroDeAccesosDjango, "registrar_accion", registrar)

    return _instalar


# --- (a) Atomicidad: si falla el ultimo paso, no queda nada a medias -----------------------------


def test_editar_datos_y_roles_se_revierten_juntos(
    fallar_registro: Callable[[AccionDeCuenta], None],
) -> None:
    admin = _usuario("admin@n.co", "administrador")
    juan = _usuario("juan@n.co", "usuario", nombre="Juan")
    sello = juan.sello_sesion
    fallar_registro(AccionDeCuenta.CAMBIO_DE_ROLES)  # el ultimo paso del cambio
    with pytest.raises(_Falla):
        composicion.editar_usuario()(_actor(admin), str(juan.id), nombre="Otro", roles=["auditor"])
    juan.refresh_from_db()
    assert (juan.nombre, juan.sello_sesion) == ("Juan", sello)
    assert set(juan.roles.values_list("codigo", flat=True)) == {"usuario"}
    assert not AccionCuenta.objects.exists()  # ni el cambio de datos ni el de roles


def test_alta_desactivacion_y_restablecimiento_se_revierten(
    fallar_registro: Callable[[AccionDeCuenta], None],
) -> None:
    admin = _usuario("admin@n.co", "administrador")
    otro = _usuario("otro@n.co", "administrador")
    ana = _usuario("ana@n.co", "usuario")
    contrasena = ana.password
    # `fallar_registro` reemplaza al anterior: se prueba una accion a la vez.
    fallar_registro(AccionDeCuenta.ALTA)
    with pytest.raises(_Falla):
        composicion.crear_usuario()(
            _actor(admin),
            correo="nueva@n.co",
            nombre="N",
            roles=["auditor"],
        )
    assert not Usuario.objects.filter(correo="nueva@n.co").exists()
    fallar_registro(AccionDeCuenta.DESACTIVACION)
    sello = ana.sello_sesion
    with pytest.raises(_Falla):
        composicion.desactivar_usuario()(_actor(admin), str(ana.id))
    ana.refresh_from_db()
    assert ana.activo and ana.sello_sesion == sello
    fallar_registro(AccionDeCuenta.RESTABLECIMIENTO_CONTRASENA)
    with pytest.raises(_Falla):
        composicion.restablecer_contrasena()(_actor(admin), str(otro.id))
    otro.refresh_from_db()
    assert otro.password == "x"  # noqa: S105  # no cambio  # nosec B105
    assert contrasena == ana.password


# --- (b) Concurrencia: hilos y conexiones reales -----------------------------------------------


def _en_hilo[T](accion: Callable[[], T]) -> T:
    salida: list[T] = []
    errores: list[BaseException] = []

    def _correr() -> None:
        try:
            salida.append(accion())
        except BaseException as error:
            errores.append(error)
        finally:
            connections.close_all()

    hilo = threading.Thread(target=_correr)
    hilo.start()
    hilo.join()
    if errores:
        raise errores[0]
    return salida[0]


def _en_paralelo(tareas: list[Callable[[], Any]]) -> list[Any]:
    """Corre las tareas a la vez; devuelve su resultado o la excepcion que lanzaron."""
    barrera = threading.Barrier(len(tareas))
    resultados: list[Any] = [None] * len(tareas)

    def _hilo(i: int) -> None:
        try:
            barrera.wait()
            resultados[i] = tareas[i]()
        except BaseException as error:
            resultados[i] = error
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=_hilo, args=(i,)) for i in range(len(tareas))]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    return resultados


def _limpiar() -> None:
    """Borra lo que crearon los hilos (estan fuera de la transaccion de la prueba)."""
    try:
        with connection.cursor() as cursor:
            for tabla in ("intento_ingreso", "accion_cuenta"):
                cursor.execute(f'ALTER TABLE "identidad"."{tabla}" DISABLE TRIGGER USER')
                cursor.execute(f'DELETE FROM "identidad"."{tabla}"')  # noqa: S608
                cursor.execute(f'ALTER TABLE "identidad"."{tabla}" ENABLE TRIGGER USER')
            # Los eventos que publicaron esas filas (outbox).
            cursor.execute('DELETE FROM "nucleo"."entrega_outbox"')
            cursor.execute('DELETE FROM "nucleo"."evento_outbox"')
            for tabla in ("segundo_factor", "usuario_rol", "usuario"):
                cursor.execute(f'DELETE FROM "identidad"."{tabla}"')  # noqa: S608
    finally:
        connections.close_all()


@pytest.fixture
def limpieza_de_hilos() -> Any:
    yield
    _en_hilo(_limpiar)


def _solo(resultados: list[Any], tipo: type) -> list[Any]:
    return [r for r in resultados if isinstance(r, tipo)]


def test_el_mismo_correo_en_altas_simultaneas_crea_un_solo_usuario(limpieza_de_hilos: Any) -> None:
    admin = _en_hilo(lambda: _actor(_usuario("admin@n.co", "administrador")))

    def alta() -> UsuarioCreado:
        return composicion.crear_usuario()(
            admin, correo="Nuevo@N.co", nombre="N", roles=["auditor"]
        )

    resultados = _en_paralelo([alta] * 4)
    assert len(_solo(resultados, UsuarioCreado)) == 1
    assert len(_solo(resultados, ConflictoDeUsuario)) == 3, resultados
    assert _en_hilo(lambda: Usuario.objects.filter(correo__iexact="nuevo@n.co").count()) == 1


def _dos_administradores() -> tuple[Actor, str, Actor, str]:
    a = _usuario("a@n.co", "administrador")
    b = _usuario("b@n.co", "administrador")
    return _actor(a), str(a.id), _actor(b), str(b.id)


def _administradores_activos() -> int:
    return Usuario.objects.filter(activo=True, asignaciones__rol_id="administrador").count()


def test_dos_administradores_que_se_desactivan_a_la_vez_dejan_uno_activo(
    limpieza_de_hilos: Any,
) -> None:
    actor_a, id_a, actor_b, id_b = _en_hilo(_dos_administradores)
    resultados = _en_paralelo(
        [
            lambda: composicion.desactivar_usuario()(actor_a, id_b),
            lambda: composicion.desactivar_usuario()(actor_b, id_a),
        ]
    )
    assert resultados.count(True) == 1
    errores = _solo(resultados, ConflictoDeUsuario)
    assert len(errores) == 1 and "al menos un administrador activo" in str(errores[0]), resultados
    assert _en_hilo(_administradores_activos) == 1


def test_dos_administradores_que_se_degradan_a_la_vez_dejan_uno(limpieza_de_hilos: Any) -> None:
    actor_a, id_a, actor_b, id_b = _en_hilo(_dos_administradores)

    def degradar(actor: Actor, objetivo: str) -> Callable[[], Any]:
        return lambda: composicion.editar_usuario()(actor, objetivo, nombre="X", roles=["auditor"])

    resultados = _en_paralelo([degradar(actor_a, id_b), degradar(actor_b, id_a)])
    assert len(_solo(resultados, ConflictoDeUsuario)) == 1, resultados
    assert _en_hilo(_administradores_activos) == 1


def test_bloquear_administradores_espera_a_quien_ya_los_bloqueo(limpieza_de_hilos: Any) -> None:
    """Prueba directa del bloqueo: mientras una transaccion los tiene, otra no puede tomarlos."""
    _en_hilo(_dos_administradores)
    tomados, soltar = threading.Event(), threading.Event()
    salida: dict[str, Any] = {}

    def dueno() -> None:
        try:
            with transaction.atomic():
                salida["ids"] = RepositorioCuentasDjango().bloquear_administradores_activos()
                tomados.set()
                soltar.wait(timeout=10)
        finally:
            connections.close_all()

    def aspirante() -> None:
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '300ms'")
                RepositorioCuentasDjango().bloquear_administradores_activos()
        except OperationalError as error:
            salida["error"] = error
        finally:
            connections.close_all()

    primero = threading.Thread(target=dueno)
    primero.start()
    assert tomados.wait(timeout=10)
    segundo = threading.Thread(target=aspirante)
    segundo.start()
    segundo.join()
    soltar.set()
    primero.join()
    assert len(salida["ids"]) == 2
    assert "error" in salida  # no pudo tomarlos mientras el otro los tenia


# --- (c) Restricciones y traduccion de errores ----------------------------------------------------


def test_el_correo_es_unico_sin_distinguir_mayusculas_en_la_base() -> None:
    _usuario("ana@n.co", "usuario")
    with pytest.raises(IntegrityError), transaction.atomic():
        _usuario("ANA@n.co", "usuario")


def test_el_adaptador_traduce_el_correo_repetido_a_un_error_de_dominio() -> None:
    _usuario("a@n.co", "usuario")
    with pytest.raises(AltaInvalida):  # correo repetido, sin distinguir mayusculas
        RepositorioCuentasDjango().crear(
            correo="A@N.CO",
            hash_contrasena="x",
            roles=frozenset(),
            temporal=True,
            ahora=AHORA,
        )


def test_actor_de_resuelve_los_roles_con_una_consulta(django_assert_num_queries: Any) -> None:
    ana = _usuario("ana@n.co", "auditor", "usuario")
    with django_assert_num_queries(1):  # roles
        actor = actor_de(ana)
    assert actor.roles == frozenset({"auditor", "usuario"})


# --- Datos que no se imprimen ---------------------------------------------------------------------


def test_la_contrasena_temporal_no_sale_en_el_repr() -> None:
    creado = UsuarioCreado(id="u", correo="a@n.co", temporal="Secreta-Temporal-123")
    assert "Secreta" not in repr(creado) and "a@n.co" in repr(creado)


# --- Pantallas de solo lectura: HEAD -------------------------------------------------------------


def test_las_pantallas_de_solo_lectura_aceptan_head(admin_cliente: Any) -> None:
    ana = _usuario("ana@n.co", "auditor")
    for ruta in ("/admin/usuarios", "/admin/usuarios/nuevo", f"/admin/usuarios/{ana.id}"):
        assert admin_cliente.head(ruta).status_code == 200
    assert admin_cliente.head(f"/admin/usuarios/{ana.id}/desactivar").status_code == 405
