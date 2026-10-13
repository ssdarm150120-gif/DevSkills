"""El despachador con hilos y conexiones reales contra PostgreSQL (DISENO, D.5.1).

Cada operación corre en un HILO con su propia conexión y sin transacción externa (autocommit, como
lo haría un worker de Celery). Las pruebas dejan sus filas confirmadas, así que limpian al final:
`transaction=True` vaciaría también el catálogo sembrado por las migraciones.
"""

import contextlib
import threading
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connections, transaction

from nucleo.adaptadores.despachador import Despachador
from nucleo.adaptadores.modelos import EntregaOutbox, EventoOutbox
from nucleo.adaptadores.publicador import PublicadorDeEventosDjango
from nucleo.puertos import EventoDeDominio, RegistroDeConsumidores

pytestmark = pytest.mark.django_db

EVENTOS = 24
DESPACHADORES = 4


def _en_hilo[T](accion: Callable[[], T]) -> T:
    resultado: list[T] = []
    errores: list[BaseException] = []

    def _correr() -> None:
        try:
            resultado.append(accion())
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


def _evento(n: int) -> EventoDeDominio:
    return EventoDeDominio(
        nombre="PurgaEjecutada",
        agregado_id=f"a-{n}",
        ocurrido_en=datetime.now(UTC),
        payload={"categoria": "c", "cantidad": n},
    )


def _limpiar() -> None:
    EntregaOutbox.objects.all().delete()
    EventoOutbox.objects.all().delete()


@pytest.fixture
def limpio():  # type: ignore[no-untyped-def]
    _en_hilo(_limpiar)
    yield
    _en_hilo(_limpiar)


def _publicar_en_hilo(consumidores: RegistroDeConsumidores, cantidad: int) -> None:
    def publicar() -> None:
        publicador = PublicadorDeEventosDjango(consumidores, "nucleo")
        for n in range(cantidad):
            with transaction.atomic():
                publicador.publicar(_evento(n))

    _en_hilo(publicar)


def test_dos_o_mas_despachadores_a_la_vez_no_entregan_dos_veces(limpio: None) -> None:
    entregas: list[str] = []
    candado = threading.Lock()

    def consumidor(evento: EventoDeDominio) -> None:
        with candado:
            entregas.append(str(evento.evento_id))

    consumidores = RegistroDeConsumidores()
    consumidores.suscribir("c", consumidor)
    _publicar_en_hilo(consumidores, EVENTOS)

    errores: list[BaseException] = []
    barrera = threading.Barrier(DESPACHADORES)

    def despachar() -> None:
        try:
            despachador = Despachador(
                consumidores, PublicadorDeEventosDjango(consumidores, "nucleo")
            )
            barrera.wait()
            while despachador.procesar_una() is not None:
                pass
        except BaseException as error:
            errores.append(error)
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=despachar) for _ in range(DESPACHADORES)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert errores == []
    assert len(entregas) == EVENTOS
    assert max(Counter(entregas).values()) == 1  # ningun evento se entrego dos veces
    assert EntregaOutbox.objects.filter(estado="entregada").count() == EVENTOS


def test_un_despachador_no_espera_a_otro_que_tiene_tomada_una_entrega(limpio: None) -> None:
    """SKIP LOCKED: mientras A trabaja la primera entrega, B toma la segunda sin esperar."""
    tomada = threading.Event()
    soltar = threading.Event()
    vistos: list[int] = []

    def consumidor(evento: EventoDeDominio) -> None:
        n = int(evento.payload["cantidad"])
        vistos.append(n)
        if n == 0:  # la primera: se queda con el candado hasta que B termine
            tomada.set()
            assert soltar.wait(timeout=20)

    consumidores = RegistroDeConsumidores()
    consumidores.suscribir("c", consumidor)
    _publicar_en_hilo(consumidores, 2)

    resultados: dict[str, str | None] = {}

    def despachador_a() -> None:
        try:
            resultados["a"] = Despachador(
                consumidores, PublicadorDeEventosDjango(consumidores, "nucleo")
            ).procesar_una()
        finally:
            connections.close_all()

    hilo_a = threading.Thread(target=despachador_a)
    hilo_a.start()
    assert tomada.wait(timeout=20)
    try:
        # B corre mientras A sigue dentro de su transaccion: toma la otra y no se bloquea.
        resultados["b"] = _en_hilo(
            lambda: Despachador(
                consumidores, PublicadorDeEventosDjango(consumidores, "nucleo")
            ).procesar_una()
        )
        resultados["b2"] = _en_hilo(
            lambda: Despachador(
                consumidores, PublicadorDeEventosDjango(consumidores, "nucleo")
            ).procesar_una()
        )
    finally:
        soltar.set()
        hilo_a.join()
    assert resultados == {"b": "entregada", "b2": None, "a": "entregada"}
    assert sorted(vistos) == [0, 1]


