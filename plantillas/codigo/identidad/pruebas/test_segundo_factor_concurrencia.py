"""El mismo codigo en peticiones SIMULTANEAS abre una sola sesion.

Sin bloqueo de la fila, dos peticiones que llegan a la vez con el mismo codigo leerian el mismo
`ultimo_paso_aceptado` y las dos entrarian. El caso de uso bloquea la fila del usuario
(`select_for_update`) y el adaptador la del segundo factor, asi que la segunda ve el paso ya usado.

Corre con hilos y conexiones reales (no puede ir dentro de la transaccion de la prueba), igual
que la prueba de concurrencia del bloqueo por contrasena en `test_endurecimiento.py`.
"""

import re
import secrets
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connection, connections
from django.test import Client
from django.test.utils import CaptureQueriesContext

from identidad.adaptadores.salida.cifrado import CifradoDeSecretos
from identidad.adaptadores.salida.modelos import Rol, SegundoFactor, Usuario, UsuarioRol
from identidad.adaptadores.salida.segundo_factor import VerificadorTotp, codigo_del_paso
from identidad.dominio.segundo_factor import ResultadoCodigo, paso_de
from identidad.pruebas.conftest import CONTRASENA

pytestmark = pytest.mark.django_db

CORREO = "concurrente-codigo@empresa.example"
HILOS = 4


