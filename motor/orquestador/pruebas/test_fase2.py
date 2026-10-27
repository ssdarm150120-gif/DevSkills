"""Fase 2: contexto con grafo, propuestas por instrucciones repetidas y resolución de proyecto (sin red)."""
import http.client
import itertools
import json
import threading
import time
from pathlib import Path

import pytest

from nucleo import resolver as mod_resolver
from nucleo import texto as tx
from nucleo.api import CABECERA_TOKEN, Servicio, crear_servidor
from nucleo.ejecutor import Ejecutor
from nucleo.grafo import Grafo
from nucleo.propuestas import (Conflicto, ErrorPropuesta, Propuestas, agrupar, limpiar, recomendar_tipo)
from nucleo.registro import Registro, Proyecto
from nucleo.sesiones import Activas, Catalogo, Propias

REPORTE = """# Graph Report - alfa  (2026-10-26)

## Summary
- 120 nodes · 300 edges · 9 communities (9 shown)

## Graph Freshness
- Built from commit: `abc1234`

## Community Hubs (Navigation)
- api.py
- ventas.py

## God Nodes (most connected - your core abstractions)
1. `calcular_presupuesto()` - 40 edges
2. `cargar_ventas()` - 20 edges

## Communities (9 total)
"""


# ------------------------------------------------------------------ grafo falso

class Llamadas:
    """Sustituto de subprocess: registra cada comando y responde como git/graphify."""

    def __init__(self, head="abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", diff="", repo=True, query="NODE x [src=C:\\Users\\yo\\secreto.py]\n"):
        self.cmds, self.envs = [], []
        self.head, self.diff, self.repo, self.query = head, diff, repo, query

    def __call__(self, cmd, cwd, timeout, env):
        self.cmds.append(cmd)
        self.envs.append(env)
        if cmd[0] == "git":
            if not self.repo:
                return 128, ""
            if "rev-parse" in cmd:
                return 0, self.head + "\n"
            if "status" in cmd:
                return 0, ""
            if "diff" in cmd:
                return 0, self.diff
        if cmd[1] == "query":
            return 0, self.query
        return 1, ""


def con_grafo(carpeta: Path):
    g = carpeta / "graphify-out"
    g.mkdir(parents=True, exist_ok=True)
    (g / "graph.json").write_text('{"nodes": []}', encoding="utf-8")
    (g / "GRAPH_REPORT.md").write_text(REPORTE, encoding="utf-8")


def grafo_falso(a, llamadas):
    a.grafo = {**a.grafo, "ejecutable": "graphify-falso"}
    return Grafo(a, ejecutar=llamadas)


def test_sin_grafo_no_ejecuta_nada(entorno):
    ll = Llamadas()
    g = grafo_falso(entorno["ajustes"], ll)
    assert g.estado(entorno["alfa"]) == {"tiene_grafo": False}
    assert g.consultar(entorno["alfa"], "hola", 1000)["error"] == "sin grafo"
    assert g.resumen(entorno["alfa"], 1000) == ""
    assert ll.cmds == []


def test_estado_al_dia_desactualizado_y_sin_git(entorno):
    con_grafo(entorno["alfa"])
    a = entorno["ajustes"]
    e = grafo_falso(a, Llamadas()).estado(entorno["alfa"])
    assert e["tiene_grafo"] and e["nodos"] == 120 and e["commit_grafo"] == "abc1234" and e["desactualizado"] is False
    e = grafo_falso(a, Llamadas(head="f" * 40, diff="app/ventas.py\napp/api.py\n")).estado(entorno["alfa"])
    assert e["desactualizado"] is True and e["archivos_cambiados"] == 2
    e = grafo_falso(a, Llamadas(head="f" * 40, diff="")).estado(entorno["alfa"])
    assert e["desactualizado"] is False
    e = grafo_falso(a, Llamadas(repo=False)).estado(entorno["alfa"])
    assert e["desactualizado"] is None and e["commit_git"] is None


