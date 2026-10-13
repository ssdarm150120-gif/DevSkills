"""Outbox, ronda 2: veneno, tiempo máximo, emisor por módulo, retención, claves prohibidas y
aislamiento de suscripciones."""

import time
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import connection, transaction

from nucleo.adaptadores.despachador import Despachador
from nucleo.adaptadores.modelos import EntregaOutbox, EventoOutbox
from nucleo.adaptadores.publicador import FabricaDePublicadoresDjango, PublicadorDeEventosDjango
from nucleo.adaptadores.purga import MARGEN_DE_RELOJ, PLAZO_DE_RETENCION, purgar
from nucleo.pruebas.aislamiento import Aislamiento
from nucleo.puertos import (
    CATALOGO,
    EmisorNoAutorizado,
    EventoDeDominio,
    EventoInvalido,
    RegistroDeConsumidores,
)
from nucleo.puertos.registro import obtener

pytestmark = pytest.mark.django_db


class Reloj:
    def __init__(self, momento: datetime | None = None) -> None:
        self.momento = momento or datetime.now(UTC)

    def ahora(self) -> datetime:
        return self.momento


def _evento(n: int = 0, nombre: str = "PurgaEjecutada", **payload: Any) -> EventoDeDominio:
    return EventoDeDominio(
        nombre=nombre,
        agregado_id=f"a-{n}",
        ocurrido_en=datetime.now(UTC),
        payload=payload or {"categoria": "c", "cantidad": n},
    )


def _todo(consumidores: RegistroDeConsumidores, reloj: Reloj) -> tuple[Any, Despachador]:
    fabrica = FabricaDePublicadoresDjango(consumidores, reloj)
    return fabrica, Despachador(consumidores, fabrica.de("nucleo"), reloj)


# --- el veneno no frena a la cola ---


def _veneno(nombre: str, payload: dict[str, Any], *, agregado: str = "v") -> EventoOutbox:
    return EventoOutbox.objects.create(
        evento_id=uuid4(),
        nombre=nombre,
        version_esquema=1,
        agregado_id=agregado,
        ocurrido_en=datetime(2020, 1, 1, tzinfo=UTC),
        registrado_en=datetime(2020, 1, 1, tzinfo=UTC),
        payload=payload,
    )


@pytest.mark.parametrize(
    ("nombre", "payload", "error"),
    [
        ("EventoQueNoExiste", {}, "EventoDesconocido"),
        ("PurgaEjecutada", {"categoria": "c"}, "EventoInvalido"),  # falta `cantidad`
        ("PurgaEjecutada", {"categoria": "c", "cantidad": 1, "clave": "x"}, "EventoInvalido"),
    ],
)
def test_un_evento_ilegible_va_a_error_sin_reintento_y_la_buena_se_entrega_en_la_misma_corrida(
    nombre: str, payload: dict[str, Any], error: str
) -> None:
    reloj = Reloj()
    consumidores = RegistroDeConsumidores()
    recibidos: list[str] = []
    consumidores.suscribir(
        "c", lambda e: recibidos.append(e.agregado_id), eventos=["PurgaEjecutada"]
    )
    fabrica, despachador = _todo(consumidores, reloj)
    ahora = reloj.ahora()
    malo = _veneno(nombre, payload)
    EntregaOutbox.objects.create(
        evento=malo,
        consumidor="c",
        estado="pendiente",
        proximo_intento_en=ahora - timedelta(hours=1),  # primero en la fila
        creada_en=ahora,
    )
    with transaction.atomic():
        fabrica.de("nucleo").publicar(_evento(1))

    resumen = despachador.procesar_lote()

    assert (resumen.entregadas, resumen.errores, resumen.reintentos) == (1, 1, 0)
    assert recibidos == ["a-1"]
    entrega = EntregaOutbox.objects.get(evento=malo)
    assert (entrega.estado, entrega.intentos, entrega.ultimo_error) == ("error", 1, error)
    aviso = EventoOutbox.objects.get(nombre="ErrorIntegracionRegistrado")
    assert aviso.payload["codigo"] == "no_reintentable"
    assert aviso.payload["error"] == error