def test_el_mismo_codigo_en_peticiones_simultaneas_abre_una_sola_sesion(settings: Any) -> None:
    secreto = secrets.token_bytes(20)
    creado: dict[str, Any] = {}
    errores: list[BaseException] = []

    def _preparar() -> None:
        try:
            ahora = datetime.now(UTC)
            usuario = Usuario.objects.create(
                correo=CORREO, password=make_password(CONTRASENA), creado_en=ahora
            )
            UsuarioRol.objects.create(
                usuario=usuario, rol=Rol.objects.get(codigo="auditor"), asignado_en=ahora
            )
            cifrado = CifradoDeSecretos(settings.APP_LLAVE_SEGUNDO_FACTOR)
            hace_un_dia = ahora - timedelta(days=1)
            SegundoFactor.objects.create(
                usuario=usuario,
                secreto_cifrado=cifrado.cifrar(secreto, str(usuario.id)),
                llave_id=cifrado.llave_id,
                creado_en=hace_un_dia,
                confirmado_en=hace_un_dia,
                ultimo_paso_aceptado=paso_de(hace_un_dia),
            )
            creado["pk"] = usuario.pk
        finally:
            connections.close_all()

    resultados: list[tuple[int, str]] = []

    def _entrar(barrera: threading.Barrier, codigo: str) -> None:
        try:
            cliente = Client()
            respuesta = cliente.post("/ingresar", {"correo": CORREO, "contrasena": CONTRASENA})
            assert respuesta["Location"] == "/ingresar/codigo"
            barrera.wait()  # todos mandan el codigo al mismo tiempo
            final = cliente.post("/ingresar/codigo", {"codigo": codigo})
            resultados.append((final.status_code, final.get("Location", "")))
        except BaseException as error:
            errores.append(error)
        finally:
            connections.close_all()

    def _limpiar() -> None:
        # Los registros son de solo insercion: se apagan los triggers un instante (la prueba corre
        # con un rol con permiso, nunca la aplicacion).
        try:
            with connection.cursor() as cursor:
                for tabla in ("intento_ingreso", "accion_cuenta"):
                    cursor.execute(f'ALTER TABLE "identidad"."{tabla}" DISABLE TRIGGER USER')
                    cursor.execute(f'DELETE FROM "identidad"."{tabla}"')  # noqa: S608
                    cursor.execute(f'ALTER TABLE "identidad"."{tabla}" ENABLE TRIGGER USER')
                # Los eventos que publicaron esas filas.
                cursor.execute('DELETE FROM "nucleo"."entrega_outbox"')
                cursor.execute('DELETE FROM "nucleo"."evento_outbox"')
                cursor.execute('DELETE FROM "identidad"."segundo_factor"')
                cursor.execute(
                    'DELETE FROM "identidad"."usuario_rol" WHERE usuario_id = %s', [creado["pk"]]
                )
                cursor.execute('DELETE FROM "identidad"."usuario" WHERE correo = %s', [CORREO])
        finally:
            connections.close_all()

    preparador = threading.Thread(target=_preparar)
    preparador.start()
    preparador.join()
    assert "pk" in creado
    try:
        codigo = codigo_del_paso(secreto, paso_de(datetime.now(UTC)))
        barrera = threading.Barrier(HILOS)
        hilos = [threading.Thread(target=_entrar, args=(barrera, codigo)) for _ in range(HILOS)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        assert errores == []
        # Exactamente UNA peticion entro (302 a "/"); las demas fueron rechazadas (422).
        assert sorted(resultados) == sorted([(302, "/")] + [(422, "")] * (HILOS - 1))
    finally:
        limpiador = threading.Thread(target=_limpiar)
        limpiador.start()
        limpiador.join()


# --- Sin transaccion externa: el adaptador bloquea por si mismo y no duplica ---
#
# Estas pruebas corren cada operacion en un HILO nuevo, sin transaccion abierta (autocommit, como
# lo llamaria un script o un worker). El bloqueo NO puede depender de quien llama.


def _en_hilo[T](accion: Callable[[], T]) -> T:
    """Corre `accion` en un hilo con su propia conexion y devuelve su resultado (o su error)."""
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


def _crear_usuario_de_finanzas(correo: str, secreto: bytes | None, llave: str) -> str:
    """Crea un usuario `finanzas` (con su segundo factor ya confirmado si hay `secreto`)."""
    ahora = datetime.now(UTC)
    usuario = Usuario.objects.create(
        correo=correo, password=make_password(CONTRASENA), creado_en=ahora
    )
    UsuarioRol.objects.create(
        usuario=usuario, rol=Rol.objects.get(codigo="auditor"), asignado_en=ahora
    )
    if secreto is not None:
        cifrado = CifradoDeSecretos(llave)
        antes = ahora - timedelta(days=1)
        SegundoFactor.objects.create(
            usuario=usuario,
            secreto_cifrado=cifrado.cifrar(secreto, str(usuario.id)),
            llave_id=cifrado.llave_id,
            creado_en=antes,
            confirmado_en=antes,
            ultimo_paso_aceptado=paso_de(antes),
        )
    return str(usuario.id)


def _borrar_usuario(correo: str) -> None:
    # Los registros son de solo insercion: se apagan los triggers un instante (como arriba).
    with connection.cursor() as cursor:
        for tabla in ("intento_ingreso", "accion_cuenta"):
            cursor.execute(f'ALTER TABLE "identidad"."{tabla}" DISABLE TRIGGER USER')
            cursor.execute(f'DELETE FROM "identidad"."{tabla}"')  # noqa: S608
            cursor.execute(f'ALTER TABLE "identidad"."{tabla}" ENABLE TRIGGER USER')
        # Los eventos que publicaron esas filas.
        cursor.execute('DELETE FROM "nucleo"."entrega_outbox"')
        cursor.execute('DELETE FROM "nucleo"."evento_outbox"')
        cursor.execute('DELETE FROM "identidad"."segundo_factor"')
        cursor.execute(
            'DELETE FROM "identidad"."usuario_rol" WHERE usuario_id IN '
            '(SELECT id FROM "identidad"."usuario" WHERE correo = %s)',
            [correo],
        )
        cursor.execute('DELETE FROM "identidad"."usuario" WHERE correo = %s', [correo])


@contextmanager
def _usuario_temporal(correo: str, secreto: bytes | None, llave: str) -> Iterator[str]:
    usuario_id = _en_hilo(lambda: _crear_usuario_de_finanzas(correo, secreto, llave))
    try:
        yield usuario_id
    finally:
        _en_hilo(lambda: _borrar_usuario(correo))


def _simultaneos[T](cantidad: int, accion: Callable[[], T]) -> list[T]:
    """Lanza `accion` en `cantidad` hilos que arrancan a la vez (barrera) y junta los resultados."""
    barrera = threading.Barrier(cantidad)
    resultados: list[T] = []
    errores: list[BaseException] = []

    def _correr() -> None:
        try:
            barrera.wait()
            resultados.append(accion())
        except BaseException as error:
            errores.append(error)
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=_correr) for _ in range(cantidad)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert errores == []
    return resultados