def test_consulta_sin_llm_sin_shell_recortada_y_enmascarada(entorno):
    con_grafo(entorno["alfa"])
    ll = Llamadas(query="".join(f"NODE nodo{i} [src=C:\\Users\\yo\\app{i}.py] token=abcdefghijkl\n" for i in range(200)))
    r = grafo_falso(entorno["ajustes"], ll).consultar(entorno["alfa"], "--rm ¿cómo calcula?", 500)
    cmd = ll.cmds[-1]
    assert cmd[1] == "query" and cmd[2] == "rm ¿como calcula?" and "--graph" in cmd and "--budget" in cmd
    assert ll.envs[-1] == {"GRAPHIFY_BACKEND": "none"}
    assert r["truncado"] and len(r["texto"]) < 600
    assert "C:\\Users" not in r["texto"] and "abcdefghijkl" not in r["texto"]


def test_resumen_del_reporte(entorno):
    con_grafo(entorno["alfa"])
    r = grafo_falso(entorno["ajustes"], Llamadas()).resumen(entorno["alfa"], 1000)
    assert "120 nodes" in r and "calcular_presupuesto" in r and "ventas.py" in r


# ------------------------------------------------------------------ modos de contexto

class EngramFalso:
    def alias(self, pid):
        return [pid]

    def disponible(self):
        return True

    def buscar(self, alias, q="", limite=10, largo=600):
        return [{"id": 1, "tipo": "decision", "titulo": "Usar Django", "actualizada": "2026-10-01",
                 "extracto": "detalle" if largo else ""}]


class Info:
    def __init__(self, sid, ms, tam=10):
        self.session_id, self.last_modified, self.file_size = sid, ms, tam
        self.custom_title, self.summary, self.cwd = "t", None, ""


def armar(entorno, sesiones=(), activas=None, ll=None):
    a = entorno["ajustes"]
    llamadas = []

    def correr(t):
        llamadas.append(t)
        return {"estado": "completada", "session_id": t["resume"] or "nueva-sid", "respuesta": "ok", "costo_usd": 0.02}

    cat = Catalogo(a.claude_home, Propias(a.sesiones_propias), Activas(lambda: activas or [], ttl=0),
                   a.umbral_actividad_s, a.sesiones_protegidas, listar=lambda d: list(sesiones))
    e = Ejecutor(a, Registro(a.registro), cat, EngramFalso(), correr=correr, grafo=grafo_falso(a, ll or Llamadas()))
    return e, llamadas


def correr_una(e, **extra):
    r = e.recibir({"proyecto": "alfa", "texto": "¿cómo se calcula el presupuesto?", "modo": "lectura", **extra})
    return e.ejecutar(e.almacen.obtener(r["id"]))


VIEJO = int((time.time() - 3600) * 1000)


def test_auto_sesion_chica_y_cerrada_reanuda(entorno):
    e, ll = armar(entorno, sesiones=[Info("aaaa-1", VIEJO)])
    f = correr_una(e)
    assert ll[0]["resume"] == "aaaa-1" and f["sesion"]["contexto"] == "sesion"
    assert f["contexto_usado"]["modo"] == "sesion" and f["contexto_usado"]["solicitado"] == "auto"
    assert "Contexto compacto" not in ll[0]["prompt"] and f["costo_usd"] == 0.02


def test_auto_sesion_grande_por_tamano_usa_grafo(entorno):
    con_grafo(entorno["alfa"])
    e, ll = armar(entorno, sesiones=[Info("aaaa-1", VIEJO, tam=5 * 1_048_576)])
    f = correr_una(e)
    assert ll[0]["resume"] is None and f["sesion"]["tipo"] == "nueva" and f["contexto_usado"]["modo"] == "grafo"
    assert "MB" in f["contexto_usado"]["motivo"]
    p = ll[0]["prompt"]
    assert "consulta el grafo ANTES de leer archivos" in p and "calcular_presupuesto" in p
    assert "graphify query" in p and "Contexto de engram" in p and p.endswith("¿cómo se calcula el presupuesto?")
    assert f["contexto_usado"]["grafo"]["tiene_grafo"] and f["contexto_usado"]["caracteres"] == len(
        p.split("\n\n", 1)[1].rsplit("\n\nInstrucción:", 1)[0])


