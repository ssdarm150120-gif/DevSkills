"""Exporta una sesión de Claude Code (archivo JSONL) a Markdown legible.

Uso:  python documentacion/analisis/exportar_sesion.py <sesion.jsonl | --ultima> <salida.md> "<título>"

Con `--ultima` usa la sesión más reciente del proyecto actual: busca en `~/.claude/projects/` la
carpeta que Claude Code crea para el directorio de trabajo (la ruta con cada carácter que no es letra,
número ni guion cambiado por `-`) y toma el `.jsonl` modificado más recientemente.
La salida va en `documentacion/sesiones/AAAA-MM-DD_<tema>.md`.

Incluye los mensajes del usuario, las respuestas del asistente y los reportes de los agentes.
Omite las salidas de herramientas, los avisos internos del sistema y el razonamiento interno.
Las horas quedan en UTC, como vienen en el archivo de la sesión.
Antes de versionar el resultado conviene revisarlo con gitleaks.
"""
import json
import pathlib
import re
import sys

RECORDATORIO = re.compile(r"<system-reminder[^>]*>.*?</system-reminder[^>]*>", re.S)
NOTIFICACION = re.compile(r"<task-notification>.*?</task-notification>", re.S)
COMANDO_LOCAL = re.compile(r"<(local-command-[a-z]+|command-[a-z]+)>.*?</\1>", re.S)
PEGADO = re.compile(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>", re.S)
AGENTE = re.compile(r"<agent-message[^>]*>(.*?)</agent-message>", re.S)
MARCO_AGENTE = re.compile(r"^\s*\[Subagent hand-back\].*?follows:\s*", re.S)
AVISO_SISTEMA = re.compile(r"\[SYSTEM NOTIFICATION - NOT USER INPUT\].*?(?=\n\n|\Z)", re.S)


def limpiar(texto: str) -> str:
    """Quita los bloques internos y deja el contenido pegado como bloque de código."""
    for patron in (RECORDATORIO, NOTIFICACION, COMANDO_LOCAL, AVISO_SISTEMA):
        texto = patron.sub("", texto)
    texto = PEGADO.sub(lambda m: "\n```\n" + m.group(1).strip() + "\n```\n", texto)
    return texto.strip()


def texto_de(mensaje: dict) -> str:
    contenido = mensaje.get("content")
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return "\n".join(
            b.get("text", "") for b in contenido if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def exportar(entrada: pathlib.Path, salida: pathlib.Path, titulo: str) -> int:
    bloques = [
        f"# {titulo}\n",
        f"Exportado de `{entrada.name}`. Sin salidas de herramientas ni avisos internos. Horas en UTC.\n",
    ]
    with entrada.open(encoding="utf-8") as lineas:
        for linea in lineas:
            try:
                dato = json.loads(linea)
            except json.JSONDecodeError:
                continue
            tipo = dato.get("type")
            if tipo not in ("user", "assistant"):
                continue
            crudo = texto_de(dato.get("message", {}))
            hora = (dato.get("timestamp") or "")[:16].replace("T", " ")
            if tipo == "user":
                for reporte in AGENTE.findall(crudo):
                    cuerpo = MARCO_AGENTE.sub("", reporte)
                    cuerpo = "\n".join(
                        r[2:] if r.startswith("  ") else r for r in cuerpo.splitlines()
                    )
                    bloques.append(f"\n---\n\n### 🤖 Reporte de agente · {hora}\n\n{cuerpo.strip()}\n")
                propio = limpiar(AGENTE.sub("", crudo))
                propio = re.sub(
                    r"(Another Claude session sent a message( while you were working)?:|"
                    r"That \"other Claude session\".*)",
                    "",
                    propio,
                    flags=re.S,
                ).strip()
                if propio and not propio.startswith("Caveat:"):
                    bloques.append(f"\n---\n\n### 👤 Usuario · {hora}\n\n{propio}\n")
            else:
                propio = limpiar(crudo)
                if propio:
                    bloques.append(f"\n### 🧭 Claude · {hora}\n\n{propio}\n")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("".join(bloques), encoding="utf-8", newline="\n")
    return len(bloques) - 2


def sesion_mas_reciente(directorio: pathlib.Path) -> pathlib.Path:
    """El .jsonl más reciente de la carpeta de Claude Code que corresponde a `directorio`."""
    raiz = pathlib.Path.home() / ".claude" / "projects"
    clave = re.sub(r"[^A-Za-z0-9-]", "-", str(directorio.resolve())).lower()
    candidatas = [d for d in raiz.iterdir() if d.is_dir() and d.name.lower() == clave] if raiz.exists() else []
    sesiones = [f for d in candidatas for f in d.glob("*.jsonl")]
    if not sesiones:
        sys.exit(f"No encontré sesiones de Claude Code para {directorio} en {raiz}")
    return max(sesiones, key=lambda f: f.stat().st_mtime)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    origen = sesion_mas_reciente(pathlib.Path.cwd()) if sys.argv[1] == "--ultima" else pathlib.Path(sys.argv[1])
    total = exportar(origen, pathlib.Path(sys.argv[2]), sys.argv[3])
    print(f"{sys.argv[2]}: {total} bloques")
