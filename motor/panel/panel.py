"""
Panel de control local: proyectos (servicios y agentes de Claude Code) y Laboratorio de ingeniería inversa.

Solo biblioteca estándar. Escucha únicamente en 127.0.0.1. Lee el registro central proyectos.json del directorio
de datos del motor (variable DEVSKILLS_DATOS, o ~/.devskills; ver comun/rutas.py).

  python panel.py iniciar [--simular] [--no-abrir] [--puerto N] [--laboratorio DIR] [--registro ARCHIVO]
  python panel.py servir  [--simular] [--puerto N] [--laboratorio DIR] [--registro ARCHIVO]  (lo usa 'iniciar')
  python panel.py apagar  [--puerto N]
  python panel.py estado  [--puerto N]

--simular: Levantar/Apagar no ejecutan nada; corren servicios.py --simular y devuelven el comando. Tampoco se ejecutan
           `gh auth switch` ni `git config` (se devuelve el comando que correría); las lecturas sí se hacen.
--laboratorio DIR: carpeta base del Laboratorio (por omisión <datos>/laboratorio).
--registro ARCHIVO: otro proyectos.json (pruebas: así el cambio de cuenta no toca el registro real).
--estado DIR: carpeta del estado persistente (avisos.json, acciones.json). Por omisión <datos>/panel/estado (puerto 18950)
           o <datos>/panel/estado-<puerto> (otras instancias).
--claude-proyectos DIR / --claude-temp DIR: otras carpetas de transcripts (pruebas: así no se leen los reales).
--raices DIR[;DIR]: raíces de la detección de proyectos en lugar de ~/Documents/Proyectos y ~/Desktop (pruebas); las
           de `raices_deteccion` del registro se suman siempre. La detección es de solo lectura.

Chat con el orquestador (caja del centro de avisos): proxy servidor a servidor bajo /api/chat/...; el token del
           orquestador (su archivo .token) se relee en cada llamada y nunca llega al navegador. Solo para pruebas:
           PANEL_ORQUESTADOR_URL (http://127.0.0.1:<puerto>), PANEL_ORQUESTADOR_TOKEN (otro .token) y
           PANEL_ORQUESTADOR_CMD (otro comando de arranque: lista JSON de argumentos). Con --simular y sin URL de prueba, el chat no envía nada al real.

Estado en disco (directorio de datos): preferencias.json (color, vista de avisos, notificación y sonido),
panel/estado/acciones.json (últimas Levantar/Apagar por servicio o proyecto), panel/estado/avisos.json (centro de
avisos, máx. 500) y laboratorio/. Lo demás
(salud, puertos, agentes activos, cachés) vive en memoria y se recalcula al arrancar.
"""
import copy
import hashlib
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

AQUI = Path(__file__).resolve().parent          # código del panel (motor/panel)
RAIZ = AQUI.parent                              # código del motor (motor/)
sys.path.insert(0, str(RAIZ))
from comun import rutas  # noqa: E402

SERVICIOS_PY = RAIZ / "servicios" / "servicios.py"
REGISTRO = rutas.registro()
INDEX = AQUI / "index.html"
ICONO = AQUI / "favicon.svg"
ARCHIVO_LOG = rutas.panel_log()
HOST = "127.0.0.1"
PUERTO_DEFAULT = 18950

ACCIONES = {"levantar", "apagar"}
TIPOS_ARRANQUE = {"dotnet", "npm", "django-devskills", "python-modulo", "docker-compose"}
PROYECTOS_CLAUDE = Path.home() / ".claude" / "projects"
TEMP_CLAUDE = Path(tempfile.gettempdir()) / "claude"
COLA_BYTES = 256 * 1024
MAX_TRANSCRIPTS = 30
ACTIVO_SEG = 120
ESPERA_SESION_SEG = 30 * 60
ESPERA_SUBAGENTE_SEG = 60 * 60
MAX_EXPLICACION = 30000
MAX_INFORME = 60000
MAX_JSON = 16 * 1024
MAX_PREFERENCIAS = 512
RE_ACENTO = re.compile(r"#[0-9a-fA-F]{6}")
MAX_SUBIDA = 200 * 1024 * 1024
MAX_INFORME_LAB = 2 * 1024 * 1024
NODE_MINIMO = (24, 22, 1)
ARCHIVOS_RESULTADO = ("INFORME.md", "BACKLOG.md", "CATALOGO.md")
OBJETIVOS_LAB = {
    "backlog": "Módulos para el backlog del proyecto",
    "inhouse": "Código reutilizable para proyectos inhouse",
}
TEXTO_CONFIRMACION = ("Confirmo que el software es propio, autorizado o de código abierto, "
                      "y que solo se hará análisis estático.")
SALUD_TIMEOUT = 1.5      # segundos por sondeo (conexión + respuesta)
SALUD_CACHE_SEG = 2.0    # varias pestañas o refrescos seguidos no repiten el sondeo
MAX_CUENTA_JSON = 512
TIPOS_CUENTA = {"organizacional", "personal"}
VISTAS_AVISOS = ("lateral", "burbuja")
MAX_ACCIONES_POR_OBJETIVO = 20   # historial de Levantar/Apagar que se conserva por servicio o proyecto
MAX_AVISOS = 500                 # avisos.json rota: se descartan los más viejos
MAX_RESUMEN_AVISO = 300
DETECTOR_SEG = 5.0               # ciclo del detector de eventos
DETECTOR_HORAS = 0.5             # solo se vigilan transcripts modificados en esta ventana
STOP_FINAL = {"end_turn", "stop_sequence", "max_tokens"}
HERRAMIENTAS_PREGUNTA = {"AskUserQuestion", "ExitPlanMode"}  # herramientas que esperan una respuesta del usuario

# Enrutamiento de modelos (Model Routing Playbook): rol del equipo -> modelo y esfuerzo, ambos en lista blanca.
# Formato de DevSkills (bin/devskills, rama feat/enrutamiento): es la fuente de verdad de las claves y la tabla por omisión.
ROLES_ENRUTAMIENTO = ("desarrollo", "desarrollo-excepcion", "angel-fixer-revision", "angel-fixer-excepcion",
                      "qa-excepcion", "qa-cierre-sprint", "verificador-ligero", "verificador-final",
                      "analista-arquitecto", "pasada-documental", "registrar-avance", "mecanico")
# Claves antiguas que escribía el panel -> claves de DevSkills a las que migran al guardar.
MIGRACION_ROLES = {"dev-a": ("desarrollo",), "dev-b": ("desarrollo",), "angel-fixer-historia": ("angel-fixer-revision",),
                   "qa-cierre": ("qa-cierre-sprint",),
                   "documental": ("pasada-documental", "registrar-avance", "mecanico")}
MODELOS_ENRUTAMIENTO = ("haiku", "sonnet", "opus")
ESFUERZOS_ENRUTAMIENTO = ("low", "medium", "high")
NIVELES_ENRUTAMIENTO = ("recomendado", "parcial", "no-recomendado")
TABLA_ENRUTAMIENTO = {
    "desarrollo": {"modelo": "sonnet", "esfuerzo": "medium"},
    "desarrollo-excepcion": {"modelo": "sonnet", "esfuerzo": "high"},
    "angel-fixer-revision": {"modelo": "sonnet", "esfuerzo": "medium"},
    "angel-fixer-excepcion": {"modelo": "opus", "esfuerzo": "high"},
    "qa-excepcion": {"modelo": "opus", "esfuerzo": "high"},
    "qa-cierre-sprint": {"modelo": "opus", "esfuerzo": "high"},
    "verificador-ligero": {"modelo": "sonnet", "esfuerzo": "medium"},
    "verificador-final": {"modelo": "sonnet", "esfuerzo": "high"},
    "analista-arquitecto": {"modelo": "opus", "esfuerzo": "medium"},
    "pasada-documental": {"modelo": "haiku", "esfuerzo": "low"},
    "registrar-avance": {"modelo": "haiku", "esfuerzo": "low"},
    "mecanico": {"modelo": "haiku", "esfuerzo": "low"},
}
ESCALAMIENTO_ENRUTAMIENTO = {"max_reintentos": 1, "orden": ["esfuerzo", "modelo"]}

ESTADO = {"token": "", "puerto": PUERTO_DEFAULT, "simular": False, "servidor": None,
          "laboratorio": rutas.laboratorio(), "node": None, "estado_dir": rutas.panel_estado()}
_candados = {}
_candados_lock = threading.Lock()
_cache = {}  # ruta -> (mtime, tamaño, resultado)
_cache_lock = threading.Lock()
_registro_cache = {"mtime": None, "datos": None, "error": None}
_registro_lock = threading.Lock()