# --- Decisión 4: tiempo máximo ---


def test_un_consumidor_que_excede_el_limite_queda_reintentable_y_no_frena_a_las_demas() -> None:
    reloj = Reloj()
    consumidores = RegistroDeConsumidores()
    recibidos: list[str] = []

    def lento(evento: EventoDeDominio) -> None:
        if evento.agregado_id == "a-0":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(5)")
        recibidos.append(evento.agregado_id)

    consumidores.suscribir("c", lento)
    fabrica = FabricaDePublicadoresDjango(consumidores, reloj)
    despachador = Despachador(
        consumidores,
        fabrica.de("nucleo"),
        reloj,
        limite_de_sentencia=timedelta(milliseconds=300),
    )
    for n in range(3):
        with transaction.atomic():
            fabrica.de("nucleo").publicar(_evento(n))
    inicio = time.monotonic()
    resumen = despachador.procesar_lote()
    assert time.monotonic() - inicio < 4  # no esperó los 5 s del consumidor lento
    assert (resumen.entregadas, resumen.reintentos, resumen.errores) == (2, 1, 0)
    assert sorted(recibidos) == ["a-1", "a-2"]
    entrega = EntregaOutbox.objects.get(evento__agregado_id="a-0")
    assert entrega.estado == "pendiente"  # reintentable, no perdida
    assert entrega.proximo_intento_en > reloj.ahora()
    assert entrega.ultimo_error == "OperationalError"  # Django envuelve QueryCanceled


def test_la_tarea_de_celery_lleva_limites_de_tiempo_y_no_usa_acks_late() -> None:
    from nucleo.tasks import despachar_outbox, purgar_outbox

    for tarea in (despachar_outbox, purgar_outbox):
        assert 0 < tarea.soft_time_limit < tarea.time_limit
        assert not tarea.acks_late


# --- Decisión 2: cada módulo publica solo sus eventos ---


def test_un_modulo_no_puede_publicar_un_evento_ajeno() -> None:
    consumidores = RegistroDeConsumidores()
    identidad = FabricaDePublicadoresDjango(consumidores).de("identidad")
    ajeno = _evento(nombre="PurgaEjecutada")  # es de `nucleo`
    with transaction.atomic(), pytest.raises(EmisorNoAutorizado, match="nucleo"):
        identidad.publicar(ajeno)
    assert EventoOutbox.objects.count() == 0


def test_el_emisor_del_catalogo_si_puede_y_un_modulo_no_puede_hacerse_pasar_por_otro() -> None:
    fabrica = FabricaDePublicadoresDjango(RegistroDeConsumidores())
    with transaction.atomic():
        fabrica.de("nucleo").publicar(_evento())
    with transaction.atomic(), pytest.raises(EmisorNoAutorizado):
        fabrica.de("Nucleo").publicar(_evento(1))  # el nombre no se normaliza
    assert EventoOutbox.objects.count() == 1


def test_los_eventos_de_cualquier_modulo_los_puede_publicar_cualquiera() -> None:
    fabrica = FabricaDePublicadoresDjango(RegistroDeConsumidores())
    with transaction.atomic():
        fabrica.de("finanzas").publicar(
            _evento(nombre="ConfiguracionCambiada", usuario_id="u", seccion="x")
        )
    assert EventoOutbox.objects.filter(nombre="ConfiguracionCambiada").count() == 1


def test_el_publicador_necesita_el_nombre_de_su_modulo() -> None:
    with pytest.raises(ValueError, match="módulo"):
        PublicadorDeEventosDjango(RegistroDeConsumidores(), "")


def test_cada_evento_del_catalogo_tiene_al_menos_un_emisor() -> None:
    assert all(especificacion.emisores for especificacion in CATALOGO.values())


