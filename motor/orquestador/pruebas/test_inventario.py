import json
import sqlite3
import time

from nucleo.engram import Engram, tapar, terminos_fts
from nucleo.inventario import Inventario
from nucleo.registro import Registro
from nucleo.sesiones import Activas, Catalogo, Propias, Sesion, carpetas_de, entrypoint_de, estado_apertura


class SinEngram:
    def alias(self, pid):
        return [pid]

    def contar(self, a):
        return 0

    def disponible(self):
        return False


def inventario(entorno):
    a = entorno["ajustes"]
    cat = Catalogo(a.claude_home, Propias(a.sesiones_propias), Activas(lambda: [], ttl=0), 120, (),
                   listar=lambda d: [])
    return Inventario(a, Registro(a.registro), cat, SinEngram())


def test_inventario_no_filtra_secretos(entorno):
    salida = json.dumps(inventario(entorno).todos(), ensure_ascii=False)
    for secreto in ("SECRETO", "PROMPT-PRIVADO", "instrucciones privadas", "npx", "secreto.ps1", "XYZ",
                    "git status", "https://x.example"):
        assert secreto not in salida, secreto


def test_inventario_trae_nombres(entorno):
    d = inventario(entorno).proyecto("alfa")
    c = d["claude"]
    assert c["mcp_json_servidores"] == ["basedatos"]
    assert c["agentes"] == ["revisor"] and c["skills"] == ["desplegar"]
    assert c["claude_md"]["existe"] is True and "contenido" not in c["claude_md"]
    assert c["settings"]["plugins_habilitados"] == ["devskills@market"]
    assert c["settings"]["permisos"] == {"allow": 1, "deny": 1}
    assert c["settings"]["hooks_eventos"] == ["PreToolUse"]
    assert c["claude_json"]["servidores_mcp"] == ["privado"]  # clave de ruta en otro formato (mayúsculas, /)
    assert inventario(entorno).todos()["servidores_mcp_usuario"] == ["rea"]


def test_carpetas_de_expande_comodines(entorno, tmp_path):
    (tmp_path / "Ex-wt-1").mkdir()
    (tmp_path / "Ex-wt-2").mkdir()
    (tmp_path / "Otra").mkdir()

    class P:
        carpeta = tmp_path / "Ex"
        transcripts = (str(tmp_path / "Ex-wt-*"),)
    nombres = sorted(c.split("\\")[-1].split("/")[-1] for c in carpetas_de(P))
    assert nombres == ["Ex", "Ex-wt-1", "Ex-wt-2"]


def test_entrypoint_lee_solo_el_principio(entorno):
    d = entorno["ajustes"].claude_home / "projects" / "C--x"
    d.mkdir(parents=True)
    (d / "abc-1.jsonl").write_text('{"type":"mode"}\n{"type":"user","entrypoint":"sdk-py"}\n', encoding="utf-8")
    assert entrypoint_de(entorno["ajustes"].claude_home, "abc-1") == "sdk-py"
    assert entrypoint_de(entorno["ajustes"].claude_home, "../etc") is None


def test_apertura_por_actividad_y_por_claude_agents():
    ahora = time.time()
    s = Sesion("abc", "t", int((ahora - 30) * 1000), 1, "")
    assert estado_apertura(s, {}, 120, ahora)["abierta"] is True
    s2 = Sesion("abc", "t", int((ahora - 3600) * 1000), 1, "")
    assert estado_apertura(s2, {}, 120, ahora)["abierta"] is False
    assert estado_apertura(s2, {"abc": {"kind": "background", "state": "blocked"}}, 120, ahora)["abierta"] is True
    e = estado_apertura(s2, None, 120, ahora)
    assert e["abierta"] is False and "no disponible" in e["deteccion"]


def crear_engram(ruta):
    c = sqlite3.connect(ruta)
    c.executescript("""
    create table observations (id integer primary key, session_id text, type text, title text, content text,
      tool_name text, project text, scope text default 'project', topic_key text, updated_at text,
      deleted_at text);
    create virtual table observations_fts using fts5(title, content, tool_name, type, project, topic_key,
      content='observations', content_rowid='id');
    """)
    filas = [(1, "decision", "Usar Celery", "token: abcdef123456 en cola", "beta", "project", None),
             (2, "decision", "Usar Celery", "otro proyecto", "gamma", "project", None),
             (3, "decision", "Celery personal", "nota", "beta", "personal", None),
             (4, "decision", "Celery borrado", "nota", "beta-vieja", "project", "2026-01-01"),
             (5, "bugfix", "Celery viejo", "nota vieja", "beta-vieja", "project", None)]
    for f in filas:
        c.execute("insert into observations (id,session_id,type,title,content,project,scope,deleted_at,updated_at) "
                  "values (?,?,?,?,?,?,?,?,datetime('now'))", (f[0], "s", *f[1:]))
    c.execute("insert into observations_fts(observations_fts) values('rebuild')")
    c.commit()
    c.close()


def test_engram_filtra_por_proyecto_scope_y_borrados_y_es_solo_lectura(entorno):
    db = entorno["ajustes"].engram_db
    crear_engram(db)
    e = Engram(db, {"beta": ["beta-vieja", "beta"]})
    r = e.buscar(e.alias("beta"), "celery")
    assert sorted(x["id"] for x in r) == [1, 5]
    assert "abcdef123456" not in json.dumps(r)
    assert e.contar(e.alias("beta")) == 2
    assert e.buscar(["beta"], 'celery" OR "x') is not None  # sin inyección FTS
    with e._conectar() as c:
        try:
            c.execute("delete from observations")
            raise AssertionError("la conexión debía ser de solo lectura")
        except sqlite3.OperationalError as ex:
            assert "readonly" in str(ex).lower()


def test_terminos_fts_y_tapar():
    assert terminos_fts('deploy; DROP "x" OR y*') == '"deploy" "DROP" "x" "OR" "y"'
    assert "abc" not in tapar("password=abcdefgh")
    assert "••••" in tapar("ghp_" + "a" * 30)
