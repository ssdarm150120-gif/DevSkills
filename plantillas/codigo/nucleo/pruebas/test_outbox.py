"""El outbox contra PostgreSQL (DISENO, D.5.1): publicación transaccional, despacho,
reintentos, estado de error, idempotencia, operación (estado de la cola y reintento manual)."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command
from django.db import transaction

from nucleo.adaptadores.despachador import (
    Despachador,
    entregas_en_error,
    estado_de_la_cola,
    reintentar,
)
from nucleo.adaptadores.modelos import EntregaOutbox, EventoOutbox
from nucleo.adaptadores.publicador import PublicadorDeEventosDjango
from nucleo.puertos import (
    ErrorTemporalDeIntegracion,
    EstadoDeEntrega,
    EventoDeDominio,
    EventoFueraDeTransaccion,
    LimiteDeSolicitudes,
    PoliticaDeReintentos,
    RegistroDeConsumidores,
    SolicitudRechazada,
)

pytestmark = pytest.mark.django_db

INICIO = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


class RelojFalso:
    def __init__(self) -> None:
        self.momento = INICIO

    def ahora(self) -> datetime:
        return self.momento

    def avanzar(self, **tiempo: float) -> None:
        self.momento += timedelta(**tiempo)


@dataclass
class Mundo:
    reloj: RelojFalso = field(default_factory=RelojFalso)
    consumidores: RegistroDeConsumidores = field(default_factory=RegistroDeConsumidores)
    politica: PoliticaDeReintentos = field(default_factory=PoliticaDeReintentos)

    def __post_init__(self) -> None:
        self.publicador = PublicadorDeEventosDjango(self.consumidores, "nucleo", self.reloj)
        self.despachador = Despachador(
            self.consumidores,
            PublicadorDeEventosDjango(self.consumidores, "nucleo", self.reloj),
            self.reloj,
            self.politica,
        )

    def publicar(self, nombre: str = "PurgaEjecutada", **payload: Any) -> EventoDeDominio:
        evento = EventoDeDominio(
            nombre=nombre,
            agregado_id="a-1",
            ocurrido_en=self.reloj.ahora(),
            payload=payload or {"categoria": "mensajes", "cantidad": 3},
        )
        self.publicador.publicar(evento)
        return evento


@pytest.fixture
def m() -> Mundo:
    return Mundo()


# --- Publicación ---


def test_publicar_guarda_el_evento_con_su_envoltura(m: Mundo) -> None:
    evento = m.publicar()
    fila = EventoOutbox.objects.get(evento_id=evento.evento_id)
    assert (fila.nombre, fila.version_esquema, fila.agregado_id) == ("PurgaEjecutada", 1, "a-1")
    assert fila.ocurrido_en == INICIO
    assert fila.registrado_en == INICIO
    assert fila.payload == {"categoria": "mensajes", "cantidad": 3}


def test_un_evento_sin_consumidores_se_guarda_y_no_deja_entregas_pendientes(m: Mundo) -> None:
    m.publicar()
    assert EventoOutbox.objects.count() == 1
    assert EntregaOutbox.objects.count() == 0
    assert m.despachador.procesar_lote().total == 0  # nada que despachar: queda despachado
    estado = estado_de_la_cola(m.reloj)
    assert (estado.pendientes, estado.en_error, estado.atraso_segundos) == (0, 0, 0)


def test_hay_una_entrega_por_cada_consumidor_suscrito_al_evento(m: Mundo) -> None:
    m.consumidores.suscribir("a", lambda e: None)
    m.consumidores.suscribir("b", lambda e: None, eventos=["PurgaEjecutada"])
    m.consumidores.suscribir("c", lambda e: None, eventos=["SesionIniciada"])
    evento = m.publicar()
    entregas = EntregaOutbox.objects.filter(evento__evento_id=evento.evento_id)
    assert sorted(entregas.values_list("consumidor", flat=True)) == ["a", "b"]
    assert set(entregas.values_list("estado", flat=True)) == {"pendiente"}


def test_publicar_dos_veces_el_mismo_evento_no_lo_duplica(m: Mundo) -> None:
    m.consumidores.suscribir("a", lambda e: None)
    evento = m.publicar()
    m.publicador.publicar(evento)
    assert EventoOutbox.objects.count() == 1
    assert EntregaOutbox.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_sin_transaccion_abierta_publicar_se_niega(m: Mundo) -> None:
    with pytest.raises(EventoFueraDeTransaccion):
        m.publicar()
    assert EventoOutbox.objects.count() == 0


def test_si_la_transaccion_de_negocio_se_revierte_no_queda_evento_ni_entrega(m: Mundo) -> None:
    m.consumidores.suscribir("a", lambda e: None)
    with pytest.raises(RuntimeError), transaction.atomic():
        m.publicar()
        raise RuntimeError("falla el cambio de negocio")
    assert EventoOutbox.objects.count() == 0
    assert EntregaOutbox.objects.count() == 0


# --- Despacho ---


def test_el_despachador_entrega_a_cada_consumidor_una_sola_vez(m: Mundo) -> None:
    recibidos: dict[str, list[EventoDeDominio]] = {"a": [], "b": []}
    m.consumidores.suscribir("a", recibidos["a"].append)
    m.consumidores.suscribir("b", recibidos["b"].append)
    evento = m.publicar()
    resumen = m.despachador.procesar_lote()
    assert (resumen.entregadas, resumen.reintentos, resumen.errores) == (2, 0, 0)
    assert [e.evento_id for e in recibidos["a"]] == [evento.evento_id]
    assert recibidos["b"][0].payload == {"categoria": "mensajes", "cantidad": 3}
    assert m.despachador.procesar_lote().total == 0  # no se vuelve a entregar
    assert len(recibidos["a"]) == 1
    entrega = EntregaOutbox.objects.get(consumidor="a")
    assert (entrega.estado, entrega.intentos, entrega.entregada_en) == ("entregada", 1, INICIO)


def test_el_consumidor_recibe_el_evento_completo_reconstruido(m: Mundo) -> None:
    recibido: list[EventoDeDominio] = []
    m.consumidores.suscribir("a", recibido.append)
    evento = m.publicar()
    m.despachador.procesar_una()
    assert recibido[0] == evento


def test_no_se_entrega_antes_de_su_hora(m: Mundo) -> None:
    llamadas: list[int] = []

    def falla_una_vez(_: EventoDeDominio) -> None:
        llamadas.append(1)
        if len(llamadas) == 1:
            raise ErrorTemporalDeIntegracion("cae")

    m.consumidores.suscribir("a", falla_una_vez)
    m.publicar()
    assert m.despachador.procesar_una() == "reintento"
    assert m.despachador.procesar_una() is None  # aun no es la hora del reintento
    m.reloj.avanzar(seconds=29)
    assert m.despachador.procesar_una() is None
    m.reloj.avanzar(seconds=1)
    assert m.despachador.procesar_una() == "entregada"
    assert len(llamadas) == 2


def test_un_consumidor_que_falla_se_reintenta_con_espera_creciente_y_luego_queda_en_error(
    m: Mundo,
) -> None:
    m.consumidores.suscribir(
        "roto",
        lambda e: (_ for _ in ()).throw(ErrorTemporalDeIntegracion("x")),
        eventos=["PurgaEjecutada"],
    )
    m.publicar()
    esperas: list[float] = []
    for _ in range(5):  # los cinco reintentos
        assert m.despachador.procesar_una() == "reintento"
        entrega = EntregaOutbox.objects.get()
        esperas.append((entrega.proximo_intento_en - m.reloj.ahora()).total_seconds())
        m.reloj.avanzar(seconds=esperas[-1])
    assert esperas == [30, 60, 120, 240, 480]
    assert m.despachador.procesar_una() == "error"  # el sexto intento: reintentos agotados
    entrega = EntregaOutbox.objects.get()
    assert (entrega.estado, entrega.intentos) == ("error", 6)
    assert entrega.ultimo_error == "ErrorTemporalDeIntegracion"  # solo el nombre, nunca el mensaje
    assert m.despachador.procesar_una() is None  # un error ya no se toca solo


def test_un_error_no_reintentable_va_directo_a_error(m: Mundo) -> None:
    def rechaza(_: EventoDeDominio) -> None:
        raise SolicitudRechazada("el proveedor no la aprobo")

    m.consumidores.suscribir("meta", rechaza, eventos=["PurgaEjecutada"])
    m.publicar()
    assert m.despachador.procesar_una() == "error"
    entrega = EntregaOutbox.objects.get(consumidor="meta")
    assert (entrega.estado, entrega.intentos) == ("error", 1)


def test_el_limite_de_envios_manda_la_espera_que_pidio_el_proveedor(m: Mundo) -> None:
    def limite(_: EventoDeDominio) -> None:
        raise LimiteDeSolicitudes("tope", reintentar_en_segundos=90)

    m.consumidores.suscribir("meta", limite)
    m.publicar()
    m.despachador.procesar_una()
    entrega = EntregaOutbox.objects.get()
    assert entrega.proximo_intento_en == INICIO + timedelta(seconds=90)


def test_si_el_consumidor_falla_se_revierten_sus_escrituras_y_las_de_los_demas_se_conservan(
    m: Mundo,
) -> None:
    def escribe_y_falla(evento: EventoDeDominio) -> None:
        EventoOutbox.objects.create(  # una escritura cualquiera del consumidor
            evento_id="00000000-0000-0000-0000-00000000aaaa",
            nombre="PurgaEjecutada",
            version_esquema=1,
            agregado_id="x",
            ocurrido_en=INICIO,
            registrado_en=INICIO,
            payload={},
        )
        raise RuntimeError("falla despues de escribir")

    m.consumidores.suscribir("a", escribe_y_falla)
    m.consumidores.suscribir("b", lambda e: None)
    m.publicar()
    resumen = m.despachador.procesar_lote()
    assert (resumen.entregadas, resumen.reintentos) == (1, 1)
    assert not EventoOutbox.objects.filter(agregado_id="x").exists()  # lo del consumidor se fue
    assert EntregaOutbox.objects.get(consumidor="b").estado == "entregada"


def test_la_entrega_es_al_menos_una_vez_si_el_proceso_se_cae_a_media_entrega(m: Mundo) -> None:
    """Una caida (excepcion que escapa de la transaccion) deja la entrega pendiente: se repite."""
    vistos: list[str] = []

    def consumidor(evento: EventoDeDominio) -> None:
        vistos.append(str(evento.evento_id))

    m.consumidores.suscribir("a", consumidor)
    m.publicar()

    class Caida(BaseException):  # no es una Exception: el despachador no la atrapa
        pass

    original = EntregaOutbox.save

    def guardar_y_caer(self: EntregaOutbox, *args: Any, **kwargs: Any) -> None:
        raise Caida

    EntregaOutbox.save = guardar_y_caer  # type: ignore[method-assign,assignment]
    try:
        with pytest.raises(Caida), transaction.atomic():
            m.despachador.procesar_una()
    finally:
        EntregaOutbox.save = original  # type: ignore[method-assign]
    assert EntregaOutbox.objects.get().estado == "pendiente"
    assert m.despachador.procesar_una() == "entregada"
    assert len(vistos) == 2  # el consumidor lo vio dos veces: por eso es idempotente


def test_un_consumidor_idempotente_no_duplica_el_efecto_aunque_reciba_dos_veces_el_evento(
    m: Mundo,
) -> None:
    """El consumidor se protege con una marca de lo ya procesado y cuenta sus efectos: la segunda
    entrega la ve (llamadas = 2) y no duplica el efecto (efectos = 1)."""
    procesados: set[str] = set()
    llamadas = [0]
    efectos = [0]

    def consumidor(evento: EventoDeDominio) -> None:
        llamadas[0] += 1
        if str(evento.evento_id) in procesados:
            return  # ya procesado: sin efecto
        procesados.add(str(evento.evento_id))
        efectos[0] += 1

    m.consumidores.suscribir("a", consumidor)
    m.publicar()
    m.despachador.procesar_una()
    EntregaOutbox.objects.update(estado="pendiente")  # simula una segunda entrega
    m.despachador.procesar_una()
    assert (llamadas[0], efectos[0]) == (2, 1)


def test_un_consumidor_que_este_proceso_no_conoce_no_se_toma(m: Mundo) -> None:
    otro = Mundo()
    otro.consumidores.suscribir("remoto", lambda e: None)
    otro.publicar()  # la entrega queda para el consumidor "remoto"
    m.consumidores.suscribir("local", lambda e: None)
    assert m.despachador.procesar_una() is None
    assert EntregaOutbox.objects.get().estado == "pendiente"


def test_un_despachador_sin_consumidores_no_hace_nada(m: Mundo) -> None:
    assert m.despachador.procesar_una() is None


def test_el_lote_respeta_el_maximo(m: Mundo) -> None:
    m.consumidores.suscribir("a", lambda e: None)
    for _ in range(5):
        m.publicar()
    assert m.despachador.procesar_lote(maximo=3).entregadas == 3
    assert m.despachador.procesar_lote().entregadas == 2


# --- Error visible y ErrorIntegracionRegistrado ---


def _agotar(m: Mundo, error: Exception) -> None:
    def falla(_: EventoDeDominio) -> None:
        raise error

    m.consumidores.suscribir("roto", falla, eventos=["PurgaEjecutada"])
    m.publicar()
    for _ in range(20):
        if m.despachador.procesar_una() == "error":
            return
        m.reloj.avanzar(hours=1)
    raise AssertionError("nunca llego a error")


def test_agotados_los_reintentos_se_publica_error_de_integracion_sin_datos_personales(
    m: Mundo,
) -> None:
    _agotar(m, RuntimeError("telefono 5512345678 invalido"))
    aviso = EventoOutbox.objects.get(nombre="ErrorIntegracionRegistrado")
    assert aviso.payload["origen"] == "despachador_outbox"
    assert aviso.payload["codigo"] == "reintentos_agotados"
    assert aviso.payload["consumidor"] == "roto"
    assert aviso.payload["error"] == "RuntimeError"
    assert "5512345678" not in str(aviso.payload)
    assert "5512345678" not in str(EntregaOutbox.objects.get(consumidor="roto").ultimo_error)


def test_el_error_registrado_lleva_la_correlacion_del_evento_original(m: Mundo) -> None:
    _agotar(m, SolicitudRechazada("x"))
    original = EventoOutbox.objects.get(nombre="PurgaEjecutada")
    aviso = EventoOutbox.objects.get(nombre="ErrorIntegracionRegistrado")
    assert aviso.payload["id_correlacion"] == str(original.evento_id)
    assert aviso.payload["codigo"] == "no_reintentable"


def test_si_falla_el_consumidor_del_aviso_no_se_genera_otro_aviso(m: Mundo) -> None:
    def falla(_: EventoDeDominio) -> None:
        raise SolicitudRechazada("x")

    m.consumidores.suscribir("operacion", falla, eventos=["ErrorIntegracionRegistrado"])
    m.consumidores.suscribir("roto", falla, eventos=["PurgaEjecutada"])
    m.publicar()
    m.despachador.procesar_lote()
    assert EventoOutbox.objects.filter(nombre="ErrorIntegracionRegistrado").count() == 1
    assert EntregaOutbox.objects.filter(estado="error").count() == 2  # los dos visibles


def test_los_logs_llevan_ids_y_nombres_pero_nunca_la_carga_ni_el_mensaje(
    m: Mundo, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="nucleo.outbox")
    m.consumidores.suscribir(
        "roto", lambda e: (_ for _ in ()).throw(RuntimeError("clave 12345 de Ana"))
    )
    m.publicar(categoria="mensajes", cantidad=3, nota="dato-personal-xyz")
    m.despachador.procesar_lote()
    texto = caplog.text
    assert "outbox_reintento" in texto
    assert "RuntimeError" in texto
    assert "dato-personal-xyz" not in texto
    assert "12345" not in texto


# --- Operación: estado de la cola y reintento manual ---


def test_el_estado_de_la_cola_muestra_atraso_reintentos_y_errores(m: Mundo) -> None:
    m.consumidores.suscribir("ok", lambda e: None, eventos=["SesionIniciada"])
    m.consumidores.suscribir(
        "roto",
        lambda e: (_ for _ in ()).throw(ErrorTemporalDeIntegracion("x")),
        eventos=["PurgaEjecutada"],
    )
    m.publicar()
    m.reloj.avanzar(seconds=45)
    estado = estado_de_la_cola(m.reloj)
    assert (estado.pendientes, estado.atraso_segundos, estado.en_reintento) == (1, 45, 0)
    m.despachador.procesar_una()
    m.reloj.avanzar(seconds=10)  # el reintento aun no vence
    estado = estado_de_la_cola(m.reloj)
    assert (estado.pendientes, estado.en_reintento, estado.atraso_segundos) == (1, 1, 0)
    assert estado.por_consumidor == {"roto": {"pendiente": 1}}


def test_reintentar_a_mano_devuelve_una_entrega_en_error_a_pendiente(m: Mundo) -> None:
    _agotar(m, SolicitudRechazada("x"))
    entrega = EntregaOutbox.objects.get(consumidor="roto")
    assert [e.pk for e in entregas_en_error()] == [entrega.pk]
    assert reintentar(entrega_id=entrega.pk, reloj=m.reloj) == 1
    entrega.refresh_from_db()
    assert (entrega.estado, entrega.intentos, entrega.ultimo_error) == ("pendiente", 0, "")
    assert estado_de_la_cola(m.reloj).en_error == 0


def test_reintentar_filtra_por_evento_y_por_consumidor_y_no_toca_lo_que_no_esta_en_error(
    m: Mundo,
) -> None:
    _agotar(m, SolicitudRechazada("x"))
    entrega = EntregaOutbox.objects.get(consumidor="roto")
    assert reintentar(consumidor="otro", reloj=m.reloj) == 0
    assert reintentar(evento_id=str(entrega.evento.evento_id), reloj=m.reloj) == 1
    assert reintentar(consumidor="roto", reloj=m.reloj) == 0  # ya no esta en error


def test_reintentar_exige_al_menos_un_filtro() -> None:
    with pytest.raises(ValueError, match="entrega_id"):
        reintentar()


def test_un_reintento_manual_vuelve_a_entregar_cuando_el_consumidor_ya_funciona(m: Mundo) -> None:
    sano = [False]
    recibidos: list[EventoDeDominio] = []

    def consumidor(evento: EventoDeDominio) -> None:
        if not sano[0]:
            raise SolicitudRechazada("x")
        recibidos.append(evento)

    m.consumidores.suscribir("a", consumidor, eventos=["PurgaEjecutada"])
    m.publicar()
    m.despachador.procesar_lote()
    assert EntregaOutbox.objects.get(consumidor="a").estado == EstadoDeEntrega.ERROR
    sano[0] = True
    reintentar(consumidor="a", reloj=m.reloj)
    m.despachador.procesar_lote()
    assert len(recibidos) == 1
    assert EntregaOutbox.objects.get(consumidor="a").estado == EstadoDeEntrega.ENTREGADA


def test_los_comandos_de_operacion_muestran_la_cola_y_reintentan(m: Mundo) -> None:
    _agotar(m, SolicitudRechazada("x"))
    salida = StringIO()
    with pytest.raises(SystemExit) as codigo:
        call_command("outbox_estado", "--errores", stdout=salida)
    assert codigo.value.code == 1  # hay errores: sirve de sonda
    texto = salida.getvalue()
    assert "en_error=1" in texto
    assert "consumidor=roto" in texto
    assert "SolicitudRechazada" in texto
    assert "mensajes" not in texto  # sin carga util

    salida = StringIO()
    call_command("outbox_reintentar", "--consumidor", "roto", stdout=salida)
    assert "reprogramadas: 1" in salida.getvalue()
    salida = StringIO()
    call_command("outbox_estado", stdout=salida)  # ya no hay errores: no sale con codigo 1
    assert "en_error=0" in salida.getvalue()


def test_el_comando_de_reintento_pide_un_filtro_y_rechaza_un_id_invalido() -> None:
    with pytest.raises(CommandError, match="entrega_id"):
        call_command("outbox_reintentar")
    with pytest.raises(CommandError):
        call_command("outbox_reintentar", "--evento", "no-es-un-uuid")


def test_la_tarea_de_celery_despacha_con_el_bus_conectado() -> None:
    from nucleo.puertos import RegistroDeConsumidores as Registro
    from nucleo.puertos.registro import obtener
    from nucleo.tasks import NOMBRE_DE_LA_TAREA, despachar_outbox

    assert despachar_outbox.name == NOMBRE_DE_LA_TAREA
    registro = obtener(Registro)
    recibidos: list[str] = []
    registro.suscribir(
        "de-prueba-tarea", lambda e: recibidos.append(e.nombre), eventos=["PurgaEjecutada"]
    )
    try:
        publicador = PublicadorDeEventosDjango(registro, "nucleo")
        publicador.publicar(
            EventoDeDominio(
                nombre="PurgaEjecutada",
                agregado_id="t",
                ocurrido_en=datetime.now(UTC),
                payload={"categoria": "c", "cantidad": 1},
            )
        )
        resultado = despachar_outbox.apply().get()
    finally:
        registro.retirar("de-prueba-tarea")
    assert resultado == {"entregadas": 1, "reintentos": 0, "errores": 0}
    assert recibidos == ["PurgaEjecutada"]


def test_celery_conoce_la_tarea_su_cola_propia_y_el_horario_de_beat() -> None:
    from celery import current_app as app

    app.loader.import_default_modules()
    assert "nucleo.despachar_outbox" in app.tasks
    assert app.conf.task_routes["nucleo.despachar_outbox"] == {"queue": "outbox"}
    horario = app.conf.beat_schedule["despachar-outbox"]
    assert horario["task"] == "nucleo.despachar_outbox"
    assert horario["schedule"] <= 10  # el atraso maximo se mide en segundos, no en minutos
    assert horario["options"]["expires"] >= horario["schedule"]