def test_auto_sesion_grande_por_tokens_usa_grafo(entorno):
    a = entorno["ajustes"]
    carpeta = a.claude_home / "projects" / "C--alfa"
    carpeta.mkdir(parents=True)
    uso = {"input_tokens": 10, "cache_read_input_tokens": 190000, "cache_creation_input_tokens": 500}
    (carpeta / "aaaa-1.jsonl").write_text(json.dumps({"type": "assistant", "message": {"usage": uso}}) + "\n",
                                          encoding="utf-8")
    e, ll = armar(entorno, sesiones=[Info("aaaa-1", VIEJO)])
    f = correr_una(e)
    assert f["contexto_usado"]["modo"] == "grafo" and "tokens" in f["contexto_usado"]["motivo"]
    assert f["contexto_usado"]["estimacion"]["tokens_contexto"] == 190510


def test_auto_sesion_abierta_usa_grafo_sin_grafo_en_disco(entorno):
    e, ll = armar(entorno, sesiones=[Info("aaaa-1", int(time.time() * 1000))])
    f = correr_una(e)
    assert ll[0]["resume"] is None and f["contexto_usado"]["modo"] == "grafo"
    assert "Sin grafo de código" in ll[0]["prompt"] and f["contexto_usado"]["grafo"] == {"tiene_grafo": False}


def test_grafo_explicito_siempre_sesion_nueva(entorno):
    e, ll = armar(entorno, sesiones=[Info("aaaa-1", VIEJO)])
    f = correr_una(e, contexto="grafo")
    assert ll[0]["resume"] is None and f["sesion"]["tipo"] == "nueva" and f["contexto"] == "grafo"
    assert "nueva-sid" in Propias(entorno["ajustes"].sesiones_propias).todas()


def test_sesion_explicita_reanuda_aunque_sea_grande(entorno):
    e, ll = armar(entorno, sesiones=[Info("aaaa-1", VIEJO, tam=50 * 1_048_576)])
    f = correr_una(e, contexto="sesion")
    assert ll[0]["resume"] == "aaaa-1" and f["contexto_usado"]["modo"] == "sesion"


def test_bloque_respeta_presupuesto(entorno):
    con_grafo(entorno["alfa"])
    entorno["ajustes"].grafo = {**entorno["ajustes"].grafo, "contexto_max_chars": 400}
    e, ll = armar(entorno, ll=Llamadas(query="NODE x\n" * 5000))
    f = correr_una(e, contexto="grafo")
    assert f["contexto_usado"]["caracteres"] <= 400 + 60


# ------------------------------------------------------------------ propuestas

_UUIDS = itertools.count()


def linea(tipo="user", texto=None, cwd="", ts="2026-10-01T10:00:00", uuid=None, **extra):
    d = {"type": tipo, "cwd": cwd, "timestamp": ts, "uuid": uuid or f"u{next(_UUIDS)}"}
    if texto is not None:
        d["message"] = {"role": tipo, "content": texto}
    d.update(extra)
    return json.dumps(d, ensure_ascii=False)


def transcript(a, carpeta_cc: str, sid: str, lineas: list[str], entrypoint="cli"):
    d = a.claude_home / "projects" / carpeta_cc
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.jsonl").write_text("\n".join([json.dumps({"type": "system", "entrypoint": entrypoint})] + lineas)
                                    + "\n", encoding="utf-8")


def sembrar(entorno):
    a = entorno["ajustes"]
    alfa, beta = str(entorno["alfa"]), str(entorno["beta"])
    # "commit y push" en alfa (2 conversaciones) y beta (1): general
    transcript(a, "C--alfa", "s1", [
        linea(texto="commit y push a la rama light", cwd=alfa, ts="2026-10-01T10:00:00"),
        linea(texto=[{"type": "tool_result", "content": "commit y push a la rama light"}], cwd=alfa,
              toolUseResult={"x": 1}),
        linea(texto="<task-notification>commit y push a la rama</task-notification>", cwd=alfa),
        linea(texto="commit y push a la rama light", cwd=alfa, isMeta=True),
        linea(texto="revisa la tabla de usuarios y sus permisos por departamento", cwd=alfa, ts="2026-10-01T11:00:00"),
        linea(texto="continúa", cwd=alfa),
    ])
    transcript(a, "C--alfa", "s2", [
        linea(texto="haz commit y push a la rama light pls", cwd=alfa, ts="2026-10-02T10:00:00"),
        linea(texto="revisa la tabla de usuarios y los permisos de cada departamento", cwd=alfa, ts="2026-10-02T11:00:00"),
        linea(texto='quiero esto <pasted_content id="1">' + "x = 1; " * 400 + "</pasted_content> arreglalo", cwd=alfa),
    ])
    transcript(a, "C--beta", "s3", [
        linea(texto="commit y push a la rama main", cwd=beta, ts="2026-10-03T10:00:00"),
        linea(texto="avísame cuando terminen los agentes", cwd=beta, ts="2026-10-03T11:00:00"),
        linea(texto="avísame cuando terminen los agentes de QA", cwd=beta, ts="2026-10-03T12:00:00"),
        linea(texto="dale, avísame cuando terminen", cwd=beta, ts="2026-10-03T13:00:00"),
    ])
    # sesión creada por un SDK: se ignora aunque repita
    transcript(a, "C--alfa", "s4", [linea(texto="commit y push a la rama light", cwd=alfa)] * 3, entrypoint="sdk-py")


