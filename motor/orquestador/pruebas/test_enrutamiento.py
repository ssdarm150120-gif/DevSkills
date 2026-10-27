"""Enrutamiento de modelo por instrucción (sin red)."""
import http.client
import json
import threading
import time

import pytest

from nucleo import enrutamiento as enr
from nucleo import validacion as v
from nucleo.api import CABECERA_TOKEN, Servicio, crear_servidor
from nucleo.ejecutor import Ejecutor, _correr_async  # noqa: F401 - se verifica que exista
from nucleo.registro import Registro, cargar
from nucleo.sesiones import Activas, Catalogo, Propias


class EngramFalso:
    def alias(self, pid):
        return [pid]

    def disponible(self):
        return True

    def buscar(self, *a, **k):
        return []


BUENA = "La función calcular() está en app/ventas.py y suma el sell in del mes contra el budget."


def activar(entorno, activo=True, pid="alfa"):
    reg = entorno["ajustes"].registro
    d = json.loads(reg.read_text(encoding="utf-8"))
    for p in d["proyectos"]:
        if p["id"] == pid:
            p["enrutamiento"] = {"activo": activo, "evaluacion": {"x": 1}, "actualizado": "2026-10-27T10:00:00"}
    reg.write_text(json.dumps(d), encoding="utf-8")


def armar(entorno, respuestas):
    """respuestas: lista de dicts que devuelve cada llamada al modelo, en orden."""
    a = entorno["ajustes"]
    llamadas = []
    cola = list(respuestas)

    def correr(t):
        llamadas.append({"modelo": t.get("modelo"), "esfuerzo": t.get("esfuerzo"), "resume": t["resume"]})
        r = dict(cola.pop(0))
        modelo = t.get("modelo") or "por-omision"
        r.setdefault("uso", {"por_modelo": {f"claude-{modelo}-x": {"costUSD": r.get("costo_usd") or 0}}})
        r.setdefault("session_id", f"sid-{len(llamadas)}")
        return r

    cat = Catalogo(a.claude_home, Propias(a.sesiones_propias), Activas(lambda: [], ttl=0), 120, (),
                   listar=lambda d: [])
    return Ejecutor(a, Registro(a.registro), cat, EngramFalso(), correr=correr), llamadas


def correr_una(e, modo="lectura", **extra):
    r = e.recibir({"proyecto": "alfa", "texto": "¿cómo se calcula?", "modo": modo, **extra})
    return e.ejecutar(e.almacen.obtener(r["id"]))


OK = {"estado": "completada", "respuesta": BUENA, "costo_usd": 0.05}


def test_registro_lee_enrutamiento_sin_escribirlo(entorno):
    activar(entorno)
    antes = entorno["ajustes"].registro.read_text(encoding="utf-8")
    ps = cargar(entorno["ajustes"].registro)
    assert ps["alfa"].enrutamiento_activo and not ps["beta"].enrutamiento_activo
    assert entorno["ajustes"].registro.read_text(encoding="utf-8") == antes


@pytest.mark.parametrize("valor", [None, "si", 1, {"activo": "true"}, {"activo": 1}])
def test_enrutamiento_mal_formado_no_activa(entorno, valor):
    d = json.loads(entorno["ajustes"].registro.read_text(encoding="utf-8"))
    d["proyectos"][0]["enrutamiento"] = valor
    entorno["ajustes"].registro.write_text(json.dumps(d), encoding="utf-8")
    assert not cargar(entorno["ajustes"].registro)["alfa"].enrutamiento_activo


def test_inactivo_no_fuerza_modelo(entorno):
    e, ll = armar(entorno, [OK])
    f = correr_una(e)
    assert ll == [{"modelo": None, "esfuerzo": None, "resume": None}]
    assert f["modelo_decision"]["origen"] == "config" and not f["escalado"]
    assert f["modelo_real"] == "claude-por-omision-x"


def test_activo_lectura_sonnet_medio_y_cambios_opus(entorno):
    activar(entorno)
    e, ll = armar(entorno, [OK, OK])
    f = correr_una(e)
    assert ll[0]["modelo"] == "sonnet" and ll[0]["esfuerzo"] == "medium"
    assert f["modelo_usado"] == "sonnet" and f["escalado"] is False and f["costo_usd"] == 0.05
    r = e.recibir({"proyecto": "alfa", "texto": "x", "modo": "cambios"})
    e.confirmar(r["id"])
    f2 = e.ejecutar(e.almacen.obtener(r["id"]))
    assert ll[1]["modelo"] == "opus" and ll[1]["esfuerzo"] is None and f2["modelo_usado"] == "opus"


