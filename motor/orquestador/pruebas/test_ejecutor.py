import json
import threading
import time

import pytest

from nucleo.ejecutor import Ejecutor, EstadoInvalido, armar_prompt
from nucleo.registro import Registro
from nucleo.sesiones import Activas, Catalogo, Propias, Sesion


class EngramFalso:
    def alias(self, pid):
        return [pid]

    def buscar(self, *a, **k):
        return [{"tipo": "decision", "titulo": "Usar Django", "actualizada": "2026-10-01"}]


class Info:
    def __init__(self, sid, ms):
        self.session_id, self.last_modified, self.file_size = sid, ms, 10
        self.custom_title, self.summary, self.cwd = "t", None, ""


def armar(entorno, sesiones=(), activas=None, politica="nueva", llamadas=None, bloqueo=None):
    a = entorno["ajustes"]
    a.politica_sesion_abierta = politica
    llamadas = [] if llamadas is None else llamadas

    def correr(t):
        llamadas.append(t)
        if bloqueo:
            bloqueo.wait(5)
        return {"estado": "completada", "session_id": t["resume"] or "nueva-sid", "respuesta": "ok",
                "costo_usd": 0.01, "bitacora": [{"herramienta": "Read", "permitida": True, "motivo": "ok"}]}

    cat = Catalogo(a.claude_home, Propias(a.sesiones_propias), Activas(lambda: activas or [], ttl=0),
                   a.umbral_actividad_s, a.sesiones_protegidas, listar=lambda d: list(sesiones))
    return Ejecutor(a, Registro(a.registro), cat, EngramFalso(), correr=correr), llamadas


def esperar(e, iid, estados=("completada", "error", "aviso_sesion_abierta")):
    for _ in range(100):
        r = e.obtener(iid)
        if r["estado"] in estados:
            return r
        time.sleep(0.05)
    raise AssertionError(r)


def test_cambios_sin_confirmar_no_ejecuta(entorno):
    e, llamadas = armar(entorno)
    e.iniciar()
    r = e.recibir({"proyecto": "alfa", "texto": "agrega un README", "modo": "cambios"})
    time.sleep(0.4)
    assert r["estado"] == "pendiente_confirmacion"
    assert e.obtener(r["id"])["estado"] == "pendiente_confirmacion"
    assert llamadas == []
    e.detener()


def test_cambios_confirmado_ejecuta_en_modo_cambios(entorno):
    e, llamadas = armar(entorno)
    e.iniciar()
    r = e.recibir({"proyecto": "alfa", "texto": "agrega un README", "modo": "cambios"})
    e.confirmar(r["id"])
    final = esperar(e, r["id"])
    assert final["estado"] == "completada" and llamadas[0]["modo"] == "cambios"
    with pytest.raises(EstadoInvalido):
        e.confirmar(r["id"])  # no se confirma dos veces
    e.detener()


def test_cancelar_y_expirar_pendientes(entorno):
    e, llamadas = armar(entorno)
    r = e.recibir({"proyecto": "alfa", "texto": "x", "modo": "cambios"})
    assert e.cancelar(r["id"])["estado"] == "cancelada"
    with pytest.raises(EstadoInvalido):
        e.confirmar(r["id"])
    r2 = e.recibir({"proyecto": "alfa", "texto": "x", "modo": "cambios"})
    e.almacen.actualizar(r2["id"], expira="2000-01-01T00:00:00")
    assert e.obtener(r2["id"])["estado"] == "expirada"
    with pytest.raises(EstadoInvalido):
        e.confirmar(r2["id"])
    assert llamadas == []


def test_lectura_reanuda_ultima_sesion_cerrada(entorno):
    viejo = int((time.time() - 3600) * 1000)
    e, llamadas = armar(entorno, sesiones=[Info("aaaa-1", viejo), Info("bbbb-2", viejo - 5000)])
    e.iniciar()
    r = e.recibir({"proyecto": "alfa", "texto": "resume", "modo": "lectura"})
    final = esperar(e, r["id"])
    assert llamadas[0]["resume"] == "aaaa-1" and llamadas[0]["modo"] == "lectura"
    assert final["sesion"]["tipo"] == "reanudada" and final["costo_usd"] == 0.01
    assert json.loads((entorno["ajustes"].historial / f"{r['id']}.json").read_text(encoding="utf-8"))["estado"] == "completada"
    e.detener()