def servicio_propuestas(entorno):
    a = entorno["ajustes"]
    a.propuestas = {**a.propuestas, "umbral_similitud": 0.4, "min_veces": 3, "min_conversaciones": 2,
                    "min_palabras": 2}
    return Propuestas(a, Registro(a.registro), Propias(a.sesiones_propias))


def por_termino(lista, termino):
    return next(p for p in lista if termino in p["grupo"]["terminos"])


def test_limpiar_excluye_lo_que_no_escribio_el_usuario():
    assert limpiar("<task-notification>x</task-notification>", 1000) is None
    assert limpiar("<command-name>/plugin</command-name>", 1000) is None
    assert limpiar("[Orquestador local · ...] hola", 1000) is None
    assert limpiar("mira esto <pasted_content id='1'>mucho texto</pasted_content> y arreglalo", 1000) == "mira esto y arreglalo"
    assert limpiar('<channel source="telegram" chat_id="1">revisa el CRM</channel>', 1000) == "revisa el CRM"
    assert limpiar("x" * 2000, 1000) is None
    assert limpiar("npm run dev > [API] (node:1) {a:[b]} <x> = |y| ; z /a/b/c_d $e" * 3, 1000) is None


def test_normalizacion_sin_acentos_rutas_ni_ids():
    n = tx.normalizar("Revisa C:\\Users\\yo\\app.py y la HU-12 en https://x.com, sesión 7b43e9c1 con 1500 filas")
    assert "users" not in n and "https" not in n and "7b43e9c1" not in n and "1500" not in n and "sesion" in n


def test_agrupacion_determinista_y_alcances(entorno):
    sembrar(entorno)
    P = servicio_propuestas(entorno)
    m1 = P.analizar()
    lista1 = P.listar()["propuestas"]
    assert m1["excluidos_sdk_u_orquestador"] == 1
    commit = por_termino(lista1, "commit")
    assert commit["grupo"]["veces"] == 3 and commit["grupo"]["conversaciones"] == 3
    assert commit["alcance"] == "general" and commit["grupo"]["proyectos"] == ["alfa", "beta"]
    aviso = por_termino(lista1, "avisame")
    assert aviso["alcance"] == "conversacion" and aviso["grupo"]["veces"] == 3
    usuarios = por_termino(lista1, "usuarios")
    assert usuarios["alcance"] == "proyecto" and usuarios["destino_sugerido"] == {"destino": "proyecto", "proyecto": "alfa"}
    assert len(lista1) == 3  # "continúa" (corto) y el pegado largo no forman grupos
    for p in lista1:
        assert p["mensaje"].startswith("Llevas ") and p["tipo_recomendado"] in ("agente", "skill", "comando")
        assert set(p["borradores"]) == {"agente", "skill", "comando"} and p["motivo_tipo"]
        assert all("<pasted_content" not in e for e in p["grupo"]["ejemplos"])
    # mismo insumo → mismos grupos e ids; no se duplican
    m2 = P.analizar()
    lista2 = P.listar()["propuestas"]
    assert [p["id"] for p in lista2] == [p["id"] for p in lista1] and m2["nuevas"] == 0


