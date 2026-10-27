"""Engancha el motor de DevSkills a Claude Code en ESTE equipo: status line de límites y, si no usas el plugin,
los hooks de Graphify. Lo invoca ``devskills motor enganchar``.

Escribe en el ``settings.json`` de usuario de Claude Code (``CLAUDE_CONFIG_DIR`` si existe; si no, ``~/.claude``)
con rutas calculadas aquí mismo, hacia la copia de DevSkills desde la que se ejecuta este script, y con el
intérprete de Python que lo está ejecutando. Así nada queda atado a las carpetas de otro equipo.

Garantías:
  * mezcla (merge) sin perder ninguna otra clave del archivo; si el JSON no se puede leer, no toca nada;
  * muestra el diff y pide confirmación (``--si`` sin terminal);
  * respaldo ``settings.json.bak-<fecha>`` antes de escribir; si no hay cambios, no escribe ni respalda (idempotente);
  * no pisa una status line ajena salvo con ``--envolver`` o confirmación explícita;
  * ``--quitar`` solo quita lo que puso este script (y devuelve la status line envuelta, si la había);
  * detecta hooks viejos pegados a mano (``sesion_inicio.py``, ``hook_guard.py``) y ofrece quitarlos cuando el
    plugin ya los trae.

Solo biblioteca estándar.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import rutas  # noqa: E402

MOTOR = Path(__file__).resolve().parent.parent
SCRIPT_STATUSLINE = "statusline_limites.py"
SCRIPTS_HOOKS = ("sesion_inicio.py", "hook_guard.py")
REFRESCO_STATUSLINE = 60
_RE_ENVOLVER = re.compile(r"""--envolver\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^']|'\\'')*)'|(\S+))""")
_RE_SEGURO = re.compile(r"^[A-Za-z0-9_./:@%+=,-]+$")


class Rechazo(Exception):
    """Algo impide continuar sin cambiar nada (mensaje para la persona)."""


# ------------------------------------------------------------------ cálculo de rutas e intérprete

def _mismo_archivo(a, b) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def interprete() -> str:
    """Comando de Python para escribir en settings.json: el nombre corto (python/python3) si en el PATH de esta
    máquina resuelve al mismo intérprete que está corriendo; si no, su ruta absoluta con barras normales."""
    actual = Path(sys.executable)
    nombres = ("python", "python3") if os.name == "nt" else ("python3", "python")
    for nombre in nombres:
        encontrado = shutil.which(nombre)
        if encontrado and _mismo_archivo(encontrado, actual):
            return nombre
    return actual.as_posix()


def ruta_script(subcarpeta: str, nombre: str) -> str:
    return (MOTOR / subcarpeta / nombre).as_posix()


def comillas(texto: str) -> str:
    """Cita un argumento para el shell de las status lines (sh o Git Bash)."""
    if _RE_SEGURO.match(texto):
        return texto
    if not re.search(r'[$"`\\!]', texto):
        return f'"{texto}"'
    return "'" + texto.replace("'", "'\\''") + "'"


def comando_statusline(envuelto: str | None) -> str:
    cmd = f"{comillas(interprete())} {comillas(ruta_script('panel', SCRIPT_STATUSLINE))}"
    if envuelto:
        cmd += " --envolver '" + envuelto.replace("'", "'\\''") + "'"
    return cmd


def manejadores_hooks() -> list[tuple[str, str | None, dict]]:
    """(evento, matcher, manejador) de los hooks de Graphify en forma sin shell (command + args)."""
    py = interprete()
    guardia = ruta_script("graphify", "hook_guard.py")
    return [
        ("SessionStart", None, {"type": "command", "command": py,
                                "args": [ruta_script("graphify", "sesion_inicio.py")]}),
        ("PreToolUse", "Bash|Grep", {"type": "command", "command": py, "args": [guardia, "search"]}),
        ("PreToolUse", "Read|Glob", {"type": "command", "command": py, "args": [guardia, "read"]}),
    ]


# ------------------------------------------------------------------ lectura de settings.json

def leer_settings(ruta: Path) -> dict:
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise Rechazo(f"No pude leer {ruta} como JSON ({e}). No cambié nada; arréglalo a mano.")
    if not isinstance(datos, dict):
        raise Rechazo(f"{ruta} no es un objeto JSON. No cambié nada.")
    return datos


