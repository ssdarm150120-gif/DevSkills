"""Hook SessionStart de Claude Code: resumen breve del grafo de Graphify.

Si el proyecto de la sesión tiene graphify-out/GRAPH_REPORT.md, inyecta en el
contexto un resumen corto (tamaño, comunidades principales, nodos centrales y
cómo consultarlo) y avisa si el grafo quedó atrás de git. No llama a ningún LLM
y nunca bloquea: ante cualquier error sale en silencio con código 0.

Variables de entorno:
    GRAPHIFY_SESION=0              desactiva este hook (no imprime nada).
    GRAPHIFY_SESION_AUTOUPDATE=1   si el grafo está desactualizado, lanza
                                   `graphify update .` en segundo plano (cero
                                   tokens). Ojo: modifica graphify-out/, que
                                   está versionado. Por omisión solo avisa.
    GRAPHIFY_SESION_MAX=1800       límite de caracteres del resumen.

Se desactiva también creando el archivo DESACTIVADO junto a este script.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

def _ejecutable_graphify() -> Path:
    """graphify del PATH o, si no, el de ~/.local/bin (uv/pipx); en Windows lleva .exe."""
    encontrado = shutil.which("graphify")
    if encontrado:
        return Path(encontrado)
    return Path.home() / ".local" / "bin" / ("graphify.exe" if os.name == "nt" else "graphify")


GRAPHIFY = _ejecutable_graphify()


def _git(raiz: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(raiz), *args],
            capture_output=True, text=True, timeout=4,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _seccion(texto: str, titulo: str, maximo: int) -> list[str]:
    m = re.search(rf"^## {re.escape(titulo)}[^\n]*\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    if not m:
        return []
    lineas = [l.rstrip() for l in m.group(1).splitlines() if l.strip().startswith(("-", "1", "2", "3", "4", "5", "6", "7", "8", "9"))]
    return lineas[:maximo]


def _frescura(raiz: Path, grafo: Path) -> tuple[str, bool]:
    """Devuelve (mensaje, desactualizado)."""
    if _git(raiz, "rev-parse", "--is-inside-work-tree") != "true":
        return "Carpeta sin git: si cambiaste código, actualiza con `graphify update .`.", False
    try:
        with grafo.open(encoding="utf-8") as fh:
            datos = json.load(fh)
        base = str(datos.get("built_at_commit") or "")
    except (OSError, ValueError):
        base = ""
    if not base or _git(raiz, "cat-file", "-e", base + "^{commit}") is None:
        return "No se pudo ubicar el commit con el que se generó el grafo; si dudas, `graphify update .`.", False
    cambios = _git(
        raiz, "diff", "--name-only", base, "HEAD", "--", ".",
        ":(exclude)graphify-out", ":(exclude).gitignore", ":(exclude).gitattributes",
        ":(exclude).graphifyignore",
    )
    if cambios is None:
        return "", False
    n = len([c for c in cambios.splitlines() if c.strip()])
    if n == 0:
        return f"Grafo al día con git (generado en {base[:8]}).", False
    return (
        f"AVISO: el grafo se generó en {base[:8]} y desde entonces cambiaron {n} archivo(s) "
        "en git; sus respuestas pueden estar desfasadas. Actualízalo con `graphify update .` "
        "(sin LLM, cero tokens) y versiona graphify-out/graph.json y GRAPH_REPORT.md.",
        True,
    )


def _actualizar_en_segundo_plano(raiz: Path) -> bool:
    if not GRAPHIFY.exists():
        return False
    try:
        extra: dict = {"start_new_session": True}
        if sys.platform == "win32":
            extra = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                     | subprocess.CREATE_NO_WINDOW}
        log = (raiz / "graphify-out" / "actualizacion_sesion.log").open("w", encoding="utf-8")
        subprocess.Popen(
            [str(GRAPHIFY), "update", "."],
            cwd=str(raiz), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            close_fds=True, **extra,
            env={**os.environ, "GRAPHIFY_BACKEND": "none", "GRAPHIFY_NO_TIPS": "1", "GRAPHIFY_MAX_WORKERS": "4"},
        )
        return True
    except OSError:
        return False


def main() -> None:
    if os.environ.get("GRAPHIFY_SESION", "1") == "0" or (AQUI / "DESACTIVADO").exists():
        return
    try:
        evento = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        evento = {}
    raiz = Path(os.environ.get("CLAUDE_PROJECT_DIR") or evento.get("cwd") or os.getcwd())
    reporte = raiz / "graphify-out" / "GRAPH_REPORT.md"
    grafo = raiz / "graphify-out" / "graph.json"
    if not reporte.is_file() or not grafo.is_file():
        return
    texto = reporte.read_text(encoding="utf-8", errors="replace")
    resumen = _seccion(texto, "Summary", 1)
    hubs = _seccion(texto, "Community Hubs", 10)
    dioses = _seccion(texto, "God Nodes", 6)
    frescura, viejo = _frescura(raiz, grafo)

    partes = ["Graphify: este proyecto tiene un grafo de conocimiento del código en graphify-out/ (generado sin LLM)."]
    if resumen:
        partes.append("Tamaño: " + resumen[0].lstrip("- ").strip())
    if hubs:
        partes.append("Comunidades principales: " + "; ".join(h.lstrip("- ").strip() for h in hubs))
    if dioses:
        partes.append("Nodos más conectados: " + "; ".join(re.sub(r"^\d+\.\s*", "", d).strip() for d in dioses))
    partes.append(
        "Para preguntas sobre el código, antes de grep o leer archivos usa `graphify query \"<pregunta>\"`, "
        "`graphify explain \"<concepto>\"` o `graphify path \"<A>\" \"<B>\"`; GRAPH_REPORT.md solo para "
        "revisión de arquitectura completa."
    )
    if frescura:
        partes.append(frescura)
    if viejo and os.environ.get("GRAPHIFY_SESION_AUTOUPDATE") == "1" and _actualizar_en_segundo_plano(raiz):
        partes.append("Se lanzó `graphify update .` en segundo plano (bitácora: graphify-out/actualizacion_sesion.log).")

    maximo = int(os.environ.get("GRAPHIFY_SESION_MAX", "1800") or 1800)
    contexto = "\n".join(partes)
    if len(contexto) > maximo:
        contexto = contexto[: maximo - 1] + "…"
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": contexto}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