@pytest.mark.parametrize("primera,motivo", [
    ({"estado": "error", "respuesta": None, "costo_usd": 0.01, "subtipo": "error_max_turns"}, "estado 'error'"),
    ({"estado": "tiempo_agotado", "costo_usd": None}, "tiempo_agotado"),
    ({"estado": "completada", "respuesta": "", "costo_usd": 0.01}, "vacía"),
    ({"estado": "completada", "respuesta": "ok", "costo_usd": 0.01}, "caracteres"),
    ({"estado": "completada", "respuesta": "No pude leer los archivos del proyecto con las herramientas disponibles.",
      "costo_usd": 0.01}, "no pudo"),
    ({"estado": "completada", "respuesta": "I was unable to find the relevant code in this folder.",
      "costo_usd": 0.01}, "no pudo"),
])
def test_lectura_enrutada_que_falla_escala_una_vez_a_opus(entorno, primera, motivo):
    activar(entorno)
    e, ll = armar(entorno, [primera, OK])
    f = correr_una(e)
    assert [x["modelo"] for x in ll] == ["sonnet", "opus"] and ll[1]["esfuerzo"] is None
    assert f["escalado"] is True and motivo in f["motivo_escalamiento"] and f["modelo_usado"] == "opus"
    assert f["estado"] == "completada" and len(f["intentos"]) == 2
    assert f["costo_usd"] == pytest.approx((primera.get("costo_usd") or 0) + 0.05)
    linea = json.loads(entorno["ajustes"].fallos_enrutamiento.read_text(encoding="utf-8").splitlines()[-1])
    assert linea["id"] == f["id"] and linea["modelo"] == "sonnet" and linea["escalado_a"] == "opus"
    assert "texto" not in linea and linea["estado_final"] == "completada" and linea["fallo_tras_escalar"] is None
    assert "sid-1" in Propias(entorno["ajustes"].sesiones_propias).todas()


def test_solo_un_escalamiento_aunque_opus_tambien_falle(entorno):
    activar(entorno)
    malo = {"estado": "completada", "respuesta": "", "costo_usd": 0.01}
    e, ll = armar(entorno, [malo, malo])
    f = correr_una(e)
    assert len(ll) == 2 and f["escalado"] and f["intentos"][-1]["fallo"] == "respuesta vacía"
    assert json.loads(entorno["ajustes"].fallos_enrutamiento.read_text(encoding="utf-8"))["fallo_tras_escalar"]


def test_respuesta_larga_con_no_pude_no_escala(entorno):
    activar(entorno)
    larga = {"estado": "completada", "costo_usd": 0.02,
             "respuesta": BUENA + " " + "Detalle del cálculo por cliente y producto. " * 20 + "No pude abrir el .env (bloqueado)."}
    e, ll = armar(entorno, [larga])
    f = correr_una(e)
    assert len(ll) == 1 and not f["escalado"]


def test_cambios_y_parametro_no_escalan(entorno):
    activar(entorno)
    malo = {"estado": "error", "costo_usd": 0.01}
    e, ll = armar(entorno, [malo, malo])
    r = e.recibir({"proyecto": "alfa", "texto": "x", "modo": "cambios"})
    e.confirmar(r["id"])
    assert not e.ejecutar(e.almacen.obtener(r["id"]))["escalado"]
    f = correr_una(e, modelo="sonnet")
    assert len(ll) == 2 and not f["escalado"] and f["modelo_decision"]["origen"] == "parametro"


def test_parametro_modelo_tiene_precedencia(entorno):
    activar(entorno)
    e, ll = armar(entorno, [OK, OK])
    correr_una(e, modelo="haiku")
    assert ll[0] == {"modelo": "haiku", "esfuerzo": None, "resume": None}
    activar(entorno, False)
    correr_una(e, modelo="opus")
    assert ll[1]["modelo"] == "opus"


@pytest.mark.parametrize("modelo", ["claude-opus-5-5", "gpt", "", "OPUS", 3, ["opus"]])
def test_validacion_modelo(modelo):
    cuerpo = {"proyecto": "alfa", "texto": "x", "modo": "lectura", "modelo": modelo}
    with pytest.raises(v.ErrorValidacion):
        v.instruccion(cuerpo, {"alfa"}, 100)


