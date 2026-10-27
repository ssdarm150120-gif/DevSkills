import asyncio

import pytest

from nucleo import permisos as p
from nucleo.ajustes import Ajustes

ESCRITURA_Y_SHELL = {"Edit", "Write", "NotebookEdit", "MultiEdit", "Bash", "PowerShell", "Agent", "Task", "Skill"}


@pytest.mark.parametrize("web", [False, True])
def test_lectura_nunca_expone_herramientas_de_escritura(web, tmp_path):
    a = Ajustes(raiz=tmp_path, lectura_permite_webfetch=web)
    kw = p.argumentos("lectura", tmp_path, a, None, guardian=None)
    assert not (set(kw["tools"]) & ESCRITURA_Y_SHELL)
    assert set(kw["tools"]) <= {"Read", "Grep", "Glob", "WebFetch"}
    assert ESCRITURA_Y_SHELL <= set(kw["disallowed_tools"])
    assert "mcp__*" in kw["disallowed_tools"]
    assert kw["allowed_tools"] == []
    assert kw["permission_mode"] == "dontAsk"
    assert kw["strict_mcp_config"] is True and kw["mcp_servers"] == {}
    assert ("WebFetch" in kw["tools"]) is web


def test_cambios_permite_editar_pero_nunca_shell(tmp_path):
    kw = p.argumentos("cambios", tmp_path, Ajustes(raiz=tmp_path), "sid", guardian=None)
    assert {"Edit", "Write"} <= set(kw["tools"])
    assert not ({"Bash", "PowerShell", "Agent", "WebFetch"} & set(kw["tools"]))
    assert {"Bash", "PowerShell", "WebFetch", "mcp__*"} <= set(kw["disallowed_tools"])
    assert kw["resume"] == "sid"


def test_modo_desconocido(tmp_path):
    with pytest.raises(ValueError):
        p.argumentos("todo", tmp_path, Ajustes(raiz=tmp_path), None, guardian=None)


@pytest.mark.parametrize("herr,entrada", [
    ("Write", {"file_path": "nuevo.txt", "content": "x"}),
    ("Edit", {"file_path": "a.py", "old_string": "a", "new_string": "b"}),
    ("NotebookEdit", {"notebook_path": "n.ipynb"}),
    ("Bash", {"command": "dir"}),
    ("PowerShell", {"command": "ls"}),
    ("Agent", {"prompt": "x"}),
    ("mcp__engram__mem_save", {}),
    ("WebFetch", {"url": "https://example.com"}),
])
def test_guardian_niega_escritura_y_shell_en_lectura(herr, entrada, tmp_path):
    ok, _ = p.decidir(herr, entrada, "lectura", tmp_path)
    assert not ok


def test_guardian_lectura_dentro_del_proyecto(tmp_path):
    (tmp_path / "src").mkdir()
    assert p.decidir("Read", {"file_path": str(tmp_path / "src" / "a.py")}, "lectura", tmp_path)[0]
    assert p.decidir("Read", {"file_path": "src/a.py"}, "lectura", tmp_path)[0]
    assert p.decidir("Grep", {"pattern": "def"}, "lectura", tmp_path)[0]
    assert p.decidir("Glob", {"pattern": "**/*.py"}, "lectura", tmp_path)[0]


@pytest.mark.parametrize("entrada", [
    {"file_path": "../fuera.txt"},
    {"file_path": "C:\\Windows\\win.ini"},
    {"file_path": ".env"},
    {"file_path": "config/.env.local"},
    {"file_path": "Api/appsettings.Development.json"},
    {"file_path": "certs/server.pem"},
    {"file_path": ".git/config"},
    {"file_path": ".token"},
    {},
])
def test_guardian_niega_rutas_fuera_o_sensibles(entrada, tmp_path):
    assert not p.decidir("Read", entrada, "lectura", tmp_path)[0]


@pytest.mark.parametrize("herr,entrada", [
    ("Glob", {"pattern": "../**/*"}),
    ("Glob", {"pattern": "C:/Users/**"}),
    ("Glob", {"pattern": "**/.env*"}),
    ("Grep", {"pattern": "x", "path": "..\\otro"}),
    ("Grep", {"pattern": "x", "glob": "**/appsettings*.json"}),
])
def test_guardian_niega_patrones_peligrosos(herr, entrada, tmp_path):
    assert not p.decidir(herr, entrada, "lectura", tmp_path)[0]


def test_guardian_cambios_solo_dentro_y_sin_secretos(tmp_path):
    assert p.decidir("Write", {"file_path": "docs/nota.md"}, "cambios", tmp_path)[0]
    assert not p.decidir("Write", {"file_path": "../otro/nota.md"}, "cambios", tmp_path)[0]
    assert not p.decidir("Edit", {"file_path": ".env"}, "cambios", tmp_path)[0]
    assert not p.decidir("Write", {"file_path": ".git/hooks/pre-commit"}, "cambios", tmp_path)[0]
    assert not p.decidir("Bash", {"command": "git commit"}, "cambios", tmp_path)[0]


def test_hook_devuelve_formato_documentado_y_registra(tmp_path):
    bitacora = []
    g = p.crear_guardian("lectura", tmp_path, False, bitacora)
    out = asyncio.run(g({"hook_event_name": "PreToolUse", "tool_name": "Write",
                         "tool_input": {"file_path": "x"}}, "t1", None))
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse" and hso["permissionDecision"] == "deny"
    out = asyncio.run(g({"hook_event_name": "PreToolUse", "tool_name": "Read",
                         "tool_input": {"file_path": "x.md"}}, "t2", None))
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert [b["permitida"] for b in bitacora] == [False, True]
