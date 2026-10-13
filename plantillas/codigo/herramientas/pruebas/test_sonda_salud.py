"""La sonda del HEALTHCHECK habla con `/salud` como lo haria nginx."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from herramientas import sonda_salud


@pytest.mark.parametrize(
    ("hosts", "esperado"),
    [
        ("app.empresa.example", "app.empresa.example"),
        (".empresa.example", "empresa.example"),  # un comodin `.dominio` empareja con `dominio`
        (" localhost , app.empresa.example", "localhost"),
        ("", "localhost"),
    ],
)
def test_el_host_de_la_sonda_es_el_primero_de_allowed_hosts(hosts: str, esperado: str) -> None:
    assert sonda_salud.host_de_la_sonda({"ALLOWED_HOSTS": hosts}) == esperado


def test_sin_allowed_hosts_la_sonda_usa_localhost() -> None:
    assert sonda_salud.host_de_la_sonda({}) == "localhost"


class _Servidor:
    def __init__(self, estado: int) -> None:
        self.estado = estado
        self.encabezados: dict[str, str] = {}
        self.ruta = ""
        propio = self

        class Manejador(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                propio.ruta = self.path
                propio.encabezados = {k.lower(): v for k, v in self.headers.items()}
                self.send_response(propio.estado)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args: object) -> None:
                pass

        self.http = HTTPServer(("127.0.0.1", 0), Manejador)
        self.puerto = self.http.server_address[1]


@pytest.fixture
def servidor_200() -> Iterator[_Servidor]:
    servidor = _Servidor(200)
    hilo = threading.Thread(target=servidor.http.serve_forever, daemon=True)
    hilo.start()
    yield servidor
    servidor.http.shutdown()
    servidor.http.server_close()


def test_la_sonda_consulta_salud_con_host_y_esquema_de_nginx(servidor_200: _Servidor) -> None:
    estado = sonda_salud.consultar({"ALLOWED_HOSTS": ".empresa.example"}, servidor_200.puerto)
    assert estado == 200
    assert servidor_200.ruta == "/salud"
    assert servidor_200.encabezados["host"] == "empresa.example"
    assert servidor_200.encabezados["x-forwarded-proto"] == "https"  # evita la redireccion a HTTPS


def test_la_sonda_devuelve_el_estado_si_no_es_200() -> None:
    servidor = _Servidor(503)
    hilo = threading.Thread(target=servidor.http.serve_forever, daemon=True)
    hilo.start()
    try:
        assert sonda_salud.consultar({}, servidor.puerto) == 503
    finally:
        servidor.http.shutdown()
        servidor.http.server_close()


def test_la_sonda_devuelve_cero_si_nadie_escucha() -> None:
    libre = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    puerto = libre.server_address[1]
    libre.server_close()  # el puerto queda sin servidor
    assert sonda_salud.consultar({}, puerto) == 0


def test_main_sale_con_0_si_salud_responde_200_y_con_1_si_no(
    servidor_200: _Servidor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUERTO_WEB", str(servidor_200.puerto))
    assert sonda_salud.main() == 0
    servidor_200.estado = 500
    assert sonda_salud.main() == 1