def log(msg):
    try:
        ARCHIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
        if ARCHIVO_LOG.exists() and ARCHIVO_LOG.stat().st_size > 512 * 1024:
            ARCHIVO_LOG.unlink()
        with open(ARCHIVO_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def archivo_token(puerto):
    return rutas.panel_token(puerto)


def archivo_preferencias(puerto):
    # Una instancia de prueba (otro puerto) nunca pisa las preferencias del panel principal.
    return rutas.preferencias(puerto)


def carpeta_estado_por_omision(puerto):
    # Igual que las preferencias: una instancia de prueba (otro puerto) nunca pisa el estado del panel principal.
    return rutas.panel_estado(puerto)


def escribir_json_atomico(destino, datos, indent=None):
    """Temporal en la misma carpeta + fsync + os.replace: un corte a media escritura nunca deja el JSON a medias.
    Con `indent` se escribe legible (sangría y salto final); sin él, compacto."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f"{destino.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(temporal, "w", encoding="utf-8", newline="\n") as f:
            if indent:
                f.write(json.dumps(datos, ensure_ascii=False, indent=indent) + "\n")
            else:
                json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, destino)
    finally:
        try:
            temporal.unlink()
        except OSError:
            pass


def leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def ruta_os(p):
    """Ruta utilizable por os.* en Windows aunque supere MAX_PATH (los transcripts de subagentes suelen hacerlo)."""
    s = os.path.abspath(str(p))
    if os.name == "nt" and len(s) >= 240 and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def candado(clave):
    with _candados_lock:
        return _candados.setdefault(clave, threading.Lock())


# ---------------------------------------------------------------- enmascarado

_PATRONES_SECRETO = [
    (re.compile(r'(?i)\b(password|passwd|pwd|secret|client_secret|token|access_token|refresh_token|'
                r'api[_-]?key|apikey|key|connectionstring|connection_string)\b(["\']?\s*[:=]\s*["\']?)'
                r'([^\s"\',;&]+)'), r"\1\2••••"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer ••••"),
    (re.compile(r"\bgh[opsur]_[A-Za-z0-9]{8,}"), "gh•_••••"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}"), "github_pat_••••"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "sk-••••"),
    (re.compile(r"\bAKIA[0-9A-Z]{12,}"), "AKIA••••"),
    (re.compile(r"(?i)(://)[^:/\s@]+:[^@\s]+@"), r"\1••••@"),
    (re.compile(r"(?i)\b(token|secret|password|contraseña)\s+[A-Za-z0-9._-]{12,}"), r"\1 ••••"),
]
_CANDIDATO_LARGO = re.compile(r"[A-Za-z0-9_+/=-]{32,}")


def _parece_secreto(m):
    s = m.group(0)
    # Cadenas aleatorias: mezclan mayúsculas, minúsculas y dígitos, casi sin guiones ni diagonales
    # (así no se enmascaran rutas, nombres de carpeta ni UUID).
    if s.count("-") > 2 or s.count("/") > 2:
        return s
    if sum(c.isdigit() for c in s) >= 4 and any(c.isupper() for c in s) and any(c.islower() for c in s):
        return "••••"
    return s


def enmascarar(texto):
    if not texto:
        return ""
    for patron, reemplazo in _PATRONES_SECRETO:
        texto = patron.sub(reemplazo, texto)
    return _CANDIDATO_LARGO.sub(_parece_secreto, texto)


def corto(texto, n=200):
    texto = " ".join(str(texto).split())
    texto = enmascarar(texto)
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def recortar(texto, n):
    texto = enmascarar(texto.strip())
    return texto if len(texto) <= n else texto[:n] + "\n\n[…texto recortado…]"


# ---------------------------------------------------------------- registro central

class ErrorRegistro(Exception):
    pass


_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def _puerto(v, donde):
    if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 65535:
        raise ErrorRegistro(f"Puerto inválido en {donde}: {v!r}")
    return v


def _url_segura(u, donde):
    if not isinstance(u, str) or urlparse(u).scheme not in ("http", "https") or not urlparse(u).hostname:
        raise ErrorRegistro(f"URL inválida en {donde} (solo http/https): {u!r}")
    return u


# Ruta HTTP absoluta del propio servicio: empieza con una sola '/', sin esquema, host, espacios, '\' ni fragmento.
_RUTA_HTTP = re.compile(r"^/(?!/)[A-Za-z0-9._~!$&'()*+,;=:@%/?-]{0,200}$")
_CUENTA_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")            # login de GitHub
_REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")  # owner/repo
_RAMA = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
_REMOTO = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
_LOCALES = {"localhost", "127.0.0.1", "::1"}


def _ruta_http(v, donde):
    if v is None:
        return None
    if not isinstance(v, str) or not _RUTA_HTTP.match(v) or ".." in v.split("?")[0].split("/"):
        raise ErrorRegistro(f"Ruta inválida en {donde} (debe empezar con '/'): {v!r}")
    return v


def _puerto_url(u):
    p = urlparse(u)
    return p.port or (443 if p.scheme == "https" else 80)


def _texto(v, donde, maximo):
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > maximo:
        raise ErrorRegistro(f"Texto inválido en {donde} (máximo {maximo} caracteres)")
    return v


def validar_cuentas(lista):
    cuentas, vistos = [], set()
    for c in lista or []:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not _CUENTA_ID.match(c["id"]):
            raise ErrorRegistro(f"Cuenta con id inválido: {c!r:.80}")
        if c["id"] in vistos:
            raise ErrorRegistro(f"Cuenta duplicada: {c['id']}")
        if c.get("tipo") not in TIPOS_CUENTA:
            raise ErrorRegistro(f"Tipo de cuenta inválido en {c['id']} (organizacional o personal)")
        vistos.add(c["id"])
        cuentas.append({"id": c["id"], "nombre": _texto(c.get("nombre"), c["id"], 80) or c["id"], "tipo": c["tipo"]})
    return cuentas


def _repo(v, donde):
    if v is None:
        return None
    if not isinstance(v, str) or not _REPO.match(v):
        raise ErrorRegistro(f"Repositorio inválido en {donde} (owner/repo): {v!r}")
    return {"repo": v, "url": "https://github.com/" + v}


def validar_repositorio(r, pid, ids_cuenta):
    """Bloque `repositorio` de un proyecto. Solo datos para mostrar: el panel nunca ejecuta nada contra GitHub."""
    if r is None:
        return None
    if not isinstance(r, dict):
        raise ErrorRegistro(f"Repositorio inválido en {pid}")
    cuenta = r.get("cuenta")
    if cuenta is not None and cuenta not in ids_cuenta:
        raise ErrorRegistro(f"Cuenta desconocida en {pid}: {cuenta!r}")
    rama = r.get("rama")
    if rama is not None and (not isinstance(rama, str) or not _RAMA.match(rama)):
        raise ErrorRegistro(f"Rama inválida en {pid}")
    remotos = []
    for x in r.get("remotos") or []:
        if not isinstance(x, dict) or not isinstance(x.get("nombre"), str) or not _REMOTO.match(x["nombre"]):
            raise ErrorRegistro(f"Remoto inválido en {pid}")
        remotos.append({"nombre": x["nombre"], **_repo(x.get("repo"), pid)})
    copias = []
    for x in r.get("copias") or []:
        if not isinstance(x, dict):
            raise ErrorRegistro(f"Copia inválida en {pid}")
        copias.append({**_repo(x.get("repo"), pid), "nota": _texto(x.get("nota"), pid, 300)})
    principal = _repo(r.get("repo"), pid)
    return {"cuenta": cuenta, "repo": principal["repo"] if principal else None,
            "url": principal["url"] if principal else None, "rama": rama, "remotos": remotos,
            "copias": copias, "nota": _texto(r.get("nota"), pid, 400)}


def validar_tabla_enrutamiento(t, donde):
    """Tabla rol -> {modelo, esfuerzo}: exactamente los roles conocidos y valores de la lista blanca."""
    if not isinstance(t, dict) or set(t) != set(ROLES_ENRUTAMIENTO):
        raise ErrorRegistro(f"Tabla de enrutamiento inválida en {donde}: debe traer exactamente los roles "
                            + ", ".join(ROLES_ENRUTAMIENTO))
    salida = {}
    for rol in ROLES_ENRUTAMIENTO:
        v = t[rol]
        if (not isinstance(v, dict) or set(v) != {"modelo", "esfuerzo"} or v["modelo"] not in MODELOS_ENRUTAMIENTO
                or v["esfuerzo"] not in ESFUERZOS_ENRUTAMIENTO):
            raise ErrorRegistro(f"Valor no permitido para {rol} en {donde}: modelo {'/'.join(MODELOS_ENRUTAMIENTO)} "
                                f"y esfuerzo {'/'.join(ESFUERZOS_ENRUTAMIENTO)}")
        salida[rol] = {"modelo": v["modelo"], "esfuerzo": v["esfuerzo"]}
    return salida


def _valor_rol(v):
    if (isinstance(v, dict) and v.get("modelo") in MODELOS_ENRUTAMIENTO
            and v.get("esfuerzo") in ESFUERZOS_ENRUTAMIENTO):
        return {"modelo": v["modelo"], "esfuerzo": v["esfuerzo"]}
    return None


def analizar_tabla_enrutamiento(t):
    """Lectura tolerante de una tabla guardada (archivo o registro). Devuelve
    {"tabla": rol -> valor o None, "estado": rol -> ok|migrable|sin-enrutar, "migrables": [...], "invalidos": [...],
     "desconocidos": [...]}. Los roles que faltan quedan "sin enrutar"; si una clave antigua del panel los cubre, su
    valor se propone como "migrable" (se escribe con la clave nueva al guardar)."""
    t = t if isinstance(t, dict) else {}
    tabla, estado, migrables, invalidos = {}, {}, [], []
    for rol in ROLES_ENRUTAMIENTO:
        v = _valor_rol(t.get(rol))
        if rol in t and v is None:
            invalidos.append(rol)
        tabla[rol], estado[rol] = v, "ok" if v else "sin-enrutar"
    for viejo, nuevos in MIGRACION_ROLES.items():
        if viejo not in t:
            continue
        v = _valor_rol(t[viejo])
        aplica = []
        for n in nuevos:
            if v and estado[n] == "sin-enrutar":  # dev-a gana sobre dev-b: va primero en MIGRACION_ROLES
                tabla[n], estado[n] = dict(v), "migrable"
                aplica.append(n)
        migrables.append({"clave": viejo, "a": list(nuevos), "valor": v, "aplica_a": aplica})
    desconocidos = [k for k in t if k not in ROLES_ENRUTAMIENTO and k not in MIGRACION_ROLES]
    return {"tabla": tabla, "estado": estado, "migrables": migrables, "invalidos": invalidos,
            "desconocidos": [str(k)[:60] for k in desconocidos][:20]}


def validar_enrutamiento(e, pid):
    """Bloque `enrutamiento` de un proyecto: {"activo", "evaluacion", "actualizado"} (+ "tabla" si no es DevSkills)."""
    if e is None:
        return None
    if not isinstance(e, dict) or not isinstance(e.get("activo"), bool):
        raise ErrorRegistro(f"Enrutamiento inválido en {pid}")
    ev = e.get("evaluacion") or {}
    if not isinstance(ev, dict) or ev.get("nivel") not in NIVELES_ENRUTAMIENTO + (None,):
        raise ErrorRegistro(f"Evaluación de enrutamiento inválida en {pid}")
    motivos = ev.get("motivos") or []
    if not isinstance(motivos, list) or not all(isinstance(m, str) and len(m) <= 300 for m in motivos):
        raise ErrorRegistro(f"Motivos de enrutamiento inválidos en {pid}")
    return {"activo": e["activo"], "evaluacion": {"nivel": ev.get("nivel"), "motivos": motivos[:20]},
            "actualizado": _texto(e.get("actualizado"), pid + ".enrutamiento", 40),
            # La tabla del registro se lee tolerante (puede traer claves antiguas del panel o roles sin enrutar);
            # solo se exige que sea un objeto. Se escribe siempre completa y validada.
            "tabla": _tabla_registro(e.get("tabla"), pid)}


def _tabla_registro(t, pid):
    if t is None:
        return None
    if not isinstance(t, dict) or len(t) > 40:
        raise ErrorRegistro(f"Tabla de enrutamiento inválida en {pid}")
    return t


_RE_ABSOLUTA = re.compile(r"^(?:[A-Za-z]:[\\/]|/)")


def es_ruta_absoluta(r):
    """Ruta absoluta de Windows (C:\\..., C:/...) o de macOS/Linux (/...). Un '~/...' se expande antes de validar."""
    return isinstance(r, str) and bool(_RE_ABSOLUTA.match(r))


def expandir_carpeta(r):
    """'~' o '~/x' pasan a la carpeta personal; lo demás queda igual (solo texto: no toca el disco)."""
    if isinstance(r, str) and (r == "~" or r.startswith(("~/", "~\\"))):
        return os.path.expanduser(r)
    return r


def validar_raices(lista):
    raices = []
    for r in lista or []:
        r = expandir_carpeta(r)
        if not es_ruta_absoluta(r) or len(r) > 260 or ".." in re.split(r"[\\/]", r):
            raise ErrorRegistro(f"Raíz de detección inválida (ruta absoluta): {r!r:.80}")
        raices.append(r)
    if len(raices) > 10:
        raise ErrorRegistro("Máximo 10 raíces de detección.")
    return raices


def codificar_carpeta(ruta):
    """Así nombra Claude Code las carpetas de ~/.claude/projects: todo lo que no es alfanumérico pasa a '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", ruta).lower()


def validar_registro(d):
    if not isinstance(d, dict) or not isinstance(d.get("proyectos"), list):
        raise ErrorRegistro("El registro debe tener una lista 'proyectos'.")
    reservados = []
    for r in d.get("puertos_reservados") or []:
        if not isinstance(r, dict):
            raise ErrorRegistro("Puerto reservado inválido.")
        reservados.append({"puerto": _puerto(r.get("puerto"), "puertos_reservados"),
                           "uso": str(r.get("uso") or ""), "proyecto": r.get("proyecto")})
    puerto_panel = (d.get("panel") or {}).get("puerto", PUERTO_DEFAULT)
    cuentas = validar_cuentas(d.get("cuentas"))
    ids_cuenta = {c["id"] for c in cuentas}
    proyectos, ids = [], set()
    for p in d["proyectos"]:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not _ID.match(p["id"]):
            raise ErrorRegistro(f"Proyecto con id inválido: {p!r:.80}")
        if p["id"] in ids:
            raise ErrorRegistro(f"Id duplicado: {p['id']}")
        ids.add(p["id"])
        carpeta = expandir_carpeta(p.get("carpeta"))
        if not es_ruta_absoluta(carpeta):
            raise ErrorRegistro(f"Carpeta inválida en {p['id']}")
        rango = p.get("rango")
        if rango is not None:
            if not isinstance(rango, dict) or rango.get("tipo") not in ("asignado", "heredado", "propuesto"):
                raise ErrorRegistro(f"Rango inválido en {p['id']}")
            if "inicio" in rango:
                ini, fin = _puerto(rango["inicio"], p["id"]), _puerto(rango.get("fin"), p["id"])
                if fin < ini:
                    raise ErrorRegistro(f"Rango invertido en {p['id']}")
                rango = {"tipo": rango["tipo"], "inicio": ini, "fin": fin}
            else:
                rango = {"tipo": rango["tipo"], "puertos": [_puerto(x, p["id"]) for x in rango.get("puertos") or []]}
        servicios = []
        for s in p.get("servicios") or []:
            if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not _ID.match(s["id"]):
                raise ErrorRegistro(f"Servicio con id inválido en {p['id']}")
            if s["id"] in ids:
                raise ErrorRegistro(f"Id duplicado: {s['id']}")
            ids.add(s["id"])
            arranque = s.get("arranque") or {}
            if arranque.get("tipo") not in TIPOS_ARRANQUE:
                raise ErrorRegistro(f"Tipo de arranque no permitido en {s['id']}")
            puertos = [_puerto(x, s["id"]) for x in s.get("puertos") or []]
            if not puertos:
                raise ErrorRegistro(f"El servicio {s['id']} no tiene puertos")
            url = _url_segura(s.get("url"), s["id"])
            salud = _ruta_http(s.get("salud"), s["id"] + ".salud")
            abrir = _ruta_http(s.get("abrir"), s["id"] + ".abrir")
            # El sondeo de salud solo va a un puerto del propio servicio y a un host local.
            puerto_salud = _puerto_url(url)
            if salud and (puerto_salud not in puertos or (urlparse(url).hostname or "").lower() not in _LOCALES):
                raise ErrorRegistro(f"La URL de {s['id']} debe ser local y usar uno de sus puertos para la salud")
            u = urlparse(url)
            servicios.append({"id": s["id"], "nombre": str(s.get("nombre") or s["id"]), "puertos": puertos,
                              "url": url, "tipo": arranque["tipo"], "salud": salud, "puerto_salud": puerto_salud,
                              "url_abrir": f"{u.scheme}://{u.netloc}{abrir}" if abrir else url})
        transcripts = [carpeta] + [t for t in (p.get("transcripts") or []) if isinstance(t, str)]
        conflictos = []
        for c in p.get("conflictos") or []:
            if isinstance(c, dict):
                conflictos.append({"puerto": c.get("puerto"), "con": str(c.get("con") or ""),
                                   "propuesta": str(c.get("propuesta") or ""), "origen": "registro"})
        proyectos.append({"id": p["id"], "nombre": str(p.get("nombre") or p["id"]),
                          "descripcion": str(p.get("descripcion") or ""), "carpeta": carpeta, "rango": rango,
                          "resumen": _texto(p.get("resumen"), p["id"], 1200),
                          "repositorio": validar_repositorio(p.get("repositorio"), p["id"], ids_cuenta),
                          "nota": str(p.get("nota") or ""), "servicios": servicios, "conflictos": conflictos,
                          "transcripts": transcripts,
                          "enrutamiento": validar_enrutamiento(p.get("enrutamiento"), p["id"])})
    detectar_conflictos(proyectos, reservados, puerto_panel)
    # Prefijos para asignar carpetas de transcripts a proyectos; el más específico (más largo) gana.
    prefijos = []
    for p in proyectos:
        for t in p["transcripts"]:
            comodin = t.endswith("*")
            prefijos.append((codificar_carpeta(t.rstrip("*")), p["id"], comodin))
    prefijos.sort(key=lambda x: len(x[0]), reverse=True)
    return {"proyectos": proyectos, "por_id": {p["id"]: p for p in proyectos},
            "servicios": {s["id"]: (p["id"], s) for p in proyectos for s in p["servicios"]},
            "reservados": reservados, "puerto_panel": puerto_panel, "prefijos": prefijos,
            "politica_rangos": str(d.get("politica_rangos") or ""), "cuentas": cuentas,
            "raices_deteccion": validar_raices(d.get("raices_deteccion"))}


def detectar_conflictos(proyectos, reservados, puerto_panel):
    """Agrega a cada proyecto los choques que se pueden detectar del propio registro."""
    usos = {}
    for p in proyectos:
        for s in p["servicios"]:
            for pt in s["puertos"]:
                usos.setdefault(pt, []).append((p["id"], s["id"]))
    for p in proyectos:
        vistos = {c["puerto"] for c in p["conflictos"]}

        def agregar(pt, con):
            if pt not in vistos:
                vistos.add(pt)
                p["conflictos"].append({"puerto": pt, "con": con, "propuesta": "", "origen": "detectado"})
        for s in p["servicios"]:
            for pt in s["puertos"]:
                if pt == puerto_panel:
                    agregar(pt, "El panel de control")
                for r in reservados:
                    if r["puerto"] == pt and r.get("proyecto") != p["id"]:
                        agregar(pt, f"Puerto reservado ({r['uso']})")
                otros = [x for x in usos.get(pt, []) if x[0] != p["id"]]
                if otros:
                    agregar(pt, "También lo usa " + ", ".join(sorted({o[0] for o in otros})))
                for q in proyectos:
                    rq = q["rango"]
                    if q["id"] != p["id"] and rq and "inicio" in rq and rq["inicio"] <= pt <= rq["fin"]:
                        agregar(pt, f"Rango asignado a {q['id']} ({rq['inicio']}-{rq['fin']})")


def registro():
    """Lee y valida proyectos.json con caché por fecha de modificación."""
    with _registro_lock:
        try:
            mtime = REGISTRO.stat().st_mtime
        except OSError:
            raise ErrorRegistro(f"No se encontró {REGISTRO}")
        if _registro_cache["mtime"] == mtime:
            if _registro_cache["error"]:
                raise ErrorRegistro(_registro_cache["error"])
            return _registro_cache["datos"]
        try:
            datos = validar_registro(json.loads(REGISTRO.read_text(encoding="utf-8")))
            _registro_cache.update(mtime=mtime, datos=datos, error=None)
            return datos
        except (ValueError, ErrorRegistro) as e:
            _registro_cache.update(mtime=mtime, datos=None, error=f"Registro inválido: {e}")
            raise ErrorRegistro(_registro_cache["error"])


def proyecto_de_carpeta(nombre, reg):
    n = nombre.lower()
    for enc, pid, comodin in reg["prefijos"]:
        if n == enc or n.startswith(enc + "-") or (comodin and n.startswith(enc)):
            return pid
    return None


# ---------------------------------------------------------------- servicios

def puertos_en_escucha():
    """Puertos TCP en escucha, o None si no se pudo saber (entonces se sondea puerto por puerto).
    Windows: `netstat -an` (un socket en escucha tiene como remota 0.0.0.0:0 o [::]:0, sin depender del idioma).
    Linux: `ss -H -ltn`. macOS: `netstat -an -p tcp` (líneas con LISTEN). Sin shell, argumentos fijos."""
    if os.name == "nt":
        cmd = ["netstat", "-an"]
    elif sys.platform == "darwin":
        cmd = ["netstat", "-an", "-p", "tcp"]
    else:
        cmd = ["ss", "-H", "-ltn"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    puertos = set()
    for linea in r.stdout.decode("oem" if os.name == "nt" else "utf-8", errors="replace").splitlines():
        partes = linea.split()
        local = None
        if os.name == "nt":
            if len(partes) >= 3 and partes[0].upper() == "TCP" and partes[2] in ("0.0.0.0:0", "[::]:0"):
                local = partes[1]
        elif sys.platform == "darwin":
            if partes and partes[0].lower().startswith("tcp") and "LISTEN" in partes:
                local = partes[3]
        elif len(partes) >= 4 and partes[0].upper() == "LISTEN":
            local = partes[3]
        if local:
            try:
                puertos.add(int(local.rsplit("." if sys.platform == "darwin" else ":", 1)[1]))
            except (ValueError, IndexError):
                pass
    return puertos


def puerto_escucha(puerto):
    """Respaldo si netstat falla: intenta conectar a 127.0.0.1 y ::1."""
    for familia, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(familia, socket.SOCK_STREAM) as s:
                s.settimeout(0.25)
                s.connect((host, puerto))
                return True
        except OSError:
            continue
    return False


def _estado_de(n, total):
    return "corriendo" if total and n == total else ("parcial" if n else "detenido")


_salud_cache = {}  # id de servicio -> (instante, código o None)
_salud_lock = threading.Lock()


def _pedir_salud(host, puerto, ruta, host_cabecera, https):
    """Un GET con http.client: no sigue redirecciones (ni a otros hosts ni al mismo) y no lee el cuerpo."""
    if https:
        # Solo loopback y solo se lee el código de estado: los certificados locales suelen ser autofirmados.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        c = http.client.HTTPSConnection(host, puerto, timeout=SALUD_TIMEOUT, context=ctx)
    else:
        c = http.client.HTTPConnection(host, puerto, timeout=SALUD_TIMEOUT)
    try:
        c.putrequest("GET", ruta, skip_host=True, skip_accept_encoding=True)
        c.putheader("Host", host_cabecera)
        c.putheader("User-Agent", "PanelLocal-salud")
        c.putheader("Accept", "*/*")
        c.putheader("Connection", "close")
        c.endheaders()
        return c.getresponse().status
    finally:
        c.close()


def sondear_salud(s):
    """Código HTTP de la ruta de salud del servicio, o None si no responde. Siempre a 127.0.0.1 (y ::1 si
    127.0.0.1 rechaza la conexión, p. ej. Vite escuchando solo en IPv6) y al puerto del registro."""
    with _salud_lock:
        c = _salud_cache.get(s["id"])
        if c and time.monotonic() - c[0] < SALUD_CACHE_SEG:
            return c[1]
    u = urlparse(s["url"])
    puerto = s["puerto_salud"]
    host_cabecera = f"{u.hostname}:{puerto}" if ":" not in u.hostname else f"[{u.hostname}]:{puerto}"
    codigo = None
    for host in ("127.0.0.1", "::1"):
        try:
            codigo = _pedir_salud(host, puerto, s["salud"], host_cabecera, u.scheme == "https")
            break
        except ConnectionRefusedError:
            continue
        except (OSError, http.client.HTTPException, ValueError):
            break
    with _salud_lock:
        _salud_cache[s["id"]] = (time.monotonic(), codigo)
    return codigo


def salud_servicio(s, puertos, estado):
    """detenido / arrancando (el puerto escucha pero la salud aún no responde) / listo."""
    escucha = {x["puerto"]: x["escucha"] for x in puertos}
    if not s["salud"]:
        # Sin ruta de salud: se decide solo por los puertos.
        e = {"corriendo": "listo", "parcial": "arrancando"}.get(estado, "detenido")
        return {"estado": e, "detalle": "Sin ruta de salud; se usa el estado de los puertos", "codigo": None}
    if not escucha.get(s["puerto_salud"]):
        return {"estado": "detenido", "detalle": f"Nada escucha en :{s['puerto_salud']}", "codigo": None}
    codigo = sondear_salud(s)
    if codigo is None:
        return {"estado": "arrancando", "detalle": f"{s['salud']} aún no responde", "codigo": None}
    if 200 <= codigo < 400 or codigo in (401, 403):
        return {"estado": "listo", "detalle": f"{s['salud']} responde HTTP {codigo}", "codigo": codigo}
    return {"estado": "arrancando", "detalle": f"{s['salud']} responde HTTP {codigo}", "codigo": codigo}


def vista_proyecto(p, en_escucha, activos=None, salud=False):
    servicios = []
    total_si = total = 0
    for s in p["servicios"]:
        puertos = [{"puerto": pt, "escucha": (pt in en_escucha) if en_escucha is not None else puerto_escucha(pt)}
                   for pt in s["puertos"]]
        n = sum(x["escucha"] for x in puertos)
        total_si += n
        total += len(puertos)
        estado = _estado_de(n, len(puertos))
        v = {"id": s["id"], "nombre": s["nombre"], "url": s["url"], "url_abrir": s["url_abrir"], "tipo": s["tipo"],
             "puertos": puertos, "estado": estado,
             "ocupado": candado(s["id"]).locked() or candado(p["id"]).locked()}
        if salud:
            v["salud"] = salud_servicio(s, puertos, estado)
        servicios.append(v)
    salida = {"id": p["id"], "nombre": p["nombre"], "descripcion": p["descripcion"], "carpeta": p["carpeta"],
              "rango": p["rango"], "nota": p["nota"], "resumen": p["resumen"], "repositorio": p["repositorio"],
              "conflictos": p["conflictos"], "servicios": servicios,
              "enrutamiento_activo": bool((p.get("enrutamiento") or {}).get("activo")),
              "estado": _estado_de(total_si, total) if total else "sin-servicios",
              "ocupado": candado(p["id"]).locked() or any(s["ocupado"] for s in servicios)}
    if activos is not None:
        salida["agentes_activos"] = activos.get(p["id"], 0)
    return salida


def estado_proyectos():
    reg = registro()
    en_escucha = puertos_en_escucha()
    activos = contar_activos(reg)
    return {"proyectos": [vista_proyecto(p, en_escucha, activos) for p in reg["proyectos"]],
            "reservados": reg["reservados"], "puerto_panel": reg["puerto_panel"], "cuentas": reg["cuentas"],
            "politica_rangos": reg["politica_rangos"], "simulacion": ESTADO["simular"], "hora": time.time()}


# ---------------------------------------------------------------- cuentas de GitHub

_registro_escritura = threading.Lock()


def _span_objeto(texto, inicio):
    """Índice justo después de la '}' que cierra el objeto JSON que abre en `inicio` (respeta cadenas)."""
    nivel, en_cadena, escape = 0, False, False
    for i in range(inicio, len(texto)):
        ch = texto[i]
        if en_cadena:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                en_cadena = False
        elif ch == '"':
            en_cadena = True
        elif ch == "{":
            nivel += 1
        elif ch == "}":
            nivel -= 1
            if nivel == 0:
                return i + 1
    raise ValueError("JSON sin cerrar")


def cambiar_cuenta(pid, cuenta):
    """Cambia `repositorio.cuenta` de un proyecto tocando solo ese valor en el texto (se conserva el formato del
    archivo), comprueba que el resultado sea exactamente el registro anterior con ese único cambio y lo escribe de
    forma atómica (temporal + os.replace). Nunca ejecuta nada contra GitHub."""
    with _registro_escritura:
        with open(REGISTRO, encoding="utf-8", newline="") as f:
            texto = f.read()
        datos = json.loads(texto)
        reg = validar_registro(datos)
        if pid not in reg["por_id"]:
            raise ValueError("Proyecto no encontrado en el registro.")
        if cuenta not in {c["id"] for c in reg["cuentas"]}:
            raise ValueError("Cuenta no permitida: usa una de la lista 'cuentas' del registro.")
        esperado = copy.deepcopy(datos)
        p = next(x for x in esperado["proyectos"] if x.get("id") == pid)
        if (p.get("repositorio") or {}).get("cuenta") == cuenta:
            return {"proyecto": pid, "cuenta": cuenta, "cambio": False}
        # Ubicar el objeto del proyecto dentro de la lista "proyectos" y, en él, su bloque "repositorio".
        lista = re.search(r'"proyectos"\s*:\s*\[', texto)
        m = re.compile(r'\{\s*"id"\s*:\s*' + re.escape(json.dumps(pid, ensure_ascii=False)) + r"\s*,").search(
            texto, lista.end() if lista else 0)
        if not m:
            raise RuntimeError("No se ubicó el proyecto en el archivo.")
        fin_p = _span_objeto(texto, m.start())
        bloque = texto[m.start():fin_p]
        nuevo_valor = json.dumps(cuenta, ensure_ascii=False)
        r = re.search(r'"repositorio"\s*:\s*\{', bloque)
        if r:
            fin_r = _span_objeto(bloque, r.end() - 1)
            sub = bloque[r.end() - 1:fin_r]
            sub2, n = re.subn(r'("cuenta"\s*:\s*)(null|"(?:[^"\\]|\\.)*")', lambda x: x.group(1) + nuevo_valor, sub, count=1)
            if n != 1:
                sub2 = sub[0] + f' "cuenta": {nuevo_valor},' + sub[1:]
            bloque2 = bloque[:r.end() - 1] + sub2 + bloque[fin_r:]
            p["repositorio"]["cuenta"] = cuenta
        else:
            # Sin bloque: se agrega después de "carpeta" con la sangría de esa línea.
            c = re.search(r'\n([ \t]*)"carpeta"\s*:\s*"(?:[^"\\]|\\.)*",', bloque)
            if not c:
                raise RuntimeError("No se encontró dónde agregar el repositorio.")
            fin_linea = "\r\n" if "\r\n" in texto else "\n"
            bloque2 = (bloque[:c.end()] + fin_linea + c.group(1) +
                       f'"repositorio": {{ "cuenta": {nuevo_valor}, "repo": null, "rama": null, "remotos": [] }},' +
                       bloque[c.end():])
            p["repositorio"] = {"cuenta": cuenta, "repo": None, "rama": None, "remotos": []}
        nuevo = texto[:m.start()] + bloque2 + texto[fin_p:]
        if json.loads(nuevo) != esperado:
            raise RuntimeError("La edición no produjo exactamente el cambio esperado; no se escribió nada.")
        validar_registro(json.loads(nuevo))
        temporal = REGISTRO.with_name(REGISTRO.name + f".{os.getpid()}.tmp")
        try:
            with open(temporal, "w", encoding="utf-8", newline="") as f:
                f.write(nuevo)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporal, REGISTRO)
        finally:
            try:
                temporal.unlink()
            except OSError:
                pass
    log(f"Cuenta de {pid} -> {cuenta}")
    return {"proyecto": pid, "cuenta": cuenta, "cambio": True}


# ---------------------------------------------------------------- GitHub CLI y credenciales por repo
# Solo se ejecutan argumentos fijos más ids de la lista 'cuentas' del registro o carpetas del registro; nunca texto
# libre ni shell. Nunca se lee ni se devuelve un token: de `gh auth status` solo se conservan cuentas y cuál está activa.

GH_EXE = os.environ.get("PANEL_GH_EXE") or shutil.which("gh") or (
    r"C:\Program Files\GitHub CLI\gh.exe" if os.name == "nt" else "/usr/bin/gh")
GH_HOST = "github.com"
CLAVE_USUARIO = "credential.https://github.com.username"
CLAVE_HELPER = "credential.https://github.com.helper"
HELPER_GH = '!"' + GH_EXE.replace("\\", "/") + '" auth git-credential'
INSTRUCCION_LOGIN = "gh auth login --hostname github.com --git-protocol https --web"
GH_CACHE_SEG = 10.0
_gh_cache = {"en": 0.0, "datos": None}
_gh_lock = threading.Lock()
_RE_GH_CUENTA = re.compile(r"(?:account|as)\s+([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\b")


def _sin_ventana():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _entorno_gh():
    e = dict(os.environ)
    e.update(GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1", NO_COLOR="1", GH_SPINNER_DISABLED="1")
    return e


def _git():
    return shutil.which("git") or "git"


def _comando_visible(cmd):
    return subprocess.list2cmdline(cmd)


def parsear_gh_status(texto):
    """Cuentas de github.com en la salida de `gh auth status`: [{"id", "activa", "ok"}]. Solo se miran las líneas
    'Logged in to … account X' / 'Failed to log in … account X' y '- Active account: true|false'; el resto (incluido
    cualquier token, aunque gh ya lo muestra enmascarado) se descarta."""
    cuentas, actual, en_host = [], None, False
    for linea in texto.splitlines():
        s = linea.strip()
        if s and not linea[:1].isspace() and not s.startswith(("✓", "X", "-", "!")):
            en_host = s.rstrip(":").lower() == GH_HOST  # cabecera de host
            continue
        if not en_host:
            continue
        if "Logged in to" in s or "Failed to log in" in s or "log in to" in s.lower():
            m = _RE_GH_CUENTA.search(s)
            if m:
                actual = {"id": m.group(1), "activa": False, "ok": "Logged in to" in s and not s.startswith("X")}
                cuentas.append(actual)
            else:
                actual = None
        elif actual is not None and re.match(r"^-\s*Active account:\s*true\b", s, re.I):
            actual["activa"] = True
    return cuentas


def estado_gh(forzar=False):
    with _gh_lock:
        if not forzar and _gh_cache["datos"] is not None and time.monotonic() - _gh_cache["en"] < GH_CACHE_SEG:
            return _gh_cache["datos"]
    if not Path(GH_EXE).is_file():
        datos = {"disponible": False, "cuentas": [], "activa": None, "error": f"No se encontró {GH_EXE}"}
    else:
        try:
            r = subprocess.run([GH_EXE, "auth", "status", "--hostname", GH_HOST], capture_output=True, timeout=15,
                               env=_entorno_gh(), creationflags=_sin_ventana())
            texto = (r.stdout + b"\n" + r.stderr).decode("utf-8", errors="replace")
            cuentas = parsear_gh_status(texto)
            activa = next((c["id"] for c in cuentas if c["activa"]), None)
            datos = {"disponible": True, "cuentas": cuentas, "activa": activa,
                     "error": None if cuentas else "gh no tiene cuentas de github.com autenticadas"}
        except (OSError, subprocess.TimeoutExpired) as e:
            datos = {"disponible": False, "cuentas": [], "activa": None, "error": f"No se pudo consultar gh: {type(e).__name__}"}
    with _gh_lock:
        _gh_cache.update(en=time.monotonic(), datos=datos)
    return datos


def _cuenta_permitida(reg, cuenta):
    if not isinstance(cuenta, str) or cuenta not in {c["id"] for c in reg["cuentas"]}:
        raise ValueError("Cuenta no permitida: usa una de la lista 'cuentas' del registro.")
    return cuenta


def usar_cuenta_gh(cuenta):
    """`gh auth switch` a una cuenta del registro que ya esté autenticada en gh. Si no lo está, no ejecuta nada y
    devuelve la instrucción para agregarla (la corre el usuario)."""
    reg = registro()
    _cuenta_permitida(reg, cuenta)
    gh = estado_gh(forzar=True)
    if not gh["disponible"]:
        return 503, {"ok": False, "error": gh["error"] or "GitHub CLI no disponible."}
    en_gh = next((c for c in gh["cuentas"] if c["id"].lower() == cuenta.lower()), None)
    if en_gh is None or not en_gh["ok"]:
        return 409, {"ok": False, "requiere_login": True, "cuenta": cuenta, "instruccion": INSTRUCCION_LOGIN,
                     "error": f"La cuenta {cuenta} no está autenticada en GitHub CLI. Agrégala tú en una terminal "
                              f"con «{INSTRUCCION_LOGIN}» (inicia sesión como {cuenta}) y vuelve a intentarlo."}
    if en_gh["activa"]:
        return 200, {"ok": True, "cambio": False, "cuenta": en_gh["id"], "mensaje": f"{en_gh['id']} ya es la cuenta activa."}
    cmd = [GH_EXE, "auth", "switch", "--hostname", GH_HOST, "--user", en_gh["id"]]
    if ESTADO["simular"]:
        log(f"gh auth switch {en_gh['id']} (simulación)")
        return 200, {"ok": True, "simulado": True, "cambio": False, "cuenta": en_gh["id"],
                     "comandos": [_comando_visible(cmd)], "mensaje": "Simulación: no se ejecutó nada."}
    c = candado("gh")
    if not c.acquire(blocking=False):
        return 409, {"ok": False, "error": "Ya hay un cambio de cuenta en curso."}
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30, env=_entorno_gh(), creationflags=_sin_ventana())
    except (OSError, subprocess.TimeoutExpired) as e:
        return 500, {"ok": False, "error": f"No se pudo ejecutar gh: {type(e).__name__}"}
    finally:
        c.release()
    salida = enmascarar((r.stdout + b"\n" + r.stderr).decode("utf-8", errors="replace").strip())[-1000:]
    log(f"gh auth switch {en_gh['id']} -> {r.returncode}")
    nuevo = estado_gh(forzar=True)
    return (200 if r.returncode == 0 else 500), {"ok": r.returncode == 0, "cambio": r.returncode == 0,
                                                  "cuenta": en_gh["id"], "activa": nuevo["activa"], "salida": salida}


def _git_leer(args, carpeta):
    try:
        r = subprocess.run([_git(), "-C", carpeta, *args], capture_output=True, timeout=10,
                           creationflags=_sin_ventana())
    except (OSError, subprocess.TimeoutExpired):
        return None, []
    return r.returncode, [x for x in r.stdout.decode("utf-8", errors="replace").splitlines() if x.strip()]


def modo_helper(valores):
    """'gcm' (Git Credential Manager), 'gh' (gh auth git-credential), 'otro' o 'ninguno'."""
    v = " ".join(valores).lower()
    if not v.strip():
        return "ninguno"
    if "manager" in v:
        return "gcm"
    if "gh" in v and "git-credential" in v:
        return "gh"
    return "otro"


def credencial_repo(pid):
    """Solo lectura: si la carpeta del proyecto es un repo git, qué cuenta tiene fijada en su config local y qué
    helper de credenciales usa el equipo."""
    reg = registro()
    if pid not in reg["por_id"]:
        raise KeyError(pid)
    p = reg["por_id"][pid]
    carpeta = p["carpeta"]
    base = {"proyecto": pid, "carpeta": carpeta, "es_repo": False, "raiz": None, "usuario": None,
            "helper_repo": [], "helper_efectivo": [], "modo": "ninguno",
            "cuenta_registro": (p["repositorio"] or {}).get("cuenta")}
    if not os.path.isdir(carpeta):
        return {**base, "motivo": "La carpeta del proyecto no existe."}
    codigo, raiz = _git_leer(["rev-parse", "--show-toplevel"], carpeta)
    if codigo != 0 or not raiz:
        return {**base, "motivo": "La carpeta no es un repositorio git."}
    _, usuario = _git_leer(["config", "--local", "--get", CLAVE_USUARIO], carpeta)
    _, helper_repo = _git_leer(["config", "--local", "--get-all", CLAVE_HELPER], carpeta)
    _, efectivo = _git_leer(["config", "--get-all", "credential.helper"], carpeta)
    _, efectivo_gh = _git_leer(["config", "--get-all", CLAVE_HELPER], carpeta)
    return {**base, "es_repo": True, "raiz": raiz[0], "usuario": usuario[-1] if usuario else None,
            "helper_repo": helper_repo, "helper_efectivo": efectivo + efectivo_gh,
            "modo": modo_helper(efectivo + efectivo_gh), "motivo": None}


def fijar_cuenta_repo(pid, cuenta):
    """`git config --local credential.https://github.com.username <cuenta>` en el repo del proyecto (y el helper de gh
    solo si el equipo ya usa gh como helper; con Git Credential Manager basta el usuario). No toca remotos."""
    reg = registro()
    if pid not in reg["por_id"]:
        raise KeyError(pid)
    _cuenta_permitida(reg, cuenta)
    estado = credencial_repo(pid)
    if not estado["es_repo"]:
        return 400, {"ok": False, "error": estado["motivo"] or "No es un repositorio git."}
    carpeta = estado["carpeta"]
    cmds = [[_git(), "-C", carpeta, "config", "--local", CLAVE_USUARIO, cuenta]]
    if estado["modo"] == "gh" and HELPER_GH not in estado["helper_repo"]:
        cmds.append([_git(), "-C", carpeta, "config", "--local", CLAVE_HELPER, HELPER_GH])
    if estado["usuario"] == cuenta and len(cmds) == 1:
        return 200, {"ok": True, "cambio": False, "usuario": cuenta, "mensaje": f"El repo ya usa {cuenta}."}
    visibles = [_comando_visible(c) for c in cmds]
    if ESTADO["simular"]:
        log(f"git config {pid} -> {cuenta} (simulación)")
        return 200, {"ok": True, "simulado": True, "cambio": False, "usuario": estado["usuario"],
                     "comandos": visibles, "mensaje": "Simulación: no se ejecutó nada."}
    c = candado("git-" + pid)
    if not c.acquire(blocking=False):
        return 409, {"ok": False, "error": "Ya hay un cambio en curso para este repo."}
    try:
        for cmd in cmds:
            r = subprocess.run(cmd, capture_output=True, timeout=10, creationflags=_sin_ventana())
            if r.returncode != 0:
                err = enmascarar(r.stderr.decode("utf-8", errors="replace").strip())[-500:]
                log(f"git config {pid} falló ({r.returncode})")
                return 500, {"ok": False, "error": "git config falló: " + (err or str(r.returncode))}
    except (OSError, subprocess.TimeoutExpired) as e:
        return 500, {"ok": False, "error": f"No se pudo ejecutar git: {type(e).__name__}"}
    finally:
        c.release()
    log(f"git config {pid} -> {cuenta}")
    return 200, {"ok": True, "cambio": True, "usuario": credencial_repo(pid)["usuario"], "comandos": visibles}


# ---------------------------------------------------------------- historial de Levantar/Apagar (persistente)

_acciones_lock = threading.Lock()
_acciones = {"datos": None}  # objetivo -> [entradas, la más reciente al final]


def archivo_acciones():
    return Path(ESTADO["estado_dir"]) / "acciones.json"


def _acciones_cargadas():
    if _acciones["datos"] is None:
        d = leer_json(archivo_acciones(), {})
        datos = {}
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(k, str) and _ID.match(k) and isinstance(v, list):
                    datos[k] = [e for e in v if isinstance(e, dict) and isinstance(e.get("salida"), str)][-MAX_ACCIONES_POR_OBJETIVO:]
        _acciones["datos"] = datos
    return _acciones["datos"]


def registrar_accion(objetivo, accion, ok, codigo, simulado, salida):
    e = {"fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "ts": round(time.time(), 3), "accion": accion, "ok": bool(ok),
         "codigo": codigo, "simulado": bool(simulado), "salida": enmascarar(salida or "")[-4000:]}
    with _acciones_lock:
        datos = _acciones_cargadas()
        lista = datos.setdefault(objetivo, [])
        lista.append(e)
        del lista[:-MAX_ACCIONES_POR_OBJETIVO]
        try:
            escribir_json_atomico(archivo_acciones(), datos)
        except OSError as ex:
            log(f"No se pudo guardar el historial de acciones: {ex}")
    return e


def historial_acciones(objetivo):
    """Entradas de un servicio o proyecto, la más reciente primero."""
    with _acciones_lock:
        return [dict(e) for e in reversed(_acciones_cargadas().get(objetivo, []))]


def resumen_acciones(ids):
    """{objetivo: {"ultima": entrada, "total": n}} para los ids dados (lo que muestra la tarjeta tras un reinicio)."""
    with _acciones_lock:
        datos = _acciones_cargadas()
        return {i: {"ultima": dict(datos[i][-1]), "total": len(datos[i])} for i in ids if datos.get(i)}


def ejecutar_accion(objetivo, accion):
    try:
        reg = registro()
    except ErrorRegistro as e:
        return 500, {"ok": False, "error": str(e)}
    if accion not in ACCIONES or (objetivo not in reg["por_id"] and objetivo not in reg["servicios"]):
        return 400, {"ok": False, "error": "Servicio, proyecto o acción no permitidos."}
    if objetivo in reg["por_id"] and not reg["por_id"][objetivo]["servicios"]:
        return 400, {"ok": False, "error": "Ese proyecto no tiene servicios que levantar."}
    # Solo se pasan argumentos fijos o ids de la lista blanca; nunca texto del usuario.
    cmd = [sys.executable, str(SERVICIOS_PY), "apagar" if accion == "apagar" else "levantar", objetivo,
           "--registro", str(REGISTRO)]
    if ESTADO["simular"]:
        cmd.append("--simular")
    proyecto = objetivo if objetivo in reg["por_id"] else reg["servicios"][objetivo][0]
    llaves = [candado(proyecto)] + ([candado(objetivo)] if objetivo != proyecto else [])
    tomadas = []
    for c in llaves:
        if not c.acquire(blocking=False):
            for t in tomadas:
                t.release()
            return 409, {"ok": False, "error": f"Ya hay una acción en curso para {proyecto}."}
        tomadas.append(c)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        texto = (r.stdout + b"\n" + r.stderr).decode("utf-8", errors="replace")
        texto = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", texto).strip()
        log(f"{accion} {objetivo} -> {r.returncode}" + (" (simulación)" if ESTADO["simular"] else ""))
        e = registrar_accion(objetivo, accion, r.returncode == 0, r.returncode, ESTADO["simular"], texto)
        return 200, {"ok": r.returncode == 0, "codigo": r.returncode, "simulado": ESTADO["simular"],
                     "salida": e["salida"], "registro": e}
    except subprocess.TimeoutExpired:
        e = registrar_accion(objetivo, accion, False, None, ESTADO["simular"], "La acción tardó más de 3 minutos.")
        return 504, {"ok": False, "error": e["salida"], "registro": e}
    except OSError as ex:
        e = registrar_accion(objetivo, accion, False, None, ESTADO["simular"], f"No se pudo ejecutar servicios.py:{ex}")
        return 500, {"ok": False, "error": e["salida"], "registro": e}
    finally:
        for t in tomadas:
            t.release()


# ---------------------------------------------------------------- agentes (transcripts de Claude Code)

def leer_cola(ruta):
    with open(ruta_os(ruta), "rb") as f:
        f.seek(0, os.SEEK_END)
        tam = f.tell()
        inicio = max(0, tam - COLA_BYTES)
        f.seek(inicio)
        datos = f.read()
    lineas = datos.split(b"\n")
    if inicio > 0:
        lineas = lineas[1:]  # la primera puede venir cortada
    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue
        try:
            yield json.loads(linea)
        except ValueError:
            continue


def analizar(ruta):
    """Extrae solo lo que se muestra: título, último texto del asistente, informe final y señales de estado.
    No se conservan nombres de herramientas, comandos ni tool_result."""
    titulo = ultimo_texto = hora_texto = informe = stop = cwd = None
    ultimo_rol = stop_ultimo = None
    pendientes, preguntas = set(), set()
    for o in leer_cola(ruta):
        tipo = o.get("type")
        if isinstance(o.get("cwd"), str) and o["cwd"]:
            cwd = o["cwd"]
        if tipo == "ai-title" and o.get("aiTitle"):
            titulo = o["aiTitle"]
        elif tipo == "summary" and o.get("summary") and not titulo:
            titulo = o["summary"]
        msg = o.get("message")
        if not isinstance(msg, dict) or tipo not in ("assistant", "user"):
            continue
        contenido = msg.get("content")
        ultimo_rol = tipo
        if tipo == "assistant":
            stop_ultimo = msg.get("stop_reason")
        if tipo == "assistant" and isinstance(contenido, list):
            stop = msg.get("stop_reason") or stop
            for b in contenido:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and (b.get("text") or "").strip():
                    ultimo_texto, hora_texto = b["text"], o.get("timestamp")
                elif b.get("type") == "tool_use":
                    if b.get("id"):
                        pendientes.add(b["id"])
                        if b.get("name") in HERRAMIENTAS_PREGUNTA:
                            preguntas.add(b["id"])  # solo el id: no se conservan nombres de herramientas
                    if b.get("name") == "SubagentHandback" and isinstance(b.get("input"), dict):
                        m = b["input"].get("message")
                        if isinstance(m, str) and m.strip():
                            informe = m
        elif tipo == "user" and isinstance(contenido, list):
            for b in contenido:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    pendientes.discard(b.get("tool_use_id"))
    if cwd is None:
        cwd = cwd_de_cabeza(ruta)
    return {"titulo": titulo, "texto": ultimo_texto, "hora_texto": hora_texto, "informe": informe,
            "stop": stop, "pendiente": bool(pendientes), "cwd": cwd, "ultimo_rol": ultimo_rol,
            "stop_ultimo": stop_ultimo, "pregunta": bool(preguntas & pendientes)}


def cwd_de_cabeza(ruta, limite=256 * 1024):
    """Si la cola no trae `cwd`, lo busca en las primeras líneas del transcript (valor exacto, sin derivarlo)."""
    try:
        with open(ruta_os(ruta), "rb") as f:
            datos = f.read(limite)
    except OSError:
        return None
    lineas = datos.split(b"\n")
    if len(datos) == limite:
        lineas = lineas[:-1]  # la última puede venir cortada
    for linea in lineas:
        try:
            o = json.loads(linea)
        except ValueError:
            continue
        if isinstance(o, dict) and isinstance(o.get("cwd"), str) and o["cwd"]:
            return o["cwd"]
    return None


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CWD_VALIDO = re.compile(r"^(?:[A-Za-z]:\\|\\\\)[^\x00-\x1f\x7f]*$")


def _cd_powershell(cwd):
    """Línea `cd` para pegar en la terminal: PowerShell para una ruta absoluta de Windows y shell POSIX (comillas
    simples) para una ruta absoluta de macOS/Linux; None si la ruta no es absoluta o trae caracteres de control."""
    if isinstance(cwd, str) and cwd.startswith("/") and len(cwd) <= 1024 and not re.search(r"[\x00-\x1f\x7f]", cwd):
        return "cd '" + cwd.replace("'", "'\\''") + "'"
    if not isinstance(cwd, str) or not _CWD_VALIDO.match(cwd) or len(cwd) > 1024:
        return None
    # Dentro de comillas dobles de PowerShell son especiales: ` " $ y las comillas tipográficas dobles.
    citado = re.sub(r'([`"$“”„])', r"`\1", cwd)
    return f'cd "{citado}"'


def comando_retomar(cwd, sesion):
    """Comando de PowerShell (solo se muestra y se copia; el panel nunca lo ejecuta) para retomar una sesión."""
    if not isinstance(sesion, str) or not _UUID.match(sesion):
        return {"cwd": None, "comando": None, "motivo": "id de sesión no válido"}
    cd = _cd_powershell(cwd)
    if cd is None:
        return {"cwd": None, "comando": None, "motivo": "directorio desconocido"}
    return {"cwd": cwd, "comando": f"{cd}\nclaude --resume {sesion}", "motivo": None}


def comando_iniciar(cwd):
    """Comando de PowerShell (solo se muestra y se copia) para abrir una conversación nueva en la carpeta del proyecto."""
    cd = _cd_powershell(cwd)
    if cd is None:
        return {"cwd": None, "comando": None, "motivo": "carpeta del proyecto no válida"}
    return {"cwd": cwd, "comando": f"{cd}\nclaude", "motivo": None}


def analizar_con_cache(ruta, st):
    clave = str(ruta)
    with _cache_lock:
        c = _cache.get(clave)
        if c and c[0] == st.st_mtime and c[1] == st.st_size:
            return c[2]
    try:
        r = analizar(ruta)
    except OSError:
        return None
    with _cache_lock:
        _cache[clave] = (st.st_mtime, st.st_size, r)
    return r


def _scandir(ruta):
    try:
        with os.scandir(ruta_os(ruta)) as it:
            return list(it)
    except OSError:
        return []


def _stat(ruta):
    try:
        return os.stat(ruta_os(ruta))
    except OSError:
        return None


def descubrir(reg, proyecto=None, horas=6.0):
    """[(ruta, stat, info)] de transcripts modificados en las últimas `horas`, asignados a proyectos del registro.
    Si se da `proyecto`, solo se recorren las carpetas que le pertenecen."""
    limite = time.time() - horas * 3600
    hallados, vistos = [], set()

    def considerar(ruta, info):
        st = _stat(ruta)
        if st and st.st_mtime >= limite and st.st_size > 0:
            hallados.append((ruta, st, info))

    if PROYECTOS_CLAUDE.is_dir():
        for carpeta in _scandir(PROYECTOS_CLAUDE):
            if not carpeta.is_dir():
                continue
            pid = proyecto_de_carpeta(carpeta.name, reg)
            if pid is None or (proyecto and pid != proyecto):
                continue
            base = PROYECTOS_CLAUDE / carpeta.name
            for e in _scandir(base):
                if e.is_file() and e.name.endswith(".jsonl"):
                    considerar(base / e.name, {"tipo": "sesion", "proyecto": pid, "sesion": e.name[:-6]})
                elif e.is_dir():
                    subs = base / e.name / "subagents"
                    for a in _scandir(subs):
                        if a.name.startswith("agent-") and a.name.endswith(".jsonl"):
                            agente = a.name[6:-6]
                            vistos.add(agente)
                            considerar(subs / a.name, {"tipo": "subagente", "proyecto": pid,
                                                       "sesion": e.name, "agente": agente})
    if TEMP_CLAUDE.is_dir():
        for carpeta in _scandir(TEMP_CLAUDE):
            if not carpeta.is_dir():
                continue
            pid = proyecto_de_carpeta(carpeta.name, reg)
            if pid is None or (proyecto and pid != proyecto):
                continue
            for e in _scandir(TEMP_CLAUDE / carpeta.name):
                if not e.is_dir():
                    continue
                tareas = TEMP_CLAUDE / carpeta.name / e.name / "tasks"
                # tasks\a*.output = transcripts JSONL de subagentes (b*.output son salidas de Bash).
                for a in _scandir(tareas):
                    if a.name.startswith("a") and a.name.endswith(".output") and a.name[:-7] not in vistos:
                        considerar(tareas / a.name, {"tipo": "subagente", "proyecto": pid,
                                                     "sesion": e.name, "agente": a.name[:-7]})
    hallados.sort(key=lambda x: x[1].st_mtime, reverse=True)
    return hallados


def contar_activos(reg):
    cuenta = {}
    for _, _, info in descubrir(reg, horas=ACTIVO_SEG / 3600):
        cuenta[info["proyecto"]] = cuenta.get(info["proyecto"], 0) + 1
    return cuenta


def leer_meta(ruta):
    meta = Path(str(ruta)[: -len(".jsonl")] + ".meta.json")
    try:
        with open(ruta_os(meta), encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def estado_de_agente(info, r, hace):
    if hace <= ACTIVO_SEG:
        return "activo", "Trabajando"
    if info["tipo"] == "subagente":
        if r["informe"] or r["stop"] == "end_turn":
            return "terminado", "Entregó su informe"
        if r["pendiente"] and hace <= ESPERA_SUBAGENTE_SEG:
            return "esperando", "Esperando una herramienta o un permiso"
        return "terminado", "Sin actividad reciente"
    if hace <= ESPERA_SESION_SEG:
        if r["pendiente"]:
            return "esperando", "Esperando un permiso o una herramienta"
        if r["stop"] == "end_turn":
            return "esperando", "Esperando tu respuesta"
    return "terminado", "Sin actividad reciente"


def estado_agentes(proyecto, horas):
    reg = registro()
    if proyecto not in reg["por_id"]:
        raise KeyError(proyecto)
    ahora = time.time()
    salida = []
    for ruta, st, info in descubrir(reg, proyecto=proyecto, horas=horas)[:MAX_TRANSCRIPTS]:
        r = analizar_con_cache(ruta, st)
        if r is None:
            continue
        meta = leer_meta(ruta) if info["tipo"] == "subagente" else {}
        hace = max(0, ahora - st.st_mtime)
        estado, detalle = estado_de_agente(info, r, hace)
        informe = r["informe"]
        explicacion = r["texto"]
        if not informe and info["tipo"] == "subagente" and estado == "terminado" and r["stop"] == "end_turn":
            informe, explicacion = explicacion, None  # su último texto es el informe final
        if informe and explicacion and explicacion.strip() == informe.strip():
            explicacion = None
        descripcion = meta.get("description") or r["titulo"] or (
            "Sesión " + info["sesion"][:8] if info["tipo"] == "sesion" else "Subagente " + info.get("agente", "")[:8])
        salida.append({
            "id": hashlib.sha1(str(ruta).encode("utf-8")).hexdigest()[:16],
            "tipo": info["tipo"],
            "tipo_agente": corto(meta.get("agentType") or "", 60) or None,
            "descripcion": corto(descripcion, 160),
            "sesion": info["sesion"][:8],
            "estado": estado,
            "estado_detalle": detalle,
            "hace_seg": int(hace),
            "explicacion": recortar(explicacion, MAX_EXPLICACION) if explicacion else None,
            "hora_explicacion": r["hora_texto"],
            "informe": recortar(informe, MAX_INFORME) if informe else None,
            "retomar": comando_retomar(r["cwd"], info["sesion"]) if info["tipo"] == "sesion" else None,
        })
    vigentes = {str(x[0]) for x in descubrir(reg, horas=72)} if len(_cache) > 400 else None
    if vigentes is not None:
        with _cache_lock:
            for k in [k for k in _cache if k not in vigentes]:
                del _cache[k]
    return {"proyecto": proyecto, "agentes": salida, "horas": horas, "hora": ahora}


def sesiones_para_retomar(proyecto, limite=25):
    """Sesiones principales del proyecto ordenadas por actividad, sin limitarse a la ventana de horas."""
    reg = registro()
    if proyecto not in reg["por_id"]:
        raise KeyError(proyecto)
    ahora = time.time()
    salida = []
    for ruta, st, info in descubrir(reg, proyecto=proyecto, horas=24 * 3650):
        if info["tipo"] != "sesion":
            continue
        r = analizar_con_cache(ruta, st)
        if r is None:
            continue
        salida.append({"id": hashlib.sha1(str(ruta).encode("utf-8")).hexdigest()[:16],
                       "titulo": corto(r["titulo"] or ("Sesión " + info["sesion"][:8]), 160),
                       "hace_seg": int(max(0, ahora - st.st_mtime)), "activa": ahora - st.st_mtime <= ACTIVO_SEG,
                       **comando_retomar(r["cwd"], info["sesion"])})
        if len(salida) >= limite:
            break
    return {"proyecto": proyecto, "sesiones": salida, "iniciar": comando_iniciar(reg["por_id"][proyecto]["carpeta"])}


MAX_RECIENTES = 20
RECIENTES_CACHE_SEG = 15.0
_recientes_cache = {"en": 0.0, "datos": None}
_recientes_lock = threading.Lock()
_RE_MARCAS_MD = re.compile(r"(?m)^\s*#{1,6}\s+|\*\*|`+|^\s*[-*]\s+|^\s*>\s?|\|")  # la tarjeta muestra texto plano


def sesiones_recientes(limite=MAX_RECIENTES):
    """Sesiones principales de todos los proyectos del registro, más recientes primero. Cada transcript se lee solo
    por su cola (COLA_BYTES) y con la caché por mtime/tamaño; el resultado completo se reutiliza unos segundos."""
    with _recientes_lock:
        if _recientes_cache["datos"] is not None and time.monotonic() - _recientes_cache["en"] < RECIENTES_CACHE_SEG:
            return _recientes_cache["datos"]
    reg = registro()
    ahora = time.time()
    salida = []
    for ruta, st, info in descubrir(reg, horas=24 * 3650):
        if info["tipo"] != "sesion":
            continue
        r = analizar_con_cache(ruta, st)
        if r is None:
            continue
        hace = max(0, ahora - st.st_mtime)
        estado, detalle = estado_de_agente(info, r, hace)
        p = reg["por_id"][info["proyecto"]]
        salida.append({"id": hashlib.sha1(str(ruta).encode("utf-8")).hexdigest()[:16],
                       "titulo": corto(r["titulo"] or ("Sesión " + info["sesion"][:8]), 160),
                       "proyecto": p["id"], "proyecto_nombre": p["nombre"],
                       "hace_seg": int(hace), "estado": estado, "estado_detalle": detalle,
                       "explicacion": corto(_RE_MARCAS_MD.sub(" ", r["texto"]), 320) if r["texto"] else None,
                       "retomar": comando_retomar(r["cwd"], info["sesion"])})
        if len(salida) >= limite:
            break
    datos = {"sesiones": salida, "hora": ahora}
    with _recientes_lock:
        _recientes_cache.update(en=time.monotonic(), datos=datos)
    return datos


# ---------------------------------------------------------------- centro de avisos (persistente)

_RE_ID_AVISO = re.compile(r"^[0-9a-f]{16}$")
_avisos_lock = threading.Lock()
_avisos = {"lista": None, "n": 0, "epoca": secrets.token_hex(4)}  # lista: más viejo primero


def archivo_avisos():
    return Path(ESTADO["estado_dir"]) / "avisos.json"


def _avisos_cargados():
    if _avisos["lista"] is None:
        d = leer_json(archivo_avisos(), {})
        lista = d.get("avisos") if isinstance(d, dict) else None
        _avisos["lista"] = [a for a in (lista or []) if isinstance(a, dict) and isinstance(a.get("id"), str)
                            and _RE_ID_AVISO.match(a["id"])][-MAX_AVISOS:]
    return _avisos["lista"]


def _guardar_avisos():
    """Se llama con _avisos_lock tomado."""
    _avisos["n"] += 1
    try:
        escribir_json_atomico(archivo_avisos(), {"version": 1, "avisos": _avisos["lista"]})
    except OSError as e:
        log(f"No se pudieron guardar los avisos: {e}")


def version_avisos():
    return f"{_avisos['epoca']}.{_avisos['n']}"


def agregar_avisos(nuevos):
    with _avisos_lock:
        lista = _avisos_cargados()
        claves = {a.get("clave") for a in lista}
        agregados = [a for a in nuevos if a["clave"] not in claves]
        if not agregados:
            return 0
        lista.extend(agregados)
        del lista[:-MAX_AVISOS]
        _guardar_avisos()
    for a in agregados:
        log(f"Aviso: {a['proyecto']} · {a['tipo']} · {a['estado']}")
    return len(agregados)


def consultar_avisos(proyecto=None, pagina=0, limite=50, version=None):
    """Página de avisos (más recientes primero) con contadores. Si `version` coincide, solo dice que no hubo cambios."""
    with _avisos_lock:
        v = version_avisos()
        if version is not None and version == v:
            return {"ok": True, "version": v, "sin_cambios": True}
        lista = _avisos_cargados()
        nombres, por_proyecto = {}, {}
        for a in lista:
            x = por_proyecto.setdefault(a["proyecto"], [0, 0])
            x[0] += 1
            x[1] += 0 if a.get("leido") else 1
            nombres[a["proyecto"]] = a.get("proyecto_nombre") or a["proyecto"]
        filtrados = [a for a in lista if not proyecto or a["proyecto"] == proyecto]
        filtrados.reverse()
        pagina_l = [{k: val for k, val in a.items() if k != "clave"} for a in filtrados[pagina * limite:(pagina + 1) * limite]]
        return {"ok": True, "version": v, "avisos": pagina_l, "pagina": pagina, "limite": limite,
                "total": len(filtrados), "hay_mas": (pagina + 1) * limite < len(filtrados),
                "no_leidos": sum(1 for a in lista if not a.get("leido")),
                "ts_max": max((a.get("ts") or 0 for a in lista), default=0),
                "proyectos": [{"id": k, "nombre": nombres[k], "total": n[0], "no_leidos": n[1]}
                              for k, n in sorted(por_proyecto.items(), key=lambda x: nombres[x[0]].lower())],
                "hora": time.time()}


def marcar_avisos_leidos(ids=None, hasta=None):
    """ids=None marca todos (o solo los de ts <= `hasta`: lo que el usuario alcanzó a ver; un aviso que llegó después
    sigue sin leer). Devuelve cuántos cambiaron."""
    with _avisos_lock:
        cambiados = 0
        for a in _avisos_cargados():
            if hasta is not None and (a.get("ts") or 0) > hasta:
                continue
            if (ids is None or a["id"] in ids) and not a.get("leido"):
                a["leido"] = True
                cambiados += 1
        if cambiados:
            _guardar_avisos()
        return cambiados


def borrar_avisos(aviso_id=None):
    """aviso_id=None borra todos. Devuelve cuántos se borraron."""
    with _avisos_lock:
        lista = _avisos_cargados()
        antes = len(lista)
        lista[:] = [] if aviso_id is None else [a for a in lista if a["id"] != aviso_id]
        borrados = antes - len(lista)
        if borrados:
            _guardar_avisos()
        return borrados


def evento_final(info, r):
    """(estado, detalle) si el transcript, ya quieto, quedó terminado o esperando al usuario; None si no."""
    if r.get("pregunta"):
        return "espera", "Te hizo una pregunta y espera tu respuesta"
    fin_de_turno = r.get("ultimo_rol") == "assistant" and r.get("stop_ultimo") in STOP_FINAL and not r["pendiente"]
    if info["tipo"] == "subagente":
        if r["informe"] or fin_de_turno:
            return "termino", "Entregó su informe final"
        return None
    if fin_de_turno:
        return "termino", "Terminó su turno; espera tu respuesta"
    return None


def construir_aviso(ruta, info, r, estado, detalle, reg):
    p = reg["por_id"][info["proyecto"]]
    meta = leer_meta(ruta) if info["tipo"] == "subagente" else {}
    descripcion = meta.get("description") or r["titulo"] or (
        "Sesión " + info["sesion"][:8] if info["tipo"] == "sesion" else "Subagente " + info.get("agente", "")[:8])
    texto = r["informe"] if info["tipo"] == "subagente" and r["informe"] else r["texto"]
    clave = hashlib.sha1(f"{ruta}|{estado}|{r.get('hora_texto')}|{len(r['informe'] or '')}|{len(r['texto'] or '')}"
                         .encode("utf-8")).hexdigest()[:24]
    return {"id": secrets.token_hex(8), "clave": clave, "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ts": round(time.time(), 3), "proyecto": p["id"], "proyecto_nombre": p["nombre"], "tipo": info["tipo"],
            "tipo_agente": corto(meta.get("agentType") or "", 60) or None, "descripcion": corto(descripcion, 160),
            "estado": estado, "detalle": detalle,
            "resumen": corto(_RE_MARCAS_MD.sub(" ", texto), MAX_RESUMEN_AVISO) if texto else "",
            "sesion": info["sesion"] if _UUID.match(info["sesion"]) else None,
            "retomar": comando_retomar(r["cwd"], info["sesion"]), "leido": False}


_detector = {"vistos": {}, "claves": {}, "base": False, "hilo": None}


def ciclo_detector():
    """Una pasada del detector. Reutiliza `descubrir` (solo stat) y `analizar_con_cache` (cola + caché por mtime/tamaño):
    un transcript se lee únicamente cuando lleva un ciclo sin cambiar (los que se están escribiendo no se leen) y una
    sola vez por versión. La primera pasada solo toma la base: no lee ni genera avisos por eventos viejos."""
    reg = registro()
    vistos, claves = _detector["vistos"], _detector["claves"]
    base = not _detector["base"]
    actuales, nuevos = set(), []
    for ruta, st, info in descubrir(reg, horas=DETECTOR_HORAS):
        k = str(ruta)
        actuales.add(k)
        sig = (st.st_mtime, st.st_size)
        v = vistos.get(k)
        if base:
            vistos[k] = {"sig": sig, "listo": True}
            continue
        if v is None or v["sig"] != sig:
            vistos[k] = {"sig": sig, "listo": False}  # nuevo o cambiando: se espera a que se quede quieto
            continue
        if v["listo"]:
            continue
        v["listo"] = True
        r = analizar_con_cache(ruta, st)
        if r is None:
            continue
        ev = evento_final(info, r)
        if ev is None:
            continue
        aviso = construir_aviso(ruta, info, r, ev[0], ev[1], reg)
        if claves.get(k) == aviso["clave"]:
            continue
        claves[k] = aviso["clave"]
        nuevos.append(aviso)
    for k in [k for k in vistos if k not in actuales]:
        del vistos[k]
        claves.pop(k, None)
    _detector["base"] = True
    return agregar_avisos(nuevos) if nuevos else 0


def hilo_detector():
    while True:
        try:
            ciclo_detector()
        except ErrorRegistro:
            pass  # el registro inválido ya se reporta en la interfaz
        except Exception as e:  # el detector nunca debe tumbar el panel
            log(f"Detector de avisos: {type(e).__name__}: {e}")
        time.sleep(DETECTOR_SEG)


def iniciar_detector():
    if _detector["hilo"] is None:
        _detector["hilo"] = threading.Thread(target=hilo_detector, name="detector-avisos", daemon=True)
        _detector["hilo"].start()


# ---------------------------------------------------------------- Laboratorio

class RutaArchivoSegura:
    """Valida un nombre de archivo recibido del navegador: solo un nombre simple (sin separadores ni '..'),
    sin caracteres prohibidos ni nombres reservados de Windows. El archivo NUNCA se guarda con este nombre:
    solo se registra en solicitud.json; en disco se usa un nombre generado."""

    _PROHIBIDOS = set('<>:"/\\|?*')
    _RESERVADOS = ({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
                   | {f"COM{i}" for i in "123456789¹²³"} | {f"LPT{i}" for i in "123456789¹²³"})

    def __init__(self, nombre):
        if not isinstance(nombre, str):
            raise ValueError("El nombre del archivo debe ser texto.")
        n = unicodedata.normalize("NFC", nombre)
        if not 1 <= len(n) <= 150:
            raise ValueError("El nombre del archivo debe tener entre 1 y 150 caracteres.")
        if any(ord(c) < 32 or ord(c) == 127 or c in self._PROHIBIDOS for c in n):
            raise ValueError("El nombre contiene separadores de ruta o caracteres no permitidos.")
        if ".." in n or n in (".",):
            raise ValueError("El nombre no puede contener '..'.")
        if n != n.strip() or n.endswith("."):
            raise ValueError("El nombre no puede empezar o terminar con espacios ni terminar en punto.")
        base = n.split(".")[0].strip().upper()
        if base in self._RESERVADOS:
            raise ValueError("Ese nombre está reservado por Windows.")
        self.nombre = n
        ext = os.path.splitext(n)[1].lower()
        self.extension = ext if re.fullmatch(r"\.[a-z0-9]{1,10}", ext) else ""


def validar_enlace(url):
    if not isinstance(url, str) or not 8 <= len(url) <= 2048:
        raise ValueError("El enlace debe tener entre 8 y 2048 caracteres.")
    if any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("El enlace no puede tener espacios ni caracteres de control.")
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise ValueError("Solo se aceptan enlaces http o https.")
    if u.username or u.password:
        raise ValueError("El enlace no puede llevar usuario ni contraseña.")
    host = (u.hostname or "").lower()
    if not host or not re.fullmatch(r"[a-z0-9.\-\[\]:]+", host):
        raise ValueError("El enlace no tiene un dominio válido.")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("No se aceptan enlaces a equipos locales.")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            raise ValueError("No se aceptan enlaces a direcciones privadas o locales.")
    except ValueError as e:
        if "No se aceptan" in str(e):
            raise
    return url


def carpeta_lab(*partes):
    return Path(ESTADO["laboratorio"]).joinpath(*partes)


_ID_SOLICITUD = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def nuevo_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def validar_meta_lab(d, reg):
    if not isinstance(d, dict):
        raise ValueError("Datos inválidos.")
    if d.get("confirmo") is not True:
        raise ValueError("Debes marcar la casilla de confirmación (software propio, autorizado o de código "
                         "abierto, y solo análisis estático).")
    pid = d.get("proyecto")
    if not isinstance(pid, str) or pid not in reg["por_id"]:
        raise ValueError("Elige un proyecto destino del registro.")
    objetivo = d.get("objetivo")
    if objetivo not in OBJETIVOS_LAB:
        raise ValueError("Elige el objetivo del análisis.")
    notas = d.get("notas") or ""
    if not isinstance(notas, str) or len(notas) > 2000:
        raise ValueError("Las notas deben ser texto de máximo 2000 caracteres.")
    return reg["por_id"][pid], objetivo, notas.strip()


def node_version():
    if ESTADO["node"] is None:
        try:
            r = subprocess.run(["node", "--version"], capture_output=True, timeout=5,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            ESTADO["node"] = r.stdout.decode("ascii", errors="replace").strip().lstrip("v") or "desconocida"
        except (OSError, subprocess.TimeoutExpired):
            ESTADO["node"] = "no encontrada"
    return ESTADO["node"]


def node_suficiente(v):
    try:
        return tuple(int(x) for x in v.split(".")[:3]) >= NODE_MINIMO
    except ValueError:
        return False


def generar_prompt(sol):
    ruta = carpeta_lab("solicitudes", sol["id"])
    resultado = ruta / "resultado"
    p = sol["proyecto"]
    if sol["fuente"]["tipo"] == "enlace":
        fuente = (f"- Enlace: {sol['fuente']['url']}\n"
                  "  (el panel NO lo visitó; trátalo como no confiable. Puedes obtener el código fuente o el paquete "
                  "para leerlo, pero nunca lo instales, compiles ni ejecutes, y no corras sus scripts de instalación: "
                  "usa `--ignore-scripts` o descarga el archivo sin instalarlo.)")
    else:
        f = sol["fuente"]
        fuente = (f"- Archivo subido: {f['ruta']}\n"
                  f"  Nombre original: {f['nombre_original']} · {f['tamano']} bytes · SHA-256 {f['sha256']}\n"
                  "  (guardado con nombre generado y sin ejecutar; si es un comprimido, puedes listar su contenido o "
                  f"extraerlo solo dentro de {resultado}\\_extraido validando rutas, y nunca ejecutar nada de ahí.)")
    if sol["objetivo"] == "backlog":
        entregable = f"""2. `BACKLOG.md`: propuesta de elementos de backlog para **{p['nombre']}** con el formato del método DevSkills,
   para que el orquestador del proyecto la incorpore con `devskills:planear-entregas` (tú NO edites el plan ni el SRS).
   Un bloque por elemento:

   ```
   ### HU-xx (propuesta) — <título corto>      (usa EN-xx si es un habilitador técnico)
   - Módulo: <módulo del proyecto destino>
   - Puntos estimados: <1, 2, 3, 5, 8 o 13>
   - Dependencias: <HU/EN de las que depende, o "ninguna">
   - Evidencia: <qué parte del objetivo analizado lo inspira (ruta:línea o pantalla)>
   - Historia: Como <rol> quiero <capacidad> para <beneficio>.
   - Gherkin:
     Escenario: <nombre>
       Dado <contexto>
       Cuando <acción>
       Entonces <resultado observable>
   ```
   Lee antes `documentacion/CONTEXTO.md`, el SRS y el PLAN del proyecto destino (si existen) para no duplicar lo que ya está."""
    else:
        entregable = """2. `CATALOGO.md`: catálogo de fragmentos o componentes reutilizables para proyectos inhouse. Por cada uno:
   nombre, qué resuelve, origen exacto (ruta y líneas o módulo), **licencia** y si permite reutilizarlo,
   dependencias y una adaptación sugerida a nuestro stack. No copies código cuya licencia no lo permita
   (sin licencia = todos los derechos reservados: solo describe la idea, sin copiar el código)."""
    return f"""# Solicitud de ingeniería inversa {sol['id']}

Proyecto destino: **{p['nombre']}** (`{p['id']}`) — carpeta `{p['carpeta']}`
Objetivo: **{OBJETIVOS_LAB[sol['objetivo']]}**
Creada: {sol['creada']}

## Fuente a analizar
{fuente}

## Reglas obligatorias
- El usuario confirmó: "{TEXTO_CONFIRMACION}"
- Usa el servidor MCP de REA (`rea-agents`) **solo con análisis estático**. Si el servidor `rea-agents` no está
  disponible en esta sesión, DETENTE y avisa al usuario (requiere Node >= 24.22.1 y `npx rea-agents setup`);
  no lo sustituyas ejecutando el objetivo.
- Nunca ejecutes, instales, compiles ni abras en un navegador el objetivo; no hagas captura en ejecución
  (tráfico, depuración, hooks, instrumentación) ni análisis dinámico de ningún tipo.
- Verifica y registra la **licencia** (archivo LICENSE, metadatos del paquete, encabezados SPDX). Si no hay licencia,
  trátalo como "todos los derechos reservados".
- **No modifiques ningún repositorio** (ni el proyecto destino ni el objetivo). Escribe únicamente dentro de
  `{resultado}`.
- No incluyas secretos, credenciales ni datos personales que encuentres; menciónalos solo como hallazgo, enmascarados.
{('- Notas del usuario: ' + sol['notas']) if sol.get('notas') else ''}

## Entregables (en `{resultado}`)
1. `INFORME.md`: cómo funciona el objetivo, con evidencias (rutas, líneas, símbolos, salidas de REA): propósito,
   arquitectura y módulos, flujos principales, datos y formatos, dependencias, licencia verificada y riesgos.
{entregable}
3. Al final de `INFORME.md`, una sección "Límites del análisis" con lo que no se pudo verificar de forma estática.

Cuando termines, responde con un resumen breve y la lista de archivos creados.
"""


def guardar_solicitud(sol):
    ruta = carpeta_lab("solicitudes", sol["id"])
    (ruta / "resultado").mkdir(parents=True, exist_ok=False)
    (ruta / "solicitud.json").write_text(json.dumps(sol, ensure_ascii=False, indent=2), encoding="utf-8")
    (ruta / "PROMPT.md").write_text(generar_prompt(sol), encoding="utf-8")
    log(f"Laboratorio: solicitud {sol['id']} ({sol['fuente']['tipo']}) para {sol['proyecto']['id']}")
    return respuesta_solicitud(sol)


def comando_lanzar(sol):
    prompt = carpeta_lab("solicitudes", sol["id"]) / "PROMPT.md"
    carpeta = sol["proyecto"]["carpeta"].replace("'", "''")
    instruccion = f"Lee el archivo {prompt} y ejecútalo al pie de la letra."
    return {"comando": f"Set-Location -LiteralPath '{carpeta}'; claude '{instruccion.replace(chr(39), chr(39) * 2)}'",
            "instruccion": instruccion, "prompt": str(prompt)}


def respuesta_solicitud(sol):
    ruta = carpeta_lab("solicitudes", sol["id"])
    resultado = ruta / "resultado"
    archivos = [a for a in ARCHIVOS_RESULTADO if (resultado / a).is_file()]
    return {"id": sol["id"], "creada": sol["creada"], "proyecto": sol["proyecto"]["id"],
            "proyecto_nombre": sol["proyecto"]["nombre"], "objetivo": sol["objetivo"],
            "objetivo_texto": OBJETIVOS_LAB.get(sol["objetivo"], ""),
            "fuente": ({"tipo": "enlace", "url": sol["fuente"]["url"]} if sol["fuente"]["tipo"] == "enlace"
                       else {"tipo": "archivo", "nombre": sol["fuente"]["nombre_original"],
                             "tamano": sol["fuente"]["tamano"]}),
            "estado": "con resultado" if "INFORME.md" in archivos else "pendiente",
            "archivos": archivos, "carpeta": str(ruta), **comando_lanzar(sol)}


def crear_solicitud_enlace(d, reg):
    p, objetivo, notas = validar_meta_lab(d, reg)
    url = validar_enlace(d.get("enlace"))
    sol = {"id": nuevo_id(), "creada": time.strftime("%Y-%m-%d %H:%M:%S"), "objetivo": objetivo, "notas": notas,
           "proyecto": {"id": p["id"], "nombre": p["nombre"], "carpeta": p["carpeta"]},
           "fuente": {"tipo": "enlace", "url": url}, "confirmacion": TEXTO_CONFIRMACION,
           "analisis": "estático (REA, rea-agents)"}
    return guardar_solicitud(sol)


def recibir_archivo(rfile, largo, d, reg):
    """Guarda el cuerpo en entrada\\<fecha>_<id>\\ con nombre generado. Nunca lo ejecuta ni lo descomprime."""
    p, objetivo, notas = validar_meta_lab(d, reg)
    seguro = RutaArchivoSegura(d.get("nombre"))
    sid = nuevo_id()
    destino_dir = carpeta_lab("entrada", f"{time.strftime('%Y%m%d')}_{sid}")
    destino_dir.mkdir(parents=True, exist_ok=False)
    destino = destino_dir / f"muestra_{sid}.bin"
    parcial = destino_dir / f"muestra_{sid}.parcial"
    h = hashlib.sha256()
    recibidos = 0
    try:
        with open(parcial, "wb") as f:
            while recibidos < largo:
                bloque = rfile.read(min(1024 * 1024, largo - recibidos))
                if not bloque:
                    break
                f.write(bloque)
                h.update(bloque)
                recibidos += len(bloque)
        if recibidos != largo:
            raise ValueError("La subida se interrumpió.")
        os.replace(parcial, destino)
    except BaseException:
        for x in (parcial, destino):
            try:
                x.unlink()
            except OSError:
                pass
        try:
            destino_dir.rmdir()
        except OSError:
            pass
        raise
    try:  # Marca de "descargado de Internet" para que Windows advierta si alguien intenta abrirlo.
        with open(str(destino) + ":Zone.Identifier", "w", encoding="ascii") as f:
            f.write("[ZoneTransfer]\r\nZoneId=3\r\n")
    except OSError:
        pass
    sol = {"id": sid, "creada": time.strftime("%Y-%m-%d %H:%M:%S"), "objetivo": objetivo, "notas": notas,
           "proyecto": {"id": p["id"], "nombre": p["nombre"], "carpeta": p["carpeta"]},
           "fuente": {"tipo": "archivo", "nombre_original": seguro.nombre, "extension_original": seguro.extension,
                      "tamano": recibidos, "sha256": h.hexdigest(), "ruta": str(destino)},
           "confirmacion": TEXTO_CONFIRMACION, "analisis": "estático (REA, rea-agents)"}
    return guardar_solicitud(sol)


def listar_solicitudes():
    salida = []
    for e in _scandir(carpeta_lab("solicitudes")):
        if not (e.is_dir() and _ID_SOLICITUD.match(e.name)):
            continue
        try:
            sol = json.loads((carpeta_lab("solicitudes", e.name) / "solicitud.json").read_text(encoding="utf-8"))
            if sol.get("id") != e.name:
                continue
            salida.append(respuesta_solicitud(sol))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    salida.sort(key=lambda s: s["id"], reverse=True)
    return salida


def leer_resultado(sid, archivo):
    if not isinstance(sid, str) or not _ID_SOLICITUD.match(sid) or archivo not in ARCHIVOS_RESULTADO:
        raise ValueError("Solicitud o archivo no válidos.")
    ruta = carpeta_lab("solicitudes", sid, "resultado", archivo)
    base = carpeta_lab("solicitudes").resolve()
    real = ruta.resolve()
    if base not in real.parents or not real.is_file():
        raise FileNotFoundError(archivo)
    with open(real, "rb") as f:
        datos = f.read(MAX_INFORME_LAB + 1)
    texto = datos[:MAX_INFORME_LAB].decode("utf-8", errors="replace")
    if len(datos) > MAX_INFORME_LAB:
        texto += "\n\n[…recortado a 2 MB…]"
    return {"id": sid, "archivo": archivo, "texto": enmascarar(texto)}


def estado_laboratorio(reg):
    v = node_version()
    return {"solicitudes": listar_solicitudes(),
            "proyectos": [{"id": p["id"], "nombre": p["nombre"]} for p in reg["proyectos"]],
            "objetivos": OBJETIVOS_LAB, "confirmacion": TEXTO_CONFIRMACION, "max_mb": MAX_SUBIDA // (1024 * 1024),
            "carpeta": str(carpeta_lab()),
            "requisitos": {"node_actual": v, "node_minimo": ".".join(map(str, NODE_MINIMO)),
                           "node_ok": node_suficiente(v)}}


# ---------------------------------------------------------------- escritura completa del registro

def ahora_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def leer_registro_crudo():
    with open(REGISTRO, encoding="utf-8") as f:
        return json.load(f)


def escribir_registro(nuevo):
    """Valida el registro completo con las mismas reglas de lectura y lo escribe de forma atómica con su formato
    (sangría de 2, UTF-8 sin escapar, salto final). Quien llama ya tiene `_registro_escritura`."""
    validar_registro(nuevo)
    escribir_json_atomico(REGISTRO, nuevo, indent=2)
    if json.loads(REGISTRO.read_text(encoding="utf-8")) != nuevo:
        raise RuntimeError("El registro escrito no coincide con el esperado.")


# ---------------------------------------------------------------- detección de proyectos (solo lectura)
# Nunca se ejecuta nada de los proyectos ni se abre un .env* o un archivo de credenciales (solo se ve si existe).
# Lo único que se lee son manifiestos (package.json, *.csproj, launchSettings.json, compose, vite.config, .git/config
# y HEAD, fuentes de arranque acotados) con un tope de bytes por archivo.

RAICES_DEFECTO = (Path.home() / "Documents" / "Proyectos", Path.home() / "Desktop")
DETECCION_CACHE_SEG = 600
MAX_LEER_DETECCION = 256 * 1024
MAX_DIRS_CANDIDATO = 2500
PROF_SERVICIOS = 3
_PODAR = {"node_modules", ".venv", "venv", "env", "__pycache__", "bin", "obj", "dist", "build", "graphify-out",
          "site-packages", "vendor", "legacy", "migrations", "coverage", "ejemplos", "examples", "docs", "tests",
          "test", "frames", "uploads", "_servicios", "plantillas", "templates", "esqueleto", "skeleton"}
_PODAR_PRUEBAS = _PODAR - {"tests", "test"}
_MARCADORES = {"package.json", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "manage.py",
               "pyproject.toml", "requirements.txt", "setup.py", "index.php", "agents.md", "claude.md", "makefile",
               "go.mod", "cargo.toml"}
_EXT_MARCADOR = (".csproj", ".sln", ".ipynb")
_SECRETOS_NOMBRE = {"credentials.json", "secrets.json", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519",
                    ".git-credentials", "appsettings.development.json", "usersecrets.json", "secrets.toml"}
_SECRETOS_EXT = (".pem", ".key", ".pfx", ".p12", ".jks", ".kdbx")
_RE_REPO_GH = re.compile(r"github\.com[:/]+([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/*$", re.I)
_RE_SALUD = (("/healthz", re.compile(r"""["']/healthz/?["']""")), ("/salud", re.compile(r"""["']/?salud/?["']""")),
             ("/health", re.compile(r"""["']/health/?["']""")))
_deteccion = {"en": 0.0, "firma": None, "datos": None}
_deteccion_lock = threading.Lock()


def es_secreto(nombre):
    n = nombre.lower()
    return n.startswith(".env") or n in _SECRETOS_NOMBRE or n.endswith(_SECRETOS_EXT) or "secret" in n


def leer_texto_seguro(ruta, maximo=MAX_LEER_DETECCION):
    """Lee un archivo de texto acotado; nunca un .env* ni algo con pinta de credencial, nunca un enlace simbólico."""
    ruta = Path(ruta)
    if es_secreto(ruta.name):
        return ""
    try:
        if ruta.is_symlink() or not ruta.is_file():
            return ""
        with open(ruta_os(ruta), "rb") as f:
            return f.read(maximo).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _json_seguro(ruta):
    try:
        d = json.loads(leer_texto_seguro(ruta).lstrip("﻿") or "null")
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def _norm_carpeta(ruta):
    s = str(ruta)
    s = s[4:] if s.startswith("\\\\?\\") else s  # rutas largas que devolvió ruta_os
    return os.path.normcase(os.path.abspath(s)).rstrip("\\/")


def _excluida(entrada_nombre, ruta):
    n = entrada_nombre
    if n.startswith(".") or n.lower() in _PODAR or re.search(r"-wt-", n, re.I):
        return True
    return (Path(ruta) / ".git").is_file()  # worktree


def _listar(d):
    try:
        with os.scandir(ruta_os(d)) as it:
            return list(it)
    except OSError:
        return []


def _es_dir(e):
    try:
        return e.is_dir(follow_symlinks=False)
    except OSError:
        return False


def _es_archivo(e):
    try:
        return e.is_file(follow_symlinks=False)
    except OSError:
        return False


def _parece_proyecto(d):
    if (d / ".git").is_dir():
        return True
    for e in _listar(d):
        n = e.name.lower()
        if _es_archivo(e) and (n in _MARCADORES or n.endswith(_EXT_MARCADOR)):
            return True
    return (d / "codigo" / "manage.py").is_file()


def candidatos_deteccion(raices):
    """Carpetas candidatas: cada hija de una raíz que parece proyecto (y los repos anidados dentro de ella); si la hija
    no parece proyecto, sus subcarpetas directas que sí lo parezcan. Excluye _servicios, worktrees y carpetas podadas."""
    vistos, salida = set(), []

    def agregar(d):
        k = _norm_carpeta(d)
        if k not in vistos:
            vistos.add(k)
            salida.append(Path(d))
    for raiz in raices:
        raiz = Path(raiz)
        if not raiz.is_dir():
            continue
        for e in sorted(_listar(raiz), key=lambda x: x.name.lower()):
            if not _es_dir(e) or _excluida(e.name, e.path):
                continue
            d = Path(e.path)
            if _parece_proyecto(d):
                agregar(d)
                for s in _listar(d):
                    if _es_dir(s) and not _excluida(s.name, s.path) and (Path(s.path) / ".git").is_dir():
                        agregar(Path(s.path))
            else:
                for s in sorted(_listar(d), key=lambda x: x.name.lower()):
                    if _es_dir(s) and not _excluida(s.name, s.path) and _parece_proyecto(Path(s.path)):
                        agregar(Path(s.path))
    return salida


def recorrer(base, prof=PROF_SERVICIOS, podar=_PODAR):
    """(carpeta, [archivos]) hasta `prof` niveles; poda dependencias, ocultas, worktrees y repos anidados."""
    pila, n = [(Path(base), 0)], 0
    while pila and n < MAX_DIRS_CANDIDATO:
        d, nivel = pila.pop()
        n += 1
        entradas = _listar(d)
        yield d, [e.name for e in entradas if _es_archivo(e)]
        if nivel >= prof:
            continue
        for e in sorted(entradas, key=lambda x: x.name.lower(), reverse=True):
            if not _es_dir(e) or e.name.startswith(".") or e.name.lower() in podar or re.search(r"-wt-", e.name, re.I):
                continue
            if (Path(e.path) / ".git").exists():
                continue
            pila.append((Path(e.path), nivel + 1))


def info_git(carpeta, ids_cuenta):
    g = Path(carpeta) / ".git"
    if not g.is_dir():
        return None
    remotos, seccion = [], None
    for linea in leer_texto_seguro(g / "config", 64 * 1024).splitlines():
        m = re.match(r'\s*\[remote\s+"([^"]+)"\]', linea)
        if m:
            seccion = m.group(1) if _REMOTO.match(m.group(1)) else None
            continue
        if linea.strip().startswith("["):
            seccion = None
            continue
        m = re.match(r"\s*url\s*=\s*(\S+)", linea)
        if seccion and m:
            url = re.sub(r"//[^/@\s]*@", "//", m.group(1))  # nunca se conserva usuario:token de la URL
            g2 = _RE_REPO_GH.search(url)
            repo = f"{g2.group(1)}/{g2.group(2)}" if g2 and _REPO.match(f"{g2.group(1)}/{g2.group(2)}") else None
            host = urlparse(url).hostname if "://" in url else (url.split("@")[-1].split(":")[0] or None)
            remotos.append({"nombre": seccion, "repo": repo, "host": (host or "")[:100]})
    head = leer_texto_seguro(g / "HEAD", 1024).strip()
    rama = head[len("ref: refs/heads/"):] if head.startswith("ref: refs/heads/") else None
    if rama and not _RAMA.match(rama):
        rama = None
    principal = next((r for r in remotos if r["nombre"] == "origin" and r["repo"]), None) or \
        next((r for r in remotos if r["repo"]), None)
    dueno = principal["repo"].split("/")[0] if principal else None
    cuenta = next((c for c in ids_cuenta if dueno and c.lower() == dueno.lower()), None)
    return {"repo": principal["repo"] if principal else None, "rama": rama, "remotos": remotos, "dueno": dueno,
            "cuenta": cuenta, "cuenta_conocida": bool(cuenta)}


def _en(rel, archivo):
    """Ruta de evidencia: 'archivo' en la raíz o 'carpeta\\archivo'."""
    return archivo if rel == "." else rel + "\\" + archivo


def _relativa(base, d):
    r = os.path.relpath(str(d), str(base))
    return "." if r in (".", "") else r.replace("/", "\\")


def _ruta_salud(textos, defecto="/"):
    for ruta, patron in _RE_SALUD:
        if any(patron.search(t) for t in textos):
            return ruta
    return defecto


def _puertos_unicos(valores, maximo=4):
    salida = []
    for v in valores:
        try:
            p = int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= p <= 65535 and p not in salida:
            salida.append(p)
    return salida[:maximo]


def _venv_relativo(base, d):
    """.venv de la carpeta, de sus ancestros hasta la raíz del proyecto o de una carpeta hija (backend\\.venv)."""
    def tiene(x):
        return (x / ".venv" / "Scripts").is_dir() or (x / ".venv" / "pyvenv.cfg").is_file()
    actual = Path(d)
    while True:
        if tiene(actual):
            return _relativa(base, actual / ".venv")
        if _norm_carpeta(actual) == _norm_carpeta(base) or actual.parent == actual:
            break
        actual = actual.parent
    for e in _listar(d):
        if _es_dir(e) and not e.name.startswith(".") and tiene(Path(e.path)):
            return _relativa(base, Path(e.path) / ".venv")
    return None


def _puerto_docs(base):
    """Puerto de runserver documentado en CONTEXTO/CLAUDE/AGENTS/README (proyectos DevSkills)."""
    for rel in ("documentacion/CONTEXTO.md", "CLAUDE.md", "AGENTS.md", "README.md", "codigo/README.md"):
        t = leer_texto_seguro(Path(base) / rel)
        m = re.search(r"runserver[^\n]{0,40}?(?:127\.0\.0\.1|localhost|0\.0\.0\.0)?:(\d{4,5})", t)
        if m:
            return int(m.group(1))
    return None


def detectar_servicios(base):
    """Servicios propuestos (mapeados a los tipos permitidos de servicios.py) y etiquetas del stack."""
    base = Path(base)
    servicios, stack = [], []

    def etiqueta(x):
        if x not in stack:
            stack.append(x)
    codigo = base / "codigo"
    dj = (codigo / "manage.py").is_file() and (codigo / "herramientas" / "base_local.py").is_file()
    if dj:
        etiqueta("Django (DevSkills)")
        urls = [leer_texto_seguro(Path(d) / "urls.py") for d, a in recorrer(codigo, 3) if "urls.py" in a]
        pd = _puerto_docs(base)
        servicios.append({"tipo": "django-devskills", "carpeta": "codigo", "nombre": "Django runserver",
                          "puertos": [pd] if pd else [], "origen_puerto": "fuente" if pd else "ninguno",
                          "esquema": "http", "salud": _ruta_salud(urls, "/salud"), "abrir": "/",
                          "evidencia": "codigo\\manage.py + codigo\\herramientas\\base_local.py"})
    for d, archivos in recorrer(base):
        rel = _relativa(base, d)
        bajos = {a.lower(): a for a in archivos}
        en_codigo_devskills = dj and (rel.lower() == "codigo" or rel.lower().startswith("codigo\\"))
        # .NET: *.csproj con Properties\launchSettings.json (los proyectos de pruebas no se levantan)
        for a in archivos:
            if not a.lower().endswith(".csproj") or re.search(r"\.tests?\.csproj$", a, re.I):
                continue
            texto = leer_texto_seguro(d / a)
            if "Microsoft.NET.Test.Sdk" in texto:
                continue
            etiqueta(".NET")
            ls = _json_seguro(d / "Properties" / "launchSettings.json")
            if not ls:
                continue
            urls_app = []
            for perfil in (ls.get("profiles") or {}).values():
                if isinstance(perfil, dict) and isinstance(perfil.get("applicationUrl"), str):
                    urls_app += [x.strip() for x in perfil["applicationUrl"].split(";") if x.strip()]
            http = [x for x in urls_app if x.startswith("http://")] or urls_app
            if not http:
                continue
            u = urlparse(http[0])
            programa = leer_texto_seguro(d / "Program.cs")
            m = re.search(r"""MapHealthChecks\(\s*["'](/[^"']*)["']""", programa)
            swagger = "Swashbuckle" in texto or "AddSwaggerGen" in programa
            salud = m.group(1) if m else ("/swagger/index.html" if swagger else _ruta_salud([programa]))
            servicios.append({"tipo": "dotnet", "carpeta": rel, "nombre": "API .NET" if swagger else Path(a).stem,
                              "puertos": _puertos_unicos([u.port]), "origen_puerto": "fuente",
                              "esquema": u.scheme if u.scheme in ("http", "https") else "http",
                              "host": u.hostname or "localhost",
                              "salud": salud, "abrir": "/swagger" if swagger and not m else "/",
                              "evidencia": _en(rel, a) + " + Properties\\launchSettings.json"})
        # npm: package.json con script dev o start
        if "package.json" in bajos:
            pk = _json_seguro(d / bajos["package.json"]) or {}
            scripts = pk.get("scripts") if isinstance(pk.get("scripts"), dict) else {}
            script = "dev" if "dev" in scripts else "start" if "start" in scripts else None
            if script and isinstance(scripts.get(script), str) and re.match(r"^[A-Za-z0-9:._-]+$", script):
                cmd = scripts[script]
                etiqueta("Node (Vite)" if "vite" in cmd else "Node")
                puertos, origen, base_url, evid = [], "ninguno", None, _en(rel, "package.json") + f" (script {script})"
                vite = next((bajos[x] for x in ("vite.config.js", "vite.config.ts", "vite.config.mjs", "vite.config.mts")
                             if x in bajos), None)
                if vite:
                    tv = leer_texto_seguro(d / vite)
                    m = re.search(r"\bport\s*:\s*(\d{2,5})", tv)
                    if m:
                        puertos, origen, evid = [int(m.group(1))], "fuente", evid + f" + {vite}"
                    mb = re.search(r"""\bbase\s*:\s*["'](/[A-Za-z0-9._~/-]*)["']""", tv)
                    base_url = mb.group(1) if mb else None
                if not puertos:
                    m = re.search(r"(?:--port|-p)[ =](\d{2,5})", cmd)
                    if m:
                        puertos, origen = [int(m.group(1))], "fuente"
                if not puertos:
                    for nombre in ("dev-server.js", "dev-server.mjs", "server.js", "server.mjs"):
                        if nombre in bajos:
                            ts = leer_texto_seguro(d / bajos[nombre])
                            hall = re.findall(r"""["']--port["']\s*,\s*["']?(\d{2,5})|(?:\b|_)PORT\s*=\s*(\d{2,5})|\.listen\(\s*(\d{2,5})""", ts)
                            puertos = _puertos_unicos([next(x for x in h if x) for h in hall])
                            if puertos:
                                origen, evid = "fuente", evid + f" + {nombre}"
                                break
                if not puertos and "vite" in cmd:
                    puertos, origen = [5173], "omision"
                elif not puertos and re.search(r"\b(next|react-scripts)\b", cmd):
                    puertos, origen = [3000], "omision"
                s = {"tipo": "npm", "carpeta": rel, "nombre": "Cliente " + ("Vite" if "vite" in cmd else "Node"),
                     "script": script, "instalar_si_falta": "node_modules", "puertos": puertos,
                     "origen_puerto": origen, "esquema": "http", "salud": base_url or "/", "abrir": base_url or "/",
                     "evidencia": evid}
                if "uvicorn" in cmd or "dev-server" in cmd:
                    v = _venv_relativo(base, d.parent)
                    if v:
                        s["venv"] = v
                servicios.append(s)
        # FastAPI (uvicorn modulo:app) y Django sin DevSkills (python -m manage runserver)
        for nombre in ("api.py", "main.py", "app.py", "server.py"):
            if nombre not in bajos or en_codigo_devskills:
                continue
            t = leer_texto_seguro(d / bajos[nombre])
            m = re.search(r"^(\w+)\s*=\s*FastAPI\(", t, re.M)
            if not m:
                continue
            etiqueta("FastAPI")
            mp = re.search(r"--port[ =](\d{2,5})", t)
            puerto = int(mp.group(1)) if mp else 8000
            s = {"tipo": "python-modulo", "carpeta": rel, "nombre": "FastAPI (uvicorn)", "modulo": "uvicorn",
                 "argumentos": [f"{Path(nombre).stem}:{m.group(1)}", "--host", "127.0.0.1", "--port", str(puerto)],
                 "puertos": [puerto], "origen_puerto": "fuente" if mp else "omision", "esquema": "http",
                 "salud": _ruta_salud([t]), "abrir": "/login" if re.search(r"""["']/login/?["']""", t) else "/",
                 "evidencia": _en(rel, bajos[nombre]) + f" ({m.group(1)} = FastAPI)"}
            v = _venv_relativo(base, d)
            if v:
                s["venv"] = v
            servicios.append(s)
            break
        if "manage.py" in bajos and not en_codigo_devskills:
            etiqueta("Django")
            s = {"tipo": "python-modulo", "carpeta": rel, "nombre": "Django runserver", "modulo": "manage",
                 "argumentos": ["runserver", "127.0.0.1:8000"], "puertos": [8000], "origen_puerto": "omision",
                 "esquema": "http", "salud": "/", "abrir": "/", "evidencia": _en(rel, "manage.py")}
            v = _venv_relativo(base, d)
            if v:
                s["venv"] = v
            servicios.append(s)
        # Paquete de Python con __main__.py y puerto en su configuración (python -m paquete)
        if "__main__.py" in bajos and "__init__.py" in bajos and rel != ".":
            padre = d.parent
            if (padre / "pyproject.toml").is_file() or (padre / "setup.py").is_file():
                fuentes = [leer_texto_seguro(padre / "dev.py"), leer_texto_seguro(d / "__main__.py"),
                           leer_texto_seguro(d / "config.py")]
                hall = []
                for t in fuentes:
                    hall += re.findall(r"""PORT["']?\s*,\s*["'](\d{4,5})["']|(?:\b|_)PORT\s*=\s*(\d{4,5})\b""", t)
                puertos = _puertos_unicos([next(x for x in h if x) for h in hall], 1)
                if puertos and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", d.name):
                    etiqueta("Python")
                    s = {"tipo": "python-modulo", "carpeta": _relativa(base, padre), "nombre": f"python -m {d.name}",
                         "modulo": d.name, "argumentos": [], "puertos": puertos, "origen_puerto": "fuente",
                         "esquema": "http", "salud": "/", "abrir": "/", "evidencia": _en(rel, "__main__.py")}
                    v = _venv_relativo(base, padre)
                    if v:
                        s["venv"] = v
                    servicios.append(s)
        # Docker Compose: puertos publicados (los compose de pruebas no se proponen)
        for nombre in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
            if nombre not in bajos:
                continue
            t = leer_texto_seguro(d / bajos[nombre])
            etiqueta("Docker Compose")
            pares = _puertos_compose(t)
            # HTTPS si el contenedor publica 443/8443; esos puertos del host van al final (la URL usa el último).
            https = _puertos_unicos([h for h, c in pares if c in (443, 8443) or h in (443, 8443)])
            puertos = _puertos_unicos([h for h, _ in pares if h not in https] + https)
            if not puertos:
                continue
            plantilla = any(x in bajos for x in (".env.example", ".env.ejemplo", ".env.sample", ".env.template"))
            devskills = (base / "codigo" / "herramientas" / "base_local.py").is_file()
            s = {"tipo": "docker-compose", "carpeta": rel, "nombre": "Docker Compose", "puertos": puertos,
                 "origen_puerto": "fuente", "esquema": "https" if https else "http",
                 "salud": "/salud" if devskills else "/", "abrir": "/", "construir": bool(re.search(r"^\s+build\s*:", t, re.M)),
                 "evidencia": _en(rel, bajos[nombre])}
            if plantilla or re.search(r"env_file\s*:", t):
                s["requiere_archivo"] = ".env"
            servicios.append(s)
            break
        if any(a.lower().endswith(".php") for a in archivos) and rel == ".":
            etiqueta("PHP")
        if any(a.lower().endswith(".ipynb") for a in archivos):
            etiqueta("Notebooks")
    if (base / "documentacion" / "CONTEXTO.md").is_file() and (base / ".devskills").is_dir():
        etiqueta("DevSkills")
    return servicios, stack


def _puertos_compose(texto):
    """[(puerto del host, puerto del contenedor)] publicados en un compose (sintaxis corta con ${VAR:-defecto} y larga
    con published/target)."""
    puertos, en_ports, sangria, largo = [], False, 0, None
    for linea in texto.splitlines():
        if not linea.strip() or linea.strip().startswith("#"):
            continue
        actual = len(linea) - len(linea.lstrip())
        if re.match(r"^\s*ports\s*:\s*$", linea):
            en_ports, sangria = True, actual
            continue
        if en_ports and actual <= sangria and not linea.strip().startswith("-"):
            en_ports = False
        if not en_ports:
            continue
        m = re.search(r"\b(published|target)\s*:\s*[\"']?(\d+)", linea)
        if m:
            if linea.lstrip().startswith("-"):
                largo = None
            largo = dict(largo or {}, **{m.group(1): int(m.group(2))})
            if "published" in largo and "target" in largo:
                puertos.append((largo["published"], largo["target"]))
                largo = None
            continue
        m = re.match(r"^\s*-\s*[\"']?([^\"'#]+?)[\"']?\s*(?:#.*)?$", linea)
        if not m:
            continue
        item = re.sub(r"\$\{[^:}]+:-([^}]*)\}", r"\1", m.group(1))
        item = re.sub(r"\$\{[^}]*\}", "", item).split("/")[0]
        partes = item.split(":")
        if len(partes) < 2:
            continue
        host = partes[-2].split("-")[0].strip()
        destino = partes[-1].split("-")[0].strip()
        if host.isdigit():
            puertos.append((int(host), int(destino) if destino.isdigit() else 0))
    return puertos


def _slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return (t or "proyecto")[:34].strip("-") or "proyecto"


def _rangos_ocupados(reg, crudo):
    ocupados = []
    for a, b in re.findall(r"(\d{4,5})\s*-\s*(\d{4,5})", reg["politica_rangos"]):
        ocupados.append((int(a), int(b)))
    for p in reg["proyectos"]:
        r = p["rango"]
        if r and "inicio" in r:
            ocupados.append((r["inicio"], r["fin"]))
        for a, b in re.findall(r"(\d{4,5})\s*-\s*(\d{4,5})", p["nota"]):
            ocupados.append((int(a), int(b)))
    usados = {pt for p in reg["proyectos"] for s in p["servicios"] for pt in s["puertos"]}
    usados |= {r["puerto"] for r in reg["reservados"]} | {reg["puerto_panel"]}
    return ocupados, usados


def proponer_bloque(reg, crudo, tomados):
    """Siguiente bloque de 50 libre según la política del registro (a partir de 18200 por omisión)."""
    m = re.search(r"a partir de (\d{4,5})", reg["politica_rangos"])
    inicio = int(m.group(1)) if m else 18200
    ocupados, usados = _rangos_ocupados(reg, crudo)
    ocupados += list(tomados)
    panel = reg["puerto_panel"]
    while inicio + 49 < 65535:
        fin = inicio + 49
        if not (any(a <= fin and inicio <= b for a, b in ocupados) or any(inicio <= u <= fin for u in usados)
                or inicio <= panel <= fin or 18950 <= fin and inicio <= 18999):
            return inicio, fin
        inicio += 50
    return None


def conflictos_puertos(puertos, reg, pid=None, escucha=None):
    salida = []
    for pt in puertos:
        if pt == reg["puerto_panel"]:
            salida.append({"puerto": pt, "con": "El panel de control"})
        for r in reg["reservados"]:
            if r["puerto"] == pt and r.get("proyecto") != pid:
                salida.append({"puerto": pt, "con": f"Puerto reservado ({r['uso']})"})
        for p in reg["proyectos"]:
            if p["id"] == pid:
                continue
            if any(pt in s["puertos"] for s in p["servicios"]):
                salida.append({"puerto": pt, "con": f"Lo usa {p['id']}"})
            r = p["rango"]
            if r and "inicio" in r and r["inicio"] <= pt <= r["fin"]:
                salida.append({"puerto": pt, "con": f"Rango asignado a {p['id']} ({r['inicio']}-{r['fin']})"})
        if escucha is not None and pt in escucha and pid is None:
            salida.append({"puerto": pt, "con": "Hay algo escuchando ahora en ese puerto", "aviso": True})
    return salida


def _clave_servicio(tipo, carpeta):
    c = (carpeta or ".").replace("/", "\\").strip("\\").lower()
    return tipo, ("." if c in ("", ".") else c)


def _comparar(reg_s, det):
    """Diferencias de puerto o comando entre un servicio del registro (crudo) y el detectado."""
    a = reg_s.get("arranque") or {}
    difs = []
    if det["origen_puerto"] == "fuente" and sorted(det["puertos"]) != sorted(reg_s.get("puertos") or []):
        difs.append({"campo": "puertos", "registrado": reg_s.get("puertos") or [], "detectado": det["puertos"]})
    if det["tipo"] == "npm" and a.get("script") != det.get("script"):
        difs.append({"campo": "script", "registrado": a.get("script"), "detectado": det.get("script")})
    if det["tipo"] == "python-modulo":
        if a.get("modulo") != det.get("modulo"):
            difs.append({"campo": "modulo", "registrado": a.get("modulo"), "detectado": det.get("modulo")})
        elif det.get("modulo") == "uvicorn" and (a.get("argumentos") or [None])[0] != det["argumentos"][0]:
            difs.append({"campo": "argumentos", "registrado": a.get("argumentos"), "detectado": det["argumentos"]})
    return difs


def detectar(forzar=False):
    """Detección completa con caché (DETECCION_CACHE_SEG o hasta que cambie el registro o las raíces)."""
    reg = registro()
    raices = [Path(r) for r in (ESTADO.get("raices") or RAICES_DEFECTO)] + [Path(r) for r in reg["raices_deteccion"]]
    try:
        firma = (REGISTRO.stat().st_mtime, tuple(str(r) for r in raices))
    except OSError:
        firma = None
    with _deteccion_lock:
        if (not forzar and _deteccion["datos"] is not None and _deteccion["firma"] == firma
                and time.monotonic() - _deteccion["en"] < DETECCION_CACHE_SEG):
            return {**_deteccion["datos"], "cache": True}
        t0 = time.monotonic()
        datos = _detectar(reg, raices)
        datos["duracion_ms"] = int((time.monotonic() - t0) * 1000)
        _deteccion.update(en=time.monotonic(), firma=firma, datos=datos)
        log(f"Detección: {len(datos['nuevos'])} nuevos, {len(datos['registrados'])} registrados "
            f"({datos['duracion_ms']} ms)")
        return {**datos, "cache": False}


def _detectar(reg, raices):
    crudo = leer_registro_crudo()
    por_carpeta = {_norm_carpeta(p["carpeta"]): p["id"] for p in reg["proyectos"]}
    crudos = {p.get("id"): p for p in crudo.get("proyectos") or []}
    ids_cuenta = [c["id"] for c in reg["cuentas"]]
    escucha = puertos_en_escucha()
    ids_tomados = set(reg["por_id"]) | set(reg["servicios"])
    bloques, nuevos, registrados = [], [], []
    for d in candidatos_deteccion(raices):
        servicios, stack = detectar_servicios(d)
        git = info_git(d, ids_cuenta)
        pid = por_carpeta.get(_norm_carpeta(d))
        if pid:
            reg_servicios = (crudos.get(pid) or {}).get("servicios") or []
            indice = {_clave_servicio((s.get("arranque") or {}).get("tipo"), (s.get("arranque") or {}).get("carpeta")): s
                      for s in reg_servicios}
            diferencias, sin_registrar, vistos = [], [], set()
            for s in servicios:
                k = _clave_servicio(s["tipo"], s["carpeta"])
                if k in indice:
                    vistos.add(k)
                    difs = _comparar(indice[k], s)
                    if difs:
                        diferencias.append({"servicio": indice[k]["id"], "tipo": s["tipo"], "carpeta": s["carpeta"],
                                            "cambios": difs, "evidencia": s["evidencia"]})
                else:
                    sin_registrar.append({k2: v for k2, v in s.items() if k2 != "host"})
            faltantes = [s["id"] for s in reg_servicios
                         if _clave_servicio((s.get("arranque") or {}).get("tipo"), (s.get("arranque") or {}).get("carpeta"))
                         not in vistos]
            registrados.append({"proyecto": pid, "nombre": reg["por_id"][pid]["nombre"], "carpeta": str(d),
                                "stack": stack, "git": git, "diferencias": diferencias,
                                "sin_registrar": sin_registrar, "no_detectados": faltantes})
            continue
        # Proyecto nuevo: id, ids de servicio y puertos propuestos
        pid = base_id = _slug(d.name)
        n = 2
        while pid in ids_tomados:
            pid, n = f"{base_id}-{n}", n + 1
        ids_tomados.add(pid)
        bloque = None
        sufijos = {"dotnet": "api", "npm": "cliente", "django-devskills": "web", "python-modulo": "web",
                   "docker-compose": "compose"}
        for s in servicios:
            if not s["puertos"]:
                if bloque is None:
                    bloque = proponer_bloque(reg, crudo, bloques)
                    if bloque:
                        bloques.append(bloque)
                if bloque:
                    s["puertos"], s["origen_puerto"] = [bloque[0] + 10 + servicios.index(s)], "propuesto"
            sid = base_sid = f"{pid}-{sufijos[s['tipo']]}"
            n = 2
            while sid in ids_tomados:
                sid, n = f"{base_sid}-{n}", n + 1
            ids_tomados.add(sid)
            s["id"] = sid
            s["conflictos"] = conflictos_puertos(s["puertos"], reg, None, escucha)
            s["incluir"] = not (s["tipo"] == "docker-compose" and any(x["tipo"] == "django-devskills" for x in servicios))
            s.pop("host", None)
        nuevos.append({"id_propuesto": pid, "nombre": d.name, "carpeta": str(d), "stack": stack, "git": git,
                       "servicios": servicios,
                       "rango_propuesto": {"tipo": "propuesto", "inicio": bloque[0], "fin": bloque[1]} if bloque else None})
    return {"ok": True, "generado": ahora_iso(), "raices": [str(r) for r in raices],
            "raices_registro": reg["raices_deteccion"], "nuevos": nuevos, "registrados": registrados,
            "simulacion": ESTADO["simular"]}


# ----- agregar / actualizar desde la detección (validación estricta contra la lista blanca)

_RE_CARPETA_REL = re.compile(r"^[A-Za-z0-9 ._()\\/-]{1,200}$")
_RE_SCRIPT_NPM = re.compile(r"^[A-Za-z0-9:._-]{1,60}$")
_RE_MODULO = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,80}$")
_RE_ARGUMENTO = re.compile(r"^[A-Za-z0-9_.:=-]{1,80}$")
_RE_ARCHIVO = re.compile(r"^[A-Za-z0-9._-]{1,60}$")
_CLAVES_SERVICIO = {"id", "nombre", "tipo", "carpeta", "puertos", "esquema", "salud", "abrir", "script",
                    "instalar_si_falta", "venv", "modulo", "argumentos", "requiere_archivo", "construir"}


def _carpeta_rel(v, base, donde, debe_existir=True):
    if v in (None, "", "."):
        return "."
    if not isinstance(v, str) or not _RE_CARPETA_REL.match(v):
        raise ValueError(f"Carpeta inválida en {donde}.")
    v = v.replace("/", "\\").strip("\\")
    partes = v.split("\\")
    if any(p in ("..", "") for p in partes) or ":" in v or os.path.isabs(v):
        raise ValueError(f"Carpeta relativa no permitida en {donde}: no se aceptan '..' ni rutas absolutas.")
    destino = Path(base) / v
    try:
        dentro = os.path.commonpath([_norm_carpeta(destino), _norm_carpeta(base)]) == _norm_carpeta(base)
    except ValueError:
        dentro = False
    if not dentro or (debe_existir and not destino.is_dir()):
        raise ValueError(f"La carpeta {v} no existe dentro del proyecto ({donde}).")
    return v


def construir_servicio(s, base, ids_ocupados):
    """Valida un servicio propuesto o editado y devuelve el objeto del registro. Rechaza cualquier clave o valor fuera
    de la lista blanca (los mismos patrones que aplica servicios.py)."""
    if not isinstance(s, dict) or not set(s) <= _CLAVES_SERVICIO:
        extra = sorted(set(s) - _CLAVES_SERVICIO) if isinstance(s, dict) else []
        raise ValueError("Servicio inválido" + (": claves no permitidas " + ", ".join(extra) if extra else "."))
    sid = s.get("id")
    if not isinstance(sid, str) or not _ID.match(sid):
        raise ValueError("Id de servicio inválido (minúsculas, dígitos y guiones; máximo 41).")
    if sid in ids_ocupados:
        raise ValueError(f"El id {sid} ya existe en el registro.")
    nombre = s.get("nombre")
    if not isinstance(nombre, str) or not 1 <= len(nombre.strip()) <= 80:
        raise ValueError(f"Nombre inválido en {sid} (1 a 80 caracteres).")
    tipo = s.get("tipo")
    if tipo not in TIPOS_ARRANQUE:
        raise ValueError(f"Tipo de arranque no permitido en {sid}: usa " + ", ".join(sorted(TIPOS_ARRANQUE)) + ".")
    puertos = s.get("puertos")
    if (not isinstance(puertos, list) or not 1 <= len(puertos) <= 4
            or not all(isinstance(p, int) and not isinstance(p, bool) and 1024 <= p <= 65535 for p in puertos)
            or len(set(puertos)) != len(puertos)):
        raise ValueError(f"Puertos inválidos en {sid}: de 1 a 4 enteros distintos entre 1024 y 65535.")
    esquema = s.get("esquema", "http")
    if esquema not in ("http", "https"):
        raise ValueError(f"Esquema inválido en {sid} (http o https).")
    try:
        salud = _ruta_http(s.get("salud"), sid + ".salud")
        abrir = _ruta_http(s.get("abrir"), sid + ".abrir")
    except ErrorRegistro as e:
        raise ValueError(str(e))
    carpeta = _carpeta_rel(s.get("carpeta"), base, sid)
    arranque = {"tipo": tipo, "carpeta": carpeta}
    permitidas = {"dotnet": set(), "django-devskills": set(), "npm": {"script", "instalar_si_falta", "venv"},
                  "python-modulo": {"modulo", "argumentos", "venv"}, "docker-compose": {"requiere_archivo", "construir"}}[tipo]
    sobran = [k for k in ("script", "instalar_si_falta", "venv", "modulo", "argumentos", "requiere_archivo", "construir")
              if k in s and s[k] not in (None, "", []) and k not in permitidas]
    if sobran:
        raise ValueError(f"El tipo {tipo} no acepta: " + ", ".join(sobran) + f" ({sid}).")
    if tipo == "npm":
        if not isinstance(s.get("script"), str) or not _RE_SCRIPT_NPM.match(s["script"]):
            raise ValueError(f"Script de npm inválido en {sid} (letras, dígitos y : . _ -).")
        arranque["script"] = s["script"]
        if s.get("instalar_si_falta"):
            arranque["instalar_si_falta"] = _carpeta_rel(s["instalar_si_falta"], Path(base) / carpeta, sid, False)
    if tipo == "python-modulo":
        if not isinstance(s.get("modulo"), str) or not _RE_MODULO.match(s["modulo"]):
            raise ValueError(f"Módulo de Python inválido en {sid}.")
        args = s.get("argumentos") or []
        if not isinstance(args, list) or len(args) > 12 or not all(isinstance(a, str) and _RE_ARGUMENTO.match(a) for a in args):
            raise ValueError(f"Argumentos inválidos en {sid}: máximo 12, cada uno con letras, dígitos y _ . : = -.")
        args = list(args)
        # El puerto editado manda: se refleja en --port (uvicorn) o en host:puerto (runserver).
        if "--port" in args and args.index("--port") + 1 < len(args):
            args[args.index("--port") + 1] = str(puertos[0])
        args = [re.sub(r"^(127\.0\.0\.1|localhost|0\.0\.0\.0):\d+$", rf"\g<1>:{puertos[0]}", a) for a in args]
        arranque["modulo"], arranque["argumentos"] = s["modulo"], args
    if tipo in ("npm", "python-modulo") and s.get("venv"):
        arranque["venv"] = _carpeta_rel(s["venv"], base, sid)
    if tipo == "docker-compose":
        if s.get("requiere_archivo"):
            if not isinstance(s["requiere_archivo"], str) or not _RE_ARCHIVO.match(s["requiere_archivo"]) or s["requiere_archivo"] in (".", ".."):
                raise ValueError(f"requiere_archivo inválido en {sid}.")
            arranque["requiere_archivo"] = s["requiere_archivo"]
        if not isinstance(s.get("construir", False), bool):
            raise ValueError(f"construir debe ser true o false en {sid}.")
        arranque["construir"] = bool(s.get("construir"))
    host = "127.0.0.1" if tipo in ("django-devskills", "python-modulo") else "localhost"
    puerto_url = next((p for p in puertos if p in (443, 8443)), puertos[-1]) if esquema == "https" else puertos[0]
    salida = {"id": sid, "nombre": nombre.strip(), "puertos": puertos, "url": f"{esquema}://{host}:{puerto_url}",
              "salud": salud, "abrir": abrir, "arranque": arranque}
    return {k: v for k, v in salida.items() if v is not None}


def _conflictos_duros(servicios, reg, pid):
    errores = []
    for s in servicios:
        for c in conflictos_puertos(s["puertos"], reg, pid):
            errores.append(f":{c['puerto']} ({s['id']}) — {c['con']}")
    return errores


def agregar_detectado(cuerpo):
    if not isinstance(cuerpo, dict) or not set(cuerpo) <= {"carpeta", "id", "nombre", "descripcion", "servicios"} \
            or not {"carpeta", "id", "nombre", "servicios"} <= set(cuerpo):
        raise ValueError('Solo se acepta {"carpeta", "id", "nombre", "descripcion", "servicios": [...]}.')
    det = detectar()
    nuevo = next((n for n in det["nuevos"] if isinstance(cuerpo["carpeta"], str)
                  and _norm_carpeta(n["carpeta"]) == _norm_carpeta(cuerpo["carpeta"])), None)
    if not nuevo:
        raise ValueError("Esa carpeta no está entre los proyectos nuevos detectados (vuelve a detectar).")
    pid, nombre = cuerpo["id"], cuerpo["nombre"]
    if not isinstance(pid, str) or not _ID.match(pid):
        raise ValueError("Id de proyecto inválido (minúsculas, dígitos y guiones; máximo 41).")
    if not isinstance(nombre, str) or not 1 <= len(nombre.strip()) <= 80:
        raise ValueError("Nombre inválido (1 a 80 caracteres).")
    descripcion = cuerpo.get("descripcion") or ""
    if not isinstance(descripcion, str) or len(descripcion) > 200:
        raise ValueError("Descripción inválida (máximo 200 caracteres).")
    if not isinstance(cuerpo["servicios"], list) or len(cuerpo["servicios"]) > 8:
        raise ValueError("servicios debe ser una lista (máximo 8).")
    with _registro_escritura:
        crudo = leer_registro_crudo()
        reg = validar_registro(crudo)
        if any(_norm_carpeta(p["carpeta"]) == _norm_carpeta(nuevo["carpeta"]) for p in reg["proyectos"]):
            raise FileExistsError("Esa carpeta ya está en el registro: no se sobrescribe.")
        if pid in reg["por_id"] or pid in reg["servicios"]:
            raise FileExistsError(f"El id {pid} ya existe en el registro: no se sobrescribe.")
        ocupados = set(reg["por_id"]) | set(reg["servicios"]) | {pid}
        servicios = []
        for s in cuerpo["servicios"]:
            r = construir_servicio(s, nuevo["carpeta"], ocupados)
            ocupados.add(r["id"])
            servicios.append(r)
        conflictos = _conflictos_duros(servicios, reg, None)
        vistos = set()
        for s in servicios:
            for pt in s["puertos"]:
                if pt in vistos:
                    conflictos.append(f":{pt} — repetido entre servicios del mismo proyecto")
                vistos.add(pt)
        if conflictos:
            raise ValueError("Conflictos de puertos (cámbialos en el formulario): " + "; ".join(conflictos))
        puertos = sorted({pt for s in servicios for pt in s["puertos"]})
        rp = nuevo.get("rango_propuesto")
        if rp and puertos and all(rp["inicio"] <= pt <= rp["fin"] for pt in puertos):
            rango = {"tipo": "propuesto", "inicio": rp["inicio"], "fin": rp["fin"]}
        else:
            rango = {"tipo": "heredado", "puertos": puertos} if puertos else None
        git = nuevo.get("git")
        repositorio = None
        if git:
            remotos = [{"nombre": r["nombre"], "repo": r["repo"]} for r in git["remotos"] if r["repo"]]
            repositorio = {"cuenta": git["cuenta"], "repo": git["repo"], "rama": git["rama"], "remotos": remotos}
            if git["dueno"] and not git["cuenta"]:
                repositorio["nota"] = f"La cuenta dueña del remoto ({git['dueno']}) no está en la lista de cuentas."
        else:
            repositorio = {"cuenta": None, "repo": None, "rama": None, "remotos": [],
                           "nota": "La carpeta no es un repositorio git."}
        proyecto = {"id": pid, "nombre": nombre.strip(), "descripcion": descripcion.strip(), "resumen": "",
                    "carpeta": nuevo["carpeta"], "rango": rango, "repositorio": repositorio, "transcripts": [],
                    "servicios": servicios, "agregado": "Detección automática " + ahora_iso()}
        crudo["proyectos"].append(proyecto)
        escribir_registro(crudo)
    log(f"Detección: agregado {pid} ({nuevo['carpeta']}) con {len(servicios)} servicios")
    with _deteccion_lock:
        _deteccion["datos"] = None
    return {"ok": True, "proyecto": pid, "servicios": [s["id"] for s in servicios]}


def actualizar_desde_deteccion(pid):
    if not isinstance(pid, str) or not _ID.match(pid):
        raise ValueError("Proyecto inválido.")
    det = detectar(forzar=True)
    entrada = next((r for r in det["registrados"] if r["proyecto"] == pid), None)
    if entrada is None:
        raise KeyError(pid)
    if not entrada["diferencias"]:
        return {"ok": True, "cambio": False, "mensaje": "Sin diferencias con la detección."}
    aplicados = []
    with _registro_escritura:
        crudo = leer_registro_crudo()
        p = next(x for x in crudo["proyectos"] if x.get("id") == pid)
        for dif in entrada["diferencias"]:
            s = next((x for x in p.get("servicios") or [] if x.get("id") == dif["servicio"]), None)
            if s is None:
                continue
            a = s.setdefault("arranque", {})
            for c in dif["cambios"]:
                if c["campo"] == "puertos":
                    viejo = (s.get("puertos") or [None])[0]
                    s["puertos"] = list(c["detectado"])
                    u = urlparse(s.get("url") or "")
                    if u.port == viejo and u.hostname:
                        s["url"] = f"{u.scheme}://{u.hostname}:{c['detectado'][0]}{u.path or ''}"
                    args = a.get("argumentos")
                    if isinstance(args, list) and "--port" in args and args.index("--port") + 1 < len(args):
                        args[args.index("--port") + 1] = str(c["detectado"][0])
                elif c["campo"] in ("script", "modulo", "argumentos"):
                    a[c["campo"]] = c["detectado"]
                aplicados.append(f"{s['id']}.{c['campo']}: {c['registrado']} → {c['detectado']}")
        reg_nuevo = validar_registro(crudo)
        servicios_p = [s for s in reg_nuevo["por_id"][pid]["servicios"]]
        conflictos = _conflictos_duros(servicios_p, reg_nuevo, pid)
        if conflictos:
            raise ValueError("Conflictos de puertos; no se actualizó: " + "; ".join(conflictos))
        escribir_registro(crudo)
    log(f"Detección: actualizado {pid}: {'; '.join(aplicados)}")
    with _deteccion_lock:
        _deteccion["datos"] = None
    return {"ok": True, "cambio": bool(aplicados), "aplicados": aplicados}


# ---------------------------------------------------------------- enrutamiento de modelos por proyecto

ARCHIVO_ENRUTAMIENTO = Path(".devskills") / "enrutamiento.json"
ARCHIVO_FALLOS = Path(".devskills") / "enrutamiento-fallos.md"


def es_devskills(carpeta):
    c = Path(carpeta)
    return (c / "documentacion" / "CONTEXTO.md").is_file() and (c / ".devskills").is_dir()


def evaluar_enrutamiento(carpeta):
    """Solo lectura: ¿hay forma barata de verificar (pruebas con comando), CI y especificación?"""
    base = Path(carpeta)
    pruebas, ci, spec, motivos, dirs_pytest = [], [], [], [], []
    if not base.is_dir():
        return {"nivel": "no-recomendado", "pruebas": [], "ci": [], "spec": [], "devskills": False,
                "motivos": ["La carpeta del proyecto no existe."]}
    for d, archivos in recorrer(base, 3, _PODAR_PRUEBAS):
        rel = _relativa(base, d)
        bajos = {a.lower(): a for a in archivos}
        donde = "" if rel == "." else f" (en {rel})"
        if ("pytest.ini" in bajos or "conftest.py" in bajos
                or ("pyproject.toml" in bajos and "[tool.pytest" in leer_texto_seguro(d / bajos["pyproject.toml"]))
                or ("setup.cfg" in bajos and "[tool:pytest]" in leer_texto_seguro(d / bajos["setup.cfg"]))
                or (d.name.lower() in ("tests", "test") and any(re.match(r"test_.*\.py$|.*_test\.py$", a) for a in archivos))):
            # Una sola entrada por árbol: si un ancestro ya tiene pytest, la subcarpeta no se repite.
            if not any(rel == x or rel.startswith(x + "\\") or x == "." for x in dirs_pytest):
                pruebas.append("pytest" + donde)
            dirs_pytest.append(rel)
        if "package.json" in bajos:
            sc = (_json_seguro(d / bajos["package.json"]) or {}).get("scripts") or {}
            if isinstance(sc, dict):
                if isinstance(sc.get("test"), str) and "no test specified" not in sc["test"]:
                    pruebas.append("npm test" + donde)
                for k in sc:
                    if isinstance(k, str) and k.startswith("test:") and _RE_SCRIPT_NPM.match(k):
                        pruebas.append(f"npm run {k}" + donde)
        for a in archivos:
            if a.lower().endswith(".csproj") and (re.search(r"\.tests?\.csproj$", a, re.I)
                                                   or "Microsoft.NET.Test.Sdk" in leer_texto_seguro(d / a)):
                pruebas.append("dotnet test" + donde)
                break
        if "go.mod" in bajos:
            pruebas.append("go test ./..." + donde)
        if "makefile" in bajos and re.search(r"^test\s*:", leer_texto_seguro(d / bajos["makefile"]), re.M):
            pruebas.append("make test" + donde)
        if any(a.lower().endswith(".feature") for a in archivos):
            spec.append("Escenarios Gherkin (.feature)" + donde)
    if (base / ".shellspec").is_file():
        pruebas.append("shellspec")
    pruebas = list(dict.fromkeys(pruebas))[:8]
    wf = base / ".github" / "workflows"
    flujos = [e.name for e in _listar(wf) if _es_archivo(e) and e.name.lower().endswith((".yml", ".yaml"))]
    if flujos:
        ci.append("GitHub Actions: " + ", ".join(sorted(flujos)[:5]))
    for nombre in (".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile"):
        if (base / nombre).is_file():
            ci.append(nombre)
    devskills = es_devskills(base)
    if devskills:
        spec.append("DevSkills (documentacion/CONTEXTO.md y .devskills/)")
    for e in _listar(base / "documentacion"):
        if _es_archivo(e) and re.match(r"(?i)srs.*\.md$", e.name):
            t = leer_texto_seguro(e.path)
            spec.append(f"documentacion/{e.name}" + (" con Gherkin" if re.search(r"(?m)^\s*(Escenario|Scenario|Dado|Given)\b", t) else ""))
            break
    spec = list(dict.fromkeys(spec))
    if pruebas and ci and spec:
        nivel = "recomendado"
        motivos.append("Tiene pruebas automatizadas con comando, CI y especificación: se puede verificar barato y escalar una vez.")
    elif pruebas:
        nivel = "parcial"
        motivos.append("Tiene pruebas automatizadas, pero " + " y ".join(
            x for x, falta in (("no tiene CI", not ci), ("no tiene especificación tipo SRS/Gherkin o DevSkills", not spec)) if falta) + ".")
    else:
        nivel = "no-recomendado"
        motivos.append("No se encontraron pruebas automatizadas: no hay forma barata de verificar el trabajo de un modelo más "
                       "barato ni de decidir cuándo escalar.")
    motivos += [f"Pruebas: {', '.join(pruebas)}" if pruebas else "Pruebas: ninguna detectada",
                f"CI: {'; '.join(ci)}" if ci else "CI: no detectado",
                f"Especificación: {'; '.join(spec)}" if spec else "Especificación: no detectada"]
    return {"nivel": nivel, "pruebas": pruebas, "ci": ci, "spec": spec, "devskills": devskills, "motivos": motivos}


def devskills_ignorado(carpeta):
    """(ignorado, aviso). Lectura con git: .devskills/enrutamiento.json debe estar ignorado y sin seguimiento."""
    codigo, raiz = _git_leer(["rev-parse", "--show-toplevel"], str(carpeta))
    if codigo != 0 or not raiz:
        return False, "La carpeta no es un repositorio git: no se puede confirmar que .devskills/ esté ignorado."
    codigo, _ = _git_leer(["check-ignore", "-q", str(ARCHIVO_ENRUTAMIENTO).replace("\\", "/")], str(carpeta))
    if codigo == 0:
        return True, None
    return False, (".devskills/ no está ignorado por git en este repo (o el archivo tiene seguimiento). Agrega "
                   "'.devskills/' al .gitignore del repo; mientras tanto no se escribe el archivo local.")


def ahora_utc():
    """Formato de DevSkills para `actualizado`: UTC con Z (date -u +%Y-%m-%dT%H:%M:%SZ)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _leer_archivo_enrutamiento(carpeta):
    """(existe, datos|None, error|None, texto). Solo se rechaza lo que no es JSON o no trae "activo" booleano; la
    tabla se analiza aparte y con tolerancia (claves antiguas migrables, roles sin enrutar)."""
    ruta = Path(carpeta) / ARCHIVO_ENRUTAMIENTO
    if not ruta.exists():
        return False, None, None, ""
    if ruta.is_symlink() or not ruta.is_file():
        return True, None, "El archivo de enrutamiento no es un archivo normal; no se toca.", ""
    try:
        with open(ruta_os(ruta), encoding="utf-8", newline="") as f:
            texto = f.read(64 * 1024)
        d = json.loads(texto.lstrip("﻿") or "null")
    except (OSError, ValueError):
        return True, None, "El archivo de enrutamiento no es JSON válido; no se toca.", ""
    if not isinstance(d, dict) or not isinstance(d.get("activo"), bool):
        return True, None, ('El archivo de enrutamiento no trae "activo": true|false; no se toca '
                            "(revísalo o reescríbelo con 'devskills enrutamiento activar --forzar')."), ""
    return True, d, None, texto


def _escribir_texto_atomico(destino, texto):
    destino = Path(destino)
    temporal = destino.with_name(f"{destino.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(temporal, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, destino)
    finally:
        try:
            temporal.unlink()
        except OSError:
            pass


def _cambiar_activo(ruta, texto, datos, activo):
    """Como `cambiar_activo` de DevSkills: solo cambia "activo" y "actualizado" (si existe) en el texto, conservando
    todo lo demás tal cual. Se comprueba que el resultado sea exactamente el archivo anterior con esos dos cambios."""
    nuevo, n = re.subn(r'("activo"\s*:\s*)(true|false)', lambda m: m.group(1) + ("true" if activo else "false"),
                       texto, count=1)
    nuevo = re.sub(r'("actualizado"\s*:\s*)"[^"\\]*"', lambda m: m.group(1) + json.dumps(ahora_utc()), nuevo, count=1)
    esperado = dict(datos, activo=activo)
    if "actualizado" in datos:
        esperado["actualizado"] = None
    try:
        obtenido = json.loads(nuevo.lstrip("﻿"))
    except ValueError:
        obtenido = None
    if n != 1 or not isinstance(obtenido, dict) or {**obtenido, **({"actualizado": None} if "actualizado" in datos else {})} != esperado:
        raise RuntimeError("No se pudo cambiar solo «activo» en el archivo de enrutamiento; no se tocó.")
    _escribir_texto_atomico(ruta, nuevo)


def leer_fallos(carpeta, limite=10):
    ruta = Path(carpeta) / ARCHIVO_FALLOS
    try:
        if ruta.is_symlink() or not ruta.is_file():
            return []
        tam = ruta.stat().st_size
        with open(ruta_os(ruta), "rb") as f:
            f.seek(max(0, tam - 64 * 1024))
            texto = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    bloques = [b.strip() for b in re.split(r"(?m)^(?=#{2,3} )", texto) if b.strip()]
    if any(b.startswith("##") for b in bloques):
        bloques = [b for b in bloques if b.startswith("##")]  # el título y la introducción no son entradas
    else:
        # Sin encabezados ##: cada viñeta es una entrada.
        bloques = [b.strip() for b in re.split(r"(?m)^(?=[-*] )", texto) if b.strip() and not b.startswith("# ")]
    return [recortar(b, 1500) for b in bloques[-limite:]][::-1]


_veredicto_cache = {}
_veredicto_lock = threading.Lock()
VEREDICTO_CACHE_SEG = 120


def veredicto_devskills(carpeta):
    """Opcional: si `devskills` está en el PATH, `devskills enrutamiento evaluar <ruta>` (solo lectura) y su última
    pareja de líneas Veredicto:/Motivo:. None si no está o no responde (se usa la evaluación del panel)."""
    exe = shutil.which("devskills")
    if not exe:
        return None
    clave = (_norm_carpeta(carpeta), exe)
    with _veredicto_lock:
        c = _veredicto_cache.get(clave)
        if c and time.monotonic() - c[0] < VEREDICTO_CACHE_SEG:
            return c[1]
    resultado = None
    try:
        r = subprocess.run([exe, "enrutamiento", "evaluar", str(carpeta)], capture_output=True, timeout=30,
                           stdin=subprocess.DEVNULL, creationflags=_sin_ventana())
        texto = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", (r.stdout + b"\n" + r.stderr).decode("utf-8", errors="replace"))
        veredictos = re.findall(r"(?m)^\s*Veredicto:\s*(.+?)\s*$", texto)
        motivos = re.findall(r"(?m)^\s*Motivo:\s*(.+?)\s*$", texto)
        if veredictos:
            v = unicodedata.normalize("NFKD", veredictos[-1]).encode("ascii", "ignore").decode().lower()
            nivel = ("no-recomendado" if re.match(r"no\b", v) else "parcial" if "parcial" in v
                     else "recomendado" if "recomendado" in v else None)
            if nivel:
                resultado = {"nivel": nivel, "veredicto": corto(veredictos[-1], 80),
                             "motivo": corto(motivos[-1], 300) if motivos else ""}
    except (OSError, subprocess.TimeoutExpired):
        resultado = None
    with _veredicto_lock:
        _veredicto_cache[clave] = (time.monotonic(), resultado)
    return resultado


def evaluacion_completa(carpeta):
    """Evaluación del panel y, en proyectos DevSkills, el veredicto de la CLI como fuente si está disponible."""
    ev = evaluar_enrutamiento(carpeta)
    ev["fuente"] = "panel"
    if ev["devskills"]:
        cli = veredicto_devskills(carpeta)
        if cli:
            ev["nivel_panel"] = ev["nivel"]
            ev["nivel"] = cli["nivel"]
            ev["fuente"] = "devskills"
            ev["motivos"] = [f"DevSkills (devskills enrutamiento evaluar): {cli['veredicto']}"
                             + (f" — {cli['motivo']}" if cli["motivo"] else "")] + ev["motivos"]
    return ev


def estado_enrutamiento(pid):
    reg = registro()
    p = reg["por_id"].get(pid)
    if not p:
        raise KeyError(pid)
    carpeta = p["carpeta"]
    ev = evaluacion_completa(carpeta)
    dev = ev["devskills"]
    ignorado, aviso = devskills_ignorado(carpeta) if dev else (None, None)
    existe, datos, error, _ = _leer_archivo_enrutamiento(carpeta) if dev else (False, None, None, "")
    en_reg = p.get("enrutamiento") or {}
    if dev:
        guardada = datos.get("tabla") if datos else None
        activo = bool(datos.get("activo")) if datos else False
    else:
        guardada = en_reg.get("tabla")
        activo = bool(en_reg.get("activo"))
    if guardada is None:
        analisis = {"tabla": copy.deepcopy(TABLA_ENRUTAMIENTO), "estado": {r: "por-omision" for r in ROLES_ENRUTAMIENTO},
                    "migrables": [], "invalidos": [], "desconocidos": []}
    else:
        analisis = analizar_tabla_enrutamiento(guardada)
    return {"ok": True, "proyecto": pid, "nombre": p["nombre"], "devskills": dev, "evaluacion": ev,
            "activo": activo, "registro": en_reg or None, "git_ignorado": ignorado, "aviso": aviso,
            "archivo": {"ruta": ".devskills/enrutamiento.json", "existe": existe, "error": error,
                        "activo": bool(datos.get("activo")) if datos else None,
                        "actualizado": datos.get("actualizado") if datos and isinstance(datos.get("actualizado"), str) else None},
            "tabla": analisis["tabla"], "estado_roles": analisis["estado"], "migrables": analisis["migrables"],
            "roles_invalidos": analisis["invalidos"], "claves_desconocidas": analisis["desconocidos"],
            "tabla_por_omision": guardada is None, "tabla_defecto": TABLA_ENRUTAMIENTO,
            "escalamiento": datos["escalamiento"] if dev and datos and isinstance(datos.get("escalamiento"), dict)
            else ESCALAMIENTO_ENRUTAMIENTO,
            "fallos": leer_fallos(carpeta) if dev or (Path(carpeta) / ARCHIVO_FALLOS).is_file() else [],
            "roles": list(ROLES_ENRUTAMIENTO), "modelos": list(MODELOS_ENRUTAMIENTO),
            "esfuerzos": list(ESFUERZOS_ENRUTAMIENTO), "simulacion": ESTADO["simular"]}


def _guardar_enrutamiento_registro(pid, activo=None, evaluacion=None, tabla=None):
    with _registro_escritura:
        crudo = leer_registro_crudo()
        p = next((x for x in crudo.get("proyectos") or [] if x.get("id") == pid), None)
        if p is None:
            raise KeyError(pid)
        actual = p.get("enrutamiento") if isinstance(p.get("enrutamiento"), dict) else {}
        nuevo = {"activo": bool(actual.get("activo")) if activo is None else activo,
                 "evaluacion": evaluacion if evaluacion is not None else actual.get("evaluacion") or {"nivel": None, "motivos": []},
                 "actualizado": ahora_utc()}
        if tabla is not None:
            nuevo["tabla"] = tabla
        elif actual.get("tabla") is not None:
            nuevo["tabla"] = actual["tabla"]
        p["enrutamiento"] = nuevo
        escribir_registro(crudo)
    return nuevo


def _evaluacion_registro(ev):
    return {"nivel": ev["nivel"], "motivos": ev["motivos"][:6]}


def activar_enrutamiento(pid, activo):
    reg = registro()
    p = reg["por_id"].get(pid)
    if not p:
        raise KeyError(pid)
    ev = evaluacion_completa(p["carpeta"])
    archivo = None
    if ev["devskills"]:
        ignorado, aviso = devskills_ignorado(p["carpeta"])
        if not ignorado:
            return 409, {"ok": False, "error": aviso, "aviso": aviso, "no_ignorado": True}
        existe, datos, error, texto = _leer_archivo_enrutamiento(p["carpeta"])
        if existe and datos is None:
            return 409, {"ok": False, "error": error}
        ruta = Path(p["carpeta"]) / ARCHIVO_ENRUTAMIENTO
        if existe:
            _cambiar_activo(ruta, texto, datos, activo)  # la tabla y todo lo demás quedan tal cual
            archivo = "actualizado"
        elif activo:
            escribir_json_atomico(ruta, {"activo": True, "version": 1, "tabla": copy.deepcopy(TABLA_ENRUTAMIENTO),
                                         "escalamiento": copy.deepcopy(ESCALAMIENTO_ENRUTAMIENTO),
                                         "actualizado": ahora_utc()}, indent=2)
            archivo = "creado"
    en_reg = _guardar_enrutamiento_registro(pid, activo=activo, evaluacion=_evaluacion_registro(ev))
    log(f"Enrutamiento de {pid} -> {'activo' if activo else 'inactivo'} (archivo: {archivo or 'sin cambios'})")
    return 200, {"ok": True, "activo": activo, "archivo": archivo, "registro": en_reg,
                 "advertencia": "La evaluación es «no recomendado»: no hay pruebas para verificar y escalar."
                 if activo and ev["nivel"] == "no-recomendado" else None}


def guardar_tabla_enrutamiento(pid, tabla):
    """Guarda la tabla completa con las claves de DevSkills. Si la guardada traía claves antiguas del panel, se
    eliminan (migración); cualquier otra clave desconocida se conserva tal cual."""
    reg = registro()
    p = reg["por_id"].get(pid)
    if not p:
        raise KeyError(pid)
    try:
        tabla = validar_tabla_enrutamiento(tabla, "la tabla enviada")
    except ErrorRegistro as e:
        raise ValueError(str(e))

    def combinar(anterior):
        anterior = anterior if isinstance(anterior, dict) else {}
        migradas = [k for k in anterior if k in MIGRACION_ROLES]
        otras = {k: v for k, v in anterior.items() if k not in MIGRACION_ROLES and k not in ROLES_ENRUTAMIENTO}
        return {**tabla, **otras}, migradas
    if es_devskills(p["carpeta"]):
        ignorado, aviso = devskills_ignorado(p["carpeta"])
        if not ignorado:
            return 409, {"ok": False, "error": aviso, "aviso": aviso, "no_ignorado": True}
        existe, datos, error, _ = _leer_archivo_enrutamiento(p["carpeta"])
        if existe and datos is None:
            return 409, {"ok": False, "error": error}
        if not existe:
            datos = {"activo": False, "version": 1, "tabla": {}, "escalamiento": copy.deepcopy(ESCALAMIENTO_ENRUTAMIENTO)}
        nueva, migradas = combinar(datos.get("tabla"))
        datos["tabla"] = nueva
        if not isinstance(datos.get("escalamiento"), dict):
            datos["escalamiento"] = copy.deepcopy(ESCALAMIENTO_ENRUTAMIENTO)
        datos["actualizado"] = ahora_utc()
        escribir_json_atomico(Path(p["carpeta"]) / ARCHIVO_ENRUTAMIENTO, datos, indent=2)
        _guardar_enrutamiento_registro(pid)
        destino = ".devskills/enrutamiento.json"
    else:
        nueva, migradas = combinar((p.get("enrutamiento") or {}).get("tabla"))
        _guardar_enrutamiento_registro(pid, tabla=nueva)
        destino = "proyectos.json"
    log(f"Tabla de enrutamiento de {pid} guardada en {destino}" + (f" (migradas: {', '.join(migradas)})" if migradas else ""))
    return 200, {"ok": True, "tabla": tabla, "destino": destino, "migradas": migradas}


# ---------------------------------------------------------------- tokens de Claude Code (solo números)
# Se suman los cuatro campos de `message.usage` de los transcripts JSONL de ~/.claude/projects (incluye subagentes),
# deduplicando por (message.id, requestId): Claude Code escribe una línea por bloque de contenido con el mismo uso.
# Lectura incremental: por archivo se guarda tamaño, mtime y offset, y solo se leen las líneas nuevas completas.
# Del transcript solo se conservan hora, modelo, carpeta y números; el contenido nunca se guarda ni se devuelve.
# El límite oficial (porcentaje y reinicio de las ventanas de 5 h y 7 días) lo escribe statusline_limites.py en
# estado\limites.json a partir del JSON documentado de la status line; sin ese dato se usa el presupuesto de
# preferencias.json.

CAMPOS_USO = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
TOKENS_DIAS = 35            # archivos sin cambios en más días no entran a ninguna ventana (la más larga es el mes)
TOKENS_CACHE_SEG = 30.0
VENTANAS_TOKENS = ("cinco_horas", "hoy", "semana", "mes")
HISTORIAL_ORQUESTADOR = rutas.orquestador_historial()
_tokens_archivos = {}       # ruta -> {"tam", "mtime", "offset", "registros": {clave: registro}}
_tokens_lock = threading.Lock()
_tokens_resultado = {"en": 0.0, "datos": None}


def _registro_uso(linea):
    """(clave, registro) de una línea de transcript con uso de la API, o None. Solo números, modelo y hora."""
    if b'"usage"' not in linea or b'"assistant"' not in linea:
        return None
    try:
        d = json.loads(linea)
    except ValueError:
        return None
    m = d.get("message") if isinstance(d, dict) and d.get("type") == "assistant" else None
    u = m.get("usage") if isinstance(m, dict) else None
    if not isinstance(u, dict):
        return None
    try:
        ts = datetime.fromisoformat(str(d.get("timestamp")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
    numeros = tuple(int(u.get(k) or 0) if isinstance(u.get(k), int) else 0 for k in CAMPOS_USO)
    clave = (str(m.get("id") or ""), str(d.get("requestId") or ""))
    if clave == ("", ""):
        clave = ("uuid", str(d.get("uuid") or ts))
    modelo = m.get("model") if isinstance(m.get("model"), str) else "desconocido"
    return clave, (ts, modelo[:60]) + numeros


def _mejor(a, b):
    """Entre dos líneas del mismo mensaje se queda la más completa (la última del streaming trae más salida)."""
    return a if a is not None and sum(a[2:]) >= sum(b[2:]) else b


def _leer_incremental(ruta, info, est):
    c = _tokens_archivos.get(ruta)
    if c is None or est.st_size < c["offset"] or est.st_mtime < c["mtime"] - 1:
        c = {"tam": 0, "mtime": 0.0, "offset": 0, "registros": {}}
    if est.st_size == c["tam"] and est.st_mtime == c["mtime"]:
        info["sin_cambios"] += 1
        _tokens_archivos[ruta] = c
        return c
    try:
        with open(ruta_os(ruta), "rb") as f:
            f.seek(c["offset"])
            bloque = f.read()
    except OSError:
        return c
    fin = bloque.rfind(b"\n")
    completas = bloque[:fin + 1] if fin >= 0 else b""  # una línea sin \n final se lee en la próxima pasada
    for linea in completas.split(b"\n"):
        r = _registro_uso(linea)
        if r:
            c["registros"][r[0]] = _mejor(c["registros"].get(r[0]), r[1])
    info["bytes_leidos"] += len(completas)
    info["leidos"] += 1
    c.update(tam=est.st_size, mtime=est.st_mtime, offset=c["offset"] + len(completas))
    _tokens_archivos[ruta] = c
    return c


def _proyecto_de_transcript(ruta, base, reg):
    try:
        primera = Path(os.path.relpath(ruta, base)).parts[0]
    except (ValueError, IndexError):
        return "otros"
    return proyecto_de_carpeta(primera, reg) or "otros"


def _registros_tokens(reg, ahora):
    """{clave: (ts, modelo, proyecto, entrada, salida, cache_creacion, cache_lectura)} deduplicado entre archivos
    (una sesión reanudada copia mensajes a un archivo nuevo)."""
    base = Path(PROYECTOS_CLAUDE)
    info = {"archivos": 0, "leidos": 0, "sin_cambios": 0, "bytes_leidos": 0}
    vistos, todos = set(), {}
    limite = ahora - TOKENS_DIAS * 86400
    # Siempre con el prefijo de rutas largas: los transcripts de subagentes suelen pasar de 260 caracteres y, sin él,
    # os.stat falla y el archivo se omitiría en silencio.
    raiz_walk = "\\\\?\\" + os.path.abspath(str(base)) if os.name == "nt" else str(base)
    for raiz, _, archivos in os.walk(raiz_walk):
        for nombre in archivos:
            if not nombre.endswith(".jsonl"):
                continue
            ruta = os.path.join(raiz, nombre)
            try:
                est = os.stat(ruta)
            except OSError:
                continue
            if est.st_mtime < limite:
                continue
            info["archivos"] += 1
            vistos.add(ruta)
            c = _leer_incremental(ruta, info, est)
            proyecto = _proyecto_de_transcript(ruta[4:] if ruta.startswith("\\\\?\\") else ruta, str(base), reg)
            for clave, r in c["registros"].items():
                nuevo = (r[0], r[1], proyecto) + r[2:]
                previo = todos.get(clave)
                if previo is None or sum(nuevo[3:]) > sum(previo[3:]):
                    todos[clave] = nuevo
    for ruta in list(_tokens_archivos):
        if ruta not in vistos:
            del _tokens_archivos[ruta]  # archivo borrado o fuera de la ventana
    return todos, info


def _bloque_cinco_horas(registros, ahora):
    """Bloque de 5 h vigente, como lo cuenta el plan: empieza en la hora cerrada del primer mensaje después de que
    terminó el bloque anterior. Aproximación local; si la status line trae resets_at, manda ese dato."""
    inicio = fin = None
    for ts in sorted(r[0] for r in registros if r[0] >= ahora - 10 * 3600):
        if fin is None or ts >= fin:
            inicio = ts - (ts % 3600)
            fin = inicio + 5 * 3600
    if fin is None or ahora >= fin:
        return None, None
    return inicio, fin


def leer_limites_oficiales(ahora):
    """Ventanas `five_hour` y `seven_day` que escribió statusline_limites.py (vigentes: resets_at en el futuro)."""
    d = leer_json(Path(ESTADO["estado_dir"]) / "limites.json", {})
    salida = {"capturado": None, "cinco_horas": None, "semana": None, "usd_por_hora": {}}
    if not isinstance(d, dict):
        return salida
    salida["capturado"] = d.get("capturado") if isinstance(d.get("capturado"), (int, float)) else None
    for origen, destino in (("five_hour", "cinco_horas"), ("seven_day", "semana")):
        v = (d.get("rate_limits") or {}).get(origen) if isinstance(d.get("rate_limits"), dict) else None
        if (isinstance(v, dict) and isinstance(v.get("used_percentage"), (int, float))
                and isinstance(v.get("resets_at"), (int, float)) and v["resets_at"] > ahora):
            salida[destino] = {"porcentaje": round(float(v["used_percentage"]), 1), "reinicia": float(v["resets_at"])}
    horas = d.get("usd_por_hora")
    if isinstance(horas, dict):
        salida["usd_por_hora"] = {k: float(v) for k, v in horas.items()
                                  if isinstance(k, str) and isinstance(v, (int, float)) and v >= 0}
    return salida


def _costo_orquestador():
    """[(epoch, usd)] de las instrucciones terminadas del orquestador (solo `terminada` y `costo_usd`)."""
    salida = []
    for e in _listar(HISTORIAL_ORQUESTADOR):
        if not (_es_archivo(e) and e.name.endswith(".json")):
            continue
        d = leer_json(e.path, None)
        if not isinstance(d, dict) or not isinstance(d.get("costo_usd"), (int, float)):
            continue
        try:
            ts = datetime.fromisoformat(str(d.get("terminada"))).timestamp()
        except ValueError:
            continue
        salida.append((ts, float(d["costo_usd"])))
    return salida


def _inicio_ventanas(ahora, oficiales, registros):
    hoy = datetime.fromtimestamp(ahora).replace(hour=0, minute=0, second=0, microsecond=0)
    ventanas = {"hoy": (hoy.timestamp(), None), "mes": (hoy.replace(day=1).timestamp(), None)}
    sem = oficiales["semana"]
    ventanas["semana"] = (sem["reinicia"] - 7 * 86400, sem["reinicia"]) if sem else (ahora - 7 * 86400, None)
    cinco = oficiales["cinco_horas"]
    if cinco:
        ventanas["cinco_horas"] = (cinco["reinicia"] - 5 * 3600, cinco["reinicia"])
    else:
        ini, fin = _bloque_cinco_horas(registros, ahora)
        ventanas["cinco_horas"] = (ini, fin)
    return ventanas


def calcular_tokens(forzar=False):
    ahora = time.time()
    if not forzar and _tokens_resultado["datos"] and time.monotonic() - _tokens_resultado["en"] < TOKENS_CACHE_SEG:
        return _tokens_resultado["datos"]
    if not _tokens_lock.acquire(blocking=False):
        # Otro hilo está leyendo: se devuelve lo último que hubo (o "cargando" en la primera pasada).
        return _tokens_resultado["datos"] or {"ok": True, "cargando": True}
    try:
        t0 = time.monotonic()
        try:
            reg = registro()
        except ErrorRegistro:
            reg = {"prefijos": [], "por_id": {}}
        registros, info = _registros_tokens(reg, ahora)
        lista = list(registros.values())
        oficiales = leer_limites_oficiales(ahora)
        costos = _costo_orquestador()
        prefs = leer_preferencias().get("presupuesto") or {}
        nombres = {pid: p["nombre"] for pid, p in reg["por_id"].items()}
        ventanas = {}
        for nombre, (ini, fin) in _inicio_ventanas(ahora, oficiales, lista).items():
            v = {"inicio": ini, "fin": fin, "tokens": 0, "entrada": 0, "salida": 0, "cache_creacion": 0,
                 "cache_lectura": 0, "mensajes": 0, "por_modelo": {}, "por_proyecto": {}}
            if ini is not None:
                for ts, modelo, proyecto, i, o, cc, cr in lista:
                    if ts < ini or ts > ahora:
                        continue
                    total = i + o + cc + cr
                    v["tokens"] += total
                    v["entrada"] += i
                    v["salida"] += o
                    v["cache_creacion"] += cc
                    v["cache_lectura"] += cr
                    v["mensajes"] += 1
                    v["por_modelo"][modelo] = v["por_modelo"].get(modelo, 0) + total
                    v["por_proyecto"][proyecto] = v["por_proyecto"].get(proyecto, 0) + total
            v["usd_orquestador"] = round(sum(u for ts, u in costos if ini is not None and ini <= ts <= ahora), 4)
            usd_sl = 0.0
            for hora, usd in oficiales["usd_por_hora"].items():
                try:
                    t = datetime.strptime(hora, "%Y-%m-%dT%H").timestamp()
                except ValueError:
                    continue
                if ini is not None and t + 3599 >= ini and t <= ahora:
                    usd_sl += usd
            v["usd_sesiones"] = round(usd_sl, 4)
            v["usd"] = round(v["usd_orquestador"] + usd_sl, 4)
            v["por_modelo"] = dict(sorted(((k, n) for k, n in v["por_modelo"].items() if n), key=lambda kv: -kv[1]))
            v["por_proyecto"] = [{"id": pid, "nombre": nombres.get(pid, "Otros (fuera del registro)"), "tokens": t}
                                 for pid, t in sorted(v["por_proyecto"].items(), key=lambda kv: -kv[1])]
            oficial = oficiales.get(nombre) if nombre in ("cinco_horas", "semana") else None
            presupuesto = prefs.get(nombre) if isinstance(prefs, dict) else None
            unidad = prefs.get("unidad", "tokens") if isinstance(prefs, dict) else "tokens"
            if oficial:
                v["limite"] = {"fuente": "claude-code", "porcentaje": oficial["porcentaje"], "reinicia": oficial["reinicia"]}
            elif presupuesto:
                usado = v["usd"] if unidad == "usd" else v["tokens"]
                v["limite"] = {"fuente": "presupuesto", "unidad": unidad, "presupuesto": presupuesto,
                               "porcentaje": round(100.0 * usado / presupuesto, 1), "reinicia": fin}
            else:
                v["limite"] = {"fuente": None, "reinicia": fin}
            ventanas[nombre] = v
        datos = {"ok": True, "generado": ahora, "ventanas": ventanas, "capturado_limites": oficiales["capturado"],
                 "presupuesto": prefs or None, "archivos": info["archivos"], "leidos": info["leidos"],
                 "sin_cambios": info["sin_cambios"], "mb_leidos": round(info["bytes_leidos"] / 1e6, 2),
                 "mensajes_unicos": len(lista), "duracion_ms": int((time.monotonic() - t0) * 1000)}
        _tokens_resultado.update(en=time.monotonic(), datos=datos)
        return datos
    finally:
        _tokens_lock.release()


def iniciar_tokens():
    """Primera lectura en segundo plano: así el primer GET /api/tokens no espera a leer cientos de MB."""
    def correr():
        try:
            d = calcular_tokens(forzar=True)
            log(f"Tokens: {d.get('mensajes_unicos')} mensajes, {d.get('archivos')} archivos, "
                f"{d.get('mb_leidos')} MB en {d.get('duracion_ms')} ms")
        except Exception as e:  # noqa: BLE001 - un transcript raro no debe tumbar el panel
            log(f"Tokens: falló la lectura inicial: {type(e).__name__}")
    threading.Thread(target=correr, daemon=True, name="tokens").start()


# ---------------------------------------------------------------- preferencias

_preferencias_lock = threading.Lock()


def validar_acento(valor):
    """Solo '#RRGGBB' exacto (fullmatch, sin espacios ni formas cortas); devuelve el valor en minúsculas o None."""
    if isinstance(valor, str) and len(valor) == 7 and RE_ACENTO.fullmatch(valor):
        return valor.lower()
    return None


def validar_vista_avisos(valor):
    """Solo un valor exacto de la lista VISTAS_AVISOS; si no, None."""
    return valor if isinstance(valor, str) and valor in VISTAS_AVISOS else None


# Cada preferencia con su validador: devuelve el valor normalizado o None si no es válido.
VALIDADORES_PREFERENCIA = {
    "acento": validar_acento,
    "vista_avisos": validar_vista_avisos,
    "avisos_notificar": lambda v: v if isinstance(v, bool) else None,
    "avisos_sonido": lambda v: v if isinstance(v, bool) else None,
    "presupuesto": lambda v: validar_presupuesto(v),
}
PREFERENCIAS_DEFECTO = {"acento": None, "vista_avisos": "lateral", "avisos_notificar": False, "avisos_sonido": False,
                        "presupuesto": None}


def validar_presupuesto(v):
    """Presupuesto propio por ventana (solo cuando Claude Code no da el límite oficial): {"unidad": "tokens"|"usd",
    "cinco_horas"|"hoy"|"semana"|"mes": número > 0}. {} lo borra. Cualquier otra clave o valor -> None."""
    if not isinstance(v, dict) or not set(v) <= {"unidad", *VENTANAS_TOKENS}:
        return None
    unidad = v.get("unidad", "tokens")
    if unidad not in ("tokens", "usd"):
        return None
    salida = {}
    for k in VENTANAS_TOKENS:
        if k in v:
            x = v[k]
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not 0 < x <= 1e13:
                return None
            salida[k] = int(x) if unidad == "tokens" else round(float(x), 2)
    if salida:
        salida["unidad"] = unidad
    return salida


def _preferencias_guardadas():
    datos = leer_json(archivo_preferencias(ESTADO["puerto"]), {})
    if not isinstance(datos, dict):
        return {}
    salida = {}
    for k, validar in VALIDADORES_PREFERENCIA.items():
        v = validar(datos.get(k))
        if v is not None:
            salida[k] = v
    return salida


def leer_preferencias():
    return {**PREFERENCIAS_DEFECTO, **_preferencias_guardadas()}


def guardar_preferencias(cambios, quitar=()):
    """Mezcla `cambios` (ya validados) con lo guardado y quita las claves de `quitar`. Escritura atómica; si no queda
    nada, se borra el archivo."""
    destino = archivo_preferencias(ESTADO["puerto"])
    with _preferencias_lock:
        datos = _preferencias_guardadas()
        datos.update(cambios)
        for k in quitar:
            datos.pop(k, None)
        if not datos:
            try:
                destino.unlink()
            except FileNotFoundError:
                pass
        else:
            escribir_json_atomico(destino, datos)
    return {**PREFERENCIAS_DEFECTO, **datos}


# ---------------------------------------------------------------- chat con el orquestador (proxy servidor a servidor)
# El navegador nunca habla con el orquestador ni conoce su token: aquí se lee el .token del orquestador en cada
# llamada (se regenera en cada arranque), se reintenta una vez ante 401 y solo se devuelven campos de lista blanca.
# Para pruebas: PANEL_ORQUESTADOR_URL (otra URL loopback), PANEL_ORQUESTADOR_TOKEN (otro .token) y
# PANEL_ORQUESTADOR_CMD (otro comando de arranque, lista JSON de argumentos).

ORQ_DIR = rutas.orquestador_dir()
ORQ_URL_DEFECTO = "http://127.0.0.1:18952"
MAX_TEXTO_CHAT = 4000
MAX_RESPUESTA_CHAT = 60000
MODOS_CHAT = ("lectura", "cambios")
CONTEXTOS_CHAT = ("auto", "sesion", "grafo")
TIPOS_PROPUESTA = ("agente", "skill", "comando")
DESTINOS_PROPUESTA = ("general", "proyecto")
_RE_ID_INSTRUCCION = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
_RE_ID_PROPUESTA = re.compile(r"^ag-[0-9a-f]{10}$")
_RE_CONTROL_CHAT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_orq_arranque = threading.Lock()


class OrquestadorNoDisponible(Exception):
    """No hay .token, no responde o la conexión falló. El mensaje nunca lleva el token."""


def _orq_sobrescrito():
    return bool(os.environ.get("PANEL_ORQUESTADOR_URL"))


def _orq_destino():
    u = urlparse(os.environ.get("PANEL_ORQUESTADOR_URL") or ORQ_URL_DEFECTO)
    if u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost") or not u.port:
        raise OrquestadorNoDisponible("URL del orquestador no válida (solo http://127.0.0.1:<puerto>).")
    return u.hostname, u.port


def _orq_leer_token():
    ruta = Path(os.environ.get("PANEL_ORQUESTADOR_TOKEN") or (ORQ_DIR / ".token"))
    d = leer_json(ruta, None)
    t = d.get("token") if isinstance(d, dict) else None
    return t if isinstance(t, str) and t else None


def orq_llamar(metodo, ruta, cuerpo=None, timeout=10):
    """(status, dict). Relee el token en cada llamada y reintenta una vez ante 401 (el orquestador lo regenera al
    arrancar). Lanza OrquestadorNoDisponible si no corre o no responde."""
    host, puerto = _orq_destino()
    for intento in (0, 1):
        token = _orq_leer_token()
        if not token:
            raise OrquestadorNoDisponible("El orquestador no está corriendo (no hay token).")
        con = http.client.HTTPConnection(host, puerto, timeout=timeout)
        try:
            cabeceras = {"X-Orquestador-Token": token, "Accept": "application/json"}
            datos = None
            if cuerpo is not None:
                datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
                cabeceras["Content-Type"] = "application/json"
            con.request(metodo, ruta, body=datos, headers=cabeceras)
            r = con.getresponse()
            crudo = r.read(4 * 1024 * 1024)
            codigo = r.status
        except (OSError, http.client.HTTPException):
            raise OrquestadorNoDisponible("El orquestador no responde.") from None
        finally:
            con.close()
        if codigo == 401 and intento == 0:
            continue
        try:
            d = json.loads(crudo.decode("utf-8")) if crudo else {}
        except ValueError:
            d = {}
        if not isinstance(d, dict):
            d = {}
        # Defensa en profundidad: aunque el orquestador lo repitiera, el token no sale de aquí.
        d = json.loads(json.dumps(d, ensure_ascii=False).replace(token, "[oculto]"))
        return codigo, d
    raise OrquestadorNoDisponible("El orquestador rechazó el token.")  # pragma: no cover


def _orq_ping():
    try:
        host, puerto = _orq_destino()
        con = http.client.HTTPConnection(host, puerto, timeout=1.5)
        try:
            con.request("GET", "/api/ping")
            r = con.getresponse()
            r.read(1024)
            return r.status == 200
        finally:
            con.close()
    except (OSError, http.client.HTTPException, OrquestadorNoDisponible):
        return False


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _cad(v, maximo):
    return v[:maximo] if isinstance(v, str) else None


def _error_orq(codigo, d):
    """Error de pasada: solo el mensaje (corto) y un código seguro para el navegador."""
    msg = _cad(d.get("error"), 300) or f"El orquestador respondió {codigo}."
    return (codigo if codigo in (400, 404, 409) else 502), {"ok": False, "error": msg}


def _chat_registro():
    return registro()["por_id"]


def _texto_chat(valor, minimo=1, maximo=MAX_TEXTO_CHAT):
    if not isinstance(valor, str):
        raise ValueError("texto debe ser una cadena.")
    t = valor.replace("\r\n", "\n").strip()
    if len(t) < minimo:
        raise ValueError("El texto está vacío.")
    if len(t) > maximo:
        raise ValueError(f"El texto supera {maximo} caracteres.")
    if _RE_CONTROL_CHAT.search(t):
        raise ValueError("El texto tiene caracteres de control.")
    return t


def _id_chat(valor, patron, nombre="id"):
    if not isinstance(valor, str) or not patron.match(valor):
        raise ValueError(f"{nombre} inválido.")
    return valor


def _solo_chat(cuerpo, obligatorios, opcionales=()):
    if (not isinstance(cuerpo, dict) or set(cuerpo) - set(obligatorios) - set(opcionales)
            or set(obligatorios) - set(cuerpo)):
        raise ValueError("Campos no permitidos o faltantes; se acepta "
                         + (", ".join(sorted(set(obligatorios) | set(opcionales))) or "un objeto vacío") + ".")
    return cuerpo


def _chat_bloqueado_simulacion():
    """En --simular, sin un orquestador de prueba, nada de lo que cuesta o escribe llega al orquestador real."""
    return ESTADO["simular"] and not _orq_sobrescrito()


def chat_estado():
    por_id = _chat_registro()
    activo = False
    if _orq_ping():
        try:
            activo = orq_llamar("GET", "/api/estado", timeout=4)[0] == 200
        except OrquestadorNoDisponible:
            activo = False
    return 200, {"ok": True, "activo": activo, "simulacion": ESTADO["simular"],
                 "bloqueado": _chat_bloqueado_simulacion(),
                 "proyectos": [{"id": p["id"], "nombre": p["nombre"]} for p in por_id.values()]}


def chat_resolver(q):
    texto = _texto_chat((q.get("texto") or [""])[0], 1, 500)
    por_id = _chat_registro()
    codigo, d = orq_llamar("GET", "/api/resolver?" + urlencode({"texto": texto}), timeout=8)
    if codigo != 200:
        return _error_orq(codigo, d)
    cand = [{"proyecto": c["proyecto"], "nombre": por_id[c["proyecto"]]["nombre"], "puntaje": _num(c.get("puntaje"))}
            for c in (d.get("candidatos") or []) if isinstance(c, dict) and c.get("proyecto") in por_id][:5]
    pid = d.get("proyecto") if d.get("proyecto") in por_id else None
    return 200, {"ok": True, "proyecto": pid, "puntaje": _num(d.get("puntaje")), "ambiguo": d.get("ambiguo") is True,
                 "candidatos": cand}


def _vista_instruccion(d):
    ctx = d.get("contexto_usado") if isinstance(d.get("contexto_usado"), dict) else None
    errores = d.get("errores") if isinstance(d.get("errores"), list) else []
    return {"ok": True, "id": d.get("id"), "estado": _cad(d.get("estado"), 40), "proyecto": _cad(d.get("proyecto"), 41),
            "modo": _cad(d.get("modo"), 10), "respuesta": _cad(d.get("respuesta"), MAX_RESPUESTA_CHAT),
            "costo_usd": _num(d.get("costo_usd")), "modelo_usado": _cad(d.get("modelo_usado"), 40),
            "escalado": d.get("escalado") is True, "motivo_escalamiento": _cad(d.get("motivo_escalamiento"), 300),
            "contexto_usado": {"modo": _cad(ctx.get("modo"), 20), "motivo": _cad(ctx.get("motivo"), 300)} if ctx else None,
            "errores": [_cad(e, 300) for e in errores[:3] if isinstance(e, str)]}


def chat_enviar(cuerpo):
    c = _solo_chat(cuerpo, {"proyecto", "texto", "modo"}, {"contexto"})
    por_id = _chat_registro()
    if not isinstance(c["proyecto"], str) or c["proyecto"] not in por_id:
        raise ValueError("Proyecto no registrado.")
    if c["modo"] not in MODOS_CHAT:
        raise ValueError("modo debe ser 'lectura' o 'cambios'.")
    contexto = c.get("contexto", "auto")
    if contexto not in CONTEXTOS_CHAT:
        raise ValueError("contexto debe ser 'auto', 'sesion' o 'grafo'.")
    texto = _texto_chat(c["texto"])
    if _chat_bloqueado_simulacion():
        return 403, {"ok": False, "error": "Modo simulación: no se envían instrucciones al orquestador real."}
    codigo, d = orq_llamar("POST", "/api/instruccion", {"proyecto": c["proyecto"], "texto": texto, "modo": c["modo"],
                                                        "contexto": contexto})
    if codigo not in (200, 202) or not isinstance(d.get("id"), str) or not _RE_ID_INSTRUCCION.match(d["id"]):
        return _error_orq(codigo, d)
    return 202, {"ok": True, "id": d["id"], "estado": _cad(d.get("estado"), 40)}


def chat_instruccion(q):
    iid = _id_chat((q.get("id") or [""])[0], _RE_ID_INSTRUCCION)
    codigo, d = orq_llamar("GET", f"/api/instruccion/{iid}")
    if codigo != 200:
        return _error_orq(codigo, d)
    return 200, _vista_instruccion(d)


def chat_accion_instruccion(accion, cuerpo):
    c = _solo_chat(cuerpo, {"id"})
    iid = _id_chat(c["id"], _RE_ID_INSTRUCCION)
    if _chat_bloqueado_simulacion():
        return 403, {"ok": False, "error": "Modo simulación: no se envían instrucciones al orquestador real."}
    codigo, d = orq_llamar("POST", f"/api/instruccion/{iid}/{accion}",
                           {"confirmacion": iid} if accion == "confirmar" else {})
    if codigo not in (200, 202):
        return _error_orq(codigo, d)
    return 200, {"ok": True, "id": iid, "estado": _cad(d.get("estado"), 40)}


def _vista_propuesta(p, por_id):
    ds = p.get("destino_sugerido") if isinstance(p.get("destino_sugerido"), dict) else {}
    g = p.get("grupo") if isinstance(p.get("grupo"), dict) else {}
    sugerido = {"destino": ds.get("destino") if ds.get("destino") in DESTINOS_PROPUESTA else "general"}
    if ds.get("proyecto") in por_id:
        sugerido["proyecto"] = ds["proyecto"]
    return {"id": p["id"], "nombre": _cad(p.get("nombre"), 80), "mensaje": _cad(p.get("mensaje"), 1200),
            "tipo_recomendado": p.get("tipo_recomendado") if p.get("tipo_recomendado") in TIPOS_PROPUESTA else "agente",
            "motivo_tipo": _cad(p.get("motivo_tipo"), 300), "alcance": _cad(p.get("alcance"), 300),
            "destino_sugerido": sugerido, "borrador": _cad(p.get("borrador"), 20000),
            "grupo": {k: _num(g.get(k)) for k in ("veces", "conversaciones", "proyectos")}}


def chat_propuestas_version():
    codigo, d = orq_llamar("GET", "/api/propuestas-agentes/version")
    if codigo != 200:
        return _error_orq(codigo, d)
    return 200, {"ok": True, "version": _num(d.get("version")), "pendientes": _num(d.get("pendientes")),
                 "total": _num(d.get("total"))}


def chat_propuestas(q):
    desde = (q.get("desde") or [""])[0]
    if desde and (not desde.isdigit() or len(desde) > 9):
        raise ValueError("desde debe ser un entero.")
    por_id = _chat_registro()
    ruta = "/api/propuestas-agentes?estado=pendiente" + (f"&desde={desde}" if desde else "")
    codigo, d = orq_llamar("GET", ruta)
    if codigo != 200:
        return _error_orq(codigo, d)
    props = [_vista_propuesta(p, por_id) for p in (d.get("propuestas") or [])
             if isinstance(p, dict) and isinstance(p.get("id"), str) and _RE_ID_PROPUESTA.match(p["id"])
             and p.get("estado", "pendiente") == "pendiente"][:20]
    return 200, {"ok": True, "version": _num(d.get("version")), "propuestas": props}


def chat_propuesta_accion(accion, cuerpo):
    if accion == "crear":
        c = _solo_chat(cuerpo, {"id", "destino"}, {"proyecto", "tipo"})
    else:
        c = _solo_chat(cuerpo, {"id"})
    pid = _id_chat(c["id"], _RE_ID_PROPUESTA)
    envio = {}
    if accion == "crear":
        if c["destino"] not in DESTINOS_PROPUESTA:
            raise ValueError("destino debe ser 'general' o 'proyecto'.")
        envio = {"confirmacion": pid, "destino": c["destino"]}
        if "proyecto" in c:
            if c["destino"] != "proyecto" or not isinstance(c["proyecto"], str) or c["proyecto"] not in _chat_registro():
                raise ValueError("proyecto solo aplica con destino 'proyecto' y debe estar registrado.")
            envio["proyecto"] = c["proyecto"]
        elif c["destino"] == "proyecto":
            raise ValueError("Falta el proyecto de destino.")
        if "tipo" in c:
            if c["tipo"] not in TIPOS_PROPUESTA:
                raise ValueError("tipo debe ser agente, skill o comando.")
            envio["tipo"] = c["tipo"]
    if _chat_bloqueado_simulacion():
        return 403, {"ok": False, "error": "Modo simulación: no se escribe nada con el orquestador real."}
    codigo, d = orq_llamar("POST", f"/api/propuestas-agentes/{pid}/{accion}", envio)
    if codigo not in (200, 201):
        return _error_orq(codigo, d)
    return 200, {"ok": True, "id": pid, "archivo": _cad(d.get("archivo"), 400), "aviso": _cad(d.get("aviso"), 600)}


def chat_arrancar_orquestador():
    """Arranca el orquestador (OPCIONAL; argumentos fijos, sin texto del usuario) y espera a que responda.
    Usa el venv que crea `devskills orquestador instalar`. Para pruebas: PANEL_ORQUESTADOR_CMD (lista JSON)."""
    if ESTADO["simular"] and not os.environ.get("PANEL_ORQUESTADOR_CMD"):
        return 200, {"ok": True, "simulado": True, "activo": False,
                     "mensaje": "Simulación: no se arrancó el orquestador (correría orquestador.py iniciar)."}
    cmd = None
    if os.environ.get("PANEL_ORQUESTADOR_CMD"):
        try:
            cmd = json.loads(os.environ["PANEL_ORQUESTADOR_CMD"])
            if not (isinstance(cmd, list) and cmd and all(isinstance(x, str) for x in cmd)):
                raise ValueError
        except ValueError:
            return 500, {"ok": False, "error": "PANEL_ORQUESTADOR_CMD debe ser una lista JSON de argumentos."}
    else:
        py = rutas.python_del_venv(rutas.orquestador_venv())
        if not py.exists():
            return 409, {"ok": False, "error": "El orquestador es opcional y no está instalado: "
                                               "corre `devskills orquestador instalar`."}
        cmd = [str(py), str(RAIZ / "orquestador" / "orquestador.py"), "iniciar"]
    if _orq_ping():
        return 200, {"ok": True, "activo": True, "mensaje": "El orquestador ya estaba corriendo."}
    if not _orq_arranque.acquire(blocking=False):
        return 409, {"ok": False, "error": "Ya se está arrancando el orquestador."}
    try:
        try:
            subprocess.Popen(cmd, cwd=str(RAIZ), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True, **rutas.opciones_desacoplado())
        except OSError as e:
            log(f"No se pudo arrancar el orquestador: {e}")
            return 500, {"ok": False, "error": "No se pudo ejecutar el orquestador."}
        for _ in range(40):
            time.sleep(0.5)
            if _orq_ping():
                log("Orquestador arrancado desde el panel.")
                return 200, {"ok": True, "activo": True}
        return 504, {"ok": False, "error": "El orquestador no respondió a tiempo; revisa orquestador/orquestador.log en el directorio de datos."}
    finally:
        _orq_arranque.release()


def chat_get(ruta, q):
    try:
        if ruta == "/api/chat/estado":
            return chat_estado()
        if ruta == "/api/chat/resolver":
            return chat_resolver(q)
        if ruta == "/api/chat/instruccion":
            return chat_instruccion(q)
        if ruta == "/api/chat/propuestas/version":
            return chat_propuestas_version()
        if ruta == "/api/chat/propuestas":
            return chat_propuestas(q)
        return 404, {"ok": False, "error": "No encontrado."}
    except ValueError as e:
        return 400, {"ok": False, "error": str(e)}
    except OrquestadorNoDisponible as e:
        return 503, {"ok": False, "apagado": True, "error": str(e)}
    except ErrorRegistro as e:
        return 500, {"ok": False, "error": str(e)}


def chat_post(ruta, cuerpo):
    try:
        if ruta == "/api/chat/enviar":
            return chat_enviar(cuerpo)
        if ruta in ("/api/chat/confirmar", "/api/chat/cancelar"):
            return chat_accion_instruccion(ruta.rsplit("/", 1)[1], cuerpo)
        if ruta in ("/api/chat/propuestas/crear", "/api/chat/propuestas/descartar"):
            return chat_propuesta_accion(ruta.rsplit("/", 1)[1], cuerpo)
        if ruta == "/api/chat/orquestador/arrancar":
            _solo_chat(cuerpo, set())
            return chat_arrancar_orquestador()
        return 404, {"ok": False, "error": "No encontrado."}
    except ValueError as e:
        return 400, {"ok": False, "error": str(e)}
    except OrquestadorNoDisponible as e:
        return 503, {"ok": False, "apagado": True, "error": str(e)}
    except ErrorRegistro as e:
        return 500, {"ok": False, "error": str(e)}


# ---------------------------------------------------------------- HTTP

class Manejador(BaseHTTPRequestHandler):
    server_version = "PanelLocal/2.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def _origen_valido(self):
        p = ESTADO["puerto"]
        permitidos_host = {f"127.0.0.1:{p}", f"localhost:{p}"}
        if self.headers.get("Host", "") not in permitidos_host:
            return False
        origen = self.headers.get("Origin")
        if origen is not None and origen not in {f"http://{h}" for h in permitidos_host}:
            return False
        sitio = self.headers.get("Sec-Fetch-Site")
        if sitio is not None and sitio not in ("same-origin", "none"):
            return False
        return True

    def _token_valido(self):
        return secrets.compare_digest(self.headers.get("X-Panel-Token", ""), ESTADO["token"])

    def _enviar(self, codigo, cuerpo, tipo="application/json; charset=utf-8"):
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; "
                         "form-action 'none'")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(datos)

    def _proteger(self):
        if not self._origen_valido():
            self._enviar(403, {"ok": False, "error": "Origen o Host no permitido."})
            return False
        if not self._token_valido():
            self._enviar(403, {"ok": False, "error": "Falta el token del panel."})
            return False
        return True

    def _rechazar_sin_leer(self, codigo, error):
        """Responde sin consumir el cuerpo pendiente y cierra la conexión."""
        self.close_connection = True
        self._enviar(codigo, {"ok": False, "error": error})

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            if not self._origen_valido():
                return self._enviar(403, {"ok": False, "error": "Origen o Host no permitido."})
            if self.headers.get("Host", "").startswith("localhost:"):
                # Un solo origen (127.0.0.1): localStorage es por origen y con dos el color "se perdía".
                self.send_response(308)
                self.send_header("Location", base_url(ESTADO["puerto"]) + "/")
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            try:
                html = INDEX.read_text(encoding="utf-8").replace("__PANEL_TOKEN__", ESTADO["token"])
            except OSError:
                return self._enviar(500, {"ok": False, "error": "No se encontró index.html"})
            return self._enviar(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if u.path in ("/favicon.svg", "/favicon.ico"):
            # Estático y público: sin token, pero con la misma validación de Host/Origin (anti DNS rebinding).
            if not self._origen_valido():
                return self._enviar(403, {"ok": False, "error": "Origen o Host no permitido."})
            if u.path == "/favicon.ico":
                # Los navegadores piden /favicon.ico por su cuenta; se redirige al SVG (no hay .ico binario que mantener).
                self.send_response(308)
                self.send_header("Location", "/favicon.svg")
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            try:
                return self._enviar(200, ICONO.read_bytes(), "image/svg+xml")
            except OSError:
                return self._enviar(404, {"ok": False, "error": "No se encontró favicon.svg"})
        if u.path == "/api/ping":
            if not self._origen_valido():
                return self._enviar(403, {"ok": False})
            return self._enviar(200, {"ok": True, "panel": True})
        if not u.path.startswith("/api/"):
            return self._enviar(404, {"ok": False, "error": "No encontrado."})
        if not self._proteger():
            return
        q = parse_qs(u.query)
        try:
            if u.path == "/api/proyectos":
                return self._enviar(200, estado_proyectos())
            if u.path == "/api/proyecto":
                reg = registro()
                p = reg["por_id"].get((q.get("id") or [""])[0])
                if not p:
                    return self._enviar(404, {"ok": False, "error": "Proyecto no encontrado."})
                datos = vista_proyecto(p, puertos_en_escucha(), contar_activos(reg), salud=True)
                acciones = resumen_acciones([p["id"]] + [s["id"] for s in p["servicios"]])
                return self._enviar(200, {**datos, "cuentas": reg["cuentas"], "simulacion": ESTADO["simular"],
                                          "acciones": acciones})
            if u.path == "/api/acciones":
                reg = registro()
                objetivo = (q.get("objetivo") or [""])[0]
                if objetivo not in reg["por_id"] and objetivo not in reg["servicios"]:
                    return self._enviar(404, {"ok": False, "error": "Servicio o proyecto no encontrado."})
                return self._enviar(200, {"ok": True, "objetivo": objetivo, "acciones": historial_acciones(objetivo)})
            if u.path == "/api/avisos":
                proyecto = (q.get("proyecto") or [""])[0]
                if proyecto and not _ID.match(proyecto):
                    return self._enviar(400, {"ok": False, "error": "Proyecto inválido."})
                try:
                    pagina = int((q.get("pagina") or ["0"])[0])
                    limite = int((q.get("limite") or ["50"])[0])
                except ValueError:
                    return self._enviar(400, {"ok": False, "error": "pagina y limite deben ser enteros."})
                if not 0 <= pagina <= 1000 or not 1 <= limite <= 100:
                    return self._enviar(400, {"ok": False, "error": "pagina (0-1000) o limite (1-100) fuera de rango."})
                version = (q.get("version") or [None])[0]
                return self._enviar(200, {**consultar_avisos(proyecto or None, pagina, limite, version),
                                          "simulacion": ESTADO["simular"]})
            if u.path.startswith("/api/chat/"):
                return self._enviar(*chat_get(u.path, q))
            if u.path == "/api/agentes":
                try:
                    horas = float((q.get("horas") or ["6"])[0])
                except ValueError:
                    horas = 6.0
                horas = min(max(horas, 0.25), 72.0)
                try:
                    return self._enviar(200, estado_agentes((q.get("proyecto") or [""])[0], horas))
                except KeyError:
                    return self._enviar(404, {"ok": False, "error": "Proyecto no encontrado."})
            if u.path == "/api/sesiones":
                try:
                    return self._enviar(200, sesiones_para_retomar((q.get("proyecto") or [""])[0]))
                except KeyError:
                    return self._enviar(404, {"ok": False, "error": "Proyecto no encontrado."})
            if u.path == "/api/sesiones-recientes":
                return self._enviar(200, {**sesiones_recientes(), "simulacion": ESTADO["simular"]})
            if u.path == "/api/github":
                return self._enviar(200, {"gh": estado_gh(), "cuentas": registro()["cuentas"],
                                          "instruccion_login": INSTRUCCION_LOGIN, "simulacion": ESTADO["simular"]})
            if u.path == "/api/proyecto/credencial":
                try:
                    return self._enviar(200, credencial_repo((q.get("id") or [""])[0]))
                except KeyError:
                    return self._enviar(404, {"ok": False, "error": "Proyecto no encontrado."})
            if u.path == "/api/tokens":
                if set(q) - {"forzar"} or q.get("forzar", ["1"]) != ["1"]:
                    return self._enviar(400, {"ok": False, "error": "Solo se acepta ?forzar=1."})
                return self._enviar(200, calcular_tokens(forzar="forzar" in q))
            if u.path == "/api/deteccion":
                if set(q) - {"forzar"} or q.get("forzar", ["1"]) != ["1"]:
                    return self._enviar(400, {"ok": False, "error": "Solo se acepta ?forzar=1."})
                return self._enviar(200, detectar(forzar="forzar" in q))
            if u.path == "/api/enrutamiento":
                pid = (q.get("id") or [""])[0]
                if not _ID.match(pid):
                    return self._enviar(400, {"ok": False, "error": "Proyecto inválido."})
                try:
                    return self._enviar(200, estado_enrutamiento(pid))
                except KeyError:
                    return self._enviar(404, {"ok": False, "error": "Proyecto no encontrado."})
            if u.path == "/api/preferencias":
                return self._enviar(200, {"ok": True, **leer_preferencias(), "guardadas": sorted(_preferencias_guardadas())})
            if u.path == "/api/laboratorio":
                return self._enviar(200, estado_laboratorio(registro()))
            if u.path == "/api/laboratorio/resultado":
                try:
                    return self._enviar(200, leer_resultado((q.get("id") or [""])[0],
                                                            (q.get("archivo") or ["INFORME.md"])[0]))
                except ValueError as e:
                    return self._enviar(400, {"ok": False, "error": str(e)})
                except OSError:
                    return self._enviar(404, {"ok": False, "error": "Todavía no hay ese archivo de resultado."})
        except ErrorRegistro as e:
            return self._enviar(500, {"ok": False, "error": str(e)})
        return self._enviar(404, {"ok": False, "error": "No encontrado."})

    def do_POST(self):
        u = urlparse(self.path)
        if not self._proteger():
            self.close_connection = True
            return
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._rechazar_sin_leer(400, "Content-Length inválido.")
        if largo < 0:
            return self._rechazar_sin_leer(400, "Content-Length inválido.")
        if u.path == "/api/laboratorio/archivo":
            return self._subir_archivo(largo)
        if largo > MAX_JSON:
            return self._rechazar_sin_leer(413, "Cuerpo demasiado grande.")
        try:
            cuerpo = json.loads(self.rfile.read(largo) or b"{}") if largo else {}
        except ValueError:
            return self._enviar(400, {"ok": False, "error": "JSON inválido."})
        if not isinstance(cuerpo, dict):
            return self._enviar(400, {"ok": False, "error": "JSON inválido."})
        if u.path.startswith("/api/chat/"):
            return self._enviar(*chat_post(u.path, cuerpo))
        if u.path == "/api/accion":
            objetivo, accion = cuerpo.get("objetivo") or cuerpo.get("servicio"), cuerpo.get("accion")
            if not isinstance(objetivo, str) or not isinstance(accion, str):
                return self._enviar(400, {"ok": False, "error": "Servicio, proyecto o acción no permitidos."})
            codigo, r = ejecutar_accion(objetivo, accion)
            return self._enviar(codigo, r)
        if u.path in ("/api/github/cuenta", "/api/proyecto/credencial"):
            # Lista blanca estricta: solo ids (cuenta de 'cuentas', proyecto del registro); nada de texto libre.
            claves = {"cuenta"} if u.path == "/api/github/cuenta" else {"proyecto", "cuenta"}
            if set(cuerpo) != claves or not all(isinstance(cuerpo[k], str) for k in claves):
                return self._enviar(400, {"ok": False, "error": "Solo se acepta " + json.dumps({k: "id" for k in sorted(claves)}) + "."})
            try:
                if u.path == "/api/github/cuenta":
                    codigo, r = usar_cuenta_gh(cuerpo["cuenta"])
                else:
                    codigo, r = fijar_cuenta_repo(cuerpo["proyecto"], cuerpo["cuenta"])
            except ErrorRegistro as e:
                return self._enviar(500, {"ok": False, "error": str(e)})
            except KeyError:
                return self._enviar(404, {"ok": False, "error": "Proyecto no encontrado."})
            except ValueError as e:
                return self._enviar(400, {"ok": False, "error": str(e)})
            return self._enviar(codigo, r)
        if u.path in ("/api/deteccion/agregar", "/api/deteccion/actualizar", "/api/enrutamiento",
                      "/api/enrutamiento/tabla"):
            return self._post_deteccion(u.path, cuerpo)
        if u.path == "/api/laboratorio/solicitud":
            try:
                return self._enviar(200, {"ok": True, "solicitud": crear_solicitud_enlace(cuerpo, registro())})
            except ErrorRegistro as e:
                return self._enviar(500, {"ok": False, "error": str(e)})
            except ValueError as e:
                return self._enviar(400, {"ok": False, "error": str(e)})
            except OSError as e:
                return self._enviar(500, {"ok": False, "error": f"No se pudo guardar la solicitud: {e}"})
        if u.path == "/api/avisos/leidos":
            # Solo {"ids": [ids de aviso]}, {"todos": true} o {"todos": true, "hasta": ts} (ts de lo que se vio).
            if set(cuerpo) in ({"todos"}, {"todos", "hasta"}) and cuerpo["todos"] is True:
                hasta = cuerpo.get("hasta")
                if "hasta" in cuerpo and (isinstance(hasta, bool) or not isinstance(hasta, (int, float))
                                          or not 0 <= hasta < 4102444800):
                    return self._enviar(400, {"ok": False, "error": "hasta debe ser un timestamp (segundos)."})
                return self._enviar(200, {"ok": True, "cambiados": marcar_avisos_leidos(None, hasta)})
            ids = cuerpo.get("ids")
            if (set(cuerpo) != {"ids"} or not isinstance(ids, list) or not 1 <= len(ids) <= MAX_AVISOS
                    or not all(isinstance(x, str) and _RE_ID_AVISO.match(x) for x in ids)):
                return self._enviar(400, {"ok": False, "error": "Solo se acepta {\"ids\": [ids de aviso]} o {\"todos\": true}."})
            return self._enviar(200, {"ok": True, "cambiados": marcar_avisos_leidos(set(ids))})
        if u.path == "/api/panel/apagar":
            self._enviar(200, {"ok": True, "mensaje": "Apagando el panel."})
            threading.Thread(target=ESTADO["servidor"].shutdown, daemon=True).start()
            return
        return self._enviar(404, {"ok": False, "error": "No encontrado."})

    def _post_deteccion(self, ruta, cuerpo):
        """Detección (agregar / actualizar) y enrutamiento (activar / tabla). Claves exactas; nada de texto libre que
        llegue a un comando: todo pasa por construir_servicio o por la lista blanca de modelos y esfuerzos."""
        try:
            if ruta == "/api/deteccion/agregar":
                return self._enviar(200, agregar_detectado(cuerpo))
            if ruta == "/api/deteccion/actualizar":
                if set(cuerpo) != {"proyecto"} or not isinstance(cuerpo["proyecto"], str):
                    return self._enviar(400, {"ok": False, "error": 'Solo se acepta {"proyecto": "id"}.'})
                return self._enviar(200, actualizar_desde_deteccion(cuerpo["proyecto"]))
            if ruta == "/api/enrutamiento":
                if (set(cuerpo) != {"proyecto", "activo"} or not isinstance(cuerpo["proyecto"], str)
                        or not _ID.match(cuerpo["proyecto"]) or not isinstance(cuerpo["activo"], bool)):
                    return self._enviar(400, {"ok": False, "error": 'Solo se acepta {"proyecto": "id", "activo": true|false}.'})
                codigo, r = activar_enrutamiento(cuerpo["proyecto"], cuerpo["activo"])
                return self._enviar(codigo, r)
            if (set(cuerpo) != {"proyecto", "tabla"} or not isinstance(cuerpo["proyecto"], str)
                    or not _ID.match(cuerpo["proyecto"])):
                return self._enviar(400, {"ok": False, "error": 'Solo se acepta {"proyecto": "id", "tabla": {...}}.'})
            codigo, r = guardar_tabla_enrutamiento(cuerpo["proyecto"], cuerpo["tabla"])
            return self._enviar(codigo, r)
        except KeyError:
            return self._enviar(404, {"ok": False, "error": "Proyecto no encontrado en el registro o en la detección."})
        except FileExistsError as e:
            return self._enviar(409, {"ok": False, "error": str(e)})
        except ValueError as e:
            return self._enviar(400, {"ok": False, "error": str(e)})
        except ErrorRegistro as e:
            return self._enviar(400 if ruta.startswith("/api/deteccion") else 500, {"ok": False, "error": str(e)})
        except (OSError, RuntimeError) as e:
            log(f"Falló {ruta}: {type(e).__name__}: {e}")
            return self._enviar(500, {"ok": False, "error": "No se pudo escribir; no se cambió nada."})

    def _subir_archivo(self, largo):
        # Todo se valida ANTES de leer el cuerpo: tamaño, metadatos, casilla y nombre del archivo.
        if largo == 0:
            return self._rechazar_sin_leer(400, "El archivo está vacío.")
        if largo > MAX_SUBIDA:
            return self._rechazar_sin_leer(413, f"El archivo supera el límite de {MAX_SUBIDA // (1024 * 1024)} MB.")
        try:
            meta = json.loads(unquote(self.headers.get("X-Lab-Datos") or ""))
        except ValueError:
            return self._rechazar_sin_leer(400, "Metadatos inválidos.")
        try:
            reg = registro()
            validar_meta_lab(meta, reg)
            RutaArchivoSegura(meta.get("nombre"))
        except ErrorRegistro as e:
            return self._rechazar_sin_leer(500, str(e))
        except ValueError as e:
            return self._rechazar_sin_leer(400, str(e))
        try:
            sol = recibir_archivo(self.rfile, largo, meta, reg)
        except ValueError as e:
            return self._rechazar_sin_leer(400, str(e))
        except OSError as e:
            return self._rechazar_sin_leer(500, f"No se pudo guardar el archivo: {e}")
        return self._enviar(200, {"ok": True, "solicitud": sol})

    def _no_permitido(self):
        self.close_connection = True
        self._enviar(405, {"ok": False, "error": "Método no permitido."})

    def do_PUT(self):
        """PUT /api/preferencias con una o más claves de VALIDADORES_PREFERENCIA (p. ej. {"acento": "#rrggbb"},
        {"vista_avisos": "burbuja"}) y PUT /api/proyecto/cuenta {"proyecto", "cuenta"}; todo lo demás se rechaza."""
        ruta = urlparse(self.path).path
        if ruta not in ("/api/preferencias", "/api/proyecto/cuenta"):
            return self._no_permitido()
        if not self._proteger():
            self.close_connection = True
            return
        if ruta == "/api/proyecto/cuenta":
            return self._cambiar_cuenta()
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            return self._rechazar_sin_leer(415, "Se espera JSON.")
        try:
            largo = int(self.headers.get("Content-Length") or "x")
        except ValueError:
            return self._rechazar_sin_leer(400, "Content-Length inválido.")
        if largo <= 0 or largo > MAX_PREFERENCIAS:
            return self._rechazar_sin_leer(413 if largo > 0 else 400, "Cuerpo inválido.")
        try:
            cuerpo = json.loads(self.rfile.read(largo))
        except ValueError:
            return self._enviar(400, {"ok": False, "error": "JSON inválido."})
        if not isinstance(cuerpo, dict) or not cuerpo or not set(cuerpo) <= set(VALIDADORES_PREFERENCIA):
            return self._enviar(400, {"ok": False, "error": "Solo se aceptan las claves " + ", ".join(VALIDADORES_PREFERENCIA) + "."})
        cambios = {}
        for k, v in cuerpo.items():
            valido = VALIDADORES_PREFERENCIA[k](v)
            if valido is None:
                error = {"acento": "El color debe ser #RRGGBB.",
                         "vista_avisos": "vista_avisos debe ser " + " o ".join(f'"{x}"' for x in VISTAS_AVISOS) + ".",
                         "presupuesto": 'presupuesto debe ser {"unidad": "tokens"|"usd", "cinco_horas"|"hoy"|"semana"|"mes": número > 0}.',
                         }.get(k, f"{k} debe ser true o false.")
                return self._enviar(400, {"ok": False, "error": error})
            cambios[k] = valido
        try:
            prefs = guardar_preferencias(cambios)
        except OSError as e:
            log(f"No se pudieron guardar las preferencias: {e}")
            return self._enviar(500, {"ok": False, "error": "No se pudieron guardar las preferencias."})
        return self._enviar(200, {"ok": True, **prefs})

    def _cambiar_cuenta(self):
        """Solo acepta {"proyecto": <id del registro>, "cuenta": <id de la lista 'cuentas'>}."""
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            return self._rechazar_sin_leer(415, "Se espera JSON.")
        try:
            largo = int(self.headers.get("Content-Length") or "x")
        except ValueError:
            return self._rechazar_sin_leer(400, "Content-Length inválido.")
        if largo <= 0 or largo > MAX_CUENTA_JSON:
            return self._rechazar_sin_leer(413 if largo > 0 else 400, "Cuerpo inválido.")
        try:
            cuerpo = json.loads(self.rfile.read(largo))
        except ValueError:
            return self._enviar(400, {"ok": False, "error": "JSON inválido."})
        if (not isinstance(cuerpo, dict) or set(cuerpo) != {"proyecto", "cuenta"}
                or not isinstance(cuerpo["proyecto"], str) or not isinstance(cuerpo["cuenta"], str)):
            return self._enviar(400, {"ok": False, "error": "Solo se acepta {\"proyecto\": \"id\", \"cuenta\": \"id\"}."})
        try:
            r = cambiar_cuenta(cuerpo["proyecto"], cuerpo["cuenta"])
        except ErrorRegistro as e:
            return self._enviar(500, {"ok": False, "error": str(e)})
        except ValueError as e:
            return self._enviar(400, {"ok": False, "error": str(e)})
        except (OSError, RuntimeError) as e:
            log(f"No se pudo cambiar la cuenta de {cuerpo['proyecto']}: {e}")
            return self._enviar(500, {"ok": False, "error": "No se pudo guardar el registro."})
        return self._enviar(200, {"ok": True, **r})

    def do_DELETE(self):
        """DELETE /api/preferencias: restablece el color (las demás preferencias se conservan).
        DELETE /api/avisos?id=<id>: borra un aviso; DELETE /api/avisos?todos=1: borra todos."""
        u = urlparse(self.path)
        if u.path not in ("/api/preferencias", "/api/avisos"):
            return self._no_permitido()
        if not self._proteger():
            self.close_connection = True
            return
        if (self.headers.get("Content-Length") or "0") != "0":
            return self._rechazar_sin_leer(400, "Sin cuerpo.")
        if u.path == "/api/avisos":
            q = parse_qs(u.query)
            if set(q) == {"todos"} and q["todos"] == ["1"]:
                return self._enviar(200, {"ok": True, "borrados": borrar_avisos(None)})
            ids = q.get("id") or []
            if set(q) != {"id"} or len(ids) != 1 or not _RE_ID_AVISO.match(ids[0]):
                return self._enviar(400, {"ok": False, "error": "Usa ?id=<id de aviso> o ?todos=1."})
            borrados = borrar_avisos(ids[0])
            if not borrados:
                return self._enviar(404, {"ok": False, "error": "Aviso no encontrado."})
            return self._enviar(200, {"ok": True, "borrados": borrados})
        try:
            prefs = guardar_preferencias({}, quitar=("acento",))
        except OSError as e:
            log(f"No se pudieron borrar las preferencias: {e}")
            return self._enviar(500, {"ok": False, "error": "No se pudieron borrar las preferencias."})
        return self._enviar(200, {"ok": True, **prefs})

    do_PATCH = _no_permitido


# ---------------------------------------------------------------- CLI

def base_url(puerto):
    return f"http://{HOST}:{puerto}"


def ping(puerto):
    try:
        with urllib.request.urlopen(base_url(puerto) + "/api/ping", timeout=1) as r:
            return json.loads(r.read()).get("panel") is True
    except Exception:
        return False


def servir(puerto, simular, laboratorio, registro_alt=None, extra=None):
    global REGISTRO, PROYECTOS_CLAUDE, TEMP_CLAUDE, HISTORIAL_ORQUESTADOR
    extra = extra or {}
    if registro_alt:
        REGISTRO = Path(registro_alt).resolve()
    if extra.get("historial_orquestador"):
        HISTORIAL_ORQUESTADOR = Path(extra["historial_orquestador"]).resolve()
    if extra.get("claude_proyectos"):
        PROYECTOS_CLAUDE = Path(extra["claude_proyectos"]).resolve()
    if extra.get("claude_temp"):
        TEMP_CLAUDE = Path(extra["claude_temp"]).resolve()
    if extra.get("raices"):
        ESTADO["raices"] = [Path(r).resolve() for r in extra["raices"].split(";") if r.strip()]
    ESTADO.update(token=secrets.token_urlsafe(32), puerto=puerto, simular=simular,
                  laboratorio=Path(laboratorio) if laboratorio else rutas.laboratorio(),
                  estado_dir=Path(extra["estado"]).resolve() if extra.get("estado") else carpeta_estado_por_omision(puerto))
    for sub in ("entrada", "solicitudes"):
        carpeta_lab(sub).mkdir(parents=True, exist_ok=True)
    Path(ESTADO["estado_dir"]).mkdir(parents=True, exist_ok=True)
    iniciar_detector()
    iniciar_tokens()
    servidor = ThreadingHTTPServer((HOST, puerto), Manejador)
    servidor.daemon_threads = True
    ESTADO["servidor"] = servidor
    token = archivo_token(puerto)
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(json.dumps({"token": ESTADO["token"], "puerto": puerto, "pid": os.getpid()}), encoding="utf-8")
    rutas.restringir(token)
    log(f"Panel escuchando en {base_url(puerto)} (simular={simular}, pid={os.getpid()}, "
        f"laboratorio={ESTADO['laboratorio']}, registro={REGISTRO}, estado={ESTADO['estado_dir']}, "
        f"transcripts={PROYECTOS_CLAUDE} | {TEMP_CLAUDE}, raíces={ESTADO.get('raices') or 'por omisión'})")
    try:
        servidor.serve_forever(poll_interval=0.5)
    finally:
        servidor.server_close()
        try:
            token.unlink()
        except OSError:
            pass
        log("Panel detenido.")


OPCIONES_RUTA = {"--estado": "estado", "--claude-proyectos": "claude_proyectos", "--claude-temp": "claude_temp",
                 "--historial-orquestador": "historial_orquestador"}


def iniciar(puerto, simular, abrir, laboratorio, registro_alt=None, extra=None):
    if not ping(puerto):
        exe = Path(sys.executable)
        sin_consola = exe.with_name("pythonw.exe")
        exe = sin_consola if sin_consola.exists() else exe
        args = [str(exe), str(Path(__file__).resolve()), "servir", "--puerto", str(puerto)]
        if simular:
            args.append("--simular")
        if laboratorio:
            args += ["--laboratorio", str(laboratorio)]
        if registro_alt:
            args += ["--registro", str(Path(registro_alt).resolve())]
        for opcion, clave in OPCIONES_RUTA.items():
            if (extra or {}).get(clave):
                args += [opcion, str(Path(extra[clave]).resolve())]
        if (extra or {}).get("raices"):
            args += ["--raices", ";".join(str(Path(r).resolve()) for r in extra["raices"].split(";") if r.strip())]
        subprocess.Popen(args, cwd=str(AQUI), close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **rutas.opciones_desacoplado())
        for _ in range(40):
            time.sleep(0.25)
            if ping(puerto):
                break
        else:
            print(f"El panel no respondió. Revisa {ARCHIVO_LOG}")
            return 1
        print(f"Panel iniciado en {base_url(puerto)}" + (" (simulación)" if simular else ""))
    else:
        print(f"El panel ya estaba corriendo en {base_url(puerto)}")
    if abrir:
        webbrowser.open(base_url(puerto) + "/")
    return 0


def apagar(puerto):
    archivo = archivo_token(puerto)
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("El panel no está corriendo (no hay archivo de token).")
        return 0
    puerto = datos.get("puerto", puerto)
    req = urllib.request.Request(base_url(puerto) + "/api/panel/apagar", data=b"{}", method="POST",
                                 headers={"X-Panel-Token": datos.get("token", ""),
                                          "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=3).read()
        print("Panel apagado.")
    except Exception as e:
        print(f"No se pudo contactar al panel ({e}); quizá ya estaba detenido.")
        try:
            archivo.unlink()
        except OSError:
            pass
    return 0


def _opcion(argv, nombre):
    if nombre in argv:
        i = argv.index(nombre)
        if i + 1 >= len(argv):
            raise SystemExit(f"Falta el valor de {nombre}")
        valor = argv[i + 1]
        del argv[i:i + 2]
        return valor
    return None


def main(argv):
    argv = list(argv)
    puerto = int(_opcion(argv, "--puerto") or PUERTO_DEFAULT)
    laboratorio = _opcion(argv, "--laboratorio")
    registro_alt = _opcion(argv, "--registro")
    extra = {clave: _opcion(argv, opcion) for opcion, clave in OPCIONES_RUTA.items()}
    extra["raices"] = _opcion(argv, "--raices")
    comando = next((a for a in argv if not a.startswith("--")), "iniciar")
    simular = "--simular" in argv or os.environ.get("PANEL_SIMULAR") == "1"
    if comando in ("iniciar", "abrir"):
        return iniciar(puerto, simular, "--no-abrir" not in argv, laboratorio, registro_alt, extra)
    if comando == "servir":
        servir(puerto, simular, laboratorio, registro_alt, extra)
        return 0
    if comando in ("apagar", "detener"):
        return apagar(puerto)
    if comando == "estado":
        print("corriendo" if ping(puerto) else "detenido")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
