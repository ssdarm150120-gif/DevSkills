"""Instrucciones repetidas del usuario → propuestas de agente, skill o comando de Claude Code, sin LLM.

1. Extracción: de los transcripts (`~/.claude/projects/*/*.jsonl`, solo el hilo principal) se toman los mensajes
   `type: user` escritos por el usuario: se excluyen tool_result, mensajes meta (recordatorios, salidas de
   comandos), resúmenes de compactación, notificaciones de tareas, comandos `/x`, sesiones creadas por un SDK y por
   el orquestador; se quita el contenido pegado (`<pasted_content>`, bloques de código) y se descartan los mensajes
   que siguen siendo largos (pegados) o demasiado cortos ("continúa", "sí"). Se suman las instrucciones del
   historial del orquestador. Por archivo se guarda una caché (tamaño + fecha) para no releer transcripts grandes.
2. Normalización: minúsculas, sin acentos, sin rutas/URLs/IDs/números, sin palabras vacías, raíz burda.
3. Agrupación determinista: vectores TF-IDF (raíces + bigramas), orden fijo (fecha, conversación) y agrupamiento por
   líder con centroide: cada instrucción entra al grupo más parecido si el coseno ≥ `umbral_similitud`; si no, abre
   uno nuevo. Mismo insumo → mismos grupos.
4. Propuesta si el grupo aparece ≥ `min_veces` o en ≥ `min_conversaciones` conversaciones. Alcance: "conversacion"
   (una sola conversación), "proyecto" (varias conversaciones de un proyecto) o "general" (varios proyectos).
5. Persistencia: `propuestas/<id>.json` con estado pendiente/aceptada/descartada. Un grupo que coincide con una
   propuesta existente (firmas de sus instrucciones) la actualiza; si ya estaba decidida no se reabre ni se duplica.
6. Tipo recomendado (reglas deterministas en `recomendar_tipo`): comando (atajo corto y casi idéntico), agente
   (delegar una tarea completa con herramientas propias) o skill (mismo procedimiento aplicado en la conversación).
   Cada propuesta trae los tres borradores, el recomendado, el porqué y un `mensaje` corto para el chat del panel.
7. Crear: escribe SOLO en `<raíz>/agents/<nombre>.md`, `<raíz>/skills/<nombre>/SKILL.md` o
   `<raíz>/commands/<nombre>.md`, con raíz `~/.claude` (general) o `<carpeta del proyecto>/.claude` (proyecto),
   creación exclusiva (nunca sobrescribe) y nombre `[a-z0-9-]`.
8. `version.json`: contador que sube con cada propuesta nueva, actualizada o decidida (el panel lo consulta barato).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import texto as tx
from .sesiones import carpetas_de

log = logging.getLogger("orquestador")

RE_ID_PROPUESTA = re.compile(r"^ag-[0-9a-f]{10}$")
RE_NOMBRE_AGENTE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){0,7}$")
ESTADOS = ("pendiente", "aceptada", "descartada")

_QUITAR = [re.compile(p, re.S | re.I) for p in (
    r"<system-reminder>.*?</system-reminder>", r"<pasted_content[^>]*>.*?(?:</pasted_content>|$)", r"```.*?(?:```|$)",
    r"(?m)^\s*(?:PS [A-Za-z]:\\[^>\n]*>|\$ ).*",  # desde un prompt de terminal pegado hasta el final (re.S)
    r"<command-[a-z]+>.*?</command-[a-z]+>", r"<local-command-[a-z]+>.*?</local-command-[a-z]+>",
    r"<bash-[a-z]+>.*?</bash-[a-z]+>", r"\[Image #\d+\]", r"\[Pasted text #\d+[^\]]*\]")]
_SIMBOLOS = frozenset(r"""[]{}()<>=|;\/_`"*#$&+~^""")
_CANAL = re.compile(r"^\s*<channel\b[^>]*>(.*)</channel>\s*$", re.S | re.I)
_PREFIJOS_IGNORADOS = ("<task-notification", "<command-", "<local-command", "<bash-", "caveat:", "<system-reminder",
                       "[request interrupted", "this session is being continued", "[orquestador local", "-- continue",
                       "<user-prompt-submit-hook", "<channel-permission")


# ---------------------------------------------------------------- extracción

def limpiar(texto: str, max_caracteres: int) -> str | None:
    """Texto escrito por el usuario sin lo pegado ni etiquetas; None si no es una instrucción útil."""
    t = (texto or "").strip()
    if m := _CANAL.match(t):  # mensajes de Telegram: <channel source="telegram" ...>texto</channel>
        t = m.group(1).strip()
    if t.lower().startswith(_PREFIJOS_IGNORADOS):
        return None
    for r in _QUITAR:
        t = r.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t or len(t) > max_caracteres:
        return None
    if len(t) > 80 and sum(c in _SIMBOLOS for c in t) / len(t) > 0.08:
        return None  # salida de terminal o código pegado sin etiqueta (muchos símbolos)
    return t


def _texto_de(contenido) -> str | None:
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        partes = [b.get("text", "") for b in contenido if isinstance(b, dict) and b.get("type") == "text"]
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in contenido):
            return None
        return " ".join(partes) if partes else None
    return None


def leer_transcript(ruta: Path, max_caracteres: int, min_palabras: int) -> dict:
    """{"entrypoint", "mensajes": [{uuid, ts, cwd, texto (enmascarado), normal}]} de un transcript."""
    salida = {"entrypoint": None, "mensajes": []}
    try:
        h = open(ruta, "rb")
    except OSError:
        return salida
    with h:
        for linea in h:
            if salida["entrypoint"] is None and b'"entrypoint"' in linea[:4000]:
                try:
                    salida["entrypoint"] = json.loads(linea).get("entrypoint")
                except ValueError:
                    pass
            if b'"type":"user"' not in linea and b'"type": "user"' not in linea:
                continue
            if b'"toolUseResult"' in linea or b'"isMeta":true' in linea or b'"isSidechain":true' in linea:
                continue
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain") or d.get("isCompactSummary") \
                    or d.get("toolUseResult") or d.get("isVisibleInTranscriptOnly"):
                continue
            crudo = _texto_de((d.get("message") or {}).get("content"))
            limpio = limpiar(crudo, max_caracteres) if crudo else None
            if not limpio:
                continue
            pal = tx.palabras(tx.normalizar(limpio))
            if len(pal) < min_palabras:
                continue
            salida["mensajes"].append({"uuid": d.get("uuid"), "ts": str(d.get("timestamp") or "")[:19],
                                       "cwd": d.get("cwd") or "", "texto": tx.enmascarar(limpio, 220),
                                       "normal": " ".join(pal)})
    return salida


def _norm_ruta(r: str) -> str:
    return os.path.normcase(os.path.normpath(r)).rstrip("\\/")


def proyecto_de_cwd(cwd: str, raices: list[tuple[str, str]]) -> str:
    """raices: [(raíz normalizada, id)] ordenadas de la más larga a la más corta."""
    c = _norm_ruta(cwd) if cwd else ""
    for raiz, pid in raices:
        if c == raiz or c.startswith(raiz + os.sep):
            return pid
    base = re.sub(r"[^a-z0-9-]+", "-", tx.sin_acentos(Path(cwd).name.lower())).strip("-") if cwd else ""
    return "otro:" + (base or "desconocido")


# ---------------------------------------------------------------- agrupación

def rasgos(normal: str) -> Counter:
    raices = [tx.raiz(w) for w in normal.split()]
    c = Counter(raices)
    c.update(f"{a}_{b}" for a, b in zip(raices, raices[1:]))
    return c


def agrupar(mensajes: list[dict], umbral: float) -> list[list[int]]:
    """Agrupamiento por líder con centroide sobre TF-IDF; determinista (orden fijo de entrada)."""
    n = len(mensajes)
    tfs = [rasgos(m["normal"]) for m in mensajes]
    df = Counter(k for tf in tfs for k in tf)
    vecs = []
    for tf in tfs:
        v = {k: (1 + math.log(c)) * (math.log((n + 1) / (df[k] + 1)) + 1) for k, c in tf.items()}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({k: x / norma for k, x in v.items()})
    grupos: list[list[int]] = []
    centros: list[dict[str, float]] = []
    normas: list[float] = []
    indice: dict[str, set[int]] = defaultdict(set)  # rasgo → grupos que lo tienen (para no comparar con todos)
    for i, v in enumerate(vecs):
        candidatos = set().union(*(indice[k] for k in v)) if v else set()
        mejor, sim_mejor = None, 0.0
        for g in sorted(candidatos):
            c = centros[g]
            sim = sum(x * c.get(k, 0.0) for k, x in v.items()) / (normas[g] or 1.0)
            if sim > sim_mejor + 1e-12:
                mejor, sim_mejor = g, sim
        if mejor is not None and sim_mejor >= umbral:
            grupos[mejor].append(i)
            c = centros[mejor]
            for k, x in v.items():
                c[k] = c.get(k, 0.0) + x
                indice[k].add(mejor)
            normas[mejor] = math.sqrt(sum(x * x for x in c.values()))
        else:
            grupos.append([i])
            centros.append(dict(v))
            normas.append(1.0)
            for k in v:
                indice[k].add(len(grupos) - 1)
    return grupos


def firma(normal: str) -> str:
    return hashlib.sha1(normal.encode("utf-8")).hexdigest()[:12]


def describir_grupo(miembros: list[dict], max_ejemplos: int) -> dict:
    convs = {m["conv"] for m in miembros}
    proys = sorted({m["proyecto"] for m in miembros})
    fechas = sorted(m["ts"] for m in miembros if m["ts"])
    palabras = Counter(w for m in miembros for w in m["normal"].split())
    por_raiz: dict[str, Counter] = defaultdict(Counter)
    for w, c in palabras.items():
        por_raiz[tx.raiz(w)][w] += c
    raices = Counter({r: sum(c.values()) for r, c in por_raiz.items()})
    terminos = [por_raiz[r].most_common(1)[0][0] for r, _ in sorted(raices.items(), key=lambda x: (-x[1], x[0]))[:8]]
    frecuentes = Counter(m["normal"] for m in miembros)
    ejemplos, vistos = [], set()
    for m in sorted(miembros, key=lambda m: (-frecuentes[m["normal"]], -len(set(m["normal"].split()) & set(terminos[:4])), m["ts"])):
        if m["texto"] not in vistos:
            vistos.add(m["texto"])
            ejemplos.append(m["texto"][:200])
        if len(ejemplos) >= max_ejemplos:
            break
    alcance = "conversacion" if len(convs) == 1 else ("proyecto" if len(proys) == 1 else "general")
    return {"veces": len(miembros), "conversaciones": len(convs), "proyectos": proys,
            "primera": fechas[0] if fechas else None, "ultima": fechas[-1] if fechas else None,
            "ejemplos": ejemplos, "terminos": terminos, "alcance": alcance,
            "firmas": sorted({firma(m["normal"]) for m in miembros})}


# ---------------------------------------------------------------- borrador del agente

_HERRAMIENTAS = [
    (("commit", "push", "pull", "rama", "merge", "git", "branch", "rebase", "stash"), ["Bash", "Read", "Grep", "Glob"]),
    (("prueba", "pruebas", "test", "tests", "pytest", "levanta", "levantar", "corre", "correr", "ejecuta", "ejecutar",
      "instala", "instalar", "build", "compila", "servicio", "servicios", "docker", "reinicia", "arranca"),
     ["Bash", "Read", "Grep", "Glob"]),
    (("agrega", "agregar", "cambia", "cambiar", "edita", "editar", "corrige", "corregir", "arregla", "arreglar",
      "crea", "crear", "modifica", "modificar", "actualiza", "actualizar", "quita", "quitar", "elimina", "implementa",
      "implementar", "hagalo", "hazlo", "pon", "ponle", "mueve", "renombra"), ["Read", "Edit", "Write", "Grep", "Glob"]),
    (("internet", "web", "documentacion", "docs", "busca en", "investiga"), ["WebSearch", "WebFetch"]),
]
_ORDEN_HERRAMIENTAS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash", "WebSearch", "WebFetch"]


def herramientas_para(miembros: list[dict]) -> list[str]:
    todas = " " + " ".join(m["normal"] for m in miembros) + " "
    elegidas = {"Read", "Grep", "Glob"}
    for claves, hs in _HERRAMIENTAS:
        if any(f" {k} " in todas for k in claves):
            elegidas.update(hs)
    return [h for h in _ORDEN_HERRAMIENTAS if h in elegidas]


def nombre_para(terminos: list[str], usados: set[str]) -> str:
    partes = [re.sub(r"[^a-z0-9]", "", tx.sin_acentos(t)) for t in terminos[:3]]
    base = "-".join(p for p in partes if p)[:48].strip("-") or "agente-repetido"
    nombre, i = base, 2
    while nombre in usados:
        nombre, i = f"{base}-{i}", i + 1
    return nombre


TIPOS = ("agente", "skill", "comando")
_DELEGACION = ("revisa", "revisar", "analiza", "analizar", "evalua", "evaluar", "audita", "auditar", "investiga",
               "investigar", "implementa", "implementar", "migra", "migrar", "refactoriza", "documenta", "diagnostica",
               "valida", "validar", "compara", "comparar")
_PROCEDIMIENTO = ("siempre", "cada", "recuerda", "formato", "regla", "reglas", "convencion", "pasos", "proceso",
                  "procedimiento", "plantilla", "estilo", "usa", "sigue", "antes", "despues")


def recomendar_tipo(miembros: list[dict], herramientas: list[str]) -> tuple[str, str]:
    """Reglas deterministas (en orden) para elegir agente, skill o comando, con el porqué.

    1. comando: instrucción corta (≤ 6 palabras de contenido en promedio) y casi idéntica cada vez (≤ 50 % de
       variantes) o que solo dispara una operación (git, pruebas): es un atajo que el usuario invoca con /nombre.
    2. agente: pide delegar una tarea completa (revisar, analizar, implementar, investigar...) o es larga (≥ 15
       palabras) y necesita herramientas de edición o de terminal: conviene un contexto y herramientas propios.
    3. skill (por omisión): el mismo procedimiento o las mismas reglas aplicados dentro de la conversación principal.
    """
    n = len(miembros) or 1
    prom = sum(len(m["normal"].split()) for m in miembros) / n
    variantes = len({m["normal"] for m in miembros}) / n
    palabras = set(" ".join(m["normal"] for m in miembros).split())
    if prom <= 6 and (variantes <= 0.5 or "Bash" in herramientas):
        porque = (f"casi siempre igual ({variantes:.0%} de variantes)" if variantes <= 0.5
                  else "solo dispara una operación de terminal (git, pruebas o servicios)")
        return "comando", (f"la petición es corta ({prom:.0f} palabras en promedio) y {porque}: un comando "
                           "/nombre la dispara sin reescribirla")
    delega = sorted(palabras & set(_DELEGACION))
    if delega or (prom >= 15 and ({"Edit", "Bash"} & set(herramientas))):
        motivo = (f"pide delegar una tarea completa ({', '.join(delega[:3])})" if delega else
                  f"es una tarea larga ({prom:.0f} palabras en promedio) que necesita editar o ejecutar")
        return "agente", motivo + ": un subagente la resuelve con su propio contexto y herramientas y solo devuelve el resultado"
    proc = sorted(palabras & set(_PROCEDIMIENTO))
    detalle = f" (menciona {', '.join(proc[:3])})" if proc else ""
    return "skill", ("se repite el mismo procedimiento o las mismas reglas" + detalle +
                     ": una skill lo aplica dentro de la conversación principal, sin abrir otro contexto")


def _comun(g: dict) -> tuple[str, str]:
    ejemplos = "\n".join(f"- «{e}»" for e in g["ejemplos"]) or "- (sin ejemplos)"
    origen = (f"Petición repetida {g['veces']} veces en {g['conversaciones']} conversación(es), entre "
              f"{g['primera'] or '?'} y {g['ultima'] or '?'}; proyectos: {', '.join(g['proyectos'])}.")
    return ejemplos, origen


def borrador_agente(nombre: str, descripcion: str, herramientas: list[str], g: dict) -> str:
    ejemplos, origen = _comun(g)
    bash = ("\n- Usa Bash solo para lo que pide la tarea (git, pruebas, levantar servicios); nunca comandos "
            "destructivos (`rm -rf`, `reset --hard`, `push --force`) ni push sin que el usuario lo pida."
            if "Bash" in herramientas else "")
    edita = ("\n- Edita solo lo necesario; al terminar, lista los archivos que cambiaste." if "Edit" in herramientas
             else "\n- Eres de solo lectura: si hacen falta cambios, descríbelos con precisión (archivos y qué cambiar).")
    return (
        f"---\nname: {nombre}\ndescription: {descripcion}\ntools: {', '.join(herramientas)}\n---\n\n"
        f"Eres el subagente `{nombre}`. {origen}\n\n"
        f"## Cuándo te usan\n\nPeticiones como estas (ejemplos reales, enmascarados):\n\n{ejemplos}\n\n"
        f"Términos frecuentes: {', '.join(g['terminos'])}.\n\n"
        "## Cómo trabajar\n\n"
        "1. Confirma en qué proyecto y carpeta trabajas; no salgas de ella.\n"
        "2. Si existe `graphify-out/GRAPH_REPORT.md` o `graphify-out/graph.json`, consúltalo ANTES de abrir archivos "
        "para ubicar los módulos relevantes; luego lee solo lo necesario (con offset y limit).\n"
        "3. Haz exactamente lo que se pide, sin ampliar el alcance.\n"
        "4. Verifica el resultado (pruebas o una revisión del cambio) antes de reportar, cuando aplique.\n"
        "5. Tu respuesta final es lo único que ve quien te llamó: di qué hiciste, qué archivos tocaste y qué queda "
        "pendiente.\n\n"
        "## Reglas\n\n"
        "- Responde en español de México, con tuteo.\n"
        "- No leas ni muestres secretos (.env, appsettings, llaves, tokens).\n"
        "- No hagas commit ni push salvo que el usuario lo pida en esta misma petición.\n"
        "- Si la petición es ambigua, dilo en tu respuesta en lugar de suponer." + bash + edita + "\n"
    )


def borrador_skill(nombre: str, descripcion: str, herramientas: list[str], g: dict) -> str:
    ejemplos, origen = _comun(g)
    return (
        f"---\nname: {nombre}\ndescription: {descripcion}\n---\n\n"
        f"# {nombre}\n\n{origen}\n\n"
        f"## Cuándo aplicarla\n\nCuando el usuario pida algo como (ejemplos reales, enmascarados):\n\n{ejemplos}\n\n"
        f"Términos frecuentes: {', '.join(g['terminos'])}.\n\n"
        "## Procedimiento\n\n"
        "1. Ubica lo relevante: si existe `graphify-out/GRAPH_REPORT.md` o `graphify-out/graph.json`, consúltalo "
        "antes de abrir archivos; lee solo lo necesario.\n"
        "2. Aplica el procedimiento de siempre para esta petición (completa aquí los pasos concretos que el usuario "
        "espera, tomando como base los ejemplos).\n"
        "3. Verifica el resultado antes de reportar.\n"
        "4. Reporta breve: qué hiciste y qué falta.\n\n"
        "## Reglas\n\n"
        "- Español de México, con tuteo.\n"
        "- Sin secretos (.env, appsettings, llaves, tokens).\n"
        "- Sin commit ni push salvo que el usuario lo pida.\n"
        f"- Herramientas que suele necesitar: {', '.join(herramientas)}.\n"
    )


def borrador_comando(nombre: str, descripcion: str, herramientas: list[str], g: dict) -> str:
    ejemplos, origen = _comun(g)
    return (
        f"---\ndescription: {descripcion}\nargument-hint: [detalle opcional]\ndisable-model-invocation: true\n---\n\n"
        f"Atajo `/{nombre}`. {origen}\n\n"
        f"Lo que el usuario suele escribir (ejemplos enmascarados):\n\n{ejemplos}\n\n"
        "Haz eso mismo en el proyecto actual. Detalle adicional del usuario (puede venir vacío): $ARGUMENTS\n\n"
        "Reglas: español de México con tuteo; sin secretos; sin commit ni push salvo que la petición lo diga "
        "explícitamente; reporta en una o dos líneas qué hiciste.\n"
    )


BORRADORES = {"agente": borrador_agente, "skill": borrador_skill, "comando": borrador_comando}


def descripcion_para(g: dict, tipo: str) -> str:
    base = {"agente": "Subagente para", "skill": "Procedimiento para", "comando": "Atajo para"}[tipo]
    d = (f"{base} peticiones sobre {', '.join(g['terminos'][:5])}. Usar cuando el usuario pida algo como "
         f"«{(g['ejemplos'] or [''])[0][:120]}» (repetido {g['veces']} veces).")
    return d.replace('"', "'").replace("\n", " ").replace(": ", " - ").replace("#", "")


_NOMBRE_TIPO = {"agente": "un subagente", "skill": "una skill", "comando": "un comando"}


def mensaje_para(g: dict, tipo: str, nombre: str, motivo: str) -> str:
    """Mensaje corto para la burbuja de conversación del panel."""
    donde = (f"{g['conversaciones']} conversación(es) de {g['proyectos'][0]}" if len(g["proyectos"]) == 1
             else f"{g['conversaciones']} conversaciones de {len(g['proyectos'])} proyectos")
    pedido = (g["ejemplos"] or [", ".join(g["terminos"][:3])])[0]
    pedido = pedido if len(pedido) <= 70 else pedido[:69].rstrip() + "…"
    invocar = f"/{nombre}" if tipo == "comando" else f"'{nombre}'"
    return (f"Llevas {g['veces']} veces pidiendo «{pedido}» en {donde}. Te propongo {_NOMBRE_TIPO[tipo]} "
            f"{invocar} porque {motivo.split(':')[0]}. {'¿La creo?' if tipo == 'skill' else '¿Lo creo?'}")


# ---------------------------------------------------------------- almacén y servicio

def _ahora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class ErrorPropuesta(ValueError):
    """Error de validación con mensaje seguro para el cliente."""


class Conflicto(Exception):
    """La propuesta no está en un estado que permita la acción, o el archivo ya existe."""


class Propuestas:
    def __init__(self, ajustes, registro, propias, ocupado=None):
        self.a = ajustes
        self.cfg = ajustes.propuestas
        self.registro = registro
        self.propias = propias
        self.carpeta = ajustes.carpeta_propuestas
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._ocupado = ocupado or (lambda: False)  # el ejecutor dice si hay una instrucción corriendo
        self._lock = threading.RLock()
        self._analizando = threading.Lock()
        self._detener = threading.Event()
        self._hilo: threading.Thread | None = None

    # ------------------------------------------------------------ persistencia
    def _archivo(self, pid: str) -> Path:
        return self.carpeta / f"{pid}.json"

    def _escribir(self, ruta: Path, datos) -> None:
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, ruta)

    def _meta_version(self) -> dict:
        try:
            return json.loads((self.carpeta / "version.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"version": 0, "actualizada": None}

    def _subir_version(self) -> int:
        """Contador monotónico: cambia cada vez que se crea, actualiza o decide una propuesta."""
        with self._lock:
            v = self._meta_version()["version"] + 1
            self._escribir(self.carpeta / "version.json", {"version": v, "actualizada": _ahora()})
            return v

    def _guardar(self, p: dict, version: int) -> None:
        p["version"] = version
        self._escribir(self._archivo(p["id"]), p)

    def version(self) -> dict:
        props = self.todas()
        meta = self._meta_version()
        return {"version": meta["version"], "actualizada": meta["actualizada"],
                "pendientes": sum(1 for p in props if p["estado"] == "pendiente"), "total": len(props)}

    def todas(self) -> list[dict]:
        salida = []
        for f in sorted(self.carpeta.glob("ag-*.json")):
            try:
                salida.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return salida

    def obtener(self, pid: str) -> dict:
        if not isinstance(pid, str) or not RE_ID_PROPUESTA.match(pid):
            raise ErrorPropuesta("id de propuesta inválido")
        try:
            return json.loads(self._archivo(pid).read_text(encoding="utf-8"))
        except OSError:
            raise KeyError(pid)

    def listar(self, estado: str | None = None, desde: int | None = None) -> dict:
        if estado is not None and estado not in ESTADOS:
            raise ErrorPropuesta("estado debe ser pendiente, aceptada o descartada")
        props = [p for p in self.todas() if (estado is None or p["estado"] == estado)
                 and (desde is None or int(p.get("version") or 0) > desde)]
        props.sort(key=lambda p: (p["estado"] != "pendiente", -p["grupo"]["veces"], -p["grupo"]["conversaciones"], p["id"]))
        try:
            meta = json.loads((self.carpeta / "analisis.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = None
        return {**self.version(), "analisis": meta, "propuestas": props}

    # ------------------------------------------------------------ extracción con caché
    def _mensajes(self) -> tuple[list[dict], dict]:
        maxc, minp = int(self.cfg["max_caracteres"]), int(self.cfg["min_palabras"])
        ruta_cache = self.carpeta / "cache_mensajes.json"
        try:
            cache = json.loads(ruta_cache.read_text(encoding="utf-8"))
            if cache.get("version") != 1 or cache.get("cfg") != [maxc, minp]:
                cache = {}
        except (OSError, ValueError):
            cache = {}
        archivos = cache.get("archivos", {}) if cache else {}
        nuevos: dict[str, dict] = {}
        stats = {"transcripts": 0, "transcripts_leidos": 0, "excluidos_sdk_u_orquestador": 0}
        propias = self.propias.todas()
        for f in sorted((self.a.claude_home / "projects").glob("*/*.jsonl")):
            stats["transcripts"] += 1
            try:
                st = f.stat()
            except OSError:
                continue
            clave = str(f)
            previo = archivos.get(clave)
            if previo and previo.get("tam") == st.st_size and previo.get("mtime") == st.st_mtime_ns:
                nuevos[clave] = previo
                continue
            stats["transcripts_leidos"] += 1
            datos = leer_transcript(f, maxc, minp)
            nuevos[clave] = {"tam": st.st_size, "mtime": st.st_mtime_ns, "sid": f.stem, **datos}
        self._escribir(ruta_cache, {"version": 1, "cfg": [maxc, minp], "archivos": nuevos})

        proyectos = self.registro.proyectos()
        raices = sorted(((_norm_ruta(c), pid) for pid, p in proyectos.items() for c in carpetas_de(p)),
                        key=lambda x: -len(x[0]))
        mensajes, vistos = [], set()
        for clave in sorted(nuevos):
            e = nuevos[clave]
            if (e.get("entrypoint") or "").startswith("sdk") or e["sid"] in propias:
                stats["excluidos_sdk_u_orquestador"] += 1
                continue
            for m in e["mensajes"]:
                if m.get("uuid") and m["uuid"] in vistos:
                    continue
                vistos.add(m.get("uuid"))
                mensajes.append({"conv": e["sid"], "proyecto": proyecto_de_cwd(m["cwd"], raices), "ts": m["ts"],
                                 "texto": m["texto"], "normal": m["normal"]})
        stats["mensajes_transcripts"] = len(mensajes)
        n_hist = 0
        for f in sorted(self.a.historial.glob("*.json")):
            try:
                r = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            limpio = limpiar(r.get("texto") or "", maxc)
            pal = tx.palabras(tx.normalizar(limpio)) if limpio else []
            if len(pal) < minp:
                continue
            conv = ((r.get("sesion") or {}).get("resultado")) or f"orquestador:{r.get('id')}"
            mensajes.append({"conv": conv, "proyecto": r.get("proyecto") or "otro:orquestador",
                             "ts": str(r.get("creada") or "")[:19], "texto": tx.enmascarar(limpio, 220),
                             "normal": " ".join(pal)})
            n_hist += 1
        stats["mensajes_historial"] = n_hist
        mensajes.sort(key=lambda m: (m["ts"], m["conv"], m["normal"]))
        return mensajes, stats

    # ------------------------------------------------------------ análisis
    def analizar(self) -> dict:
        if not self._analizando.acquire(blocking=False):
            raise Conflicto("ya hay un análisis en curso")
        try:
            t0 = time.monotonic()
            mensajes, stats = self._mensajes()
            grupos = agrupar(mensajes, float(self.cfg["umbral_similitud"]))
            resumen = self._fusionar(mensajes, grupos)
            meta = {"fecha": _ahora(), "duracion_ms": int((time.monotonic() - t0) * 1000), **stats,
                    "mensajes": len(mensajes), "grupos": len(grupos),
                    "grupos_repetidos": resumen.pop("repetidos"), **resumen,
                    "parametros": {k: self.cfg[k] for k in ("umbral_similitud", "min_veces", "min_conversaciones",
                                                            "min_palabras", "max_caracteres")}}
            self._escribir(self.carpeta / "analisis.json", meta)
            log.info("Análisis de instrucciones repetidas: %s mensajes, %s grupos, %s nuevas", len(mensajes),
                     len(grupos), meta["nuevas"])
            return {**meta, "version": self._meta_version()["version"]}
        finally:
            self._analizando.release()

    def _contenido(self, g: dict, miembros: list[dict], nombre: str) -> dict:
        herramientas = herramientas_para(miembros)
        tipo, motivo = recomendar_tipo(miembros, herramientas)
        borradores = {t: f(nombre, descripcion_para(g, t), herramientas, g) for t, f in BORRADORES.items()}
        return {"tipo_recomendado": tipo, "motivo_tipo": motivo, "alcance": g["alcance"],
                "descripcion": descripcion_para(g, tipo), "herramientas": herramientas,
                "destino_sugerido": self._destino(g), "borrador": borradores[tipo], "borradores": borradores,
                "mensaje": mensaje_para(g, tipo, nombre, motivo)}

    def _fusionar(self, mensajes: list[dict], grupos: list[list[int]]) -> dict:
        min_v, min_c = int(self.cfg["min_veces"]), int(self.cfg["min_conversaciones"])
        nuevas = actualizadas = ya_decididas = repetidos = 0
        with self._lock:
            existentes = self.todas()
            usados = {p["nombre"] for p in existentes}
            cambios: list[dict] = []
            for idx in grupos:
                miembros = [mensajes[i] for i in idx]
                g = describir_grupo(miembros, int(self.cfg["max_ejemplos"]))
                if not (g["veces"] >= min_v or g["conversaciones"] >= min_c):
                    continue
                repetidos += 1
                previa = self._coincidente(g, existentes)
                if previa is not None:
                    firmas = sorted(set(previa["grupo"]["firmas"]) | set(g["firmas"]))
                    if previa["estado"] != "pendiente":
                        ya_decididas += 1  # decidida: no se reabre ni se duplica; solo se recuerdan las firmas
                        if firmas != previa["grupo"]["firmas"]:
                            previa["grupo"]["firmas"] = firmas
                            self._escribir(self._archivo(previa["id"]), previa)
                        continue
                    visibles = ("grupo", "tipo_recomendado", "motivo_tipo", "alcance", "descripcion", "herramientas",
                                "destino_sugerido", "borrador", "borradores", "mensaje")
                    antes = json.dumps({k: previa.get(k) for k in visibles}, sort_keys=True, ensure_ascii=False)
                    previa["grupo"] = {**g, "firmas": firmas}
                    previa.update(self._contenido(g, miembros, previa["nombre"]))
                    if antes != json.dumps({k: previa.get(k) for k in visibles}, sort_keys=True, ensure_ascii=False):
                        previa["actualizada"] = _ahora()
                        cambios.append(previa)
                        actualizadas += 1
                    else:
                        self._escribir(self._archivo(previa["id"]), previa)
                    continue
                pid = "ag-" + hashlib.sha1("|".join(g["firmas"]).encode()).hexdigest()[:10]
                if self._archivo(pid).exists():
                    continue
                nombre = nombre_para(g["terminos"], usados)
                usados.add(nombre)
                p = {"id": pid, "estado": "pendiente", "creada": _ahora(), "actualizada": _ahora(),
                     "decidida": None, "nombre": nombre, "grupo": g, **self._contenido(g, miembros, nombre),
                     "archivo": None, "destino": None, "tipo_creado": None}
                existentes.append(p)
                cambios.append(p)
                nuevas += 1
            if cambios:
                v = self._subir_version()
                for p in cambios:
                    self._guardar(p, v)
        return {"nuevas": nuevas, "actualizadas": actualizadas, "ya_decididas": ya_decididas, "repetidos": repetidos}

    @staticmethod
    def _coincidente(g: dict, existentes: list[dict]) -> dict | None:
        nuevas = set(g["firmas"])
        mejor, valor = None, 0.0
        for p in existentes:
            viejas = set(p["grupo"]["firmas"])
            solape = len(nuevas & viejas) / (min(len(nuevas), len(viejas)) or 1)
            if solape > valor:
                mejor, valor = p, solape
        return mejor if valor >= 0.5 else None

    def _destino(self, g: dict) -> dict:
        if g["alcance"] == "general":
            return {"destino": "general"}
        pid = g["proyectos"][0]
        if pid in self.registro.proyectos():
            return {"destino": "proyecto", "proyecto": pid}
        return {"destino": "general"}

    # ------------------------------------------------------------ decisiones
    def crear(self, pid: str, cuerpo) -> dict:
        if not isinstance(cuerpo, dict):
            raise ErrorPropuesta("el cuerpo debe ser un objeto JSON")
        sobran = set(cuerpo) - {"confirmacion", "destino", "proyecto", "tipo"}
        if sobran:
            raise ErrorPropuesta("campos no permitidos: " + ", ".join(sorted(sobran)))
        if cuerpo.get("confirmacion") != pid:
            raise ErrorPropuesta("confirmacion debe ser exactamente el id de la propuesta")
        destino = cuerpo.get("destino")
        if destino not in ("general", "proyecto"):
            raise ErrorPropuesta("destino debe ser 'general' o 'proyecto'")
        with self._lock:
            p = self.obtener(pid)
            tipo = cuerpo.get("tipo", p.get("tipo_recomendado", "agente"))
            if tipo not in TIPOS:
                raise ErrorPropuesta("tipo debe ser 'agente', 'skill' o 'comando'")
            if p["estado"] != "pendiente":
                raise Conflicto(f"la propuesta está '{p['estado']}', no se puede crear")
            nombre = p.get("nombre")
            if not isinstance(nombre, str) or not RE_NOMBRE_AGENTE.match(nombre) or len(nombre) > 64:
                raise ErrorPropuesta("nombre inválido (solo [a-z0-9-])")
            if destino == "general":
                if "proyecto" in cuerpo:
                    raise ErrorPropuesta("proyecto solo aplica con destino 'proyecto'")
                base = self.a.claude_home
                raiz = base
                aviso = "Creado para todos tus proyectos."
            else:
                proy = cuerpo.get("proyecto")
                proyectos = self.registro.proyectos()
                if not isinstance(proy, str) or proy not in proyectos:
                    raise ErrorPropuesta("proyecto inválido o no registrado")
                base = proyectos[proy].carpeta
                if not base.is_dir():
                    raise ErrorPropuesta("la carpeta del proyecto no existe")
                raiz = base / ".claude"
                aviso = ("Creado en el proyecto. El archivo queda SIN COMMIT en el repositorio: revísalo y haz "
                         "commit tú si lo quieres conservar (el orquestador no hace commits).")
            aviso += {"agente": " Claude Code recarga los agentes en segundos (si es la primera carpeta de agentes, "
                                "reinicia la sesión).",
                      "skill": " Las sesiones nuevas la ven; en una sesión abierta puede requerir reiniciarla.",
                      "comando": f" Se invoca con /{nombre}."}[tipo]
            final = self._escribir_artefacto(base, raiz, tipo, nombre, p["borradores"][tipo] if p.get("borradores")
                                             else p["borrador"])
            v = self._subir_version()
            p.update(estado="aceptada", decidida=_ahora(), archivo=str(final), tipo_creado=tipo,
                     destino={"destino": destino, **({"proyecto": cuerpo["proyecto"]} if destino == "proyecto" else {})})
            self._guardar(p, v)
            log.info("Propuesta %s aceptada: %s %s (%s)", pid, tipo, nombre, destino)
            return {**p, "aviso": aviso}

    @staticmethod
    def _escribir_artefacto(base: Path, raiz: Path, tipo: str, nombre: str, contenido: str) -> Path:
        """Escribe SOLO dentro de <raiz>/agents, <raiz>/skills/<nombre> o <raiz>/commands (raiz dentro de base),
        con creación exclusiva: nunca sobrescribe. Un enlace que saque la ruta de `base` se rechaza."""
        base_r = base.resolve()
        sub = {"agente": "agents", "skill": "skills", "comando": "commands"}[tipo]
        carpeta = raiz / sub
        carpeta.mkdir(parents=True, exist_ok=True)
        carpeta_r = carpeta.resolve()
        if not carpeta_r.is_relative_to(base_r) or carpeta_r != base_r / carpeta.relative_to(base):
            raise ErrorPropuesta("la carpeta de destino sale de la ubicación permitida (enlace)")
        # una skill y un comando con el mismo nombre chocan (los dos crean /nombre): se rechaza
        if tipo == "skill" and (raiz / "commands" / f"{nombre}.md").exists():
            raise Conflicto("ya existe un comando con ese nombre")
        if tipo == "comando" and (raiz / "skills" / nombre).exists():
            raise Conflicto("ya existe una skill con ese nombre")
        if tipo == "skill":
            dir_skill = carpeta_r / nombre
            try:
                dir_skill.mkdir()
            except FileExistsError:
                raise Conflicto("ya existe una skill con ese nombre; no se sobrescribe")
            final = dir_skill / "SKILL.md"
        else:
            final = carpeta_r / f"{nombre}.md"
        if not final.resolve().is_relative_to(carpeta_r):
            raise ErrorPropuesta("ruta inválida")
        try:
            with open(final, "x", encoding="utf-8", newline="\n") as h:
                h.write(contenido)
        except FileExistsError:
            raise Conflicto(f"ya existe un {tipo} con ese nombre; no se sobrescribe")
        return final

    def descartar(self, pid: str, cuerpo) -> dict:
        if not isinstance(cuerpo, dict) or set(cuerpo) - {"motivo"}:
            raise ErrorPropuesta("solo se acepta el campo opcional motivo")
        motivo = cuerpo.get("motivo")
        if motivo is not None and (not isinstance(motivo, str) or len(motivo) > 300):
            raise ErrorPropuesta("motivo debe ser texto de hasta 300 caracteres")
        with self._lock:
            p = self.obtener(pid)
            if p["estado"] != "pendiente":
                raise Conflicto(f"la propuesta está '{p['estado']}', no se puede descartar")
            p.update(estado="descartada", decidida=_ahora(), motivo=motivo)
            self._guardar(p, self._subir_version())
            return p

    # ------------------------------------------------------------ recálculo periódico
    def iniciar(self) -> None:
        if float(self.cfg.get("cada_h") or 0) <= 0:
            return
        self._hilo = threading.Thread(target=self._ciclo, name="propuestas", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._detener.set()

    def _ciclo(self) -> None:
        espera = float(self.cfg.get("retraso_inicial_min", 10)) * 60
        while not self._detener.wait(espera):
            if self._ocupado():  # memoria escasa: no se analiza mientras corre una instrucción
                espera = 300
                continue
            try:
                self.analizar()
            except Conflicto:
                pass
            except Exception:  # noqa: BLE001
                log.exception("Falló el análisis periódico de instrucciones repetidas")
            espera = float(self.cfg["cada_h"]) * 3600