def test_la_fabrica_conectada_entrega_publicadores_por_modulo() -> None:
    from nucleo.puertos import FabricaDePublicadores

    fabrica = obtener(FabricaDePublicadores)
    assert fabrica.de("identidad") is not fabrica.de("nucleo")


# --- claves prohibidas por subcadena y correos como valor ---


@pytest.mark.parametrize(
    "clave",
    [
        "correo",
        "Correo_Cliente",
        "email",
        "emailPersonal",
        "telefono",
        "telefono_contacto",
        "numero",
        "ip",
        "IP",
        "direccion_ip",
        "ipOrigen",
        "contrasena",
        "contrasena_nueva",
        "password",
        "Password2",
        "secret",
        "client_secret",
        "secreto",
        "otp",
        "codigo",
        "codigo_segundo_factor",
        "codigoTotp",
        "token",
        "access_token",
        "clave",
    ],
)
def test_una_clave_prohibida_se_rechaza_en_cualquier_forma_y_profundidad(clave: str) -> None:
    for payload in (
        {"categoria": "c", "cantidad": 1, clave: "x"},
        {"categoria": "c", "cantidad": 1, "anidado": [{"x": {clave: 1}}]},
    ):
        with pytest.raises(EventoInvalido, match="nunca viaja"):
            _evento(0, "PurgaEjecutada", **payload)


@pytest.mark.parametrize(
    "clave",
    ["tipo", "descripcion", "terminacion_nueva", "huella_correo", "usuario_id"],
)
def test_las_claves_legitimas_no_se_prohiben_por_parecerse(clave: str) -> None:
    assert (
        _evento(0, "PurgaEjecutada", categoria="c", cantidad=1, **{clave: "x"}).payload[clave]
        == "x"
    )


def test_las_excepciones_por_evento_del_diseno_se_respetan_solo_en_ese_evento() -> None:
    error = _evento(
        nombre="ErrorIntegracionRegistrado",
        origen="o",
        codigo="reintentos_agotados",
        mensaje="m",
        id_correlacion="i",
    )
    assert error.payload["codigo"] == "reintentos_agotados"
    configuracion = _evento(nombre="ConfiguracionCambiada", usuario_id="u", clave="zona_horaria")
    assert configuracion.payload["clave"] == "zona_horaria"
    with pytest.raises(EventoInvalido, match="nunca viaja"):  # `codigo` no es libre en otro evento
        _evento(categoria="c", cantidad=1, codigo="x")


@pytest.mark.parametrize(
    "valor", ["ana@empresa.example", "contacto: ana@empresa.example.", "a.b+c@x.co"]
)
def test_un_valor_con_forma_de_correo_se_rechaza_aunque_la_clave_sea_inocente(valor: str) -> None:
    with pytest.raises(EventoInvalido, match="correo"):
        _evento(categoria="c", cantidad=1, nota=valor)
    with pytest.raises(EventoInvalido, match="correo"):
        _evento(categoria="c", cantidad=1, lista=[{"x": valor}])


def test_un_texto_con_arroba_que_no_es_correo_pasa() -> None:
    assert _evento(categoria="c", cantidad=1, nota="@usuario sin dominio").payload["nota"]


# --- Decisión 1 y 3: retención y purga ---


def _crear(
    nombre: str, hace: timedelta, estados: list[tuple[str, timedelta | None]]
) -> EventoOutbox:
    """Un evento registrado `hace` atras con entregas (estado, hace cuanto se entregó)."""
    ahora = datetime.now(UTC)
    evento = EventoOutbox.objects.create(
        evento_id=uuid4(),
        nombre="PurgaEjecutada",
        version_esquema=1,
        agregado_id=nombre,
        ocurrido_en=ahora - hace,
        registrado_en=ahora - hace,
        payload={"categoria": "c", "cantidad": 1},
    )
    for i, (estado, entregada_hace) in enumerate(estados):
        EntregaOutbox.objects.create(
            evento=evento,
            consumidor=f"c{i}",
            estado=estado,
            proximo_intento_en=ahora - hace,
            entregada_en=None if entregada_hace is None else ahora - entregada_hace,
            creada_en=ahora - hace,
        )
    return evento


