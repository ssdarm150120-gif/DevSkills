"""Rutas del motor de DevSkills: dónde vive el ESTADO (fuera del repositorio) y dónde vive el CÓDIGO.

El estado (registro de proyectos, preferencias, tokens, historiales, logs, entornos virtuales) vive en el
directorio de datos, que se resuelve en este orden:

  1. la variable de entorno DEVSKILLS_DATOS, si existe y no está vacía;
  2. ``~/.devskills``.

Nota: la variable se llama DEVSKILLS_DATOS y no DEVSKILLS_HOME porque ``bin/devskills`` ya usa DEVSKILLS_HOME
para la carpeta de la CARGA ÚTIL (el clon o la copia instalada con plantillas y skills). Reutilizarla para los
datos rompería ``devskills init`` y ``devskills update`` cuando alguien la define.

Solo biblioteca estándar. Todas las funciones leen el entorno en cada llamada (las pruebas lo cambian).
"""
from __future__ import annotations

import os
from pathlib import Path

VARIABLE_DATOS = "DEVSKILLS_DATOS"
PUERTO_PANEL = 18950

# motor/ (esta carpeta es motor/comun/)
CODIGO = Path(__file__).resolve().parent.parent


def datos() -> Path:
    """Directorio de datos del motor (no se crea aquí; quien escribe crea lo que necesita)."""
    valor = os.environ.get(VARIABLE_DATOS, "").strip()
    if valor:
        return Path(os.path.expandvars(os.path.expanduser(valor))).resolve()
    return Path.home() / ".devskills"


def claude_dir() -> Path:
    """Carpeta de configuración de Claude Code: CLAUDE_CONFIG_DIR si existe y no está vacía; si no, ``~/.claude``."""
    valor = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    if valor:
        return Path(os.path.expandvars(os.path.expanduser(valor))).resolve()
    return Path.home() / ".claude"


def claude_json() -> Path:
    """Archivo ``.claude.json`` de Claude Code: dentro de CLAUDE_CONFIG_DIR si está definida; si no, ``~/.claude.json``."""
    if os.environ.get("CLAUDE_CONFIG_DIR", "").strip():
        return claude_dir() / ".claude.json"
    return Path.home() / ".claude.json"


def registro() -> Path:
    return datos() / "proyectos.json"


def plantilla_registro() -> Path:
    return CODIGO / "plantillas" / "proyectos.ejemplo.json"


def laboratorio() -> Path:
    return datos() / "laboratorio"


def _sufijo(puerto: int | None, base: str, ext: str = "") -> str:
    """Nombre de archivo o carpeta del panel: el del puerto por omisión, o con el puerto para otras instancias,
    de modo que una instancia de prueba nunca pise el estado de la principal."""
    if puerto is None or puerto == PUERTO_PANEL:
        return f"{base}{ext}"
    return f"{base}-{puerto}{ext}"


def preferencias(puerto: int | None = None) -> Path:
    return datos() / _sufijo(puerto, "preferencias", ".json")


def panel_dir() -> Path:
    return datos() / "panel"


def panel_estado(puerto: int | None = None) -> Path:
    return panel_dir() / _sufijo(puerto, "estado")


def panel_token(puerto: int | None = None) -> Path:
    return panel_dir() / _sufijo(puerto, ".token")


def panel_log() -> Path:
    return panel_dir() / "panel.log"


def orquestador_dir() -> Path:
    return datos() / "orquestador"


def orquestador_token() -> Path:
    return orquestador_dir() / ".token"


def orquestador_historial() -> Path:
    return orquestador_dir() / "historial"


def orquestador_propuestas() -> Path:
    return orquestador_dir() / "propuestas"


def orquestador_fallos() -> Path:
    return orquestador_dir() / "enrutamiento-fallos.jsonl"


def orquestador_log() -> Path:
    return orquestador_dir() / "orquestador.log"


def orquestador_config() -> Path:
    return orquestador_dir() / "config.json"


def orquestador_config_defecto() -> Path:
    return CODIGO / "orquestador" / "config.defecto.json"


def orquestador_venv() -> Path:
    return orquestador_dir() / ".venv"


def servicios_dir() -> Path:
    return datos() / "servicios"


def servicios_logs() -> Path:
    return servicios_dir() / "logs"


def servicios_pids() -> Path:
    return servicios_dir() / "pids"


def python_del_venv(venv: Path) -> Path:
    """Intérprete dentro de un venv, según el sistema operativo."""
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def opciones_desacoplado() -> dict:
    """Argumentos de subprocess.Popen para lanzar un proceso que sobreviva a quien lo lanza, sin consola."""
    if os.name == "nt":
        import subprocess
        return {"creationflags": 0x00000008 | 0x00000200 | getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {"start_new_session": True}


def restringir(ruta: Path) -> None:
    """Deja el archivo legible solo por su dueño (en Windows el chmod apenas aplica; no falla)."""
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass
