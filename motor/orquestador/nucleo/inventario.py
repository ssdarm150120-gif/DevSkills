"""Inventario de configuración de Claude por proyecto, SIN valores secretos.

Regla: de cada archivo solo salen nombres (servidores MCP, agentes, skills, plugins, eventos de hooks) y conteos;
nunca valores de `env`, `args`, `headers`, URLs, comandos ni el contenido de CLAUDE.md/AGENTS.md.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

RE_NOMBRE = re.compile(r"^[\w .:@/+-]{1,80}$")


def _nombre(n) -> str | None:
    return n if isinstance(n, str) and RE_NOMBRE.match(n) else None


def _nombres(iterable) -> list[str]:
    return sorted({x for x in (_nombre(n) for n in iterable) if x})


def _json(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _archivo(ruta: Path) -> dict:
    try:
        st = ruta.stat()
    except OSError:
        return {"existe": False}
    return {"existe": True, "tamano": st.st_size,
            "modificado": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))}


def _settings(ruta: Path) -> dict:
    d = _json(ruta)
    if not isinstance(d, dict):
        return {"existe": ruta.exists(), "legible": False} if ruta.exists() else {"existe": False}
    perm = d.get("permissions") if isinstance(d.get("permissions"), dict) else {}
    plugins = d.get("enabledPlugins") if isinstance(d.get("enabledPlugins"), dict) else {}
    hooks = d.get("hooks") if isinstance(d.get("hooks"), dict) else {}
    return {
        "existe": True,
        "claves": _nombres(d.keys()),
        "permisos": {k: len(perm.get(k) or []) for k in ("allow", "deny", "ask") if isinstance(perm.get(k), list)},
        "plugins_habilitados": _nombres(k for k, v in plugins.items() if v is True),
        "hooks_eventos": _nombres(hooks.keys()),
    }


def _norm(ruta: str) -> str:
    return ruta.replace("\\", "/").rstrip("/").lower()


def claude_json_por_proyecto(claude_json: Path) -> tuple[dict[str, dict], list[str]]:
    """Del ~/.claude.json solo se toman NOMBRES de servidores MCP por proyecto y los del usuario."""
    d = _json(claude_json)
    if not isinstance(d, dict):
        return {}, []
    por: dict[str, dict] = {}
    for clave, v in (d.get("projects") or {}).items():
        if not isinstance(v, dict) or not isinstance(clave, str):
            continue
        k = _norm(clave)
        e = por.setdefault(k, {"servidores_mcp": set(), "mcpjson_habilitados": set(), "mcpjson_deshabilitados": set()})
        e["servidores_mcp"].update(_nombres((v.get("mcpServers") or {}).keys()))
        e["mcpjson_habilitados"].update(_nombres(v.get("enabledMcpjsonServers") or []))
        e["mcpjson_deshabilitados"].update(_nombres(v.get("disabledMcpjsonServers") or []))
    por = {k: {kk: sorted(vv) for kk, vv in e.items()} for k, e in por.items()}
    return por, _nombres((d.get("mcpServers") or {}).keys())


def config_claude(carpeta: Path, claude_json_proyectos: dict[str, dict]) -> dict:
    cl = carpeta / ".claude"
    mcp = _json(carpeta / ".mcp.json")
    agentes = sorted(p.stem for p in (cl / "agents").glob("*.md")) if (cl / "agents").is_dir() else []
    skills = sorted(p.parent.name for p in (cl / "skills").glob("*/SKILL.md")) if (cl / "skills").is_dir() else []
    return {
        "claude_md": _archivo(carpeta / "CLAUDE.md"),
        "claude_md_en_carpeta_claude": _archivo(cl / "CLAUDE.md"),
        "agents_md": _archivo(carpeta / "AGENTS.md"),
        "mcp_json_servidores": _nombres((mcp.get("mcpServers") or {}).keys()) if isinstance(mcp, dict) else [],
        "agentes": _nombres(agentes),
        "skills": _nombres(skills),
        "settings": _settings(cl / "settings.json"),
        "settings_local": _settings(cl / "settings.local.json"),
        "claude_json": claude_json_por_proyecto_de(carpeta, claude_json_proyectos),
    }


def claude_json_por_proyecto_de(carpeta: Path, por: dict[str, dict]) -> dict:
    return por.get(_norm(str(carpeta)), {"servidores_mcp": [], "mcpjson_habilitados": [], "mcpjson_deshabilitados": []})


class Inventario:
    def __init__(self, ajustes, registro, catalogo, engram, grafo=None):
        self.a = ajustes
        self.grafo = grafo
        self.registro = registro
        self.catalogo = catalogo
        self.engram = engram

    def proyecto(self, pid: str, detalle: bool = True) -> dict:
        p = self.registro.proyectos()[pid]
        por, _ = claude_json_por_proyecto(self.a.claude_json)
        sesiones = self.catalogo.sesiones(p)
        ultima = self.catalogo.ultima_principal(p, sesiones)
        u = None
        if ultima:
            u = ultima.resumen()
            u.update(self.catalogo.apertura(ultima))
        alias = self.engram.alias(pid)
        salida = {
            "id": pid, "nombre": p.nombre, "carpeta_existe": p.carpeta.is_dir(),
            "sesiones": {"total": len(sesiones), "ultima_principal": u},
            "claude": config_claude(p.carpeta, por) if p.carpeta.is_dir() else None,
            "engram": {"proyectos": alias, "observaciones": self.engram.contar(alias)},
            "grafo": (self.grafo.estado(p.carpeta) if self.grafo is not None and p.carpeta.is_dir()
                      else {"tiene_grafo": False}),
        }
        if detalle:
            salida["sesiones"]["recientes"] = [s.resumen() for s in sesiones[:5]]
        return salida

    def todos(self) -> dict:
        _, globales = claude_json_por_proyecto(self.a.claude_json)
        return {"servidores_mcp_usuario": globales,
                "engram_disponible": self.engram.disponible(),
                "proyectos": [self.proyecto(pid, detalle=False) for pid in sorted(self.registro.proyectos())]}