def test_agrupar_es_determinista():
    ms = [{"normal": t} for t in ["commit push rama light", "commit push rama main", "revisa tabla usuarios permisos",
                                  "revisa usuarios permisos departamento", "commit push"]]
    assert agrupar(ms, 0.4) == agrupar(list(ms), 0.4)
    assert agrupar(ms, 0.4)[0][:2] == [0, 1]


def test_tipo_recomendado():
    corto = [{"normal": "commit push"}] * 3
    assert recomendar_tipo(corto, ["Bash", "Read"])[0] == "comando"
    largo = [{"normal": "revisa tabla usuarios permisos departamento"}, {"normal": "revisa tabla usuarios"}]
    assert recomendar_tipo(largo, ["Read", "Grep", "Glob"])[0] == "agente"
    proc = [{"normal": "siempre usa formato tabla resumen semanal ventas"},
            {"normal": "usa formato tabla resumen mensual ventas"}]
    assert recomendar_tipo(proc, ["Read", "Grep", "Glob"])[0] == "skill"


def test_version_y_desde(entorno):
    sembrar(entorno)
    P = servicio_propuestas(entorno)
    assert P.version()["version"] == 0
    P.analizar()
    v1 = P.version()
    assert v1["version"] == 1 and v1["pendientes"] == 3
    assert P.listar(desde=1)["propuestas"] == []
    P.analizar()
    assert P.version()["version"] == 1  # sin cambios no sube
    pid = P.listar()["propuestas"][0]["id"]
    P.descartar(pid, {"motivo": "no lo necesito"})
    assert P.version()["version"] == 2 and [p["id"] for p in P.listar(desde=1)["propuestas"]] == [pid]


def test_decididas_no_se_reabren_ni_duplican(entorno):
    sembrar(entorno)
    P = servicio_propuestas(entorno)
    P.analizar()
    commit = por_termino(P.listar()["propuestas"], "commit")
    P.descartar(commit["id"], {})
    # una conversación nueva con la misma instrucción
    transcript(entorno["ajustes"], "C--beta", "s5", [linea(texto="commit y push a la rama light", cwd=str(entorno["beta"]),
                                                           ts="2026-10-05T10:00:00")])
    m = P.analizar()
    lista = P.listar()["propuestas"]
    assert m["nuevas"] == 0 and m["ya_decididas"] >= 1
    assert sum("commit" in p["grupo"]["terminos"] for p in lista) == 1
    assert P.obtener(commit["id"])["estado"] == "descartada"
    with pytest.raises(Conflicto):
        P.descartar(commit["id"], {})


@pytest.mark.parametrize("tipo,ruta", [("agente", "agents/{n}.md"), ("skill", "skills/{n}/SKILL.md"),
                                       ("comando", "commands/{n}.md")])
def test_crear_general_por_tipo_sin_sobrescribir(entorno, tipo, ruta):
    sembrar(entorno)
    P = servicio_propuestas(entorno)
    P.analizar()
    props = P.listar()["propuestas"]
    p = props[0]
    r = P.crear(p["id"], {"confirmacion": p["id"], "destino": "general", "tipo": tipo})
    destino = entorno["ajustes"].claude_home / ruta.format(n=p["nombre"])
    assert Path(r["archivo"]) == destino.resolve() and r["estado"] == "aceptada" and r["tipo_creado"] == tipo
    contenido = destino.read_text(encoding="utf-8")
    assert contenido.startswith("---\n") and f"description: " in contenido
    if tipo != "comando":
        assert f"name: {p['nombre']}\n" in contenido
    if tipo == "agente":
        assert "\ntools: " in contenido
    with pytest.raises(Conflicto):  # ya aceptada
        P.crear(p["id"], {"confirmacion": p["id"], "destino": "general", "tipo": tipo})
    # otra propuesta con el mismo nombre: no sobrescribe
    otra = props[1]
    datos = P.obtener(otra["id"])
    datos["nombre"] = p["nombre"]
    P._escribir(P._archivo(otra["id"]), datos)
    antes = destino.read_text(encoding="utf-8")
    with pytest.raises(Conflicto):
        P.crear(otra["id"], {"confirmacion": otra["id"], "destino": "general", "tipo": tipo})
    assert destino.read_text(encoding="utf-8") == antes
    assert P.obtener(otra["id"])["estado"] == "pendiente"