def test_sesion_abierta_en_terminal_usa_sesion_nueva(entorno):
    reciente = int(time.time() * 1000)
    e, llamadas = armar(entorno, sesiones=[Info("aaaa-1", reciente)])
    e.iniciar()
    r = e.recibir({"proyecto": "alfa", "texto": "resume", "modo": "lectura"})
    final = esperar(e, r["id"])
    assert llamadas[0]["resume"] is None
    assert final["sesion"]["tipo"] == "nueva" and "transcript modificado" in final["sesion"]["motivo"]
    assert "Contexto de engram" in llamadas[0]["prompt"]
    assert "nueva-sid" in Propias(entorno["ajustes"].sesiones_propias).todas()
    e.detener()


def test_sesion_activa_segun_claude_agents_con_politica_aviso_no_ejecuta(entorno):
    viejo = int((time.time() - 3600) * 1000)
    e, llamadas = armar(entorno, sesiones=[Info("aaaa-1", viejo)], politica="aviso",
                        activas=[{"sessionId": "aaaa-1", "kind": "interactive", "status": "busy"}])
    e.iniciar()
    r = e.recibir({"proyecto": "alfa", "texto": "resume", "modo": "lectura"})
    final = esperar(e, r["id"])
    assert final["estado"] == "aviso_sesion_abierta" and llamadas == []
    assert "claude agents" in final["aviso"]
    e.detener()


def test_sesion_protegida_nunca_se_reanuda(entorno):
    entorno["ajustes"].sesiones_protegidas = frozenset({"aaaa-1"})
    viejo = int((time.time() - 3600) * 1000)
    e, llamadas = armar(entorno, sesiones=[Info("aaaa-1", viejo)])
    e.iniciar()
    final = esperar(e, e.recibir({"proyecto": "alfa", "texto": "x", "modo": "lectura"})["id"])
    assert llamadas[0]["resume"] is None and final["sesion"]["tipo"] == "nueva"
    e.detener()


def test_sesiones_propias_no_cuentan_como_principales(entorno):
    viejo = int((time.time() - 3600) * 1000)
    Propias(entorno["ajustes"].sesiones_propias).agregar("propia-1")
    e, llamadas = armar(entorno, sesiones=[Info("propia-1", viejo), Info("usuario-2", viejo - 1000)])
    e.iniciar()
    esperar(e, e.recibir({"proyecto": "alfa", "texto": "x", "modo": "lectura"})["id"])
    assert llamadas[0]["resume"] == "usuario-2"
    e.detener()


def test_una_a_la_vez_por_proyecto(entorno):
    entorno["ajustes"].trabajadores = 2
    bloqueo = threading.Event()
    e, llamadas = armar(entorno, bloqueo=bloqueo)
    e.iniciar()
    r1 = e.recibir({"proyecto": "alfa", "texto": "1", "modo": "lectura"})
    r2 = e.recibir({"proyecto": "alfa", "texto": "2", "modo": "lectura"})
    r3 = e.recibir({"proyecto": "beta", "texto": "3", "modo": "lectura"})
    time.sleep(0.5)
    assert e.obtener(r2["id"])["estado"] == "en_cola"  # alfa ocupado
    assert e.obtener(r3["id"])["estado"] == "ejecutando"  # beta corre en paralelo
    bloqueo.set()
    for r in (r1, r2, r3):
        esperar(e, r["id"])
    e.detener()


def test_prompt_marca_modo_y_contexto_como_datos():
    t = armar_prompt("lectura", "hola", [{"tipo": "x", "titulo": "y", "actualizada": "z"}])
    assert "MODO LECTURA" in t and "no instrucciones" in t and t.endswith("hola")
