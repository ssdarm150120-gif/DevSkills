"""API HTTP local (solo stdlib). Escucha únicamente en 127.0.0.1 y exige el token del archivo .token.

Defensas: Host debe ser 127.0.0.1:<puerto> o localhost:<puerto> (anti DNS rebinding); si llega Origin debe ser el
mismo origen; sin CORS; token por cabecera X-Orquestador-Token comparado en tiempo constante; cuerpo JSON de
máximo 16 KB con campos en lista blanca.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import enrutamiento as mod_enr
from . import resolver as mod_resolver
from . import validacion as v
from .ejecutor import EstadoInvalido
from .propuestas import Conflicto, ErrorPropuesta

log = logging.getLogger("orquestador")
MAX_CUERPO = 16 * 1024
CABECERA_TOKEN = "X-Orquestador-Token"

R_INV = re.compile(r"^/api/inventario/([^/]+)$")
R_INS = re.compile(r"^/api/instruccion/([^/]+)$")
R_ACC = re.compile(r"^/api/instruccion/([^/]+)/(confirmar|cancelar)$")
R_CTX = re.compile(r"^/api/contexto/([^/]+)$")
R_GRAFO = re.compile(r"^/api/grafo/([^/]+)$")
R_PROP = re.compile(r"^/api/propuestas-agentes/([^/]+)$")
R_PROP_ACC = re.compile(r"^/api/propuestas-agentes/([^/]+)/(crear|descartar)$")
MAX_RESOLVER = 500


class Servicio:
    """Agrupa las dependencias que usa el manejador HTTP (facilita las pruebas)."""

    def __init__(self, ajustes, registro, inventario, engram, ejecutor, token: str, puerto: int,
                 grafo=None, propuestas=None):
        self.a = ajustes
        self.grafo = grafo
        self.propuestas = propuestas
        self.registro = registro
        self.inventario = inventario
        self.engram = engram
        self.ejecutor = ejecutor
        self.token = token
        self.puerto = puerto
        self.servidor: ThreadingHTTPServer | None = None


class Manejador(BaseHTTPRequestHandler):
    servicio: Servicio  # se asigna en crear_servidor
    server_version = "orquestador/1"
    sys_version = ""

    def log_message(self, fmt, *args):  # sin query strings ni cuerpos en el log
        log.debug("%s %s", self.command, urlsplit(self.path).path)

    # ------------------------------------------------------------ utilidades
    def _json(self, codigo: int, datos) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _host_ok(self) -> bool:
        s = self.servicio
        host = (self.headers.get("Host") or "").lower()
        if host not in (f"127.0.0.1:{s.puerto}", f"localhost:{s.puerto}"):
            return False
        origen = self.headers.get("Origin")
        return origen is None or origen.lower() in (f"http://127.0.0.1:{s.puerto}", f"http://localhost:{s.puerto}")

    def _token_ok(self) -> bool:
        return secrets.compare_digest(self.headers.get(CABECERA_TOKEN, ""), self.servicio.token)

    def _cuerpo(self):
        tipo = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if tipo != "application/json":
            raise v.ErrorValidacion("Content-Type debe ser application/json")
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise v.ErrorValidacion("Content-Length inválido")
        if largo <= 0 or largo > MAX_CUERPO:
            raise v.ErrorValidacion(f"cuerpo vacío o mayor a {MAX_CUERPO} bytes")
        try:
            return json.loads(self.rfile.read(largo).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise v.ErrorValidacion("JSON inválido")

    def _proteger(self, metodo) -> None:
        if not self._host_ok():
            return self._json(403, {"error": "host u origen no permitido"})
        ruta = urlsplit(self.path).path
        if ruta == "/api/ping" and self.command == "GET":
            return self._json(200, {"orquestador": True})
        if not self._token_ok():
            return self._json(401, {"error": "token ausente o inválido"})
        try:
            metodo(ruta)
        except (v.ErrorValidacion, ErrorPropuesta) as e:
            self._json(400, {"error": str(e)})
        except KeyError:
            self._json(404, {"error": "no encontrado"})
        except (EstadoInvalido, Conflicto) as e:
            self._json(409, {"error": str(e)})
        except Exception:  # noqa: BLE001
            log.exception("Error atendiendo %s %s", self.command, ruta)
            self._json(500, {"error": "error interno (ver orquestador.log)"})

    # ------------------------------------------------------------ rutas
    def do_GET(self):
        self._proteger(self._get)

    def do_POST(self):
        self._proteger(self._post)

    def _no_permitido(self):
        self._json(405, {"error": "método no permitido"})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _no_permitido

    def _get(self, ruta: str) -> None:
        s = self.servicio
        permitidos = s.registro.proyectos()
        if ruta == "/api/estado":
            return self._json(200, {"puerto": s.puerto, "cola": s.ejecutor.estado(),
                                    "proyectos": len(permitidos), "engram": s.engram.disponible()})
        if ruta == "/api/inventario":
            return self._json(200, s.inventario.todos())
        if m := R_INV.match(ruta):
            return self._json(200, s.inventario.proyecto(v.proyecto(m.group(1), permitidos)))
        if ruta == "/api/instrucciones":
            return self._json(200, {"instrucciones": [_resumen(r) for r in s.ejecutor.almacen.listar()]})
        if m := R_INS.match(ruta):
            r = s.ejecutor.obtener(v.id_instruccion(m.group(1)))
            if r is None:
                raise KeyError(m.group(1))
            return self._json(200, r)
        if m := R_CTX.match(ruta):
            pid = v.proyecto(m.group(1), permitidos)
            qs = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            if set(qs) - {"q"} or len(qs.get("q", [])) > 1:
                raise v.ErrorValidacion("solo se acepta el parámetro q")
            q = v.consulta((qs.get("q") or [""])[0], s.a.max_consulta)
            alias = s.engram.alias(pid)
            if not s.engram.disponible():
                return self._json(503, {"error": "engram no disponible"})
            return self._json(200, {"proyecto": pid, "engram_proyectos": alias, "q": q,
                                    "resultados": s.engram.buscar(alias, q)})
        if m := R_GRAFO.match(ruta):
            pid = v.proyecto(m.group(1), permitidos)
            q = v.consulta(self._param("q"), s.a.max_consulta)
            carpeta = permitidos[pid].carpeta
            estado = s.grafo.estado(carpeta)
            salida = {"proyecto": pid, "grafo": estado, "q": q, "resumen": "", "resultado": None}
            if estado.get("tiene_grafo"):
                maximo = int(s.a.grafo["api_max_chars"])
                salida["resumen"] = s.grafo.resumen(carpeta, min(maximo, int(s.a.grafo["resumen_chars"])))
                if q:
                    salida["resultado"] = s.grafo.consultar(carpeta, q, maximo)
            return self._json(200, salida)
        if ruta == "/api/enrutamiento":
            self._params(set())
            return self._json(200, mod_enr.resumen(s.ejecutor.almacen.listar(limite=10_000), permitidos,
                                                   s.ejecutor.fallos))
        if ruta == "/api/resolver":
            texto = v.consulta(self._param("texto"), MAX_RESOLVER)
            if not texto:
                raise v.ErrorValidacion("falta el parámetro texto")
            return self._json(200, {"texto": texto, **mod_resolver.resolver(texto, permitidos, s.a.alias_proyectos)})
        if ruta == "/api/propuestas-agentes":
            qs = self._params({"estado", "desde"})
            desde = qs.get("desde")
            if desde is not None and (not desde.isdigit() or len(desde) > 9):
                raise v.ErrorValidacion("desde debe ser un entero (versión)")
            return self._json(200, s.propuestas.listar(qs.get("estado"), int(desde) if desde else None))
        if ruta == "/api/propuestas-agentes/version":
            return self._json(200, s.propuestas.version())
        if m := R_PROP.match(ruta):
            return self._json(200, s.propuestas.obtener(m.group(1)))
        raise KeyError(ruta)

    def _params(self, permitidos: set[str]) -> dict[str, str]:
        qs = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if set(qs) - permitidos or any(len(x) > 1 for x in qs.values()):
            raise v.ErrorValidacion("parámetros permitidos: " + ", ".join(sorted(permitidos)))
        return {k: x[0] for k, x in qs.items()}

    def _param(self, nombre: str) -> str:
        return self._params({nombre}).get(nombre, "")

    def _post(self, ruta: str) -> None:
        s = self.servicio
        if ruta == "/api/instruccion":
            datos = v.instruccion(self._cuerpo(), s.registro.proyectos(), s.a.max_texto)
            r = s.ejecutor.recibir(datos)
            return self._json(202 if r["estado"] == "en_cola" else 200, r)
        if m := R_ACC.match(ruta):
            iid = v.id_instruccion(m.group(1))
            if m.group(2) == "confirmar":
                v.confirmacion(self._cuerpo(), iid)
                return self._json(202, s.ejecutor.confirmar(iid))
            return self._json(200, s.ejecutor.cancelar(iid))
        if ruta == "/api/propuestas-agentes/analizar":
            v.solo_campos(self._cuerpo(), set())
            return self._json(200, s.propuestas.analizar())
        if m := R_PROP_ACC.match(ruta):
            pid = m.group(1)
            if m.group(2) == "crear":
                return self._json(201, s.propuestas.crear(pid, self._cuerpo()))
            return self._json(200, s.propuestas.descartar(pid, self._cuerpo()))
        if ruta == "/api/apagar":
            self._json(200, {"apagando": True})
            s.ejecutor.detener()
            if s.propuestas is not None:
                s.propuestas.detener()
            threading.Thread(target=s.servidor.shutdown, daemon=True).start()
            return None
        raise KeyError(ruta)


def _resumen(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "proyecto", "modo", "estado", "creada", "terminada", "costo_usd",
                                  "modelo_usado", "escalado")}


class ServidorExclusivo(ThreadingHTTPServer):
    """En Windows SO_REUSEADDR deja que otro proceso se enganche al mismo puerto; se usa SO_EXCLUSIVEADDRUSE."""
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def crear_servidor(servicio: Servicio) -> ThreadingHTTPServer:
    manejador = type("ManejadorOrquestador", (Manejador,), {"servicio": servicio})
    srv = ServidorExclusivo(("127.0.0.1", servicio.puerto), manejador)
    srv.daemon_threads = True
    servicio.servidor = srv
    return srv
