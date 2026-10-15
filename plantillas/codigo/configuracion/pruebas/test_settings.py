import ast
import importlib
import os
import re
import ssl
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, RequestFactory, override_settings

from configuracion import localizacion
from configuracion.entorno import (
    LLAVE_HUELLA_DE_DESARROLLO,
    LLAVE_SEGUNDO_FACTOR_DE_DESARROLLO,
)
from identidad.adaptadores.entrada.contexto import contexto_de_la_aplicacion

CODIGO = Path(__file__).resolve().parent.parent.parent
DIRECTORIO_SETTINGS = CODIGO / "configuracion" / "settings"
MODULOS_SETTINGS = ("base", "dev", "pruebas", "prod", "migraciones")

# Clave de PRUEBA, valida y no secreta: >= 50 caracteres y >= 16 distintos (W009 pide 5).
# CI usa los mismos valores en `.github/workflows/ci.yml` (job `calidad`, paso `check --deploy`).
SECRET_KEY_DE_PRUEBA = "ci-clave-de-prueba-no-secreta-solo-para-check-deploy-0123456789"  # noqa: S105
VARIABLES_PROD = {
    "SECRET_KEY": SECRET_KEY_DE_PRUEBA,
    "ALLOWED_HOSTS": "app.empresa.example,www.app.empresa.example",
    "DATABASE_URL": "postgres://app:clave@db:5432/app",
    "REDIS_URL": "redis://redis:6379/0",
    "APP_LLAVE_HUELLA": "ci-llave-de-huella-de-prueba-no-secreta-solo-para-check-deploy-9876543210",
    "APP_LLAVE_SEGUNDO_FACTOR": (
        "ci-llave-del-segundo-factor-de-prueba-no-secreta-solo-para-check-deploy-5555"
    ),
}
HOSTS_LOCALES = {"", "localhost", "127.0.0.1", "::1", "[::1]"}


def _nombre_completo(nombre: str) -> str:
    return f"configuracion.settings.{nombre}"


def _cargar(nombre: str) -> ModuleType:
    """Importa `configuracion.settings.<nombre>` desde cero (para que lea el entorno actual)."""
    sys.modules.pop(_nombre_completo(nombre), None)
    return importlib.import_module(_nombre_completo(nombre))


def _cargar_con_base(nombre: str) -> ModuleType:
    """Como `_cargar`, pero tambien relee `base` (su valor depende del entorno actual)."""
    sys.modules.pop(_nombre_completo("base"), None)
    return _cargar(nombre)


def _cargar_prod() -> ModuleType:
    return _cargar("prod")


@contextmanager
def _restaurar_modulos_de_settings() -> Iterator[None]:
    """Las pruebas recargan los settings: al salir se deja `sys.modules` como estaba.

    En particular, `configuracion.settings.prod` NO debe quedar importado (ni como atributo del
    paquete) si no lo estaba, para no contaminar a otras pruebas.
    """
    paquete = importlib.import_module("configuracion.settings")
    previos = {nombre: sys.modules.get(_nombre_completo(nombre)) for nombre in MODULOS_SETTINGS}
    try:
        yield
    finally:
        for nombre, modulo in previos.items():
            if modulo is None:
                sys.modules.pop(_nombre_completo(nombre), None)
                if hasattr(paquete, nombre):
                    delattr(paquete, nombre)
            else:
                sys.modules[_nombre_completo(nombre)] = modulo
                setattr(paquete, nombre, modulo)


@pytest.fixture(autouse=True)
def _aislar_modulos_de_settings() -> Iterator[None]:
    with _restaurar_modulos_de_settings():
        yield