def test_verificar_sin_transaccion_externa_bloquea_la_fila(settings: Any) -> None:
    """`select_for_update` va SIEMPRE, aunque quien llama no abrio una transaccion."""
    secreto = secrets.token_bytes(20)

    def _verificar_y_capturar(usuario_id: str) -> tuple[bool, ResultadoCodigo, list[str]]:
        ahora = datetime.now(UTC)
        sin_transaccion = not connection.in_atomic_block
        with CaptureQueriesContext(connection) as consultas:
            resultado = VerificadorTotp().verificar(
                usuario_id, codigo_del_paso(secreto, paso_de(ahora)), ahora, confirmando=False
            )
        return sin_transaccion, resultado, [c["sql"] for c in consultas.captured_queries]

    llave = settings.APP_LLAVE_SEGUNDO_FACTOR
    with _usuario_temporal("bloqueo-fila@empresa.example", secreto, llave) as usuario_id:
        sin_transaccion, resultado, sql = _en_hilo(lambda: _verificar_y_capturar(usuario_id))
    assert sin_transaccion  # de verdad no habia transaccion externa
    assert resultado is ResultadoCodigo.ACEPTADO
    assert any("FOR UPDATE" in consulta for consulta in sql)


def test_el_mismo_codigo_en_hilos_simultaneos_sin_transaccion_externa_solo_lo_acepta_uno(
    settings: Any,
) -> None:
    """/: el un-solo-uso lo garantiza el adaptador, no el llamador."""
    secreto = secrets.token_bytes(20)
    llave = settings.APP_LLAVE_SEGUNDO_FACTOR
    with _usuario_temporal("un-solo-uso@empresa.example", secreto, llave) as usuario_id:
        ahora = datetime.now(UTC)
        codigo = codigo_del_paso(secreto, paso_de(ahora))
        resultados = _simultaneos(
            HILOS,
            lambda: VerificadorTotp().verificar(usuario_id, codigo, ahora, confirmando=False),
        )
    assert sorted(resultado.name for resultado in resultados) == sorted(
        [ResultadoCodigo.ACEPTADO.name] + [ResultadoCodigo.REPETIDO.name] * (HILOS - 1)
    )


def test_iniciar_el_enrolamiento_en_hilos_simultaneos_crea_un_solo_secreto(settings: Any) -> None:
    """en el adaptador: varias peticiones a la vez no chocan ni crean dos secretos."""
    correo = "enrolar-simultaneo@empresa.example"
    with _usuario_temporal(correo, None, settings.APP_LLAVE_SEGUNDO_FACTOR) as usuario_id:
        ahora = datetime.now(UTC)
        enrolamientos = _simultaneos(
            HILOS, lambda: VerificadorTotp().iniciar_enrolamiento(usuario_id, correo, ahora)
        )
        filas = _en_hilo(lambda: SegundoFactor.objects.filter(usuario_id=usuario_id).count())
    assert filas == 1
    assert len({enrolamiento.clave for enrolamiento in enrolamientos}) == 1  # todos, la misma


def test_dos_get_simultaneos_a_enrolar_ven_la_misma_clave_y_se_crea_un_solo_secreto(
    settings: Any,
) -> None:
    """(HTTP): dos GET a `/ingresar/enrolar` a la vez; ninguno falla y comparten el secreto."""
    correo = "get-doble@empresa.example"
    with _usuario_temporal(correo, None, settings.APP_LLAVE_SEGUNDO_FACTOR) as usuario_id:

        def _abrir_etapa() -> Client:
            cliente = Client()
            respuesta = cliente.post("/ingresar", {"correo": correo, "contrasena": CONTRASENA})
            assert respuesta["Location"] == "/ingresar/enrolar"
            return cliente

        clientes = [_en_hilo(_abrir_etapa) for _ in range(2)]
        paginas = _simultaneos_con_clientes(clientes)
        filas = _en_hilo(lambda: SegundoFactor.objects.filter(usuario_id=usuario_id).count())
    assert [estado for estado, _ in paginas] == [200, 200]
    claves = set()
    for _, pagina in paginas:
        coincidencia = re.search(r'<code id="clave">([^<]+)</code>', pagina)
        assert coincidencia
        claves.add(coincidencia.group(1))
    assert len(claves) == 1
    assert filas == 1


def _simultaneos_con_clientes(clientes: list[Client]) -> list[tuple[int, str]]:
    """Cada cliente pide `/ingresar/enrolar` en su hilo, todos a la vez."""
    barrera = threading.Barrier(len(clientes))
    paginas: list[tuple[int, str]] = []
    errores: list[BaseException] = []

    def _pedir(cliente: Client) -> None:
        try:
            barrera.wait()
            respuesta = cliente.get("/ingresar/enrolar")
            paginas.append((respuesta.status_code, respuesta.content.decode()))
        except BaseException as error:
            errores.append(error)
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=_pedir, args=(cliente,)) for cliente in clientes]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert errores == []
    return paginas
