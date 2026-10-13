"""Selección de adaptadores por configuración y prohibición de los falsos en producción.

DISENO D.1.4: "En producción está prohibido conectar un adaptador falso: la aplicación se niega a
arrancar". `configuracion` conecta los adaptadores a los puertos de `nucleo.puertos` al arrancar.

El esqueleto no trae puertos elegibles, así que estas pruebas declaran uno de ejemplo
(`APP_ADAPTADOR_EJEMPLO`) para ejercitar el mecanismo; cada puerto que el proyecto agregue hereda
estas reglas.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.core.exceptions import ImproperlyConfigured

from configuracion import adaptadores
from configuracion.adaptadores import PuertoElegible
from configuracion.pruebas.test_settings import (
    SECRET_KEY_DE_PRUEBA,
    VARIABLES_PROD,
    _aislar_modulos_de_settings,  # noqa: F401  (fixture autouse: restaura los settings recargados)
    _cargar,
    _cargar_prod,
)
from nucleo.pruebas.aislamiento import Aislamiento
from nucleo.puertos import registro

DESPLIEGUE = Path(__file__).resolve().parents[2] / "despliegue"
VARIABLE = "APP_ADAPTADOR_EJEMPLO"
EJEMPLO = PuertoElegible(VARIABLE, (adaptadores.FALSO, "real"), "real")


@pytest.fixture
def entorno_prod(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for nombre, valor in VARIABLES_PROD.items():
        monkeypatch.setenv(nombre, valor)
    for variable in (VARIABLE, "APP_PERMITIR_ADAPTADORES_FALSOS"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(adaptadores, "PUERTOS_ELEGIBLES", (EJEMPLO,))
    return monkeypatch


# --- Producción se niega a arrancar con un adaptador falso ----------------------------------------


def test_prod_por_defecto_elige_los_adaptadores_reales(entorno_prod: pytest.MonkeyPatch) -> None:
    assert _cargar_prod().APP_ADAPTADORES == {VARIABLE: "real"}


def test_prod_se_niega_a_arrancar_con_un_adaptador_falso(entorno_prod: pytest.MonkeyPatch) -> None:
    entorno_prod.setenv(VARIABLE, "falso")
    with pytest.raises(ImproperlyConfigured, match=f"{VARIABLE}=falso no se admite en producción"):
        _cargar_prod()


@pytest.mark.parametrize(
    "hosts", ["app.empresa.example", "localhost,app.empresa.example", "10.0.0.5"]
)
def test_el_permiso_de_falsos_no_vale_en_un_servidor_real(
    entorno_prod: pytest.MonkeyPatch, hosts: str
) -> None:
    entorno_prod.setenv("ALLOWED_HOSTS", hosts)
    entorno_prod.setenv("APP_PERMITIR_ADAPTADORES_FALSOS", "true")
    entorno_prod.setenv(VARIABLE, "falso")
    with pytest.raises(ImproperlyConfigured, match="APP_PERMITIR_ADAPTADORES_FALSOS"):
        _cargar_prod()


def test_el_permiso_tampoco_se_deja_puesto_con_adaptadores_reales(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    """Un servidor real con la variable de desarrollo olvidada también falla."""
    entorno_prod.setenv("APP_PERMITIR_ADAPTADORES_FALSOS", "true")
    with pytest.raises(ImproperlyConfigured, match="APP_PERMITIR_ADAPTADORES_FALSOS"):
        _cargar_prod()


def test_el_permiso_olvidado_falla_aunque_no_haya_puertos_elegibles(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    """Así arranca el esqueleto: sin puertos elegibles, la regla del permiso sigue vigente."""
    entorno_prod.setattr(adaptadores, "PUERTOS_ELEGIBLES", ())
    entorno_prod.setenv("APP_PERMITIR_ADAPTADORES_FALSOS", "true")
    with pytest.raises(ImproperlyConfigured, match="APP_PERMITIR_ADAPTADORES_FALSOS"):
        _cargar_prod()


@pytest.mark.parametrize("hosts", ["localhost", "127.0.0.1", "localhost,127.0.0.1,[::1]"])
def test_el_compose_de_desarrollo_en_la_propia_maquina_si_arranca_con_falsos(
    entorno_prod: pytest.MonkeyPatch, hosts: str
) -> None:
    entorno_prod.setenv("ALLOWED_HOSTS", hosts)
    entorno_prod.setenv("APP_PERMITIR_ADAPTADORES_FALSOS", "true")
    entorno_prod.setenv(VARIABLE, "falso")
    assert _cargar_prod().APP_ADAPTADORES == {VARIABLE: "falso"}


def test_sin_el_permiso_ni_en_localhost_se_aceptan_los_falsos(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("ALLOWED_HOSTS", "localhost")
    entorno_prod.setenv(VARIABLE, "falso")
    with pytest.raises(ImproperlyConfigured, match="no se admite en producción"):
        _cargar_prod()


@pytest.mark.parametrize("permitir", ["true", "false"])
def test_elegir_en_produccion_exige_hosts_y_no_acepta_una_lista_vacia(
    entorno_prod: pytest.MonkeyPatch, permitir: str
) -> None:
    """`set() <= HOSTS_DE_LA_MAQUINA` es verdadero; sin hosts no se puede decidir nada."""
    entorno_prod.setenv("APP_PERMITIR_ADAPTADORES_FALSOS", permitir)
    entorno_prod.setenv(VARIABLE, "falso")
    vacios: tuple[Sequence[str], ...] = ([], ())
    for vacio in vacios:
        with pytest.raises(ImproperlyConfigured, match="al menos un host"):
            adaptadores.elegir_en_produccion(vacio)


@pytest.mark.parametrize(
    "hosts", ["localhost", "127.0.0.1", "", "app.empresa.example", b"localhost"]
)
def test_elegir_en_produccion_rechaza_un_texto_suelto_como_hosts(
    entorno_prod: pytest.MonkeyPatch, hosts: str
) -> None:
    entorno_prod.setenv("APP_PERMITIR_ADAPTADORES_FALSOS", "true")
    entorno_prod.setenv(VARIABLE, "falso")
    with pytest.raises(TypeError, match="hosts_permitidos"):
        adaptadores.elegir_en_produccion(hosts)  # type: ignore[arg-type]


def test_elegir_en_produccion_acepta_una_lista_o_tupla_de_hosts_de_la_maquina(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("APP_PERMITIR_ADAPTADORES_FALSOS", "true")
    entorno_prod.setenv(VARIABLE, "falso")
    assert adaptadores.elegir_en_produccion(["localhost"]) == {VARIABLE: "falso"}
    assert adaptadores.elegir_en_produccion(("127.0.0.1", "[::1]")) == {VARIABLE: "falso"}


def test_un_adaptador_desconocido_no_arranca(entorno_prod: pytest.MonkeyPatch) -> None:
    entorno_prod.setenv(VARIABLE, "inventado")
    with pytest.raises(ImproperlyConfigured, match=VARIABLE):
        _cargar_prod()


# --- Desarrollo y pruebas usan los falsos ---------------------------------------------------------


def test_desarrollo_usa_los_falsos_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://app:clave@db:5432/app")
    monkeypatch.delenv(VARIABLE, raising=False)
    monkeypatch.setattr(adaptadores, "PUERTOS_ELEGIBLES", (EJEMPLO,))
    assert _cargar("dev").APP_ADAPTADORES == {VARIABLE: "falso"}


def test_desarrollo_acepta_un_adaptador_real_por_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://app:clave@db:5432/app")
    monkeypatch.setenv(VARIABLE, "real")
    monkeypatch.setattr(adaptadores, "PUERTOS_ELEGIBLES", (EJEMPLO,))
    assert _cargar("dev").APP_ADAPTADORES == {VARIABLE: "real"}


def test_las_pruebas_siempre_usan_los_falsos_aunque_el_entorno_diga_otra_cosa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(VARIABLE, "real")
    monkeypatch.setattr(adaptadores, "PUERTOS_ELEGIBLES", (EJEMPLO,))
    assert _cargar("pruebas").APP_ADAPTADORES == {VARIABLE: "falso"}


def test_el_esqueleto_no_declara_puertos_elegibles() -> None:
    """Si esta prueba falla es porque agregaste tu primer puerto elegible: bórrala y agrega las
    pruebas de ese puerto (su adaptador falso conectado al arrancar y su prueba de contrato)."""
    assert adaptadores.PUERTOS_ELEGIBLES == ()
    assert adaptadores.falsos() == {}


def test_el_paso_de_migraciones_no_elige_adaptadores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", SECRET_KEY_DE_PRUEBA)
    monkeypatch.setenv("DATABASE_MIGRACIONES_URL", "postgres://app_migraciones:clave@db:5432/app")
    migraciones = _cargar("migraciones")
    assert not hasattr(migraciones, "APP_ADAPTADORES")


# --- Conexión de los adaptadores al arrancar ------------------------------------------------------


def test_conectar_rechaza_un_adaptador_de_un_puerto_no_declarado() -> None:
    with pytest.raises(ImproperlyConfigured, match="APP_ADAPTADOR_FANTASMA"):
        adaptadores.conectar({"APP_ADAPTADOR_FANTASMA": "falso"})


def test_al_arrancar_se_conecta_el_verificador_del_segundo_factor() -> None:
    """El segundo factor no falla cerrado por falta de adaptador; el TOTP real esta conectado."""
    from identidad.adaptadores.salida.segundo_factor import VerificadorTotp
    from identidad.aplicacion.puertos import VerificadorSegundoFactor

    assert isinstance(registro.obtener(VerificadorSegundoFactor), VerificadorTotp)


def test_el_segundo_factor_se_conecta_una_sola_vez() -> None:
    with Aislamiento():
        adaptadores.conectar_segundo_factor()
        with pytest.raises(registro.PuertoYaConectado):
            adaptadores.conectar_segundo_factor()


# --- Docker Compose -------------------------------------------------------------------------------


class _Cargador(yaml.SafeLoader):
    """Lee los Compose ignorando etiquetas propias de Compose (`!reset`, `!override`)."""


_Cargador.add_multi_constructor("!", lambda cargador, sufijo, nodo: None)


def _compose(nombre: str) -> dict[str, Any]:
    texto = (DESPLIEGUE / nombre).read_text(encoding="utf-8")
    datos: dict[str, Any] = yaml.load(texto, Loader=_Cargador)  # noqa: S506  # nosec B506
    return datos


def test_el_compose_de_desarrollo_arranca_web_y_worker_con_el_permiso_de_falsos() -> None:
    desarrollo = _compose("docker-compose.yml")
    assert desarrollo["x-entorno-app"]["APP_PERMITIR_ADAPTADORES_FALSOS"] == "true"
    for servicio in ("web", "worker"):
        entorno = desarrollo["services"][servicio]["environment"]
        assert entorno["APP_PERMITIR_ADAPTADORES_FALSOS"] == "true"


def test_el_compose_pasa_la_llave_del_segundo_factor_a_web_y_worker() -> None:
    desarrollo = _compose("docker-compose.yml")
    assert "APP_LLAVE_SEGUNDO_FACTOR" in desarrollo["x-entorno-app"]
    for servicio in ("web", "worker"):
        assert "APP_LLAVE_SEGUNDO_FACTOR" in desarrollo["services"][servicio]["environment"]
    # La llave NO llega al paso de migraciones, que no usa el segundo factor.
    assert "APP_LLAVE_SEGUNDO_FACTOR" not in desarrollo["services"]["migrar"]["environment"]


def test_el_compose_de_pruebas_revierte_los_falsos() -> None:
    pruebas = _compose("docker-compose.pruebas.yml")
    for servicio in ("web", "worker"):
        entorno = pruebas["services"][servicio]["environment"]
        assert entorno["APP_PERMITIR_ADAPTADORES_FALSOS"] == "false"
