import http.client
import json
import threading

import pytest

from nucleo.api import CABECERA_TOKEN, Servicio, crear_servidor
from nucleo.ejecutor import Ejecutor
from nucleo.registro import Registro
from nucleo.sesiones import Activas, Catalogo, Propias

TOKEN = "t" * 43


class EngramFalso:
    def alias(self, pid):
        return [pid]

    def disponible(self):
        return True

    def buscar(self, alias, q="", **k):
        return [{"titulo": f"{alias[0]}:{q}"}]


class InventarioFalso:
    def todos(self):
        return {"proyectos": []}

    def proyecto(self, pid):
        return {"id": pid}


@pytest.fixture
def servidor(entorno):
    a = entorno["ajustes"]
    llamadas = []
    cat = Catalogo(a.claude_home, Propias(a.sesiones_propias), Activas(lambda: [], ttl=0), 120, (),
                   listar=lambda d: [])
    ej = Ejecutor(a, Registro(a.registro), cat, EngramFalso(),
                  correr=lambda t: llamadas.append(t) or {"estado": "completada", "session_id": "s"})
    s = Servicio(a, Registro(a.registro), InventarioFalso(), EngramFalso(), ej, TOKEN, 0)
    srv = crear_servidor(s)
    s.puerto = srv.server_address[1]
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield s, llamadas
    srv.shutdown()
    srv.server_close()


def pedir(s, metodo, ruta, cuerpo=None, token=TOKEN, host=None, extra=None):
    c = http.client.HTTPConnection("127.0.0.1", s.puerto, timeout=5)
    h = {"Host": host or f"127.0.0.1:{s.puerto}", "Content-Type": "application/json"}
    if token is not None:
        h[CABECERA_TOKEN] = token
    h.update(extra or {})
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    c.request(metodo, ruta, body=datos, headers=h)
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_ping_sin_token(servidor):
    assert pedir(servidor[0], "GET", "/api/ping", token=None) == (200, {"orquestador": True})


def test_sin_token_o_token_malo(servidor):
    assert pedir(servidor[0], "GET", "/api/inventario", token=None)[0] == 401
    assert pedir(servidor[0], "GET", "/api/inventario", token="x")[0] == 401


def test_host_y_origen_ajenos(servidor):
    assert pedir(servidor[0], "GET", "/api/inventario", host="evil.example:80")[0] == 403
    assert pedir(servidor[0], "GET", "/api/inventario", extra={"Origin": "https://evil.example"})[0] == 403


def test_flujo_cambios_confirmacion(servidor):
    s, llamadas = servidor
    codigo, r = pedir(s, "POST", "/api/instruccion", {"proyecto": "alfa", "texto": "x", "modo": "cambios"})
    assert codigo == 200 and r["estado"] == "pendiente_confirmacion" and llamadas == []
    assert pedir(s, "POST", f"/api/instruccion/{r['id']}/confirmar", {})[0] == 400
    assert pedir(s, "POST", f"/api/instruccion/{r['id']}/confirmar", {"confirmacion": "si"})[0] == 400
    assert pedir(s, "GET", f"/api/instruccion/{r['id']}")[1]["estado"] == "pendiente_confirmacion"
    codigo, r2 = pedir(s, "POST", f"/api/instruccion/{r['id']}/confirmar", {"confirmacion": r["id"]})
    assert codigo == 202 and r2["estado"] == "en_cola"


def test_validaciones_http(servidor):
    s, _ = servidor
    assert pedir(s, "POST", "/api/instruccion", {"proyecto": "zeta", "texto": "x", "modo": "lectura"})[0] == 400
    assert pedir(s, "POST", "/api/instruccion",
                 {"proyecto": "alfa", "texto": "x", "modo": "lectura", "cwd": "C:\\"})[0] == 400
    assert pedir(s, "GET", "/api/instruccion/..%2F..%2Fx")[0] == 400
    assert pedir(s, "GET", "/api/instruccion/20261026-120000-abcdef")[0] == 404
    assert pedir(s, "GET", "/api/contexto/alfa?q=celery&ruta=C:/")[0] == 400
    assert pedir(s, "GET", "/api/contexto/alfa?q=celery")[1]["resultados"] == [{"titulo": "alfa:celery"}]
    assert pedir(s, "GET", "/api/inventario/zeta")[0] == 400
    assert pedir(s, "DELETE", "/api/inventario")[0] == 405


def test_cuerpo_no_json_o_grande(servidor):
    s, _ = servidor
    c = http.client.HTTPConnection("127.0.0.1", s.puerto, timeout=5)
    c.request("POST", "/api/instruccion", body=b"x" * 20000,
              headers={"Host": f"127.0.0.1:{s.puerto}", CABECERA_TOKEN: TOKEN, "Content-Type": "application/json"})
    assert c.getresponse().status == 400
