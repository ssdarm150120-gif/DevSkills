"""Modelo de permisos de las instrucciones (ver DISENO.md, sección "Permisos").

Capas, de la más externa a la más interna; cualquiera basta para bloquear una escritura en modo lectura:
1. `tools`: el modelo solo VE las herramientas del modo (lectura: Read, Grep, Glob).
2. `disallowed_tools`: nombres desnudos (Bash, Edit, Write, Agent, mcp__*, ...) que el CLI quita del contexto,
   más reglas Read(...) que niegan archivos sensibles también a Grep/Glob.
3. `strict_mcp_config=True` y `mcp_servers={}`: ningún servidor MCP (ni de .mcp.json, ni de plugins, ni conectores).
4. `permission_mode="dontAsk"`: lo que no esté aprobado se NIEGA (nunca se queda esperando una pregunta).
5. Hook PreToolUse sin matcher (`guardian`): aprueba solo herramientas de la lista del modo, con rutas dentro de la
   carpeta del proyecto y fuera de la lista de archivos sensibles; todo lo demás lo niega. Corre antes que las reglas.
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

LECTURA = ("Read", "Grep", "Glob")
ESCRITURA = ("Edit", "Write", "NotebookEdit", "MultiEdit")
HERRAMIENTAS = {"lectura": LECTURA, "cambios": LECTURA + ("Edit", "Write", "NotebookEdit")}

PROHIBIDAS_SIEMPRE = (
    "Bash", "PowerShell", "BashOutput", "KillShell", "Monitor", "Agent", "Task", "WebSearch", "Skill",
    "SlashCommand", "SendMessage", "TaskStop", "CronCreate", "EnterWorktree", "ExitWorktree", "mcp__*",
)

SENSIBLES = (
    ".env", ".env.*", "*.env", "*.pem", "*.key", "*.pfx", "*.p12", "*.kdbx", "*.jks", "*.keystore",
    "id_rsa*", "id_ed25519*", "id_ecdsa*", "appsettings*.json", "secrets.json", "secrets.*.json", "secrets.y*ml",
    "credentials", "credentials.json", ".git-credentials", ".netrc", "_netrc", ".npmrc", ".pypirc",
    ".token", ".token-*", "*.tfstate", "*.tfvars",
)
CARPETAS_SENSIBLES = (".git", ".ssh", ".aws", ".azure", ".gnupg", ".docker", ".kube")
REGLAS_LECTURA_NEGADAS = tuple(f"Read(**/{p})" for p in (".env", ".env.*", "*.pem", "*.key", "*.pfx",
                                                           "appsettings*.json", "secrets.json", ".git-credentials",
                                                           ".token", ".git/**"))

_PARAMS_RUTA = {"Read": ("file_path",), "Edit": ("file_path",), "Write": ("file_path",),
                "MultiEdit": ("file_path",), "NotebookEdit": ("notebook_path",), "Grep": ("path",), "Glob": ("path",)}
_PARAMS_PATRON = {"Grep": ("glob",), "Glob": ("pattern",)}
_ABSOLUTA = re.compile(r"^([a-zA-Z]:|[\\/]{1,2}|~)")
_UNIDAD_O_UNC = re.compile(r"^([a-zA-Z]:|//)")
_ES_WINDOWS = os.name == "nt"


def herramientas(modo: str, permite_webfetch: bool = False) -> tuple[str, ...]:
    base = HERRAMIENTAS[modo]
    return base + ("WebFetch",) if (modo == "lectura" and permite_webfetch) else base


def prohibidas(modo: str, permite_webfetch: bool = False) -> list[str]:
    salida = list(PROHIBIDAS_SIEMPRE)
    if modo == "lectura":
        salida += list(ESCRITURA)
    else:
        salida.append("MultiEdit")
    if not (modo == "lectura" and permite_webfetch):
        salida.append("WebFetch")
    return salida + list(REGLAS_LECTURA_NEGADAS)


def es_sensible(ruta: Path) -> bool:
    partes = [p.lower() for p in ruta.parts]
    if any(p in CARPETAS_SENSIBLES for p in partes[:-1]) or (partes and partes[-1] in CARPETAS_SENSIBLES):
        return True
    nombre = partes[-1] if partes else ""
    return any(fnmatch.fnmatch(nombre, p) for p in SENSIBLES)


def _ruta_insegura(ruta: str) -> bool:
    """Chequeo léxico independiente del SO: la barra invertida es separador en cualquier plataforma.

    Niega cualquier componente `..` y, fuera de Windows, las formas que solo existen en Windows (letra de unidad,
    UNC, raíz con barra invertida): en POSIX serían relativas y pasarían la comprobación de contención.
    """
    norm = ruta.replace("\\", "/")
    if ".." in norm.split("/"):
        return True
    return not _ES_WINDOWS and (bool(_UNIDAD_O_UNC.match(norm)) or ruta.startswith("\\"))


def dentro_de(ruta: str, carpeta: Path) -> Path | None:
    """Resuelve la ruta (relativa a la carpeta del proyecto) siguiendo enlaces; None si queda fuera."""
    p = Path(ruta)
    if not p.is_absolute():
        p = carpeta / p
    real = Path(os.path.realpath(p))
    base = os.path.normcase(os.path.realpath(carpeta))
    try:
        if os.path.commonpath([os.path.normcase(str(real)), base]) != base:
            return None
    except ValueError:  # otra unidad
        return None
    return real


def _patron_peligroso(patron: str) -> bool:
    bajo = patron.replace("\\", "/").lower()
    if _ABSOLUTA.match(bajo) or ".." in bajo.split("/"):
        return True
    return any(s in bajo for s in (".env", ".pem", ".key", "id_rsa", "appsettings", ".git/", "secrets",
                                   "credentials", ".token", ".ssh", ".aws"))


def decidir(herramienta: str, entrada: dict, modo: str, carpeta: Path, permite_webfetch: bool = False) -> tuple[bool, str]:
    """Decisión pura (sin E/S salvo realpath) que usa el hook; probada sin red en pruebas/test_permisos.py."""
    if modo not in HERRAMIENTAS:
        return False, "modo desconocido"
    if herramienta not in herramientas(modo, permite_webfetch):
        return False, f"{herramienta} no está permitida en modo {modo}"
    entrada = entrada if isinstance(entrada, dict) else {}
    if herramienta == "WebFetch":
        url = str(entrada.get("url", ""))
        return (url.startswith("https://"), "solo https" if not url.startswith("https://") else "ok")
    for param in _PARAMS_RUTA.get(herramienta, ()):
        valor = entrada.get(param)
        if valor in (None, ""):
            if herramienta in ("Grep", "Glob"):
                continue  # sin ruta = carpeta de trabajo (el proyecto)
            return False, f"falta {param}"
        if not isinstance(valor, str):
            return False, f"{param} inválido"
        real = None if _ruta_insegura(valor) else dentro_de(valor, carpeta)
        if real is None:
            return False, "ruta fuera de la carpeta del proyecto"
        if es_sensible(real):
            return False, "archivo sensible (secretos/credenciales/.git): no se lee ni se escribe"
    for param in _PARAMS_PATRON.get(herramienta, ()):
        valor = entrada.get(param)
        if isinstance(valor, str) and _patron_peligroso(valor):
            return False, f"patrón no permitido en {param}"
    return True, "ok"


def crear_guardian(modo: str, carpeta: Path, permite_webfetch: bool, bitacora: list | None = None):
    """Hook PreToolUse (firma documentada: input_data, tool_use_id, context)."""

    async def guardian(input_data, tool_use_id, context):
        nombre = input_data.get("tool_name", "")
        ok, motivo = decidir(nombre, input_data.get("tool_input") or {}, modo, carpeta, permite_webfetch)
        if bitacora is not None:
            bitacora.append({"herramienta": nombre, "permitida": ok, "motivo": motivo})
        return {"hookSpecificOutput": {"hookEventName": input_data.get("hook_event_name", "PreToolUse"),
                                       "permissionDecision": "allow" if ok else "deny",
                                       "permissionDecisionReason": f"Orquestador ({modo}): {motivo}"}}

    return guardian


def argumentos(modo: str, carpeta: Path, ajustes, resume: str | None, guardian) -> dict:
    """Argumentos de ClaudeAgentOptions (solo campos verificados en la referencia oficial del SDK de Python)."""
    if modo not in HERRAMIENTAS:
        raise ValueError("modo desconocido")
    web = ajustes.lectura_permite_webfetch
    return {
        "cwd": str(carpeta),
        "resume": resume,
        "tools": list(herramientas(modo, web)),
        "allowed_tools": [],  # la aprobación la da el hook, con chequeo de rutas; un 'Read' desnudo aprobaría todo
        "disallowed_tools": prohibidas(modo, web),
        "permission_mode": "dontAsk",
        "strict_mcp_config": True,
        "mcp_servers": {},
        "setting_sources": ["project", "local"],
        "max_turns": ajustes.max_turnos,
        "max_budget_usd": ajustes.presupuesto_usd.get(modo),
        "model": ajustes.modelo,
        "env": {"CLAUDE_AGENT_SDK_CLIENT_APP": "orquestador-local/1"},
        "hooks_guardian": guardian,
    }
