import re
import socket
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ImproperlyConfigured

from configuracion import entorno


def test_requerida_devuelve_el_valor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_X", "valor")
    assert entorno.requerida("APP_X") == "valor"


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_requerida_falla_si_falta_o_esta_vacia(
    monkeypatch: pytest.MonkeyPatch, valor: str | None
) -> None:
    if valor is None:
        monkeypatch.delenv("APP_X", raising=False)
    else:
        monkeypatch.setenv("APP_X", valor)
    with pytest.raises(ImproperlyConfigured, match="APP_X"):
        entorno.requerida("APP_X")


def test_texto_usa_el_valor_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_X", raising=False)
    assert entorno.texto("APP_X", "defecto") == "defecto"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("1", True), ("TRUE", True), ("si", True), ("0", False), ("false", False), ("", False)],
)
def test_booleana(monkeypatch: pytest.MonkeyPatch, valor: str, esperado: bool) -> None:
    monkeypatch.setenv("APP_B", valor)
    assert entorno.booleana("APP_B", not esperado) is esperado


def test_booleana_invalida_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_B", "quizas")
    with pytest.raises(ImproperlyConfigured):
        entorno.booleana("APP_B", False)


def test_lista_ignora_espacios_y_vacios() -> None:
    assert entorno.lista("a.com, b.com,,  ") == ["a.com", "b.com"]


def test_zona_horaria_acepta_un_nombre_iana_y_recorta_espacios() -> None:
    assert entorno.zona_horaria(" America/Bogota ", variable="APP_X") == "America/Bogota"
    assert entorno.zona_horaria("UTC", variable="APP_X") == "UTC"


@pytest.mark.parametrize("valor", ["", "Mexico", "America/Nadie", "../etc/passwd", "a\x00b"])
def test_zona_horaria_desconocida_falla_al_arrancar(valor: str) -> None:
    with pytest.raises(ImproperlyConfigured, match="APP_X"):
        entorno.zona_horaria(valor, variable="APP_X")


@pytest.mark.parametrize(
    "legada",
    [
        "posixrules",
        "EST5EDT",
        "CST6CDT",
        "EST",
        "CST",
        "PST8PDT",
        "GMT",
        "Cuba",
        "Japan",
        "Etc/GMT+5",
        "Etc/UTC",
        "Etc/GMT",
        "US/Eastern",
        "US/Central",
        "Canada/Eastern",
        "Mexico/General",
        "Brazil/East",
        "Australia/ACT",
        "Australia/NSW",
        "posix/America/Bogota",
        "right/America/Bogota",
    ],
)
def test_zona_horaria_rechaza_nombres_legados_o_ambiguos_aunque_zoneinfo_los_conozca(
    legada: str,
) -> None:
    with pytest.raises(ImproperlyConfigured, match=r"APP_X.*legada o ambigua"):
        entorno.zona_horaria(legada, variable="APP_X")


@pytest.mark.parametrize("legada", ["EST5EDT", "US/Eastern", "Etc/GMT+5", "Cuba"])
def test_zoneinfo_si_conoce_los_nombres_legados_por_eso_no_basta_con_zoneinfo(
    legada: str,
) -> None:
    ZoneInfo(legada)  # no lanza: la lista de arriba es una regla propia, no la de `zoneinfo`


@pytest.mark.parametrize(
    "valida", ["UTC", "America/Mexico_City", "America/New_York", "Europe/Madrid", "Asia/Tokyo"]
)
def test_zona_horaria_acepta_utc_y_las_zonas_area_ciudad(valida: str) -> None:
    assert entorno.zona_horaria(valida, variable="APP_X") == valida


def test_parsear_url_base_de_datos() -> None:
    config = entorno.parsear_url_base_de_datos("postgres://app:p%40ss@db.interno:5433/app_prod")
    assert config == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "app_prod",
        "USER": "app",
        "PASSWORD": "p@ss",
        "HOST": "db.interno",
        "PORT": "5433",
    }