def _quedan() -> set[str]:
    return set(EventoOutbox.objects.values_list("agregado_id", flat=True))


def test_la_purga_borra_lo_despachado_de_hace_mas_de_30_dias_y_solo_eso() -> None:
    dias = lambda n: timedelta(days=n)  # noqa: E731
    _crear("viejo_entregado", dias(40), [("entregada", dias(40)), ("entregada", dias(39))])
    _crear("viejo_sin_entregas", dias(40), [])
    _crear("reciente_entregado", dias(29), [("entregada", dias(29))])
    _crear("viejo_en_error", dias(90), [("entregada", dias(90)), ("error", None)])
    _crear("viejo_pendiente", dias(90), [("pendiente", None)])
    _crear("viejo_pero_entregado_hace_poco", dias(40), [("entregada", dias(5))])
    resumen = purgar(Reloj())
    assert (resumen.candidatos, resumen.borrados, resumen.dry_run) == (2, 2, False)
    assert _quedan() == {
        "reciente_entregado",
        "viejo_en_error",
        "viejo_pendiente",
        "viejo_pero_entregado_hace_poco",
    }
    assert EntregaOutbox.objects.filter(evento__agregado_id="viejo_entregado").count() == 0


def test_los_eventos_en_error_o_pendientes_nunca_se_borran_solos_por_viejos_que_sean() -> None:
    _crear("error", timedelta(days=3650), [("error", None)])
    _crear("pendiente", timedelta(days=3650), [("pendiente", None)])
    assert purgar(Reloj()).borrados == 0
    # Aunque un reloj adelantado quiera "envejecerlos", la base se niega a borrar lo reciente.
    with pytest.raises(Exception, match="purga_fuera_de_plazo"), transaction.atomic():
        purgar(Reloj(datetime.now(UTC) + timedelta(days=40)))
    assert _quedan() == {"error", "pendiente"}


def test_el_plazo_es_de_treinta_dias_mas_el_margen_de_reloj_y_la_frontera_se_respeta() -> None:
    assert timedelta(days=30) == PLAZO_DE_RETENCION
    assert timedelta(hours=1) == MARGEN_DE_RELOJ
    _crear("a_29d_23h", timedelta(days=29, hours=23), [("entregada", timedelta(days=29, hours=23))])
    _crear(
        "a_30d_mas_media_hora", timedelta(days=30, minutes=30), [("entregada", timedelta(days=30))]
    )
    _crear("a_30d_mas_margen", timedelta(days=30, hours=1, minutes=1), [])
    assert purgar(Reloj()).borrados == 1
    assert _quedan() == {"a_29d_23h", "a_30d_mas_media_hora"}
    # Con el reloj de la prueba 2 dias atras, ya nada de lo que queda cumple el plazo.
    assert purgar(Reloj(datetime.now(UTC) - timedelta(days=2))).borrados == 0


def test_la_purga_tolera_una_aplicacion_adelantada_respecto_a_la_base() -> None:
    """el reloj de la aplicacion va 30 minutos adelantado y la purga NO falla."""
    _crear("viejo", timedelta(days=40), [("entregada", timedelta(days=40))])
    assert purgar(Reloj(datetime.now(UTC) + timedelta(minutes=30))).borrados == 1


def test_un_desfase_mayor_al_margen_hace_fallar_la_purga_en_lugar_de_borrar_de_mas() -> None:
    _crear("viejo", timedelta(days=40), [("entregada", timedelta(days=40))])
    with pytest.raises(Exception, match="purga_fuera_de_plazo"), transaction.atomic():
        purgar(Reloj(datetime.now(UTC) + timedelta(hours=3)))
    assert _quedan() == {"viejo"}


def test_dry_run_cuenta_sin_borrar() -> None:
    _crear("viejo", timedelta(days=40), [("entregada", timedelta(days=40))])
    resumen = purgar(Reloj(), dry_run=True)
    assert (resumen.candidatos, resumen.borrados, resumen.dry_run) == (1, 0, True)
    assert _quedan() == {"viejo"}


