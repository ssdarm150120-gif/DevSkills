"""El aviso por reuso, con peticiones SIMULTANEAS.

Corre con hilos y conexiones reales (no puede ir dentro de la transaccion de la prueba), igual que
`test_segundo_factor_concurrencia.py`. Dos riesgos:

* Dos pestañas abren el inicio a la vez: el aviso no debe salir dos veces.
* Un intento nuevo llega ENTRE la lectura y la marca: no debe darse por visto sin haberse mostrado.
  Por eso la marca es el ID del ultimo intento mostrado (el nuevo tiene un id mayor).

El inicio lee SIN bloqueo y solo toma el bloqueo si hay un aviso pendiente (con una segunda
comprobacion): aqui todas las pestañas ven el pendiente al mismo tiempo y aun asi sale una vez.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connection, connections, transaction

from identidad.adaptadores.entrada import composicion
from identidad.adaptadores.salida.avisos_reuso import (
    AvisosDeReusoDjango,
    ZonaHorariaDeConfiguracion,
)
from identidad.adaptadores.salida.modelos import IntentoIngreso, Usuario
from identidad.aplicacion.avisos_pendientes import AvisosPendientes
from identidad.dominio.aviso_reuso import AvisoDeReuso, IntentoDeReuso
from identidad.pruebas.conftest import CONTRASENA
from nucleo.actor import Actor

pytestmark = pytest.mark.django_db

CORREO = "concurrente-aviso@empresa.example"
HILOS = 4
ESPERA = 10.0  # segundos: una prueba que se queda esperando falla, no se cuelga


def _en_un_hilo[T](trabajo: Callable[[], T]) -> T:
    """Corre `trabajo` en un hilo propio (su propia conexion, que se cierra) y devuelve su valor."""
    resultado: list[T] = []
    errores: list[BaseException] = []

    def _correr() -> None:
        try:
            resultado.append(trabajo())
        except BaseException as error:
            errores.append(error)
        finally:
            connections.close_all()

    hilo = threading.Thread(target=_correr)
    hilo.start()
    hilo.join()
    if errores:
        raise errores[0]
    return resultado[0]


def _insertar_intento(usuario_id: Any, momento: datetime) -> int:
    return IntentoIngreso.objects.create(
        usuario_id=usuario_id,
        huella_correo="0" * 64,
        factor="codigo",
        resultado="fallido",
        motivo="codigo_repetido",
        ip="203.0.113.9",
        ocurrido_en=momento,
    ).pk


def _limpiar() -> None:
    # Los registros son de solo insercion: se apagan los triggers un instante (la prueba corre con
    # un rol con permiso, nunca la aplicacion).
    try:
        with connection.cursor() as cursor:
            cursor.execute('ALTER TABLE "identidad"."intento_ingreso" DISABLE TRIGGER USER')
            cursor.execute('DELETE FROM "identidad"."intento_ingreso"')
            cursor.execute('ALTER TABLE "identidad"."intento_ingreso" ENABLE TRIGGER USER')
            cursor.execute('DELETE FROM "identidad"."usuario" WHERE correo = %s', [CORREO])
    finally:
        connections.close_all()


@contextmanager
def _usuario_con_un_reuso(momento: datetime) -> Iterator[Actor]:
    """Un usuario CONFIRMADO en la base (otra conexion), con un intento de reuso en `momento`."""

    def _preparar() -> Actor:
        usuario = Usuario.objects.create(
            correo=CORREO, password=make_password(CONTRASENA), creado_en=momento
        )
        _insertar_intento(usuario.id, momento)
        return Actor.de(str(usuario.id), ["usuario"])

    actor = _en_un_hilo(_preparar)
    try:
        yield actor
    finally:
        _en_un_hilo(_limpiar)


def _pedir_aviso(actor: Actor) -> AvisoDeReuso | None:
    """Lo que hace la vista del inicio: el caso de uso dentro de una transaccion."""
    with transaction.atomic():
        return composicion.avisos_pendientes()(actor)


def test_dos_pestanas_a_la_vez_muestran_el_aviso_una_sola_vez() -> None:
    momento = datetime(2026, 10, 12, 18, 0, tzinfo=UTC)
    with _usuario_con_un_reuso(momento) as actor:
        barrera = threading.Barrier(HILOS)
        avisos: list[AvisoDeReuso | None] = []
        errores: list[BaseException] = []

        def _abrir_el_inicio() -> None:
            try:
                barrera.wait(ESPERA)  # todas abren el inicio al mismo tiempo
                avisos.append(_pedir_aviso(actor))
            except BaseException as error:
                errores.append(error)
            finally:
                connections.close_all()

        hilos = [threading.Thread(target=_abrir_el_inicio) for _ in range(HILOS)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        assert errores == []
        mostrados = [aviso for aviso in avisos if aviso is not None]
        assert len(avisos) == HILOS
        assert len(mostrados) == 1  # exactamente UNA pestaña lo ve
        assert mostrados[0].ocurrido_en == momento


class _AvisosQueSeDetienen:
    """El adaptador real, con una pausa justo antes de marcar: aqui llega el intento nuevo."""

    def __init__(self) -> None:
        self.real = AvisosDeReusoDjango()
        self.leyo = threading.Event()
        self.continuar = threading.Event()

    def marca(self, usuario_id: str) -> int | None:
        return self.real.marca(usuario_id)

    def bloquear_marca(self, usuario_id: str) -> int | None:
        return self.real.bloquear_marca(usuario_id)

    def ultimo_intento_de_reuso(
        self, usuario_id: str, *, despues_de: int | None
    ) -> IntentoDeReuso | None:
        return self.real.ultimo_intento_de_reuso(usuario_id, despues_de=despues_de)

    def marcar_visto(self, usuario_id: str, *, hasta_id: int) -> None:
        self.leyo.set()  # ya leyo el intento; todavia no marca
        assert self.continuar.wait(ESPERA)
        self.real.marcar_visto(usuario_id, hasta_id=hasta_id)


def test_un_intento_que_llega_entre_la_lectura_y_la_marca_no_se_pierde() -> None:
    primero = datetime.now(UTC) - timedelta(minutes=5)
    with _usuario_con_un_reuso(primero) as actor:
        avisos = _AvisosQueSeDetienen()
        caso = AvisosPendientes(avisos, ZonaHorariaDeConfiguracion())
        mostrado: list[AvisoDeReuso | None] = []
        errores: list[BaseException] = []

        def _inicio_de_la_primera_pestana() -> None:
            try:
                with transaction.atomic():
                    mostrado.append(caso(actor))
            except BaseException as error:
                errores.append(error)
            finally:
                connections.close_all()

        hilo = threading.Thread(target=_inicio_de_la_primera_pestana)
        hilo.start()
        try:
            assert avisos.leyo.wait(ESPERA)
            # Con la lectura hecha y la marca pendiente, alguien intenta reusar OTRO codigo. Su
            # momento es de ahora: posterior al que se esta mostrando, pero ANTERIOR a cuando la
            # marca se va a escribir.
            nuevo = datetime.now(UTC)
            id_nuevo = _en_un_hilo(lambda: _insertar_intento(actor.id, nuevo))
        finally:
            avisos.continuar.set()
            hilo.join()
        assert errores == []
        assert mostrado[0] is not None
        assert mostrado[0].ocurrido_en == primero  # se mostro el que se habia leido
        # La marca quedo en el id del intento mostrado (no en el del nuevo): este sigue pendiente.
        marca = _en_un_hilo(
            lambda: Usuario.objects.get(pk=actor.id).aviso_reuso_visto_hasta_id,
        )
        assert marca is not None
        assert marca < id_nuevo
        siguiente = _en_un_hilo(lambda: _pedir_aviso(actor))
        assert siguiente is not None
        assert siguiente.ocurrido_en == nuevo
        assert _en_un_hilo(lambda: _pedir_aviso(actor)) is None