def test_parsear_url_con_host_de_socket_y_opciones() -> None:
    config = entorno.parsear_url_base_de_datos(
        "postgresql://postgres:@/postgres?host=/tmp/pg&sslmode=disable"
    )
    assert config["HOST"] == "/tmp/pg"  # noqa: S108
    assert config["OPTIONS"] == {"sslmode": "disable"}


def test_parsear_url_rechaza_otros_motores() -> None:
    with pytest.raises(ImproperlyConfigured):
        entorno.parsear_url_base_de_datos("mysql://u:p@h/db")


# --- entero y marcador de ejemplo --------------------------------------------------------


def test_entero_usa_el_valor_por_defecto_si_falta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_N", raising=False)
    assert entorno.entero("APP_N", 7, minimo=1) == 7
    monkeypatch.setenv("APP_N", "  ")
    assert entorno.entero("APP_N", 7, minimo=1) == 7


def test_entero_lee_el_valor_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_N", " 300 ")
    assert entorno.entero("APP_N", 7, minimo=1) == 300


@pytest.mark.parametrize("valor", ["0", "-5", "abc", "1.5", "11"])
def test_entero_rechaza_lo_que_no_cumple_el_rango(
    monkeypatch: pytest.MonkeyPatch, valor: str
) -> None:
    monkeypatch.setenv("APP_N", valor)
    with pytest.raises(ImproperlyConfigured, match="APP_N"):
        entorno.entero("APP_N", 7, minimo=1, maximo=10)


@pytest.mark.parametrize(
    "valor",
    [
        "CAMBIAR_clave",
        "cambiar-clave",
        "postgres://app_web:CAMBIAR_clave@postgres:5432/app",
        "  Cambiar  ",
    ],
)
def test_sin_marcador_de_ejemplo_rechaza_los_valores_de_env_ejemplo(valor: str) -> None:
    with pytest.raises(ImproperlyConfigured, match="CLAVE"):
        entorno.sin_marcador_de_ejemplo("CLAVE", valor)


def test_sin_marcador_de_ejemplo_acepta_un_secreto_real() -> None:
    secreto = "9f2c" * 16
    assert entorno.sin_marcador_de_ejemplo("CLAVE", secreto) == secreto


# --- Public Suffix List empaquetada ------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    [".github.io", ".herokuapp.com", ".com.mx", ".co.uk", ".nom.es", ".ne.jp", ".gob.mx"],
)
def test_hosts_rechaza_un_comodin_que_es_un_sufijo_publico(host: str) -> None:
    with pytest.raises(ImproperlyConfigured, match="sufijo publico"):
        entorno.hosts_permitidos_de_produccion(f"app.empresa.example,{host}")


@pytest.mark.parametrize("host", [".empresa.example", ".empresa.com.mx", "app.empresa.example"])
def test_hosts_acepta_lo_que_cuelga_de_un_dominio_registrado(host: str) -> None:
    assert entorno.hosts_permitidos_de_produccion(host) == [host]


def test_la_lista_de_sufijos_publicos_se_usa_sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """La PSL viene empaquetada: validar hosts no abre NINGUNA conexion ni resuelve nombres."""

    def prohibido(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("se intento usar la red")

    for nombre in ("getaddrinfo", "gethostbyname", "create_connection"):
        monkeypatch.setattr(socket, nombre, prohibido)
    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(socket.socket, "connect_ex", prohibido)

    # Una instancia NUEVA (relee el archivo empaquetado) y la validacion completa, ambas sin red.
    from publicsuffixlist import PublicSuffixList

    assert PublicSuffixList().publicsuffix("app.empresa.com.mx") == "com.mx"
    with pytest.raises(ImproperlyConfigured):
        entorno.hosts_permitidos_de_produccion(".github.io")
    assert entorno.hosts_permitidos_de_produccion(".empresa.example") == [".empresa.example"]


def test_el_codigo_no_usa_la_descarga_de_la_lista() -> None:
    from pathlib import Path

    fuente = Path(entorno.__file__).read_text(encoding="utf-8")
    assert not re.search(r"(import|from)\s+publicsuffixlist\.update", fuente)
    assert "tldextract" not in fuente
