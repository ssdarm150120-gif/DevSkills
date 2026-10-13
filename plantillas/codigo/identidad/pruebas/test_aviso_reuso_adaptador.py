"""Aviso por reuso de un codigo del segundo factor: adaptadores de salida y pantalla de inicio.

El caso de uso se prueba con puertos falsos en `test_aviso_reuso.py`; los escenarios, en
`test_escenarios_aviso_por_reuso.py`; las carreras, en `test_aviso_reuso_concurrencia.py`. Aqui va
lo que depende de Django y de la base: el bloqueo de la fila, el filtro de intentos, la zona horaria
configurada, y que la pantalla no filtre datos, no se guarde en cache y no cambie el ingreso.
"""

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

import pytest
from django.db import connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext

from identidad.adaptadores.entrada import composicion
from identidad.adaptadores.salida.avisos_reuso import (
    AvisosDeReusoDjango,
    ZonaHorariaDeConfiguracion,
)
from identidad.adaptadores.salida.modelos import IntentoIngreso, Usuario
from identidad.adaptadores.salida.segundo_factor import codigo_del_paso
from identidad.aplicacion.errores import CuentaNoDisponible
from identidad.dominio.acceso import Factor, Motivo, Resultado
from identidad.dominio.segundo_factor import paso_de
from identidad.pruebas.conftest import CONTRASENA, entrar
from nucleo.actor import Actor

pytestmark = pytest.mark.django_db

