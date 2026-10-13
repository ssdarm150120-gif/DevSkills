"""Aviso por reuso de un codigo del segundo factor: dominio y caso de uso, con puertos falsos."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from identidad.aplicacion.avisos_pendientes import AvisosPendientes
from identidad.dominio.aviso_reuso import AvisoDeReuso
from identidad.pruebas.falsos import AvisosEnMemoria, ZonaFalsa
from nucleo.actor import Actor

T0 = datetime(2026, 10, 12, 18, 30, 7, tzinfo=UTC)
ANA = "u-1"


def _actor(id: str = ANA) -> Actor:
    return Actor.de(id, ["auditor"])


def _caso(avisos: AvisosEnMemoria, zona: ZonaFalsa | None = None) -> AvisosPendientes:
    return AvisosPendientes(avisos, zona or ZonaFalsa())


# --- Dominio ------------------------------------------------------------------------------------


def test_el_momento_se_muestra_en_la_zona_configurada_con_dia_mes_anio() -> None:
    aviso = AvisoDeReuso(T0, ZoneInfo("America/Mexico_City"))
    assert aviso.momento_local == "12/10/2026 12:30:07 CST (America/Mexico_City)"
    otra = AvisoDeReuso(T0, ZoneInfo("America/Bogota"))
    assert otra.momento_local == "12/10/2026 13:30:07 -05 (America/Bogota)"  # sin letras: el offset
    assert AvisoDeReuso(T0, ZoneInfo("UTC")).momento_local == "12/10/2026 18:30:07 UTC (UTC)"


def test_el_mensaje_es_el_del_requisito() -> None:
    aviso = AvisoDeReuso(T0, ZoneInfo("America/Mexico_City"))
    assert aviso.mensaje == (
        "Alguien intentó usar un código tuyo ya utilizado el 12/10/2026 12:30:07 CST "
        "(America/Mexico_City); si no fuiste tú, cambia tu contraseña y avisa al administrador"
    )


def test_al_terminar_el_horario_de_verano_dos_instantes_distintos_no_se_ven_iguales() -> None:
    """el 1 nov 2026 en Nueva York la hora 01:30 ocurre DOS veces (EDT y luego EST)."""
    nueva_york = ZoneInfo("America/New_York")
    primera = AvisoDeReuso(datetime(2026, 11, 1, 5, 30, tzinfo=UTC), nueva_york)
    segunda = AvisoDeReuso(datetime(2026, 11, 1, 6, 30, tzinfo=UTC), nueva_york)
    assert primera.momento_local == "01/11/2026 01:30:00 EDT (America/New_York)"
    assert segunda.momento_local == "01/11/2026 01:30:00 EST (America/New_York)"
    assert primera.momento_local != segunda.momento_local


def test_el_cambio_de_dia_por_la_zona_se_respeta() -> None:
    tarde = datetime(2026, 10, 13, 3, 0, tzinfo=UTC)  # en México todavía es el día 12
    assert AvisoDeReuso(tarde, ZoneInfo("America/Mexico_City")).momento_local.startswith(
        "12/10/2026 21:00:00"
    )


def test_un_momento_sin_zona_horaria_se_rechaza() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        AvisoDeReuso(datetime(2026, 10, 12, 12, 0), ZoneInfo("UTC"))


# --- Caso de uso --------------------------------------------------------------------------------


def test_sin_intentos_de_reuso_no_hay_aviso_ni_marca() -> None:
    avisos = AvisosEnMemoria()
    assert _caso(avisos)(_actor()) is None
    assert avisos.marcas == []  # nada que dar por visto
    assert avisos.lecturas == 1  # se miro sin bloqueo...
    assert avisos.bloqueos == 0  # ...y como no habia nada, la fila NO se bloqueo


def test_con_un_intento_pendiente_devuelve_el_aviso_con_su_momento() -> None:
    avisos = AvisosEnMemoria()
    avisos.intento(ANA, T0)
    aviso = _caso(avisos)(_actor())
    assert aviso is not None
    assert aviso.ocurrido_en == T0
    assert aviso.momento_local.endswith("(America/Mexico_City)")
    assert avisos.bloqueos == 1  # con un pendiente SI se toma el bloqueo, una sola vez
    assert avisos.lecturas == 1


def test_con_varios_intentos_muestra_el_mas_reciente_y_da_por_vistos_los_anteriores() -> None:
    avisos = AvisosEnMemoria()
    for minutos in (0, 10, 40):  # llegan en este orden: el ultimo (id mayor) es el mas reciente
        avisos.intento(ANA, T0 + timedelta(minutes=minutos))
    caso = _caso(avisos)
    aviso = caso(_actor())
    assert aviso is not None
    assert aviso.ocurrido_en == T0 + timedelta(minutes=40)
    assert caso(_actor()) is None  # los anteriores tambien quedaron vistos


def test_el_aviso_sale_una_sola_vez() -> None:
    avisos = AvisosEnMemoria()
    avisos.intento(ANA, T0)
    caso = _caso(avisos)
    assert caso(_actor()) is not None
    assert caso(_actor()) is None
    assert caso(_actor()) is None


def test_un_intento_nuevo_despues_del_aviso_vuelve_a_avisar_solo_ese() -> None:
    avisos = AvisosEnMemoria()
    avisos.intento(ANA, T0)
    caso = _caso(avisos)
    caso(_actor())
    nuevo = T0 + timedelta(hours=2)
    avisos.intento(ANA, nuevo)
    aviso = caso(_actor())
    assert aviso is not None
    assert aviso.ocurrido_en == nuevo


def test_la_marca_es_el_id_del_intento_mostrado() -> None:
    avisos = AvisosEnMemoria()
    avisos.intento(ANA, T0)
    mostrado = avisos.intento(ANA, T0 + timedelta(minutes=1))
    _caso(avisos)(_actor())
    assert avisos.marcas == [mostrado]
    assert avisos.visto_hasta[ANA] == mostrado


def test_el_orden_es_el_del_id_y_no_el_de_la_fecha() -> None:
    """un reloj que se atrasa no esconde un intento nuevo ni resucita uno ya visto."""
    avisos = AvisosEnMemoria()
    avisos.intento(ANA, T0 + timedelta(hours=5))
    caso = _caso(avisos)
    assert caso(_actor()) is not None
    atrasado = T0  # el intento NUEVO tiene una fecha ANTERIOR a la del ya visto (reloj atrasado)
    avisos.intento(ANA, atrasado)
    aviso = caso(_actor())
    assert aviso is not None  # con una marca por fecha este aviso se perderia
    assert aviso.ocurrido_en == atrasado
    assert caso(_actor()) is None


def test_la_marca_nunca_retrocede() -> None:
    avisos = AvisosEnMemoria()
    avisos.intento(ANA, T0)
    avisos.intento(ANA, T0)
    caso = _caso(avisos)
    caso(_actor())
    assert avisos.visto_hasta[ANA] == 2
    avisos.marcar_visto(ANA, hasta_id=1)  # una marca vieja llega tarde
    assert avisos.visto_hasta[ANA] == 2


def test_si_otra_pestana_gana_el_bloqueo_la_segunda_comprobacion_no_muestra_nada() -> None:
    """Doble comprobacion: entre la lectura sin bloqueo y el bloqueo, otra pestaña ya
    mostro y marco el aviso; esta no lo repite ni deja otra marca."""
    avisos = AvisosEnMemoria()
    ultimo = avisos.intento(ANA, T0)
    avisos.antes_de_bloquear = lambda: avisos.visto_hasta.__setitem__(ANA, ultimo)
    assert _caso(avisos)(_actor()) is None
    assert avisos.bloqueos == 1
    assert avisos.marcas == []  # no marco nada: la otra pestaña ya lo habia hecho


def test_un_intento_que_llega_entre_la_lectura_y_la_marca_no_se_pierde() -> None:
    avisos = AvisosEnMemoria()
    avisos.intento(ANA, T0)
    llegada = T0 + timedelta(seconds=1)
    avisos.al_marcar = lambda: avisos.intento(ANA, llegada)  # llega justo antes de marcar
    caso = _caso(avisos)
    aviso = caso(_actor())
    assert aviso is not None
    assert aviso.ocurrido_en == T0  # el que se leyo
    avisos.al_marcar = None
    siguiente = caso(_actor())
    assert siguiente is not None
    assert siguiente.ocurrido_en == llegada  # el nuevo sigue pendiente


def test_un_intento_igual_o_anterior_a_la_marca_no_vuelve_a_avisar() -> None:
    avisos = AvisosEnMemoria()
    avisos.intento(ANA, T0)
    avisos.intento(ANA, T0 - timedelta(days=1))
    avisos.visto_hasta[ANA] = 2  # la marca ya cubre ambos ids
    assert _caso(avisos)(_actor()) is None
    assert avisos.bloqueos == 0


def test_solo_cuentan_los_intentos_del_propio_usuario() -> None:
    avisos = AvisosEnMemoria()
    avisos.intento("u-2", T0)
    assert _caso(avisos)(_actor(ANA)) is None
    assert avisos.visto_hasta.get("u-2") is None  # y no toca la marca de otro


@pytest.mark.parametrize("zona", ["America/Mexico_City", "America/Bogota", "UTC"])
def test_la_zona_sale_de_la_configuracion(zona: str) -> None:
    avisos = AvisosEnMemoria()
    avisos.intento(ANA, T0)
    aviso = _caso(avisos, ZonaFalsa(zona))(_actor())
    assert aviso is not None
    assert aviso.zona.key == zona