def test_validacion_modelo_valido():
    assert v.instruccion({"proyecto": "alfa", "texto": "x", "modo": "lectura", "modelo": "sonnet"},
                         {"alfa"}, 100)["modelo"] == "sonnet"
    assert "modelo" not in v.instruccion({"proyecto": "alfa", "texto": "x", "modo": "lectura"}, {"alfa"}, 100)


def test_sdk_recibe_model_y_effort(entorno, monkeypatch):
    """El trabajo con modelo/esfuerzo se traduce a ClaudeAgentOptions(model=..., effort=...)."""
    import asyncio

    claude_agent_sdk = pytest.importorskip("claude_agent_sdk")  # opcional: solo con `devskills orquestador instalar`

    vistos = {}

    def query_falso(prompt, options):
        vistos["model"], vistos["effort"] = options.model, options.effort

        async def gen():
            if False:
                yield None
        return gen()

    monkeypatch.setattr(claude_agent_sdk, "query", query_falso)
    t = {"modo": "lectura", "carpeta": entorno["alfa"], "resume": None, "prompt": "x", "ajustes": entorno["ajustes"],
         "modelo": "sonnet", "esfuerzo": "medium"}
    asyncio.run(_correr_async(t))
    assert vistos == {"model": "sonnet", "effort": "medium"}


def test_resumen_costos_y_tasa(entorno):
    activar(entorno)
    malo = {"estado": "completada", "respuesta": "", "costo_usd": 0.01}
    e, ll = armar(entorno, [OK, malo, OK, OK])
    correr_una(e)
    correr_una(e)
    correr_una(e, modelo="opus")
    s = enr.resumen(e.almacen.listar(1000), Registro(entorno["ajustes"].registro).proyectos(), e.fallos)
    assert s["proyectos_activos"] == ["alfa"] and s["lecturas_enrutadas"] == 2 and s["escaladas"] == 1
    assert s["tasa_escalamiento"] == 0.5 and s["escaladas_resueltas"] == 1
    assert s["por_modelo"]["claude-sonnet-x"]["intentos"] == 2 and s["por_modelo"]["claude-opus-x"]["intentos"] == 2
    assert s["costo_total_usd"] == pytest.approx(0.05 + 0.01 + 0.05 + 0.05)
    assert s["por_origen"] == {"enrutamiento": 2, "parametro": 1} and len(s["ultimos_fallos"]) == 1


# ------------------------------------------------------------------ API

TOKEN = "t" * 43


@pytest.fixture
def servidor(entorno):
    a = entorno["ajustes"]
    activar(entorno)
    e, ll = armar(entorno, [OK] * 5)
    s = Servicio(a, Registro(a.registro), None, EngramFalso(), e, TOKEN, 0)
    srv = crear_servidor(s)
    s.puerto = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield s, ll
    srv.shutdown()
    srv.server_close()


def pedir(s, metodo, ruta, cuerpo=None):
    c = http.client.HTTPConnection("127.0.0.1", s.puerto, timeout=5)
    c.request(metodo, ruta, body=json.dumps(cuerpo).encode() if cuerpo is not None else None,
              headers={"Host": f"127.0.0.1:{s.puerto}", CABECERA_TOKEN: TOKEN, "Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_api_modelo_y_enrutamiento(servidor):
    s, ll = servidor
    assert pedir(s, "POST", "/api/instruccion", {"proyecto": "alfa", "texto": "x", "modo": "lectura",
                                                 "modelo": "gpt-5"})[0] == 400
    c, r = pedir(s, "POST", "/api/instruccion", {"proyecto": "alfa", "texto": "x", "modo": "lectura", "modelo": "haiku"})
    assert c == 202 and r["modelo"] == "haiku"
    s.ejecutor.ejecutar(s.ejecutor.almacen.obtener(r["id"]))
    c, d = pedir(s, "GET", f"/api/instruccion/{r['id']}")
    assert d["modelo_usado"] == "haiku" and d["escalado"] is False and d["motivo_escalamiento"] is None
    c, e = pedir(s, "GET", "/api/enrutamiento")
    assert c == 200 and e["proyectos_activos"] == ["alfa"] and "por_modelo" in e and "tasa_escalamiento" in e
    assert pedir(s, "GET", "/api/enrutamiento?x=1")[0] == 400
    lista = pedir(s, "GET", "/api/instrucciones")[1]["instrucciones"]
    assert {"modelo_usado", "escalado"} <= set(lista[0])