@pytest.fixture
def entorno_prod(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for nombre, valor in VARIABLES_PROD.items():
        monkeypatch.setenv(nombre, valor)
    return monkeypatch


def test_el_aislamiento_no_deja_prod_en_sys_modules(entorno_prod: pytest.MonkeyPatch) -> None:
    paquete = importlib.import_module("configuracion.settings")
    sys.modules.pop(_nombre_completo("prod"), None)
    if hasattr(paquete, "prod"):
        delattr(paquete, "prod")
    with _restaurar_modulos_de_settings():
        _cargar_prod()
        assert _nombre_completo("prod") in sys.modules
    assert _nombre_completo("prod") not in sys.modules
    assert not hasattr(paquete, "prod")


def test_prod_carga_con_todas_las_variables(entorno_prod: pytest.MonkeyPatch) -> None:
    prod = _cargar_prod()
    assert prod.DEBUG is False
    assert prod.ALLOWED_HOSTS == ["app.empresa.example", "www.app.empresa.example"]
    assert prod.DATABASES["default"]["HOST"] == "db"
    assert prod.CELERY_BROKER_URL == "redis://redis:6379/0"
    assert prod.SESSION_COOKIE_SECURE and prod.CSRF_COOKIE_SECURE
    assert prod.SECURE_HSTS_SECONDS >= 31536000


@pytest.mark.parametrize("faltante", sorted(VARIABLES_PROD))
def test_prod_falla_rapido_si_falta_un_secreto(
    entorno_prod: pytest.MonkeyPatch, faltante: str
) -> None:
    entorno_prod.delenv(faltante)
    with pytest.raises(ImproperlyConfigured, match=faltante):
        _cargar_prod()


def test_prod_sin_ninguna_variable_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    for nombre in VARIABLES_PROD:
        monkeypatch.delenv(nombre, raising=False)
    with pytest.raises(ImproperlyConfigured):
        _cargar_prod()


def test_la_zona_horaria_por_defecto_sale_de_localizacion_y_se_cambia_por_variable(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    # `devskills init --zona ...` reescribe el valor por defecto de `localizacion.py`.
    assert _cargar_con_base("prod").APP_ZONA_HORARIA == localizacion.ZONA_PREDETERMINADA
    entorno_prod.setenv("APP_ZONA_HORARIA", "America/Mexico_City")
    assert _cargar_con_base("prod").APP_ZONA_HORARIA == "America/Mexico_City"
    entorno_prod.setenv("APP_ZONA_HORARIA", "")  # vacia, como la pasa el Compose por defecto
    assert _cargar_con_base("prod").APP_ZONA_HORARIA == localizacion.ZONA_PREDETERMINADA


def test_el_idioma_por_defecto_sale_de_localizacion_y_se_cambia_por_variable(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    # `devskills init --idioma ...` reescribe el valor por defecto de `localizacion.py`.
    assert _cargar_con_base("prod").LANGUAGE_CODE == localizacion.IDIOMA_PREDETERMINADO
    entorno_prod.setenv("APP_IDIOMA", "en")
    assert _cargar_con_base("prod").LANGUAGE_CODE == "en"
    entorno_prod.setenv("APP_IDIOMA", "ES_mx")
    assert _cargar_con_base("prod").LANGUAGE_CODE == "es-mx"
    entorno_prod.setenv("APP_IDIOMA", "")  # vacia, como la pasa el Compose por defecto
    assert _cargar_con_base("prod").LANGUAGE_CODE == localizacion.IDIOMA_PREDETERMINADO


@pytest.mark.parametrize("valor", ["español", "e", "es mx", "es--mx", "123"])
def test_el_arranque_falla_si_el_idioma_es_invalido(
    entorno_prod: pytest.MonkeyPatch, valor: str
) -> None:
    entorno_prod.setenv("APP_IDIOMA", valor)
    with pytest.raises(ImproperlyConfigured, match="APP_IDIOMA"):
        _cargar_con_base("prod")


def test_la_etiqueta_lang_de_las_paginas_sigue_al_idioma_configurado(settings: Any) -> None:
    settings.LANGUAGE_CODE = "pt-br"
    contexto = contexto_de_la_aplicacion(RequestFactory().get("/"))
    assert contexto["idioma_html"] == "pt-br"


@pytest.mark.parametrize("valor", ["posixrules", "Etc/GMT+5", "EST5EDT", "US/Eastern"])
def test_el_arranque_falla_con_un_mensaje_claro_si_la_zona_es_invalida(
    entorno_prod: pytest.MonkeyPatch, valor: str
) -> None:
    entorno_prod.setenv("APP_ZONA_HORARIA", valor)
    with pytest.raises(ImproperlyConfigured, match=r"APP_ZONA_HORARIA.*legada o ambigua"):
        _cargar_con_base("prod")


def test_prod_usa_el_secreto_del_entorno_y_no_el_de_desarrollo(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    prod = _cargar_prod()
    entorno_prod.delenv("SECRET_KEY")
    entorno_prod.setenv("DATABASE_URL", "postgres://u:p@h.invalid/app")
    por_defecto_de_dev = _cargar("dev").SECRET_KEY  # dev si trae un valor por defecto
    assert VARIABLES_PROD["SECRET_KEY"] == prod.SECRET_KEY
    assert por_defecto_de_dev != prod.SECRET_KEY


def test_prod_rechaza_un_secreto_vacio(entorno_prod: pytest.MonkeyPatch) -> None:
    entorno_prod.setenv("SECRET_KEY", "   ")
    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY"):
        _cargar_prod()


# --- SECRET_KEY y ALLOWED_HOSTS estrictos en prod --------------------------------------


@pytest.mark.parametrize("largo", [1, 10, 49])
def test_prod_rechaza_una_secret_key_corta(entorno_prod: pytest.MonkeyPatch, largo: int) -> None:
    entorno_prod.setenv("SECRET_KEY", "k" * largo)
    with pytest.raises(ImproperlyConfigured, match=r"SECRET_KEY.*50"):
        _cargar_prod()


def test_prod_acepta_una_secret_key_de_exactamente_50_caracteres_con_variedad(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    clave = ("abcdefghijklmnopqrstuvwxyz0123456789" * 2)[:50]  # 36 distintos
    entorno_prod.setenv("SECRET_KEY", clave)
    prod = _cargar_prod()
    assert clave == prod.SECRET_KEY


def test_prod_quita_los_espacios_de_la_secret_key(entorno_prod: pytest.MonkeyPatch) -> None:
    entorno_prod.setenv("SECRET_KEY", f"  {SECRET_KEY_DE_PRUEBA}" + chr(10))
    assert _cargar_prod().SECRET_KEY == SECRET_KEY_DE_PRUEBA


@pytest.mark.parametrize(
    ("clave", "motivo"),
    [
        ("k" * 50, "distintos"),
        ("x" + " " * 49, "50"),  # el strip la deja en 1 caracter
        ("ab" * 30, "distintos"),
        ("abcde" * 10, "distintos"),  # 50 caracteres con solo 5 distintos
        ("abcdefghijklmno" * 4, "distintos"),  # 15 distintos: justo bajo el minimo
        ("django-insecure-" + "aZ3$kQ9!mP" * 5, "django-insecure-"),
        ("django-insecure-" + "k" * 50, "django-insecure-"),
    ],
)
def test_prod_rechaza_secret_keys_debiles(
    entorno_prod: pytest.MonkeyPatch, clave: str, motivo: str
) -> None:
    entorno_prod.setenv("SECRET_KEY", clave)
    with pytest.raises(ImproperlyConfigured, match=f"SECRET_KEY.*{motivo}"):
        _cargar_prod()


@pytest.mark.parametrize("relleno", ["", "X" * 10, "-0123456789abcdefghij"])
def test_prod_rechaza_la_secret_key_de_desarrollo_aunque_este_rellenada(
    entorno_prod: pytest.MonkeyPatch, relleno: str
) -> None:
    from configuracion import entorno

    clave = f"{relleno}{entorno.SECRET_KEY_DE_DESARROLLO}{relleno}"
    assert len(entorno.SECRET_KEY_DE_DESARROLLO) < entorno.LARGO_MINIMO_SECRET_KEY
    entorno_prod.setenv("SECRET_KEY", clave.ljust(60, "Z"))
    with pytest.raises(ImproperlyConfigured, match="clave de desarrollo"):
        _cargar_prod()


@pytest.mark.parametrize(
    ("clave", "motivo"),
    [
        ("DJANGO-INSECURE-" + "aZ3$kQ9!mP" * 5, "django-insecure-"),
        ("Django-Insecure-" + "aZ3$kQ9!mP" * 5, "django-insecure-"),
        ("dJaNgO-InSeCuRe-" + "aZ3$kQ9!mP" * 5, "django-insecure-"),
        (
            "X" * 5 + "DEV-SOLO-PARA-DESARROLLO-NO-USAR-EN-PRODUCCION" + "Z" * 12,
            "clave de desarrollo",
        ),
        (
            "Q" * 9 + "Dev-Solo-Para-Desarrollo-No-Usar-En-Produccion" + "kQ9" * 3,
            "clave de desarrollo",
        ),
    ],
)
def test_prod_rechaza_secret_keys_debiles_sin_importar_las_mayusculas(
    entorno_prod: pytest.MonkeyPatch, clave: str, motivo: str
) -> None:
    entorno_prod.setenv("SECRET_KEY", clave)
    with pytest.raises(ImproperlyConfigured, match=f"SECRET_KEY.*{motivo}"):
        _cargar_prod()


def test_dev_y_prod_comparten_la_constante_de_la_clave_de_desarrollo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from configuracion import entorno

    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h.invalid/app")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert _cargar("dev").SECRET_KEY == entorno.SECRET_KEY_DE_DESARROLLO


@pytest.mark.parametrize("hosts", ["*", "app.empresa.example,*", " * ", "*,*", ",", " , ,", ","])
def test_prod_rechaza_allowed_hosts_con_comodin_o_sin_hosts(
    entorno_prod: pytest.MonkeyPatch, hosts: str
) -> None:
    entorno_prod.setenv("ALLOWED_HOSTS", hosts)
    with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
        _cargar_prod()


@pytest.mark.parametrize(
    "hosts",
    [
        "*.empresa.example",
        "app.empresa.example,*.empresa.example",
        ".",
        ".com",
        ".com.ar",  # sufijos publicos de la PSL: cualquier host bajo ellos
        ".com.mx",
        ".co.uk",
        ".gob.pe",
        ".gob.mx",
        ".nom.es",
        ".ne.jp",
        ".github.io",  # sufijos PRIVADOS de la PSL: tambien habilitarian a terceros
        ".herokuapp.com",
        ".ORG.br",
        "app.empresa.example,.com.mx",
        "0.0.0.0",  # noqa: S104
        "a.com,.com",
        "0.0.0.0:8000",
        "[::]:80",
        "::",
        "[::]",
        "[0:0:0:0:0:0:0:0]",
        "0:0:0:0:0:0:0:0",
        "app.empresa.example:8000",
        ".empresa.example:443",
        "10.0.0.5:8000",
        "[2001:db8::1]:443",
        "[2001:db8::1",
        "[2001:db8::1]x",
        "[app.empresa.example]",
        "[10.0.0.5]",
        "2001:db8::1",
    ],
)
def test_prod_rechaza_hosts_comodin_amplios_o_inexistentes_en_django(
    entorno_prod: pytest.MonkeyPatch, hosts: str
) -> None:
    entorno_prod.setenv("ALLOWED_HOSTS", hosts)
    with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
        _cargar_prod()


@pytest.mark.parametrize(
    ("hosts", "esperado"),
    [
        ("app.empresa.example", ["app.empresa.example"]),
        (".empresa.example", [".empresa.example"]),
        (".empresa.com.mx", [".empresa.com.mx"]),  # dominio propio, aunque cuelgue de un .com.mx
        (".comunicaciones.mx", [".comunicaciones.mx"]),  # `comunicaciones` no es un registro
        ("app.empresa.example, .empresa.example", ["app.empresa.example", ".empresa.example"]),
        ("10.0.0.5", ["10.0.0.5"]),
        ("[2001:db8::1]", ["[2001:db8::1]"]),
        (
            "app.empresa.example,10.0.0.5,[2001:db8::1]",
            ["app.empresa.example", "10.0.0.5", "[2001:db8::1]"],
        ),
    ],
)
def test_prod_acepta_hosts_validos(
    entorno_prod: pytest.MonkeyPatch, hosts: str, esperado: list[str]
) -> None:
    entorno_prod.setenv("ALLOWED_HOSTS", hosts)
    prod = _cargar_prod()
    assert esperado == prod.ALLOWED_HOSTS


def test_las_variables_de_ci_para_check_deploy_son_validas() -> None:
    from configuracion import entorno

    ci = (CODIGO.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    clave = re.search(r"^\s+SECRET_KEY: (\S+)$", ci, re.MULTILINE)
    hosts = re.search(r"^\s+ALLOWED_HOSTS: (\S+)$", ci, re.MULTILINE)
    assert clave and hosts
    assert entorno.secret_key_de_produccion(clave.group(1)) == clave.group(1)
    assert entorno.hosts_permitidos_de_produccion(hosts.group(1))


@pytest.mark.lento
def test_check_deploy_con_las_variables_de_prueba_no_da_advertencias() -> None:
    # Es el mismo comando que corre CI: `manage.py check --deploy --fail-level WARNING`.
    resultado = _ejecutar_sin_settings(
        "from django.core.management import execute_from_command_line as e; "
        "e(['manage.py', 'check', '--deploy', '--fail-level', 'WARNING'])",
        DJANGO_SETTINGS_MODULE="configuracion.settings.prod",
        **VARIABLES_PROD,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "no issues" in resultado.stdout


@pytest.mark.lento
def test_check_deploy_falla_con_una_secret_key_debil_sin_que_prod_la_rechace() -> None:
    # Defensa en profundidad: la clave corta ya la rechaza prod.py; aqui se confirma que el chequeo
    # de Django (que CI ejecuta) tambien se rompe si alguien afloja la validacion de prod.
    resultado = _ejecutar_sin_settings(
        "from django.conf import settings; settings.configure(SECRET_KEY='corta', DEBUG=False); "
        "import django; django.setup(); "
        "from django.core.management import call_command; "
        "call_command('check', deploy=True, fail_level='WARNING')",
    )
    assert resultado.returncode != 0
    assert "security.W009" in resultado.stderr


def test_pruebas_usa_celery_eager_y_utc() -> None:
    from django.conf import settings

    assert settings.CELERY_TASK_ALWAYS_EAGER is True
    assert settings.USE_TZ is True
    assert settings.TIME_ZONE == "UTC"


def test_celery_ejecuta_tareas_en_modo_eager() -> None:
    from configuracion.celery import app

    @app.task
    def sumar(a: int, b: int) -> int:
        return a + b

    assert sumar.delay(2, 3).get() == 5


# --- Ningun entorno apunta por defecto a localhost:5432 (alli corre otro PostgreSQL) -----------


def test_dev_exige_database_url_y_explica_como_arrancar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ImproperlyConfigured, match="DATABASE_URL") as error:
        _cargar("dev")
    assert "herramientas.base_local" in str(error.value)


def test_dev_usa_la_database_url_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@base.interna:5544/app_dev")
    config = _cargar("dev").DATABASES["default"]
    assert (config["HOST"], config["PORT"], config["NAME"]) == ("base.interna", "5544", "app_dev")


def test_pruebas_sin_database_url_apunta_a_un_host_inalcanzable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _cargar("pruebas").DATABASES["default"]["HOST"] == "pruebas.invalid"


@pytest.mark.parametrize("nombre", ["dev", "pruebas", "prod"])
def test_ningun_settings_apunta_por_defecto_a_localhost_5432(
    nombre: str, entorno_prod: pytest.MonkeyPatch
) -> None:
    entorno_prod.delenv("DATABASE_URL")
    try:
        config = _cargar(nombre).DATABASES["default"]
    except ImproperlyConfigured:
        return  # exige la variable: no hay valor por defecto
    local_y_puerto_de_otro_sistema = config["HOST"] in HOSTS_LOCALES and config["PORT"] in {
        "",
        "5432",
    }
    assert not local_y_puerto_de_otro_sistema, (
        f"{nombre} apunta por defecto a {config['HOST']}:5432"
    )


@pytest.mark.parametrize("nombre", MODULOS_SETTINGS)
def test_el_codigo_de_settings_no_menciona_localhost_5432(nombre: str) -> None:
    arbol = ast.parse((DIRECTORIO_SETTINGS / f"{nombre}.py").read_text(encoding="utf-8"))
    cadenas = [n.value for n in ast.walk(arbol) if isinstance(n, ast.Constant)]
    for cadena in (c for c in cadenas if isinstance(c, str)):
        assert not re.search(r"(localhost|127\.0\.0\.1|\[::1\]):5432", cadena), cadena


# --- DRF deniega por defecto (D.6.3) -----------------------------------------------------------


def test_drf_exige_autenticacion_por_defecto() -> None:
    from django.conf import settings

    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]


def test_una_vista_drf_sin_permisos_explicitos_rechaza_al_anonimo() -> None:
    from rest_framework.request import Request
    from rest_framework.response import Response
    from rest_framework.test import APIRequestFactory
    from rest_framework.views import APIView

    class VistaSinPermisos(APIView):
        def get(self, request: Request) -> Response:
            return Response({"secreto": 1})

    respuesta = VistaSinPermisos.as_view()(APIRequestFactory().get("/x"))
    assert respuesta.status_code in {401, 403}
    assert "secreto" not in str(respuesta.data)


def test_una_vista_drf_publica_debe_declararlo_con_allowany() -> None:
    from rest_framework.permissions import AllowAny
    from rest_framework.request import Request
    from rest_framework.response import Response
    from rest_framework.test import APIRequestFactory
    from rest_framework.views import APIView

    class VistaPublica(APIView):
        permission_classes = [AllowAny]  # noqa: RUF012

        def get(self, request: Request) -> Response:
            return Response({"ok": True})

    assert VistaPublica.as_view()(APIRequestFactory().get("/x")).status_code == 200


# --- CSP estricta en prod (D.6.3) --------------------------------------------------------------


def _directivas(politica: str) -> dict[str, list[str]]:
    resultado: dict[str, list[str]] = {}
    for parte in politica.split(";"):
        nombre, *valores = parte.split()
        resultado[nombre] = valores
    return resultado


def test_prod_define_una_csp_estricta(entorno_prod: pytest.MonkeyPatch) -> None:
    prod = _cargar_prod()
    directivas = _directivas(prod.CONTENT_SECURITY_POLICY)
    assert directivas == {
        "default-src": ["'self'"],
        "frame-ancestors": ["'none'"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
    }
    assert "'unsafe-inline'" not in prod.CONTENT_SECURITY_POLICY
    assert "'unsafe-eval'" not in prod.CONTENT_SECURITY_POLICY
    assert "configuracion.seguridad.EncabezadoCSPMiddleware" in prod.MIDDLEWARE


def test_el_middleware_csp_va_justo_despues_de_securitymiddleware(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    middleware = _cargar_prod().MIDDLEWARE
    assert middleware[0] == "django.middleware.security.SecurityMiddleware"
    assert middleware[1] == "configuracion.seguridad.EncabezadoCSPMiddleware"
    assert len(middleware) == len(set(middleware))


def test_prod_envia_la_csp_y_los_demas_encabezados(entorno_prod: pytest.MonkeyPatch) -> None:
    prod = _cargar_prod()
    with override_settings(
        MIDDLEWARE=prod.MIDDLEWARE,
        CONTENT_SECURITY_POLICY=prod.CONTENT_SECURITY_POLICY,
        SECURE_SSL_REDIRECT=False,  # la redireccion a https la cubre nginx
        SECURE_HSTS_SECONDS=prod.SECURE_HSTS_SECONDS,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=prod.SECURE_HSTS_INCLUDE_SUBDOMAINS,
        SECURE_HSTS_PRELOAD=prod.SECURE_HSTS_PRELOAD,
    ):
        respuesta = Client().get("/salud", secure=True)
    assert respuesta.status_code == 200
    assert _directivas(respuesta["Content-Security-Policy"])["frame-ancestors"] == ["'none'"]
    assert "includeSubDomains" in respuesta["Strict-Transport-Security"]
    assert respuesta["X-Frame-Options"] == "DENY"
    assert respuesta["X-Content-Type-Options"] == "nosniff"
    assert respuesta["Referrer-Policy"] == "same-origin"


def test_el_middleware_csp_falla_si_la_politica_esta_vacia() -> None:
    from django.http import HttpRequest, HttpResponse

    from configuracion.seguridad import EncabezadoCSPMiddleware

    def vista(request: HttpRequest) -> HttpResponse:
        return HttpResponse()

    for vacia in ("", "   ", None):
        with (
            override_settings(CONTENT_SECURITY_POLICY=vacia),
            pytest.raises(ImproperlyConfigured, match="CONTENT_SECURITY_POLICY"),
        ):
            EncabezadoCSPMiddleware(vista)  # falla al arrancar
    middleware = EncabezadoCSPMiddleware(vista)
    with (
        override_settings(CONTENT_SECURITY_POLICY=""),
        pytest.raises(ImproperlyConfigured, match="CONTENT_SECURITY_POLICY"),
    ):
        middleware(HttpRequest())  # y tambien si se vacia despues de arrancar


def test_el_middleware_csp_usa_la_politica_estricta_si_no_hay_setting() -> None:
    from django.http import HttpRequest, HttpResponse

    from configuracion.seguridad import POLITICA_CSP, EncabezadoCSPMiddleware

    # `pruebas` no define `CONTENT_SECURITY_POLICY`: rige la politica estricta por defecto.
    respuesta = EncabezadoCSPMiddleware(lambda request: HttpResponse())(HttpRequest())
    assert respuesta["Content-Security-Policy"] == POLITICA_CSP


def test_el_middleware_csp_no_pisa_un_encabezado_explicito_de_la_vista() -> None:
    from django.http import HttpRequest, HttpResponse

    from configuracion.seguridad import EncabezadoCSPMiddleware

    def vista(request: HttpRequest) -> HttpResponse:
        respuesta = HttpResponse()
        respuesta["Content-Security-Policy"] = "default-src 'none'"
        return respuesta

    with override_settings(CONTENT_SECURITY_POLICY="default-src 'self'"):
        respuesta = EncabezadoCSPMiddleware(vista)(HttpRequest())
    assert respuesta["Content-Security-Policy"] == "default-src 'none'"


@pytest.mark.parametrize("vacia", ["", "   ", "\t"])
def test_una_csp_vacia_fijada_por_la_vista_se_trata_como_ausente(vacia: str) -> None:
    """`Content-Security-Policy:` en blanco no protege nada; rige la politica del sitio."""
    from django.http import HttpRequest, HttpResponse

    from configuracion.seguridad import EncabezadoCSPMiddleware

    def vista(request: HttpRequest) -> HttpResponse:
        respuesta = HttpResponse()
        respuesta["Content-Security-Policy"] = vacia
        return respuesta

    with override_settings(CONTENT_SECURITY_POLICY="default-src 'self'"):
        respuesta = EncabezadoCSPMiddleware(vista)(HttpRequest())
    assert respuesta["Content-Security-Policy"] == "default-src 'self'"


@pytest.mark.parametrize("nombre", ["dev", "pruebas"])
def test_dev_y_pruebas_no_agregan_la_csp(nombre: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # La CSP estricta es de prod; en dev/pruebas el debug toolbar y similares la romperian.
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h.invalid/app")
    modulo = _cargar(nombre)
    assert not hasattr(modulo, "CONTENT_SECURITY_POLICY")
    assert "configuracion.seguridad.EncabezadoCSPMiddleware" not in modulo.MIDDLEWARE


# --- Puntos de entrada: wsgi/asgi/Celery arrancan con prod, nunca con dev ---------------


def _ejecutar_sin_settings(codigo: str, **entorno: str) -> subprocess.CompletedProcess[str]:
    """Corre Python en un proceso NUEVO sin `DJANGO_SETTINGS_MODULE` (como lo hace gunicorn)."""
    variables = {
        nombre: valor
        for nombre, valor in os.environ.items()
        if nombre != "DJANGO_SETTINGS_MODULE" and nombre not in VARIABLES_PROD
    }
    variables.update(entorno)
    return subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=CODIGO,
        env=variables,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.lento
@pytest.mark.parametrize("punto_de_entrada", ["wsgi", "asgi"])
def test_wsgi_y_asgi_sin_settings_cargan_prod_y_exigen_sus_secretos(
    punto_de_entrada: str,
) -> None:
    resultado = _ejecutar_sin_settings(f"import configuracion.{punto_de_entrada}")
    assert resultado.returncode != 0
    assert "ImproperlyConfigured" in resultado.stderr
    assert "SECRET_KEY" in resultado.stderr  # lo exige prod; dev tiene un valor por defecto


@pytest.mark.lento
@pytest.mark.parametrize("punto_de_entrada", ["wsgi", "asgi"])
def test_wsgi_y_asgi_sin_settings_arrancan_con_prod_si_hay_secretos(punto_de_entrada: str) -> None:
    resultado = _ejecutar_sin_settings(
        f"import os, configuracion.{punto_de_entrada}\nprint(os.environ['DJANGO_SETTINGS_MODULE'])",
        **VARIABLES_PROD,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "configuracion.settings.prod"


def test_dev_sin_redis_corre_celery_en_modo_local_y_cache_en_memoria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Docker y Redis son opcionales en desarrollo: sin REDIS_URL no se apunta a ningun puerto 6379.
    monkeypatch.setenv("DATABASE_URL", "postgres://u:c@localhost:55432/app")
    monkeypatch.delenv("REDIS_URL", raising=False)
    dev = _cargar_con_base("dev")
    assert dev.CELERY_TASK_ALWAYS_EAGER is True
    assert dev.CELERY_BROKER_URL == "memory://"
    assert dev.CACHES["default"]["BACKEND"].endswith("LocMemCache")


def test_dev_con_redis_usa_el_broker_y_la_cache_reales(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://u:c@localhost:55432/app")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    dev = _cargar_con_base("dev")
    assert dev.CELERY_TASK_ALWAYS_EAGER is False
    assert dev.CELERY_BROKER_URL == "redis://redis:6379/0"
    assert dev.CACHES["default"]["BACKEND"].endswith("RedisCache")


@pytest.mark.lento
def test_importar_el_paquete_no_fija_los_settings_por_defecto() -> None:
    # `configuracion/__init__` importa Celery: un setdefault ahi le ganaria a wsgi/asgi.
    resultado = _ejecutar_sin_settings(
        "import os, configuracion\nprint(os.environ.get('DJANGO_SETTINGS_MODULE', 'sin-definir'))"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "sin-definir"


@pytest.mark.lento
def test_el_worker_de_celery_sin_settings_no_cae_en_dev() -> None:
    resultado = _ejecutar_sin_settings(
        "from configuracion.celery import app\nprint(app.conf.broker_url)"
    )
    assert resultado.returncode != 0
    assert "DJANGO_SETTINGS_MODULE" in resultado.stderr  # exige configurarlo de forma explicita
    assert "redis://localhost" not in resultado.stdout  # no tomo el broker de desarrollo


@pytest.mark.lento
def test_el_worker_de_celery_con_prod_exige_sus_secretos() -> None:
    resultado = _ejecutar_sin_settings(
        "from configuracion.celery import app\nprint(app.conf.broker_url)",
        DJANGO_SETTINGS_MODULE="configuracion.settings.prod",
    )
    assert resultado.returncode != 0
    assert "ImproperlyConfigured" in resultado.stderr


# --- Despliegue con Compose: HSTS, confianza en el proxy y rol sin ownership -------------


def test_prod_por_defecto_usa_hsts_de_produccion(entorno_prod: pytest.MonkeyPatch) -> None:
    prod = _cargar_prod()
    assert prod.SECURE_HSTS_SECONDS == 31536000
    assert prod.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert prod.SECURE_HSTS_PRELOAD is True


def test_prod_acepta_un_hsts_corto_solo_en_la_propia_maquina_y_lo_advierte(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("ALLOWED_HOSTS", "localhost")
    entorno_prod.setenv("HSTS_SEGUNDOS", "300")
    entorno_prod.setenv("HSTS_SUBDOMINIOS", "false")
    entorno_prod.setenv("HSTS_PRELOAD", "false")
    with pytest.warns(RuntimeWarning, match="HSTS_SEGUNDOS=300"):
        prod = _cargar_prod()
    assert prod.SECURE_HSTS_SECONDS == 300
    assert prod.SECURE_HSTS_INCLUDE_SUBDOMAINS is False
    assert prod.SECURE_HSTS_PRELOAD is False


def test_prod_rechaza_un_hsts_menor_a_un_ano_en_un_servidor_real(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("HSTS_SEGUNDOS", "1")
    with pytest.raises(ImproperlyConfigured, match=r"Transporte inseguro.*HSTS_SEGUNDOS=1"):
        _cargar_prod()


def test_prod_rechaza_apagar_la_redireccion_a_https_en_un_servidor_real(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("SECURE_SSL_REDIRECT", "false")
    with pytest.raises(ImproperlyConfigured, match=r"Transporte inseguro.*SECURE_SSL_REDIRECT"):
        _cargar_prod()


def test_prod_advierte_si_se_apaga_la_redireccion_en_la_propia_maquina(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("ALLOWED_HOSTS", "localhost")
    entorno_prod.setenv("SECURE_SSL_REDIRECT", "false")
    with pytest.warns(RuntimeWarning, match="SECURE_SSL_REDIRECT"):
        assert _cargar_prod().SECURE_SSL_REDIRECT is False


def test_prod_no_exige_tls_a_los_datos_por_defecto(entorno_prod: pytest.MonkeyPatch) -> None:
    prod = _cargar_prod()
    assert not hasattr(prod, "CELERY_BROKER_USE_SSL")


def test_prod_con_tls_exigido_acepta_base_y_redis_cifrados(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("APP_EXIGIR_TLS_DATOS", "true")
    entorno_prod.setenv("DATABASE_URL", "postgres://app:clave@db:5432/app?sslmode=verify-full")
    entorno_prod.setenv("REDIS_URL", "rediss://:clave@redis:6379/0")
    prod = _cargar_prod()
    assert prod.DATABASES["default"]["OPTIONS"]["sslmode"] == "verify-full"
    assert prod.CELERY_BROKER_USE_SSL == {"ssl_cert_reqs": ssl.CERT_REQUIRED}


@pytest.mark.parametrize(
    ("base", "redis", "esperado"),
    [
        ("postgres://app:clave@db:5432/app", "rediss://redis:6379/0", "sslmode"),
        ("postgres://app:clave@db:5432/app?sslmode=disable", "rediss://redis:6379/0", "sslmode"),
        ("postgres://app:clave@db:5432/app?sslmode=prefer", "rediss://redis:6379/0", "sslmode"),
        ("postgres://app:clave@db:5432/app?sslmode=require", "redis://redis:6379/0", "rediss://"),
    ],
)
def test_prod_con_tls_exigido_rechaza_datos_sin_cifrar(
    entorno_prod: pytest.MonkeyPatch, base: str, redis: str, esperado: str
) -> None:
    entorno_prod.setenv("APP_EXIGIR_TLS_DATOS", "true")
    entorno_prod.setenv("DATABASE_URL", base)
    entorno_prod.setenv("REDIS_URL", redis)
    with pytest.raises(ImproperlyConfigured, match=esperado):
        _cargar_prod()


@pytest.mark.parametrize("valor", ["0", "-1", "mucho", "1.5"])
def test_prod_rechaza_un_hsts_que_lo_desactiva_o_no_es_entero(
    entorno_prod: pytest.MonkeyPatch, valor: str
) -> None:
    entorno_prod.setenv("HSTS_SEGUNDOS", valor)
    with pytest.raises(ImproperlyConfigured, match="HSTS_SEGUNDOS"):
        _cargar_prod()


def test_prod_no_confia_en_x_forwarded_proto_si_no_se_declara(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.delenv("CONFIAR_EN_PROXY_TLS", raising=False)
    assert not hasattr(_cargar_prod(), "SECURE_PROXY_SSL_HEADER")


def test_prod_confia_en_x_forwarded_proto_solo_si_se_declara(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("CONFIAR_EN_PROXY_TLS", "true")
    assert _cargar_prod().SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_sin_confianza_un_cliente_no_puede_falsificar_el_esquema_https() -> None:
    """El cliente manda `X-Forwarded-Proto: https` por HTTP plano: Django NO lo da por seguro."""
    with override_settings(SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=["testserver"]):
        respuesta = Client().get("/salud", HTTP_X_FORWARDED_PROTO="https")
    assert respuesta.status_code == 301
    assert respuesta["Location"].startswith("https://")


def test_con_confianza_en_el_proxy_x_forwarded_proto_https_cuenta_como_seguro() -> None:
    with override_settings(
        SECURE_SSL_REDIRECT=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        ALLOWED_HOSTS=["testserver"],
    ):
        respuesta = Client().get("/salud", HTTP_X_FORWARDED_PROTO="https")
    assert respuesta.status_code == 200


def test_prod_rechaza_valores_de_ejemplo_en_las_urls(entorno_prod: pytest.MonkeyPatch) -> None:
    entorno_prod.setenv("DATABASE_URL", "postgres://app_web:CAMBIAR_clave@postgres:5432/app")
    with pytest.raises(ImproperlyConfigured, match="DATABASE_URL"):
        _cargar_prod()
    entorno_prod.setenv("DATABASE_URL", VARIABLES_PROD["DATABASE_URL"])
    entorno_prod.setenv("REDIS_URL", "redis://:CAMBIAR_clave@redis:6379/0")
    with pytest.raises(ImproperlyConfigured, match="REDIS_URL"):
        _cargar_prod()


def test_prod_rechaza_una_secret_key_de_ejemplo(entorno_prod: pytest.MonkeyPatch) -> None:
    entorno_prod.setenv("SECRET_KEY", "CAMBIAR_" + "aZ3kQ9mPx7" * 6)
    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY"):
        _cargar_prod()


URL_MIGRACIONES = "postgres://app_migraciones:clave-de-migraciones@db:5432/app"


def test_prod_rechaza_las_credenciales_del_rol_de_migraciones(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    """D.6.3: el proceso que atiende peticiones nunca recibe el rol dueno del esquema."""
    entorno_prod.setenv("DATABASE_MIGRACIONES_URL", URL_MIGRACIONES)
    with pytest.raises(ImproperlyConfigured, match="DATABASE_MIGRACIONES_URL"):
        _cargar_prod()


@pytest.mark.parametrize(
    ("variable", "valor"),
    [
        ("DATABASE_ADMIN_URL", "postgres://app_admin:clave-de-admin@db:5432/app"),
        ("APP_MIGRACIONES_PASSWORD", "clave-de-migraciones"),
    ],
)
def test_prod_rechaza_las_credenciales_de_administracion_y_la_clave_de_migraciones(
    entorno_prod: pytest.MonkeyPatch, variable: str, valor: str
) -> None:
    """la aplicacion tampoco recibe el rol administrador ni la clave del dueno"""
    entorno_prod.setenv(variable, valor)
    with pytest.raises(ImproperlyConfigured, match=variable):
        _cargar_prod()


@pytest.mark.parametrize("variable", ["DATABASE_ADMIN_URL", "APP_MIGRACIONES_PASSWORD"])
def test_prod_ignora_esas_variables_si_estan_vacias(
    entorno_prod: pytest.MonkeyPatch, variable: str
) -> None:
    entorno_prod.setenv(variable, "  ")
    assert _cargar_prod().DEBUG is False


def test_migraciones_usa_el_rol_de_migraciones_y_no_el_de_la_aplicacion(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("DATABASE_MIGRACIONES_URL", URL_MIGRACIONES)
    entorno_prod.delenv("DATABASE_URL")  # el paso `migrar` no necesita el rol de ejecucion
    entorno_prod.delenv("REDIS_URL")
    migraciones = _cargar("migraciones")
    assert migraciones.DATABASES["default"]["USER"] == "app_migraciones"
    assert migraciones.DEBUG is False
    assert migraciones.ALLOWED_HOSTS == []
    assert "rest_framework" in migraciones.INSTALLED_APPS  # mismas apps y migraciones que prod


def test_migraciones_exige_su_url_y_una_secret_key_valida(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.delenv("DATABASE_MIGRACIONES_URL", raising=False)
    with pytest.raises(ImproperlyConfigured, match="DATABASE_MIGRACIONES_URL"):
        _cargar("migraciones")
    entorno_prod.setenv("DATABASE_MIGRACIONES_URL", URL_MIGRACIONES)
    entorno_prod.setenv("SECRET_KEY", "corta")
    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY"):
        _cargar("migraciones")


def test_migraciones_no_cae_en_la_url_de_la_aplicacion(entorno_prod: pytest.MonkeyPatch) -> None:
    """Sin `DATABASE_MIGRACIONES_URL` no se usa `DATABASE_URL` (seria el rol equivocado)."""
    entorno_prod.delenv("DATABASE_MIGRACIONES_URL", raising=False)
    assert "DATABASE_URL" in os.environ
    with pytest.raises(ImproperlyConfigured, match="DATABASE_MIGRACIONES_URL"):
        _cargar("migraciones")


# --- Autenticacion (DISENO D.6.3) ---------------------------------------------------


def test_prod_autentica_con_argon2_y_el_usuario_de_identidad(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    prod = _cargar_prod()
    assert prod.AUTH_USER_MODEL == "identidad.Usuario"
    assert prod.PASSWORD_HASHERS == ["django.contrib.auth.hashers.Argon2PasswordHasher"]


def test_prod_cierra_la_sesion_a_las_3_horas_de_inactividad_no_absolutas(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    prod = _cargar_prod()
    assert prod.SESSION_COOKIE_AGE == 3 * 60 * 60
    assert prod.SESSION_SAVE_EVERY_REQUEST is True  # cada peticion renueva el vencimiento
    assert prod.SESSION_COOKIE_HTTPONLY is True
    assert prod.SESSION_COOKIE_SECURE is True


def test_prod_guarda_las_sesiones_en_redis(entorno_prod: pytest.MonkeyPatch) -> None:
    prod = _cargar_prod()
    assert prod.SESSION_ENGINE == "django.contrib.sessions.backends.cache"
    assert prod.CACHES["default"]["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert prod.CACHES["default"]["LOCATION"] == VARIABLES_PROD["REDIS_URL"]


def test_prod_solo_confia_en_la_ip_del_proxy_si_el_despliegue_lo_declara(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.delenv("CONFIAR_EN_PROXY_TLS", raising=False)
    assert _cargar_prod().APP_IP_DESDE_PROXY is False
    entorno_prod.setenv("CONFIAR_EN_PROXY_TLS", "true")
    assert _cargar_prod().APP_IP_DESDE_PROXY is True


def test_el_middleware_de_identidad_va_despues_de_la_autenticacion(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    middleware = _cargar_prod().MIDDLEWARE
    assert middleware.index("identidad.adaptadores.entrada.middleware.ActorMiddleware") == (
        middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1
    )


# --- Ronda 2 de: llave de la huella, cookie __Host-, tope de sesion, Celery -------------


def test_prod_exige_la_llave_de_la_huella(entorno_prod: pytest.MonkeyPatch) -> None:
    entorno_prod.delenv("APP_LLAVE_HUELLA")
    with pytest.raises(ImproperlyConfigured, match="APP_LLAVE_HUELLA"):
        _cargar_prod()


@pytest.mark.parametrize(
    "valor",
    [
        "corta",
        "k" * 50,
        "CAMBIAR_llave_de_huella_de_64_caracteres_hexadecimales" + "a" * 20,
        "x" * 10 + "dev-llave-de-huella-solo-para-desarrollo" + "y" * 10,
    ],
)
def test_prod_rechaza_una_llave_de_huella_debil_o_de_ejemplo(
    entorno_prod: pytest.MonkeyPatch, valor: str
) -> None:
    entorno_prod.setenv("APP_LLAVE_HUELLA", valor)
    with pytest.raises(ImproperlyConfigured, match="APP_LLAVE_HUELLA"):
        _cargar_prod()


def test_prod_rechaza_que_la_llave_de_la_huella_sea_la_secret_key(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    entorno_prod.setenv("APP_LLAVE_HUELLA", VARIABLES_PROD["SECRET_KEY"])
    with pytest.raises(ImproperlyConfigured, match="distinta de SECRET_KEY"):
        _cargar_prod()


def test_prod_usa_la_llave_de_la_huella_del_entorno(entorno_prod: pytest.MonkeyPatch) -> None:
    assert VARIABLES_PROD["APP_LLAVE_HUELLA"] == _cargar_prod().APP_LLAVE_HUELLA


def test_dev_y_pruebas_tienen_una_llave_local_por_defecto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_LLAVE_HUELLA", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/b")
    assert _cargar_con_base("pruebas").APP_LLAVE_HUELLA == LLAVE_HUELLA_DE_DESARROLLO
    assert _cargar_con_base("dev").APP_LLAVE_HUELLA == LLAVE_HUELLA_DE_DESARROLLO


def test_la_csp_no_se_relajo_para_el_qr_del_segundo_factor() -> None:
    """dibuja el QR en el servidor (un <svg> sin estilos en linea): la CSP no se toca."""
    from configuracion.seguridad import POLITICA_CSP

    assert POLITICA_CSP == (
        "default-src 'self'; frame-ancestors 'none'; object-src 'none'; "
        "base-uri 'self'; form-action 'self'"
    )
    for relajado in ("unsafe-inline", "unsafe-eval", "data:", "img-src", "script-src", "style-src"):
        assert relajado not in POLITICA_CSP


# --- llave que cifra el secreto del segundo factor ---------------------------------------


def test_prod_exige_la_llave_del_segundo_factor(entorno_prod: pytest.MonkeyPatch) -> None:
    entorno_prod.delenv("APP_LLAVE_SEGUNDO_FACTOR")
    with pytest.raises(ImproperlyConfigured, match="APP_LLAVE_SEGUNDO_FACTOR"):
        _cargar_prod()


@pytest.mark.parametrize(
    "valor",
    [
        "corta",
        "k" * 50,
        "abcde" * 10,  # largo suficiente, entropia insuficiente
        "abcdefghijklmno" * 4,  # 15 distintos
        "CAMBIAR_llave_del_segundo_factor_de_64_caracteres_hexadecimales" + "a" * 20,
        "x" * 10 + LLAVE_SEGUNDO_FACTOR_DE_DESARROLLO + "y" * 10,
        "x" * 10 + LLAVE_HUELLA_DE_DESARROLLO + "y" * 10,
    ],
)
def test_prod_rechaza_una_llave_del_segundo_factor_debil_o_de_ejemplo(
    entorno_prod: pytest.MonkeyPatch, valor: str
) -> None:
    entorno_prod.setenv("APP_LLAVE_SEGUNDO_FACTOR", valor)
    with pytest.raises(ImproperlyConfigured, match="APP_LLAVE_SEGUNDO_FACTOR"):
        _cargar_prod()


@pytest.mark.parametrize("otra", ["SECRET_KEY", "APP_LLAVE_HUELLA"])
def test_prod_rechaza_que_la_llave_del_segundo_factor_repita_otra_llave(
    entorno_prod: pytest.MonkeyPatch, otra: str
) -> None:
    entorno_prod.setenv("APP_LLAVE_SEGUNDO_FACTOR", VARIABLES_PROD[otra])
    with pytest.raises(ImproperlyConfigured, match="distinta de SECRET_KEY y de APP_LLAVE_HUELLA"):
        _cargar_prod()


def test_prod_usa_la_llave_del_segundo_factor_del_entorno(
    entorno_prod: pytest.MonkeyPatch,
) -> None:
    assert VARIABLES_PROD["APP_LLAVE_SEGUNDO_FACTOR"] == _cargar_prod().APP_LLAVE_SEGUNDO_FACTOR


def test_el_dev_de_las_tres_llaves_es_distinto_entre_si() -> None:
    from configuracion.entorno import SECRET_KEY_DE_DESARROLLO

    llaves = {
        SECRET_KEY_DE_DESARROLLO,
        LLAVE_HUELLA_DE_DESARROLLO,
        LLAVE_SEGUNDO_FACTOR_DE_DESARROLLO,
    }
    assert len(llaves) == 3


def test_dev_y_pruebas_tienen_una_llave_local_del_segundo_factor_por_defecto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_LLAVE_SEGUNDO_FACTOR", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/b")
    assert (
        _cargar_con_base("pruebas").APP_LLAVE_SEGUNDO_FACTOR == LLAVE_SEGUNDO_FACTOR_DE_DESARROLLO
    )
    assert _cargar_con_base("dev").APP_LLAVE_SEGUNDO_FACTOR == LLAVE_SEGUNDO_FACTOR_DE_DESARROLLO


def test_prod_usa_la_cookie_de_sesion_con_prefijo_host(entorno_prod: pytest.MonkeyPatch) -> None:
    prod = _cargar_prod()
    assert prod.SESSION_COOKIE_NAME == "__Host-sessionid"
    # Requisitos del prefijo `__Host-`: Secure, Path=/ y sin Domain.
    assert prod.SESSION_COOKIE_SECURE is True
    assert getattr(prod, "SESSION_COOKIE_PATH", "/") == "/"
    assert getattr(prod, "SESSION_COOKIE_DOMAIN", None) is None


def test_el_tope_de_sesion_es_de_12_horas_por_defecto_y_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import timedelta

    monkeypatch.delenv("APP_SESION_DURACION_MAXIMA_HORAS", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/b")
    assert timedelta(hours=12) == _cargar_con_base("pruebas").APP_SESION_DURACION_MAXIMA
    monkeypatch.setenv("APP_SESION_DURACION_MAXIMA_HORAS", "8")
    assert timedelta(hours=8) == _cargar_con_base("pruebas").APP_SESION_DURACION_MAXIMA
    monkeypatch.setenv("APP_SESION_DURACION_MAXIMA_HORAS", "0")
    with pytest.raises(ImproperlyConfigured):
        _cargar_con_base("pruebas")


def test_el_nombre_de_la_app_de_celery_sale_de_la_configuracion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codigo = "import os; from configuracion.celery import app; print(app.main)"
    sin = _ejecutar_sin_settings(codigo)
    assert sin.stdout.strip() == "app"
    con = _ejecutar_sin_settings(codigo, APP_NOMBRE_CELERY="mi_empresa")
    assert con.stdout.strip() == "mi_empresa"


# Nombres propios que NO deben aparecer en el codigo (en minusculas): el de tu empresa, sus marcas,
# sus dominios. Lo propio de una empresa va en la configuracion (`.env`, catalogos), no en el codigo
# ni en los docstrings: asi el sistema se puede instalar para otra empresa sin tocarlo.
NOMBRES_PROPIOS_PROHIBIDOS: tuple[str, ...] = ()


def test_el_codigo_no_lleva_nombres_propios_de_una_empresa() -> None:
    ofensores = [
        str(ruta.relative_to(CODIGO))
        for ruta in CODIGO.rglob("*.py")
        if "pruebas" not in ruta.parts
        and ".venv" not in ruta.parts
        and any(
            nombre in ruta.read_text(encoding="utf-8").casefold()
            for nombre in NOMBRES_PROPIOS_PROHIBIDOS
        )
    ]
    assert ofensores == []