def test_si_la_transaccion_de_negocio_falla_no_queda_evento_confirmado(limpio: None) -> None:
    consumidores = RegistroDeConsumidores()
    consumidores.suscribir("c", lambda e: None)

    def negocio_que_falla() -> None:
        try:
            with transaction.atomic():
                PublicadorDeEventosDjango(consumidores, "nucleo").publicar(_evento(1))
                raise RuntimeError("falla el cambio de negocio")
        except RuntimeError:
            pass

    _en_hilo(negocio_que_falla)
    assert EventoOutbox.objects.count() == 0
    assert EntregaOutbox.objects.count() == 0


def test_un_consumidor_que_cae_a_media_entrega_no_pierde_la_entrega(limpio: None) -> None:
    """Si la conexion del despachador se cae con el candado puesto, la entrega sigue pendiente."""
    consumidores = RegistroDeConsumidores()
    consumidores.suscribir("c", lambda e: None)
    _publicar_en_hilo(consumidores, 1)

    class Caida(BaseException):
        pass

    def cae() -> None:
        def falla(_: EventoDeDominio) -> None:
            raise Caida

        registro = RegistroDeConsumidores()
        registro.suscribir("c", falla)
        with contextlib.suppress(Caida):
            Despachador(registro, PublicadorDeEventosDjango(registro, "nucleo")).procesar_una()

    _en_hilo(cae)
    assert EntregaOutbox.objects.get().estado == "pendiente"
    assert (
        _en_hilo(
            lambda: Despachador(
                consumidores, PublicadorDeEventosDjango(consumidores, "nucleo")
            ).procesar_una()
        )
        == "entregada"
    )


# --- Controles de seguridad del despachador y de la purga ---


def test_los_limites_de_tiempo_valen_solo_dentro_de_la_transaccion_del_despachador(
    limpio: None,
) -> None:
    """Corre en un hilo con su conexion: tras `procesar_una` la conexion queda sin limites.

    Mata `set_config(..., false)` (la fuga de los limites a toda la conexion) y la ausencia de
    cualquiera de los dos limites dentro de la transaccion.
    """
    dentro: dict[str, str] = {}

    def consumidor(evento: EventoDeDominio) -> None:
        with connections["default"].cursor() as cursor:
            for nombre in ("statement_timeout", "lock_timeout"):
                cursor.execute(f"SHOW {nombre}")
                dentro[nombre] = cursor.fetchone()[0]

    consumidores = RegistroDeConsumidores()
    consumidores.suscribir("c", consumidor)
    _publicar_en_hilo(consumidores, 1)

    def despachar_y_mirar() -> dict[str, str]:
        resultado = Despachador(
            consumidores, PublicadorDeEventosDjango(consumidores, "nucleo")
        ).procesar_una()
        assert resultado == "entregada"
        fuera = {}
        with connections["default"].cursor() as cursor:
            for nombre in ("statement_timeout", "lock_timeout"):
                cursor.execute(f"SHOW {nombre}")
                fuera[nombre] = cursor.fetchone()[0]
        return fuera

    fuera = _en_hilo(despachar_y_mirar)
    assert dentro == {"statement_timeout": "30s", "lock_timeout": "5s"}
    assert fuera == {"statement_timeout": "0", "lock_timeout": "0"}