def test_crear_en_proyecto(entorno):
    sembrar(entorno)
    P = servicio_propuestas(entorno)
    P.analizar()
    p = por_termino(P.listar()["propuestas"], "usuarios")
    r = P.crear(p["id"], {"confirmacion": p["id"], "destino": "proyecto", "proyecto": "alfa"})
    assert Path(r["archivo"]).is_relative_to(entorno["alfa"].resolve() / ".claude")
    assert "SIN COMMIT" in r["aviso"]


def test_rechazos_de_creacion(entorno):
    sembrar(entorno)
    P = servicio_propuestas(entorno)
    P.analizar()
    p = P.listar()["propuestas"][0]
    pid = p["id"]
    malos = [
        {"confirmacion": "otro", "destino": "general"},
        {"confirmacion": pid, "destino": "C:\\Windows"},
        {"confirmacion": pid, "destino": "proyecto"},
        {"confirmacion": pid, "destino": "proyecto", "proyecto": "zeta"},
        {"confirmacion": pid, "destino": "proyecto", "proyecto": "../alfa"},
        {"confirmacion": pid, "destino": "general", "proyecto": "alfa"},
        {"confirmacion": pid, "destino": "general", "tipo": "hook"},
        {"confirmacion": pid, "destino": "general", "ruta": "C:\\x"},
    ]
    for cuerpo in malos:
        with pytest.raises(ErrorPropuesta):
            P.crear(pid, cuerpo)
    for nombre in ("../evil", "Mayus", "con espacio", "a/b", "..", "x" * 70, "-a"):
        datos = P.obtener(pid)
        datos["nombre"] = nombre
        P._escribir(P._archivo(pid), datos)
        with pytest.raises(ErrorPropuesta):
            P.crear(pid, {"confirmacion": pid, "destino": "general"})
    with pytest.raises(ErrorPropuesta):
        P.obtener("../../x")
    assert not (entorno["ajustes"].claude_home / "agents").exists() or not any(
        (entorno["ajustes"].claude_home / "agents").iterdir())
    assert not (entorno["tmp"] / "evil.md").exists()


# ------------------------------------------------------------------ resolver

def proyectos_falsos():
    p = lambda pid, nombre: Proyecto(pid, nombre, Path("C:/x") / pid, ())  # noqa: E731
    return {"kpis": p("kpis", "Prototipo de KPIs"), "kpis-acme": p("kpis-acme", "KPIs Acme"),
            "dashboard": p("dashboard", "Dashboard General"), "demo": p("demo", "Demo · Portal de Compras"),
            "crm": p("crm", "CRM"), "calculadora": p("calculadora", "Calculadora de Envío")}


ALIAS = {"demo": ["compras", "compras/demo"], "kpis-acme": ["kpis acme", "acme"],
         "calculadora": ["calculadora"], "dashboard": ["dashboard", "tablero"]}


@pytest.mark.parametrize("texto,esperado", [
    ("revisa el dashboard", "dashboard"), ("en la calculadora de envíos", "calculadora"),
    ("pendientes de compras/demo", "demo"), ("los kpis de acme", "kpis-acme"),
    ("kpis acme", "kpis-acme"), ("el prototipo de kpis", "kpis"), ("abre el CRM", "crm"),
    ("dashbord general", "dashboard")])
def test_resolver(texto, esperado):
    r = mod_resolver.resolver(texto, proyectos_falsos(), ALIAS)
    assert r["proyecto"] == esperado and not r["ambiguo"] and r["puntaje"] >= 0.6


def test_resolver_ambiguo_y_sin_coincidencia():
    r = mod_resolver.resolver("compara kpis con el crm", proyectos_falsos(), ALIAS)
    assert r["proyecto"] is None and r["ambiguo"] and {c["proyecto"] for c in r["candidatos"][:2]} == {"kpis", "crm"}
    r = mod_resolver.resolver("algo sin relación", proyectos_falsos(), ALIAS)
    assert r["proyecto"] is None and r["candidatos"] == []


# ------------------------------------------------------------------ API

TOKEN = "t" * 43


