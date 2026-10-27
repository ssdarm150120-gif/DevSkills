"""
Envoltura del PreToolUse de Graphify para Claude Code (Bash|Grep y Read|Glob), en Python.

Debe ser Python y no un script de bash: en Windows, un hook de bash lanza un bash.exe extra en CADA llamada a
herramienta de cada sesión y subagente, y con muchas llamadas en paralelo la capa MSYS de Git Bash falla con
"add_item (...) failed, errno 1". Solo invoca `graphify hook-guard <search|read>` si el proyecto tiene grafo.
Nunca bloquea: siempre sale con 0. stdin y stdout se heredan tal cual hacia graphify.
Desactivar: GRAPHIFY_GUARDIA=0, o crear el archivo DESACTIVADO junto a este script.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def localizar_graphify():
    """graphify del PATH o, si no, el de ~/.local/bin (uv/pipx); en Windows lleva .exe. None si no está."""
    encontrado = shutil.which("graphify")
    if encontrado:
        return Path(encontrado)
    exe = Path.home() / ".local" / "bin" / ("graphify.exe" if os.name == "nt" else "graphify")
    return exe if exe.is_file() else None


def main():
    if os.environ.get("GRAPHIFY_GUARDIA", "1") == "0":
        return
    if (Path(__file__).resolve().parent / "DESACTIVADO").exists():
        return
    proyecto = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    if not (proyecto / "graphify-out" / "graph.json").is_file():
        return
    exe = localizar_graphify()
    if exe is None:
        return
    modo = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("search", "read") else "search"
    try:
        subprocess.run([str(exe), "hook-guard", modo], cwd=str(proyecto), stderr=subprocess.DEVNULL, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        pass


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
