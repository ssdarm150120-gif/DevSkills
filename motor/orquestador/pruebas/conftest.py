import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.ajustes import Ajustes  # noqa: E402


@pytest.fixture
def entorno(tmp_path):
    """Registro, proyectos, ~/.claude y ~/.claude.json falsos dentro de tmp_path (sin red ni datos reales)."""
    proyectos = tmp_path / "proyectos"
    alfa = proyectos / "alfa"
    beta = proyectos / "beta"
    for p in (alfa, beta):
        (p / ".claude" / "agents").mkdir(parents=True)
    (alfa / "CLAUDE.md").write_text("instrucciones privadas del proyecto", encoding="utf-8")
    (alfa / ".claude" / "agents" / "revisor.md").write_text("---\nname: revisor\n---", encoding="utf-8")
    (alfa / ".claude" / "skills" / "desplegar").mkdir(parents=True)
    (alfa / ".claude" / "skills" / "desplegar" / "SKILL.md").write_text("x", encoding="utf-8")
    (alfa / ".mcp.json").write_text(json.dumps({"mcpServers": {"basedatos": {
        "command": "npx", "args": ["--token", "ARG-SECRETO-123"], "env": {"DB_PASSWORD": "VALOR-SECRETO-456"}}}}),
        encoding="utf-8")
    (alfa / ".claude" / "settings.json").write_text(json.dumps({
        "permissions": {"allow": ["Bash(git status)"], "deny": ["Read(.env)"]},
        "enabledPlugins": {"devskills@market": True, "otro@market": False},
        "env": {"API_KEY": "VALOR-SECRETO-789"},
        "hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "secreto.ps1 --clave XYZ"}]}]}}),
        encoding="utf-8")
    (alfa / ".env").write_text("DB_PASSWORD=VALOR-SECRETO-ENV", encoding="utf-8")
    registro = tmp_path / "proyectos.json"
    registro.write_text(json.dumps({"proyectos": [
        {"id": "alfa", "nombre": "Alfa", "carpeta": str(alfa), "transcripts": [], "extra": {"x": 1}},
        {"id": "beta", "nombre": "Beta", "carpeta": str(beta)},
        {"id": "../malo", "carpeta": str(beta)},
        {"id": "relativo", "carpeta": "carpeta/relativa"},
    ]}), encoding="utf-8")
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({
        "mcpServers": {"rea": {"command": "rea", "env": {"TOKEN": "VALOR-SECRETO-GLOBAL"}}},
        "projects": {str(alfa).replace("\\", "/").upper(): {
            "mcpServers": {"privado": {"url": "https://x.example/?key=VALOR-SECRETO-URL"}},
            "enabledMcpjsonServers": ["basedatos"], "lastSessionFirstPrompt": "PROMPT-PRIVADO"}}}),
        encoding="utf-8")
    raiz = tmp_path / "orq"
    raiz.mkdir()
    a = Ajustes(raiz=raiz, registro=registro, claude_home=tmp_path / ".claude", claude_json=claude_json,
                engram_db=tmp_path / "engram.db", engram_alias={"beta": ["beta-vieja", "beta"]})
    (tmp_path / ".claude" / "projects").mkdir(parents=True)
    return {"ajustes": a, "alfa": alfa, "beta": beta, "tmp": tmp_path}