@pytest.fixture
def api(entorno):
    a = entorno["ajustes"]
    sembrar(entorno)
    con_grafo(entorno["alfa"])
    a.alias_proyectos = {"alfa": ["primero"]}
    reg = Registro(a.registro)
    cat = Catalogo(a.claude_home, Propias(a.sesiones_propias), Activas(lambda: [], ttl=0), 120, (), listar=lambda d: [])
    g = grafo_falso(a, Llamadas())
    ej = Ejecutor(a, reg, cat, EngramFalso(), correr=lambda t: {"estado": "completada"}, grafo=g)
    s = Servicio(a, reg, None, EngramFalso(), ej, TOKEN, 0, grafo=g, propuestas=servicio_propuestas(entorno))
    srv = crear_servidor(s)
    s.puerto = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield s
    srv.shutdown()
    srv.server_close()


def pedir(s, metodo, ruta, cuerpo=None, token=TOKEN):
    c = http.client.HTTPConnection("127.0.0.1", s.puerto, timeout=10)
    h = {"Host": f"127.0.0.1:{s.puerto}", "Content-Type": "application/json"}
    if token:
        h[CABECERA_TOKEN] = token
    c.request(metodo, ruta, body=json.dumps(cuerpo).encode() if cuerpo is not None else None, headers=h)
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_api_grafo(api):
    assert pedir(api, "GET", "/api/grafo/alfa", token=None)[0] == 401
    c, r = pedir(api, "GET", "/api/grafo/alfa?q=presupuesto")
    assert c == 200 and r["grafo"]["tiene_grafo"] and r["resultado"]["codigo"] == 0 and "C:\\Users" not in r["resultado"]["texto"]
    c, r = pedir(api, "GET", "/api/grafo/beta")
    assert c == 200 and r["grafo"] == {"tiene_grafo": False} and r["resultado"] is None
    assert pedir(api, "GET", "/api/grafo/zeta?q=x")[0] == 400
    assert pedir(api, "GET", "/api/grafo/alfa?q=x&graph=C:/x")[0] == 400
    assert pedir(api, "GET", "/api/grafo/alfa?q=" + "x" * 300)[0] == 400


def test_api_resolver(api):
    c, r = pedir(api, "GET", "/api/resolver?texto=revisa%20el%20primero")
    assert c == 200 and r["proyecto"] == "alfa"
    assert pedir(api, "GET", "/api/resolver")[0] == 400
    assert pedir(api, "GET", "/api/resolver?texto=a&otro=1")[0] == 400


def test_api_propuestas_flujo(api, entorno):
    c, r = pedir(api, "POST", "/api/propuestas-agentes/analizar", {})
    assert c == 200 and r["nuevas"] == 3 and r["version"] == 1
    assert pedir(api, "POST", "/api/propuestas-agentes/analizar", {"x": 1})[0] == 400
    c, v = pedir(api, "GET", "/api/propuestas-agentes/version")
    assert v == {"version": 1, "actualizada": v["actualizada"], "pendientes": 3, "total": 3}
    c, lst = pedir(api, "GET", "/api/propuestas-agentes?estado=pendiente")
    pid = lst["propuestas"][0]["id"]
    assert pedir(api, "GET", "/api/propuestas-agentes?estado=raro")[0] == 400
    assert pedir(api, "GET", "/api/propuestas-agentes?desde=x")[0] == 400
    assert pedir(api, "GET", f"/api/propuestas-agentes/{pid}")[1]["id"] == pid
    assert pedir(api, "GET", "/api/propuestas-agentes/ag-0000000000")[0] == 404
    assert pedir(api, "POST", f"/api/propuestas-agentes/{pid}/crear", {"destino": "general"})[0] == 400
    c, r = pedir(api, "POST", f"/api/propuestas-agentes/{pid}/crear",
                 {"confirmacion": pid, "destino": "general", "tipo": "skill"})
    assert c == 201 and r["estado"] == "aceptada"
    assert pedir(api, "POST", f"/api/propuestas-agentes/{pid}/crear", {"confirmacion": pid, "destino": "general"})[0] == 409
    otro = lst["propuestas"][1]["id"]
    assert pedir(api, "POST", f"/api/propuestas-agentes/{otro}/descartar", {})[1]["estado"] == "descartada"
    assert pedir(api, "POST", f"/api/propuestas-agentes/{otro}/descartar", {})[0] == 409
    assert pedir(api, "GET", "/api/propuestas-agentes?desde=1")[1]["version"] == 3
