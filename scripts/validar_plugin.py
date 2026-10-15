"""Valida la estructura del plugin DevSkills sin depender de Claude Code.

Uso: python scripts/validar_plugin.py   (desde la raíz del repositorio)
Revisa los manifiestos, que cada skill tenga su SKILL.md con frontmatter y
descripción, que cada agente tenga frontmatter, y que las skills y los agentes
referidos como `devskills:<nombre>` existan.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def frontmatter(archivo: Path) -> str:
    texto = archivo.read_text(encoding="utf-8")
    if not texto.startswith("---\n") or "\n---\n" not in texto[4:]:
        raise SystemExit(f"sin frontmatter: {archivo}")
    return texto[4:].split("\n---\n", 1)[0]


def main() -> int:
    plugin = json.loads((RAIZ / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    mercado = json.loads((RAIZ / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    if plugin.get("name") != "devskills" or not plugin.get("version"):
        raise SystemExit("plugin.json incompleto")
    if not mercado.get("name") or not mercado.get("owner", {}).get("name"):
        raise SystemExit("marketplace.json incompleto")
    if not any(p.get("name") == plugin["name"] for p in mercado.get("plugins", [])):
        raise SystemExit("el marketplace no lista el plugin")

    skills = {p.name for p in (RAIZ / "skills").iterdir() if p.is_dir()}
    agentes = {p.stem for p in (RAIZ / "agents").glob("*.md")}
    for nombre in sorted(skills):
        archivo = RAIZ / "skills" / nombre / "SKILL.md"
        if not archivo.is_file():
            raise SystemExit(f"skill sin SKILL.md: {nombre}")
        if "description:" not in frontmatter(archivo):
            raise SystemExit(f"skill sin description: {nombre}")
    for nombre in sorted(agentes):
        cabecera = frontmatter(RAIZ / "agents" / f"{nombre}.md")
        if "description:" not in cabecera or f"name: {nombre}" not in cabecera:
            raise SystemExit(f"agente con frontmatter incompleto: {nombre}")

    ganchos = json.loads((RAIZ / "hooks/hooks.json").read_text(encoding="utf-8"))
    comandos = [
        gancho.get("command", "")
        for eventos in ganchos.get("hooks", {}).values()
        for grupo in eventos
        for gancho in grupo.get("hooks", [])
    ]
    if not comandos:
        raise SystemExit("hooks/hooks.json no declara ningún gancho")
    for comando in comandos:
        for ruta in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"\s]+)", comando):
            if not (RAIZ / ruta).is_file():
                raise SystemExit(f"el gancho apunta a un archivo que no existe: {ruta}")

    conocidos = skills | agentes
    rotas: set[str] = set()
    for archivo in [*RAIZ.glob("agents/*.md"), *RAIZ.glob("skills/**/*.md"), *RAIZ.glob("plantillas/**/*.md")]:
        for referencia in re.findall(r"devskills:([a-z][a-z0-9-]*)", archivo.read_text(encoding="utf-8")):
            if referencia not in conocidos:
                rotas.add(f"{archivo.relative_to(RAIZ)} -> devskills:{referencia}")
    if rotas:
        raise SystemExit("referencias a skills o agentes que no existen:\n  " + "\n  ".join(sorted(rotas)))

    # Los permisos amplios (Bash(git *), Bash(python *), Bash(docker *)) solo pueden aparecer para advertir que NO se usen.
    amplios = ("Bash(git *)", "Bash(python *)", "Bash(docker *)", "Bash(gh *)")
    for archivo in [*RAIZ.glob("docs/*.md"), *RAIZ.glob("skills/**/*.md"), *RAIZ.glob("agents/*.md"), RAIZ / "README.md"]:
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            if any(patron in linea for patron in amplios) and "No uses" not in linea:
                raise SystemExit(f"permiso demasiado amplio recomendado en {archivo.relative_to(RAIZ)}:{numero}")

    print(f"plugin {plugin['version']}: {len(agentes)} agentes, {len(skills)} skills, referencias correctas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