def plugin_activo(config: Path, settings: dict) -> bool:
    """¿Está habilitado el plugin devskills? Se mira enabledPlugins del settings; sin esa clave, plugins instalados."""
    habilitados = settings.get("enabledPlugins")
    if isinstance(habilitados, dict):
        for clave, valor in habilitados.items():
            if isinstance(clave, str) and clave.startswith("devskills@"):
                return valor is not False
    try:
        instalados = json.loads((config / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        plugins = instalados.get("plugins", {}) if isinstance(instalados, dict) else {}
        return any(isinstance(k, str) and k.startswith("devskills@") for k in plugins)
    except (OSError, ValueError):
        return False


# ------------------------------------------------------------------ hooks

def _texto(manejador) -> str:
    if not isinstance(manejador, dict):
        return ""
    args = manejador.get("args")
    return " ".join([str(manejador.get("command", "")), *(str(a) for a in args)] if isinstance(args, list)
                    else [str(manejador.get("command", ""))])


def _es_de_graphify(manejador) -> bool:
    texto = _texto(manejador).replace("\\", "/")
    return any(re.search(rf"(^|/|\s){re.escape(n)}(\s|$)", texto) for n in SCRIPTS_HOOKS)


def _es_gestionado(manejador) -> bool:
    return _es_de_graphify(manejador) and isinstance(manejador, dict) and isinstance(manejador.get("args"), list)


def hooks_encontrados(settings: dict) -> list[tuple[str, dict]]:
    """[(evento, manejador)] de los hooks de Graphify presentes en el settings."""
    hallados = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return hallados
    for evento, grupos in hooks.items():
        for grupo in grupos if isinstance(grupos, list) else []:
            for m in grupo.get("hooks", []) if isinstance(grupo, dict) else []:
                if _es_de_graphify(m):
                    hallados.append((evento, m))
    return hallados


def quitar_hooks(settings: dict, solo_gestionados: bool) -> int:
    """Quita los hooks de Graphify (todos, o solo los gestionados por este script). Limpia lo que quede vacío."""
    quitados = 0
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    for evento in list(hooks):
        grupos = hooks[evento]
        if not isinstance(grupos, list):
            continue
        nuevos = []
        for grupo in grupos:
            if isinstance(grupo, dict) and isinstance(grupo.get("hooks"), list):
                antes = len(grupo["hooks"])
                grupo["hooks"] = [m for m in grupo["hooks"]
                                  if not (_es_de_graphify(m) and (_es_gestionado(m) or not solo_gestionados))]
                quitados += antes - len(grupo["hooks"])
                if not grupo["hooks"]:
                    continue
            nuevos.append(grupo)
        if nuevos:
            hooks[evento] = nuevos
        else:
            del hooks[evento]
    if not hooks:
        del settings["hooks"]
    return quitados


def poner_hooks(settings: dict) -> bool:
    """Deja exactamente los tres hooks gestionados (y ningún otro de Graphify). False si ya estaban tal cual."""
    esperados = manejadores_hooks()
    actuales = hooks_encontrados(settings)
    if len(actuales) == len(esperados) and all(
        _es_gestionado(m) for _, m in actuales
    ) and sorted(json.dumps(m, sort_keys=True) for _, m in actuales) == sorted(
        json.dumps(m, sort_keys=True) for _, _, m in esperados
    ):
        return False
    quitar_hooks(settings, solo_gestionados=False)
    hooks = settings.setdefault("hooks", {})
    for evento, matcher, manejador in esperados:
        grupo: dict = {"matcher": matcher} if matcher else {}
        grupo["hooks"] = [manejador]
        hooks.setdefault(evento, []).append(grupo)
    return True


# ------------------------------------------------------------------ status line

def es_propia(statusline) -> bool:
    return isinstance(statusline, dict) and SCRIPT_STATUSLINE in str(statusline.get("command", ""))


def envuelto_de(statusline) -> str | None:
    """Comando ajeno que la status line propia ya trae envuelto con --envolver."""
    m = _RE_ENVOLVER.search(str(statusline.get("command", ""))) if isinstance(statusline, dict) else None
    if not m:
        return None
    if m.group(1) is not None:
        return re.sub(r'\\(["\\])', r"\1", m.group(1))
    return m.group(2).replace("'\\''", "'") if m.group(2) is not None else m.group(3)


def poner_statusline(settings: dict, envolver: str | None, preguntar) -> str:
    """Pone la status line propia. ``preguntar(actual_cmd)`` decide qué hacer con una ajena sin --envolver:
    devuelve 'envolver', 'reemplazar' o 'no'. Devuelve un texto que describe lo hecho."""
    actual = settings.get("statusLine")
    envuelto = envolver
    descripcion = "status line de límites"
    if actual is not None and not es_propia(actual):
        cmd_ajeno = str(actual.get("command", "")) if isinstance(actual, dict) else ""
        if envolver is None:
            decision = preguntar(cmd_ajeno)
            if decision == "envolver" and cmd_ajeno:
                envuelto = cmd_ajeno
                descripcion = "status line de límites (envolviendo la tuya)"
            elif decision != "reemplazar":
                raise Rechazo("Ya tienes otra status line y no la voy a pisar. Para conservarla, repite con "
                              "--envolver \"<tu comando>\" (se muestra antes de los límites).")
    elif es_propia(actual) and envolver is None:
        envuelto = envuelto_de(actual)
    nueva = dict(actual) if isinstance(actual, dict) else {}
    nueva["type"] = "command"
    nueva["command"] = comando_statusline(envuelto)
    if not isinstance(nueva.get("refreshInterval"), int):
        nueva["refreshInterval"] = REFRESCO_STATUSLINE
    settings["statusLine"] = nueva
    return descripcion


def quitar_statusline(settings: dict) -> str | None:
    actual = settings.get("statusLine")
    if not es_propia(actual):
        return None
    envuelto = envuelto_de(actual)
    if envuelto:
        restaurada = {k: v for k, v in actual.items() if k != "refreshInterval" or v != REFRESCO_STATUSLINE}
        restaurada["command"] = envuelto
        settings["statusLine"] = restaurada
        return "status line de límites (devolví la tuya original)"
    del settings["statusLine"]
    return "status line de límites"


# ------------------------------------------------------------------ escritura

def diferencias(antes: dict, despues: dict) -> str:
    a = json.dumps(antes, indent=2, ensure_ascii=False).splitlines()
    b = json.dumps(despues, indent=2, ensure_ascii=False).splitlines()
    return "\n".join(difflib.unified_diff(a, b, "settings.json (actual)", "settings.json (nuevo)", lineterm="", n=2))


def respaldar(ruta: Path) -> Path:
    base = f"{ruta.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    destino = ruta.with_name(base)
    contador = 1
    while destino.exists():
        destino = ruta.with_name(f"{base}-{contador}")
        contador += 1
    shutil.copy2(ruta, destino)
    return destino


def escribir_atomico(ruta: Path, datos: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f"{ruta.name}.{os.getpid()}.tmp")
    try:
        temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporal, ruta)
    finally:
        try:
            temporal.unlink()
        except OSError:
            pass


def preguntar_texto(pregunta: str) -> str:
    """input() que trata el fin de la entrada como falta de terminal (en Windows, NUL se reporta como tty)."""
    try:
        return input(pregunta).strip().lower()
    except EOFError:
        raise Rechazo("Sin terminal no cambio nada. Revisa el diff y repite con --si.")


def con_terminal() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


# ------------------------------------------------------------------ programa

def procesar(a: argparse.Namespace) -> int:
    config = Path(a.config).expanduser() if a.config else rutas.claude_dir()
    ruta = config / "settings.json"
    actual = leer_settings(ruta)
    nuevo = copy.deepcopy(actual)
    hechos: list[str] = []
    avisos: list[str] = []
    interactivo = con_terminal() and not a.si

    def preguntar(cmd_ajeno: str) -> str:
        if not interactivo:
            return "no"
        print(f"Ya tienes una status line: {cmd_ajeno or '(sin comando)'}")
        r = preguntar_texto("¿La envuelvo para conservarla (e), la reemplazo (r) o no toco nada (N)? [e/r/N]: ")
        return {"e": "envolver", "r": "reemplazar"}.get(r, "no")

    plugin = plugin_activo(config, actual)
    if a.quitar:
        d = quitar_statusline(nuevo)
        if d:
            hechos.append(f"quito la {d}")
        elif "statusLine" in actual:
            avisos.append("La status line del settings no es la de DevSkills; no la toco.")
        n = quitar_hooks(nuevo, solo_gestionados=not a.limpiar_hooks)
        if n:
            hechos.append(f"quito {n} hook(s) de Graphify" + ("" if a.limpiar_hooks else " puestos por este comando"))
        elif hooks_encontrados(actual):
            avisos.append("Hay hooks de Graphify pegados a mano; con --limpiar-hooks también los quito.")
    else:
        hechos.append(poner_statusline(nuevo, a.envolver, preguntar))
        hechos[-1] = "pongo la " + hechos[-1]
        if a.hooks:
            if plugin:
                raise Rechazo("El plugin devskills ya está habilitado y trae los hooks de Graphify: --hooks los "
                              "duplicaría. Si no quieres el plugin, deshabilítalo primero.")
            if poner_hooks(nuevo):
                hechos.append("pongo los hooks de Graphify (sin shell, con el Python de este equipo)")
        else:
            viejos = hooks_encontrados(nuevo)
            if viejos and (plugin or a.limpiar_hooks):
                n = quitar_hooks(nuevo, solo_gestionados=False)
                hechos.append(f"quito {n} hook(s) viejo(s) de Graphify, que ahora trae el plugin")
            elif viejos:
                avisos.append(f"Hay {len(viejos)} hook(s) de Graphify pegados a mano y no detecto el plugin devskills "
                              "habilitado: no los toco. Con el plugin ya no hacen falta (quedarían duplicados); sin "
                              "el plugin, 'devskills motor enganchar --hooks' los reescribe con rutas de este equipo.")

    if not a.quitar and re.search(r"/plugins/(cache|marketplaces)/", MOTOR.as_posix()):
        avisos.append("Estás corriendo esto desde la carpeta de plugins de Claude Code: su ruta cambia al actualizar el "
                      "plugin. Para una ruta estable instala el CLI (bash install.sh) y corre 'devskills motor enganchar' "
                      "desde ahí, o repite este comando después de cada actualización.")
    for texto in avisos:
        print(f"Aviso: {texto}")
    if nuevo == actual:
        print(f"Sin cambios: {ruta} ya está como corresponde.")
        return 0

    print(f"Archivo: {ruta}")
    print(diferencias(actual, nuevo))
    print("")
    print("Voy a: " + "; ".join(hechos) + ".")
    if not a.si:
        if not interactivo:
            raise Rechazo("Sin terminal no cambio nada. Revisa el diff y repite con --si.")
        if preguntar_texto("¿Aplicar estos cambios? (s/N): ") != "s":
            print("Cancelado; no cambié nada.")
            return 0
    if ruta.exists():
        print(f"Respaldo: {respaldar(ruta)}")
    escribir_atomico(ruta, nuevo)
    print(f"Listo: actualicé {ruta}. Reinicia Claude Code para que lo tome.")
    return 0


def main(argv: list[str]) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="devskills motor enganchar", description=__doc__.split("\n\n")[0])
    p.add_argument("--quitar", action="store_true", help="quita lo que puso este comando")
    p.add_argument("--si", action="store_true", help="aplica sin preguntar (obligatorio sin terminal)")
    p.add_argument("--envolver", metavar="CMD", help="conserva esta status line ajena y muestra sus datos antes")
    p.add_argument("--hooks", action="store_true", help="escribe también los hooks de Graphify (solo si NO usas el plugin)")
    p.add_argument("--limpiar-hooks", action="store_true", help="quita los hooks viejos de Graphify aunque no detecte el plugin")
    p.add_argument("--config", metavar="DIR", help="carpeta de configuración de Claude Code (por omisión CLAUDE_CONFIG_DIR o ~/.claude)")
    a = p.parse_args(argv)
    if a.envolver is not None and not a.envolver.strip():
        p.error("--envolver necesita el comando de tu status line.")
    if a.quitar and (a.envolver or a.hooks):
        p.error("--quitar no se combina con --envolver ni con --hooks.")
    try:
        return procesar(a)
    except Rechazo as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