def test_el_lock_timeout_corta_la_espera_de_un_candado_y_deja_la_entrega_reintentable(
    limpio: None,
) -> None:
    """Un consumidor espera un candado que otro tiene: a los 300 ms se corta, no a los segundos."""
    consumidores = RegistroDeConsumidores()
    _publicar_en_hilo(consumidores, 1)
    bloqueado = EventoOutbox.objects.get()
    tomado, soltar = threading.Event(), threading.Event()

    def quien_tiene_el_candado() -> None:
        try:
            with transaction.atomic():
                list(EventoOutbox.objects.select_for_update().filter(pk=bloqueado.pk))
                tomado.set()
                soltar.wait(timeout=30)
        finally:
            connections.close_all()

    def consumidor(evento: EventoDeDominio) -> None:
        list(EventoOutbox.objects.select_for_update().filter(pk=bloqueado.pk))  # espera el candado

    consumidores.suscribir("c", consumidor)
    _en_hilo(
        lambda: EntregaOutbox.objects.create(
            evento=bloqueado,
            consumidor="c",
            estado="pendiente",
            proximo_intento_en=datetime(2020, 1, 1, tzinfo=UTC),
            creada_en=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    dueno = threading.Thread(target=quien_tiene_el_candado)
    dueno.start()
    assert tomado.wait(timeout=20)
    try:
        inicio = time.monotonic()
        resultado = _en_hilo(
            lambda: Despachador(
                consumidores,
                PublicadorDeEventosDjango(consumidores, "nucleo"),
                limite_de_sentencia=timedelta(seconds=20),  # el que corta es el de bloqueo
                limite_de_bloqueo=timedelta(milliseconds=300),
            ).procesar_una()
        )
        transcurrido = time.monotonic() - inicio
    finally:
        soltar.set()
        dueno.join()
    assert resultado == "reintento"
    assert transcurrido < 5  # sin `lock_timeout` esperaria hasta los 20 s de la sentencia
    entrega = EntregaOutbox.objects.get()
    assert (entrega.estado, entrega.ultimo_error) == ("pendiente", "OperationalError")


def test_la_funcion_de_purga_es_security_definer_con_search_path_fijo_y_sin_permiso_a_public(
    limpio: None,
) -> None:
    """Mata las mutaciones que quitan `SET search_path` o el `REVOKE ... FROM PUBLIC`."""
    with connections["default"].cursor() as cursor:
        cursor.execute(
            "SELECT prosecdef, proconfig, proacl::text[] FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'nucleo' AND p.proname = 'purgar_eventos_outbox'"
        )
        seguro, configuracion, acl = cursor.fetchone()
    assert seguro is True
    assert any(c.startswith("search_path=") for c in configuracion or [])
    assert "pg_temp" in "".join(configuracion)  # pg_temp al final: no puede esconder objetos
    # `=X/dueno` es el permiso de PUBLIC (el que da PostgreSQL por defecto): no debe existir.
    assert acl is not None
    assert not [entrada for entrada in acl if entrada.startswith("=")]


def test_la_tarea_de_celery_se_interrumpe_con_el_limite_suave_sin_tragarselo(
    limpio: None,
) -> None:
    """`SoftTimeLimitExceeded` hereda de Exception y NO es un fallo del consumidor."""
    from celery.exceptions import SoftTimeLimitExceeded

    llamadas: list[str] = []

    def consumidor(evento: EventoDeDominio) -> None:
        llamadas.append(evento.agregado_id)
        raise SoftTimeLimitExceeded

    consumidores = RegistroDeConsumidores()
    consumidores.suscribir("c", consumidor)
    _publicar_en_hilo(consumidores, 3)

    def despachar() -> None:
        Despachador(consumidores, PublicadorDeEventosDjango(consumidores, "nucleo")).procesar_lote()

    with pytest.raises(SoftTimeLimitExceeded):
        _en_hilo(despachar)
    assert len(llamadas) == 1  # el lote se detuvo: no siguio con las demas hasta el limite duro
    estados = set(EntregaOutbox.objects.values_list("estado", "intentos"))
    assert estados == {("pendiente", 0)}  # la entrega en curso queda reintentable, sin intento