def test_la_purga_va_por_lotes_hasta_vaciar_lo_que_cumple() -> None:
    for n in range(7):
        _crear(f"v{n}", timedelta(days=40), [("entregada", timedelta(days=40))])
    assert purgar(Reloj(), lote=3).borrados == 7
    assert _quedan() == set()


def test_el_comando_de_purga_tiene_dry_run() -> None:
    _crear("viejo", timedelta(days=40), [("entregada", timedelta(days=40))])
    salida = StringIO()
    call_command("outbox_purgar", "--dry-run", stdout=salida)
    assert "se borrarían: 1" in salida.getvalue()
    assert _quedan() == {"viejo"}
    salida = StringIO()
    call_command("outbox_purgar", stdout=salida)
    assert "borrados: 1" in salida.getvalue()
    assert _quedan() == set()


def test_la_funcion_de_la_base_se_niega_a_borrar_lo_reciente_aunque_se_lo_pidan() -> None:
    _crear("reciente", timedelta(days=5), [("entregada", timedelta(days=5))])
    ahora = datetime.now(UTC)
    for corte in (ahora, ahora - timedelta(days=29)):
        with (
            pytest.raises(Exception, match="purga_fuera_de_plazo"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT nucleo.purgar_eventos_outbox(%s, 10)", [corte])
    with (
        pytest.raises(Exception, match="purga_lote_invalido"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT nucleo.purgar_eventos_outbox(%s, 0)", [ahora - timedelta(days=31)])
    assert _quedan() == {"reciente"}


def test_beat_programa_la_purga_una_vez_al_dia_fuera_de_la_cola_del_outbox() -> None:
    from celery import current_app as app

    app.loader.import_default_modules()
    assert "nucleo.purgar_outbox" in app.tasks
    horario = app.conf.beat_schedule["purgar-outbox"]
    assert horario["task"] == "nucleo.purgar_outbox"
    assert horario["schedule"].hour == {9}
    assert "nucleo.purgar_outbox" not in app.conf.task_routes  # cola por defecto, no `outbox`


# --- Aislamiento: las suscripciones de una prueba no se fugan ---


def test_aislamiento_retira_los_consumidores_suscritos_adentro() -> None:
    from nucleo.puertos import RegistroDeConsumidores as Registro

    registro = obtener(Registro)
    antes = registro.nombres()
    with Aislamiento():
        registro.suscribir("fugado", lambda e: None)
        assert "fugado" in registro.nombres()
    assert registro.nombres() == antes


def test_suscribir_tarde_no_reentrega_lo_ya_publicado() -> None:
    reloj = Reloj()
    consumidores = RegistroDeConsumidores()
    fabrica = FabricaDePublicadoresDjango(consumidores, reloj)
    with transaction.atomic():
        fabrica.de("nucleo").publicar(_evento(1))
    recibidos: list[str] = []
    consumidores.suscribir("tardio", lambda e: recibidos.append(e.agregado_id))
    with transaction.atomic():
        fabrica.de("nucleo").publicar(_evento(2))
    Despachador(consumidores, fabrica.de("nucleo"), reloj).procesar_lote()
    assert recibidos == ["a-2"]  # el evento anterior a la suscripcion no se reentrega


def test_retirar_suscripciones_nuevas_deja_el_registro_como_estaba_sin_depender_del_orden() -> None:
    """Es lo que corre el fixture autouse de `conftest.py` despues de cada prueba."""
    from nucleo.pruebas.aislamiento import retirar_suscripciones_nuevas, suscripciones_actuales

    registro = obtener(RegistroDeConsumidores)
    previas = suscripciones_actuales()
    registro.suscribir("de-esta-prueba", lambda e: None)
    assert "de-esta-prueba" in registro.nombres()
    retirar_suscripciones_nuevas(previas)
    assert registro.nombres() == previas