T0 = datetime(2026, 10, 12, 18, 30, 7, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _zona_de_la_ciudad_de_mexico(settings: Any) -> None:
    """Las fechas esperadas de estas pruebas estan en la zona de la Ciudad de Mexico."""
    settings.APP_ZONA_HORARIA = "America/Mexico_City"


def _intento(
    usuario: Usuario | None,
    momento: datetime,
    motivo: Motivo = Motivo.CODIGO_REPETIDO,
    ip: str = "203.0.113.9",
) -> IntentoIngreso:
    return IntentoIngreso.objects.create(
        usuario_id=usuario.id if usuario else None,
        huella_correo="0" * 64,
        factor=Factor.CODIGO.value,
        resultado=Resultado.FALLIDO.value,
        motivo=motivo.value,
        ip=ip,
        ocurrido_en=momento,
    )


# --- El adaptador de la marca ------------------------------------------------------------------


def test_bloquear_la_marca_exige_una_transaccion(crear_usuario: Callable[..., Usuario]) -> None:
    usuario = crear_usuario()
    adaptador = AvisosDeReusoDjango()
    # Dentro de la transaccion de la prueba funciona: no hay marca todavia.
    assert adaptador.bloquear_marca(str(usuario.id)) is None


@pytest.mark.django_db(transaction=True)
def test_sin_transaccion_el_bloqueo_falla_en_voz_alta(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    # Sin el bloqueo dos lecturas simultaneas mostrarian el mismo aviso: no se calla.
    with pytest.raises(transaction.TransactionManagementError):
        AvisosDeReusoDjango().bloquear_marca(str(usuario.id))


@pytest.mark.parametrize("identificador", [str(uuid.UUID(int=0)), "no-es-un-uuid", ""])
def test_un_usuario_que_no_existe_es_un_error_de_dominio(identificador: str) -> None:
    with pytest.raises(CuentaNoDisponible):
        AvisosDeReusoDjango().bloquear_marca(identificador)


def test_el_ultimo_intento_solo_cuenta_reusos_del_propio_usuario(
    crear_usuario: Callable[..., Usuario],
) -> None:
    ana = crear_usuario(correo="ana@empresa.example")
    luis = crear_usuario(correo="luis@empresa.example")
    _intento(ana, T0 - timedelta(hours=3))
    _intento(ana, T0, Motivo.CODIGO_REPETIDO)
    _intento(ana, T0 + timedelta(hours=1), Motivo.CODIGO_INVALIDO)  # otro motivo: no cuenta
    _intento(ana, T0 + timedelta(hours=2), Motivo.CONTRASENA_INCORRECTA)
    _intento(luis, T0 + timedelta(hours=5))  # de otro usuario
    _intento(None, T0 + timedelta(hours=6))  # sin usuario
    adaptador = AvisosDeReusoDjango()
    ultimo_de_ana = adaptador.ultimo_intento_de_reuso(str(ana.id), despues_de=None)
    assert ultimo_de_ana is not None
    assert ultimo_de_ana.ocurrido_en == T0
    ultimo_de_luis = adaptador.ultimo_intento_de_reuso(str(luis.id), despues_de=None)
    assert ultimo_de_luis is not None
    assert ultimo_de_luis.ocurrido_en == T0 + timedelta(hours=5)


def test_el_ultimo_intento_es_el_de_mayor_id_aunque_su_fecha_sea_anterior(
    crear_usuario: Callable[..., Usuario],
) -> None:
    """manda el id (el orden de llegada), no el reloj."""
    usuario = crear_usuario()
    _intento(usuario, T0 + timedelta(hours=5))
    nuevo = _intento(usuario, T0)  # llega despues, con una fecha anterior (reloj atrasado)
    ultimo = AvisosDeReusoDjango().ultimo_intento_de_reuso(str(usuario.id), despues_de=None)
    assert ultimo is not None
    assert (ultimo.id, ultimo.ocurrido_en) == (nuevo.pk, T0)


def test_despues_de_es_estricto_y_por_id(crear_usuario: Callable[..., Usuario]) -> None:
    usuario = crear_usuario()
    intento = _intento(usuario, T0)
    adaptador = AvisosDeReusoDjango()
    assert adaptador.ultimo_intento_de_reuso(str(usuario.id), despues_de=intento.pk) is None
    visto = adaptador.ultimo_intento_de_reuso(str(usuario.id), despues_de=intento.pk - 1)
    assert visto is not None
    assert visto.id == intento.pk


def test_la_marca_se_lee_sin_bloqueo_y_con_bloqueo(crear_usuario: Callable[..., Usuario]) -> None:
    usuario = crear_usuario(aviso_reuso_visto_hasta_id=77)
    adaptador = AvisosDeReusoDjango()
    with CaptureQueriesContext(connection) as sin_bloqueo:
        assert adaptador.marca(str(usuario.id)) == 77
    with CaptureQueriesContext(connection) as con_bloqueo:
        assert adaptador.bloquear_marca(str(usuario.id)) == 77
    assert not any("FOR UPDATE" in q["sql"].upper() for q in sin_bloqueo.captured_queries)
    assert any("FOR UPDATE" in q["sql"].upper() for q in con_bloqueo.captured_queries)


@pytest.mark.parametrize("identificador", [str(uuid.UUID(int=0)), "no-es-un-uuid", ""])
def test_leer_la_marca_de_un_usuario_que_no_existe_es_un_error_de_dominio(
    identificador: str,
) -> None:
    with pytest.raises(CuentaNoDisponible):
        AvisosDeReusoDjango().marca(identificador)


def test_marcar_visto_guarda_el_id_y_no_retrocede(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    adaptador = AvisosDeReusoDjango()
    adaptador.marcar_visto(str(usuario.id), hasta_id=50)
    adaptador.marcar_visto(str(usuario.id), hasta_id=10)  # una marca vieja
    usuario.refresh_from_db()
    assert usuario.aviso_reuso_visto_hasta_id == 50
    adaptador.marcar_visto(str(usuario.id), hasta_id=50)  # la misma: no cambia
    adaptador.marcar_visto(str(usuario.id), hasta_id=51)
    usuario.refresh_from_db()
    assert usuario.aviso_reuso_visto_hasta_id == 51


def test_marcar_visto_no_toca_a_otro_usuario(crear_usuario: Callable[..., Usuario]) -> None:
    ana = crear_usuario(correo="ana@empresa.example")
    luis = crear_usuario(correo="luis@empresa.example")
    AvisosDeReusoDjango().marcar_visto(str(ana.id), hasta_id=5)
    luis.refresh_from_db()
    assert luis.aviso_reuso_visto_hasta_id is None


def test_la_marca_admite_ids_de_bigint(crear_usuario: Callable[..., Usuario]) -> None:
    grande = 2**40  # mas que un entero de 32 bits
    usuario = crear_usuario()
    AvisosDeReusoDjango().marcar_visto(str(usuario.id), hasta_id=grande)
    usuario.refresh_from_db()
    assert usuario.aviso_reuso_visto_hasta_id == grande


# --- La zona horaria configurada --------------------------------------------------------------


def test_la_zona_sale_de_la_configuracion(settings: Any) -> None:
    settings.APP_ZONA_HORARIA = "America/Bogota"
    assert ZonaHorariaDeConfiguracion().zona().key == "America/Bogota"  # gitleaks:allow
    settings.APP_ZONA_HORARIA = "UTC"
    assert ZonaHorariaDeConfiguracion().zona().key == "UTC"  # gitleaks:allow


# --- La pantalla de inicio ---------------------------------------------------------------------


def _con_aviso(crear_usuario: Callable[..., Usuario], **campos: Any) -> tuple[Usuario, Client]:
    usuario = crear_usuario(**campos)
    _intento(usuario, T0)
    return usuario, entrar(usuario)


def test_el_inicio_muestra_el_aviso_y_deja_la_marca_en_el_id_del_intento(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    _intento(usuario, T0 - timedelta(hours=1))
    mostrado = _intento(usuario, T0)
    pagina = entrar(usuario).get("/")
    assert "12/10/2026 12:30:07 CST (America/Mexico_City)" in pagina.content.decode()
    usuario.refresh_from_db()
    assert usuario.aviso_reuso_visto_hasta_id == mostrado.pk


@pytest.mark.parametrize(
    ("zona", "esperado"),
    [
        ("America/Mexico_City", "12/10/2026 12:30:07 CST (America/Mexico_City)"),
        ("America/Bogota", "12/10/2026 13:30:07 -05 (America/Bogota)"),
        ("America/New_York", "12/10/2026 14:30:07 EDT (America/New_York)"),
        ("UTC", "12/10/2026 18:30:07 UTC (UTC)"),
    ],
)
def test_la_hora_se_muestra_en_la_zona_configurada(
    crear_usuario: Callable[..., Usuario], settings: Any, zona: str, esperado: str
) -> None:
    settings.APP_ZONA_HORARIA = zona
    _, navegador = _con_aviso(crear_usuario)
    assert esperado in navegador.get("/").content.decode()


def test_el_aviso_no_revela_nada_de_quien_intento(crear_usuario: Callable[..., Usuario]) -> None:
    usuario = crear_usuario()
    _intento(usuario, T0, ip="198.51.100.23")
    contenido = entrar(usuario).get("/").content.decode()
    assert "Alguien intentó usar un código tuyo ya utilizado el" in contenido
    assert "198.51.100.23" not in contenido
    assert "0" * 64 not in contenido  # la huella del correo capturado


def test_la_respuesta_con_aviso_no_se_guarda_en_cache(
    crear_usuario: Callable[..., Usuario],
) -> None:
    _, navegador = _con_aviso(crear_usuario)
    respuesta = navegador.get("/")
    control = respuesta["Cache-Control"]
    assert "no-store" in control
    assert "private" in control
    assert "no-cache" in control


def test_la_pantalla_con_aviso_no_lleva_javascript_ni_estilos_en_linea(
    crear_usuario: Callable[..., Usuario],
) -> None:
    _, navegador = _con_aviso(crear_usuario)
    contenido = navegador.get("/").content.decode().lower()
    assert 'id="aviso-reuso"' in contenido
    for prohibido in ("<script", "style=", "<style", "javascript:", "onclick=", "onload="):
        assert prohibido not in contenido, prohibido


class _ZonaConHtml(tzinfo):
    """Una zona cuyo nombre y abreviatura traen HTML: el aviso debe mostrarlos como texto."""

    key = "<img src=x onerror=alert(1)>&\"'"

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return "<b>Z</b>"


def test_el_aviso_escapa_su_contenido(
    crear_usuario: Callable[..., Usuario], monkeypatch: pytest.MonkeyPatch
) -> None:
    """se inyecta HTML en el texto del aviso (por el puerto de zonas) y sale escapado.

    Con `|safe` en la plantilla, o con el autoescape apagado, el HTML llegaria tal cual."""
    monkeypatch.setattr(
        ZonaHorariaDeConfiguracion, "zona", lambda self: _ZonaConHtml(), raising=True
    )
    _, navegador = _con_aviso(crear_usuario)
    contenido = navegador.get("/").content.decode()
    assert "&lt;b&gt;Z&lt;/b&gt;" in contenido  # la abreviatura
    assert "&lt;img src=x onerror=alert(1)&gt;&amp;&quot;&#x27;" in contenido  # el nombre
    assert "<b>Z</b>" not in contenido
    assert "<img" not in contenido
    assert "onerror=alert(1)>" not in contenido


def test_sin_sesion_el_inicio_no_muestra_nada() -> None:
    respuesta = Client().get("/")
    assert respuesta.status_code == 302
    assert "aviso" not in respuesta.content.decode().lower()


def test_otra_pantalla_no_consume_el_aviso(crear_usuario: Callable[..., Usuario]) -> None:
    usuario, navegador = _con_aviso(crear_usuario)
    assert navegador.get("/cuenta/contrasena").status_code == 200
    usuario.refresh_from_db()
    assert usuario.aviso_reuso_visto_hasta_id is None  # solo el inicio lo muestra y lo marca
    assert 'id="aviso-reuso"' in navegador.get("/").content.decode()


# --- Las etapas intermedias del ingreso ni muestran ni consumen el aviso -------------


def _sin_aviso(usuario: Usuario, *respuestas: Any) -> None:
    """Ninguna de las respuestas trae el aviso y la marca del usuario sigue sin tocarse."""
    for respuesta in respuestas:
        contenido = respuesta.content.decode()
        assert "Alguien intentó" not in contenido
        assert 'id="aviso-reuso"' not in contenido
    usuario.refresh_from_db()
    assert usuario.aviso_reuso_visto_hasta_id is None


def _paso_uno(correo: str) -> tuple[Client, str]:
    """Contrasena correcta: devuelve el navegador (con la etapa pendiente) y a donde lo manda."""
    navegador = Client()
    respuesta = navegador.post("/ingresar", {"correo": correo, "contrasena": CONTRASENA})
    return navegador, respuesta["Location"]


def test_la_etapa_del_codigo_ni_muestra_ni_consume_el_aviso(
    crear_usuario: Callable[..., Usuario], registrar_segundo_factor: Callable[..., bytes]
) -> None:
    usuario = crear_usuario(roles=("auditor",))
    secreto = registrar_segundo_factor(usuario)
    _intento(usuario, T0)
    navegador, destino = _paso_uno(usuario.correo)
    assert destino == "/ingresar/codigo"
    pagina = navegador.get("/ingresar/codigo")
    incorrecto = navegador.post("/ingresar/codigo", {"codigo": "000000"})
    assert (pagina.status_code, incorrecto.status_code) == (200, 422)
    _sin_aviso(usuario, pagina, incorrecto)
    # El codigo bueno termina el ingreso (302 sin cuerpo): tampoco consume el aviso...
    bueno = navegador.post(
        "/ingresar/codigo", {"codigo": codigo_del_paso(secreto, paso_de(datetime.now(UTC)))}
    )
    assert (bueno.status_code, bueno["Location"]) == (302, "/")
    _sin_aviso(usuario, bueno)
    # ...porque el aviso es del inicio, y sale ahi.
    assert 'id="aviso-reuso"' in navegador.get("/").content.decode()


def test_la_etapa_del_enrolamiento_ni_muestra_ni_consume_el_aviso(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario(roles=("auditor",))  # rol sensible y sin aplicacion registrada
    _intento(usuario, T0)
    navegador, destino = _paso_uno(usuario.correo)
    assert destino == "/ingresar/enrolar"
    pagina = navegador.get("/ingresar/enrolar")
    incorrecto = navegador.post("/ingresar/enrolar", {"codigo": "000000"})
    assert (pagina.status_code, incorrecto.status_code) == (200, 422)
    _sin_aviso(usuario, pagina, incorrecto)


def test_el_cambio_obligatorio_de_contrasena_ni_muestra_ni_consume_el_aviso(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario(debe_cambiar_contrasena=True)
    _intento(usuario, T0)
    navegador, destino = _paso_uno(usuario.correo)
    assert destino == "/ingresar/contrasena"
    pagina = navegador.get("/ingresar/contrasena")
    distinta = navegador.post(
        "/ingresar/contrasena", {"nueva": "una-contrasena-9Lunar", "confirmar": "otra"}
    )
    assert (pagina.status_code, distinta.status_code) == (200, 422)
    _sin_aviso(usuario, pagina, distinta)
    nueva = "otra-contrasena-larga-7Sol"
    definida = navegador.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    assert (definida.status_code, definida["Location"]) == (302, "/")
    _sin_aviso(usuario, definida)
    assert 'id="aviso-reuso"' in navegador.get("/").content.decode()  # solo en el inicio


# --- El inicio lee sin bloqueo y bloquea solo si hay un aviso pendiente ----------------


def _hay_for_update(consultas: CaptureQueriesContext) -> bool:
    return any("FOR UPDATE" in q["sql"].upper() for q in consultas.captured_queries)


def test_sin_avisos_pendientes_el_inicio_no_toma_el_bloqueo_de_la_fila(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    navegador = entrar(usuario)
    with CaptureQueriesContext(connection) as consultas:
        assert navegador.get("/").status_code == 200
    assert not _hay_for_update(consultas)
    # Un reuso de OTRO tipo o de otro usuario tampoco es un pendiente.
    _intento(usuario, T0, Motivo.CODIGO_INVALIDO)
    _intento(crear_usuario(correo="luis@empresa.example"), T0)
    with CaptureQueriesContext(connection) as consultas:
        navegador.get("/")
    assert not _hay_for_update(consultas)


def test_con_un_aviso_pendiente_el_inicio_toma_el_bloqueo_y_despues_ya_no(
    crear_usuario: Callable[..., Usuario],
) -> None:
    _, navegador = _con_aviso(crear_usuario)
    with CaptureQueriesContext(connection) as con_aviso:
        assert 'id="aviso-reuso"' in navegador.get("/").content.decode()
    assert _hay_for_update(con_aviso)
    with CaptureQueriesContext(connection) as sin_aviso:
        assert 'id="aviso-reuso"' not in navegador.get("/").content.decode()
    assert not _hay_for_update(sin_aviso)  # ya visto: vuelve a la lectura sin bloqueo


def test_si_la_cuenta_ya_no_existe_el_inicio_no_es_un_500(
    crear_usuario: Callable[..., Usuario], monkeypatch: pytest.MonkeyPatch
) -> None:
    usuario, navegador = _con_aviso(crear_usuario)

    def _sin_cuenta(actor: Actor) -> None:
        raise CuentaNoDisponible

    monkeypatch.setattr(composicion, "avisos_pendientes", lambda: _sin_cuenta)
    navegador.raise_request_exception = False
    respuesta = navegador.get("/")
    assert respuesta.status_code == 200
    assert 'id="aviso-reuso"' not in respuesta.content.decode()
    usuario.refresh_from_db()
    assert usuario.aviso_reuso_visto_hasta_id is None


def test_si_la_pantalla_no_se_arma_el_aviso_no_queda_como_visto(
    crear_usuario: Callable[..., Usuario], monkeypatch: pytest.MonkeyPatch
) -> None:
    usuario, navegador = _con_aviso(crear_usuario)
    navegador.raise_request_exception = False

    def _falla(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("la plantilla fallo")

    monkeypatch.setattr("identidad.adaptadores.entrada.vistas.render", _falla)
    assert navegador.get("/").status_code == 500
    usuario.refresh_from_db()
    assert usuario.aviso_reuso_visto_hasta_id is None  # la transaccion se deshizo
    monkeypatch.undo()
    assert 'id="aviso-reuso"' in navegador.get("/").content.decode()


def test_un_intento_posterior_a_la_marca_vuelve_a_mostrarse(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario, navegador = _con_aviso(crear_usuario)
    assert 'id="aviso-reuso"' in navegador.get("/").content.decode()
    assert 'id="aviso-reuso"' not in navegador.get("/").content.decode()
    _intento(usuario, T0 + timedelta(hours=1))
    contenido = navegador.get("/").content.decode()
    assert "12/10/2026 13:30:07 CST (America/Mexico_City)" in contenido


def test_el_aviso_es_solo_del_dueno(crear_usuario: Callable[..., Usuario]) -> None:
    _, navegador_de_ana = _con_aviso(crear_usuario, correo="ana@empresa.example")
    luis = crear_usuario(correo="luis@empresa.example")
    assert 'id="aviso-reuso"' not in entrar(luis).get("/").content.decode()
    assert 'id="aviso-reuso"' in navegador_de_ana.get("/").content.decode()


def test_el_caso_de_uso_compuesto_usa_al_actor_y_la_zona_configurada(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario()
    _intento(usuario, T0)
    with transaction.atomic():
        aviso = composicion.avisos_pendientes()(Actor.de(str(usuario.id), ["usuario"]))
    assert aviso is not None
    assert aviso.zona.key == "America/Mexico_City"  # gitleaks:allow


# --- El aviso no cambia el ingreso (sin oraculo de tiempo ni de mensajes) ------------


def _forma(consultas: CaptureQueriesContext) -> list[str]:
    """La forma del trabajo de base de datos: que tipo de sentencia y sobre que tabla."""
    forma = []
    for consulta in consultas.captured_queries:
        sql = consulta["sql"]
        verbo = sql.split()[0].upper()
        tabla = re.search(r'(?:FROM|INTO|UPDATE)\s+("[^"]+"\."[^"]+")', sql)
        forma.append(f"{verbo} {tabla.group(1) if tabla else ''}")
    return forma


def test_el_ingreso_hace_el_mismo_trabajo_con_o_sin_intentos_de_reuso_pendientes(
    crear_usuario: Callable[..., Usuario],
) -> None:
    """Ni la contrasena ni el codigo miran el aviso: solo el inicio lo calcula.

    Si el ingreso hiciera una consulta de mas cuando hay reusos pendientes, el tiempo de respuesta
    de las etapas delataria que alguien intento entrar a esa cuenta (el mismo tipo de oraculo que
    cerro `test_tiempo_ingreso.py`)."""
    sin_nada = crear_usuario(correo="limpio@empresa.example", roles=("usuario",))
    con_reusos = crear_usuario(correo="reusos@empresa.example", roles=("usuario",))
    for hora in range(3):
        _intento(con_reusos, T0 + timedelta(hours=hora))
    formas = []
    respuestas = []
    for usuario in (sin_nada, con_reusos):
        cliente = Client()
        with CaptureQueriesContext(connection) as consultas:
            respuesta = cliente.post(
                "/ingresar", {"correo": usuario.correo, "contrasena": CONTRASENA}
            )
        formas.append(_forma(consultas))
        respuestas.append((respuesta.status_code, respuesta["Location"], len(respuesta.content)))
    assert formas[0] == formas[1]
    assert respuestas[0] == respuestas[1] == (302, "/", 0)


def test_el_codigo_hace_el_mismo_trabajo_con_o_sin_intentos_de_reuso_pendientes(
    crear_usuario: Callable[..., Usuario], registrar_segundo_factor: Callable[..., bytes]
) -> None:
    """Lo mismo para la etapa del codigo, que es donde termina el ingreso con segundo factor."""
    formas = []
    respuestas = []
    for correo, reusos in (("limpio@empresa.example", 0), ("reusos@empresa.example", 3)):
        usuario = crear_usuario(correo=correo, roles=("auditor",))
        secreto = registrar_segundo_factor(usuario)
        for hora in range(reusos):
            _intento(usuario, T0 + timedelta(hours=hora))
        cliente = Client()
        cliente.post("/ingresar", {"correo": correo, "contrasena": CONTRASENA})
        codigo = codigo_del_paso(secreto, paso_de(datetime.now(UTC)))
        with CaptureQueriesContext(connection) as consultas:
            respuesta = cliente.post("/ingresar/codigo", {"codigo": codigo})
        formas.append(_forma(consultas))
        respuestas.append((respuesta.status_code, respuesta["Location"], len(respuesta.content)))
    assert formas[0] == formas[1]
    assert respuestas[0] == respuestas[1] == (302, "/", 0)


def test_las_etapas_del_ingreso_no_consultan_los_intentos_de_reuso(
    crear_usuario: Callable[..., Usuario],
) -> None:
    """Hasta el ingreso completo no hay ninguna consulta de reusos: ni en la contrasena ni en el
    codigo. La consulta del aviso solo existe en el inicio."""
    usuario = crear_usuario(roles=("usuario",))
    _intento(usuario, T0)
    cliente = Client()
    with CaptureQueriesContext(connection) as consultas:
        cliente.post("/ingresar", {"correo": usuario.correo, "contrasena": CONTRASENA})
    marca = "aviso_reuso_visto_hasta_id"
    intentos_de_reuso = [
        q["sql"]
        for q in consultas.captured_queries
        if "intento_ingreso" in q["sql"] and q["sql"].startswith("SELECT")
    ]
    assert intentos_de_reuso == []
    # Y la marca no se lee ni se escribe fuera de las columnas completas del usuario.
    assert not any(
        marca in q["sql"] and q["sql"].startswith("UPDATE") for q in consultas.captured_queries
    )
    with CaptureQueriesContext(connection) as inicio:
        cliente.get("/")
    assert any("intento_ingreso" in q["sql"] for q in inicio.captured_queries)
