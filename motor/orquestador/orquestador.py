"""Orquestador local (fases 1 y 2): API en 127.0.0.1 para mandar instrucciones a la última sesión de Claude Code de
cada proyecto del registro, con inventario, contexto de engram y confirmación para cambios. Ver DISENO.md.

OPCIONAL: necesita su propio venv con claude-agent-sdk (`devskills orquestador instalar`). Su estado vive en
<datos>/orquestador (DEVSKILLS_DATOS o ~/.devskills).

Uso (normalmente vía `devskills orquestador`):
  python orquestador.py            inicia en segundo plano (o avisa si ya corre)
  python orquestador.py estado     corriendo/detenido, puerto y cola
  python orquestador.py apagar     apaga el servicio
  python orquestador.py servir     corre en primer plano (lo usa 'iniciar')
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from nucleo import ajustes as mod_ajustes  # noqa: E402
from nucleo.ajustes import rutas  # noqa: E402
from nucleo.api import CABECERA_TOKEN, Servicio, crear_servidor  # noqa: E402
from nucleo.ejecutor import Ejecutor  # noqa: E402
from nucleo.engram import Engram  # noqa: E402
from nucleo.grafo import Grafo  # noqa: E402
from nucleo.propuestas import Propuestas  # noqa: E402
from nucleo.inventario import Inventario  # noqa: E402
from nucleo.registro import Registro  # noqa: E402
from nucleo.sesiones import Activas, Catalogo, Propias  # noqa: E402

log = logging.getLogger("orquestador")


def leer_token(a) -> dict | None:
    try:
        d = json.loads(a.archivo_token.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and d.get("token") and d.get("puerto") else None
    except (OSError, ValueError):
        return None


def ping(puerto: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/ping", timeout=1.5) as r:
            return json.loads(r.read()).get("orquestador") is True
    except Exception:  # noqa: BLE001
        return False


def llamar(a, metodo: str, ruta: str, cuerpo: dict | None = None, timeout: float = 5):
    t = leer_token(a)
    if not t:
        raise ConnectionError("no hay archivo .token: el orquestador no está corriendo")
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{t['puerto']}{ruta}", data=datos, method=metodo,
                                 headers={CABECERA_TOKEN: t["token"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def puerto_libre(preferido: int, rango: tuple[int, int]) -> int:
    for p in [preferido] + [x for x in range(preferido + 1, rango[1] + 1)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit(f"No hay puertos libres entre {preferido} y {rango[1]}")


def configurar_log(a) -> None:
    h = logging.handlers.RotatingFileHandler(a.archivo_log, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


def construir(a, token: str, puerto: int) -> Servicio:
    registro = Registro(a.registro)
    engram = Engram(a.engram_db, a.engram_alias)
    propias = Propias(a.sesiones_propias)
    catalogo = Catalogo(a.claude_home, propias, Activas(), a.umbral_actividad_s, a.sesiones_protegidas)
    grafo = Grafo(a)
    ejecutor = Ejecutor(a, registro, catalogo, engram, grafo=grafo)
    inventario = Inventario(a, registro, catalogo, engram, grafo=grafo)
    ocupado = lambda: bool(ejecutor.estado()["ejecutando"]) or ejecutor.estado()["en_cola"] > 0  # noqa: E731
    propuestas = Propuestas(a, registro, propias, ocupado=ocupado)
    return Servicio(a, registro, inventario, engram, ejecutor, token, puerto, grafo=grafo, propuestas=propuestas)


def servir(a) -> int:
    configurar_log(a)
    puerto = puerto_libre(a.puerto, a.rango)
    if puerto != a.puerto:
        log.warning("Puerto %s ocupado; se usa %s", a.puerto, puerto)
    token = secrets.token_urlsafe(32)
    servicio = construir(a, token, puerto)
    srv = crear_servidor(servicio)
    servicio.ejecutor.iniciar()
    servicio.propuestas.iniciar()
    a.archivo_token.write_text(json.dumps({"token": token, "puerto": puerto, "pid": os.getpid()}), encoding="utf-8")
    rutas.restringir(a.archivo_token)
    log.info("Orquestador escuchando en http://127.0.0.1:%s (pid %s)", puerto, os.getpid())
    try:
        srv.serve_forever(poll_interval=0.5)
    finally:
        servicio.ejecutor.detener()
        servicio.propuestas.detener()
        srv.server_close()
        try:
            t = leer_token(a)
            if t and t.get("pid") == os.getpid():
                a.archivo_token.unlink()
        except OSError:
            pass
        log.info("Orquestador detenido.")
    return 0


def corriendo(a) -> dict | None:
    t = leer_token(a)
    return t if t and ping(int(t["puerto"])) else None


def iniciar(a) -> int:
    t = corriendo(a)
    if t:
        print(f"El orquestador ya estaba corriendo en http://127.0.0.1:{t['puerto']}")
        return 0
    try:
        a.archivo_token.unlink()  # token viejo de una ejecución que no cerró bien
    except OSError:
        pass
    exe = Path(sys.executable)
    sin_consola = exe.with_name("pythonw.exe")
    exe = sin_consola if sin_consola.exists() else exe
    subprocess.Popen([str(exe), str(AQUI / "orquestador.py"), "servir"], cwd=str(AQUI), close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     **rutas.opciones_desacoplado())
    for _ in range(60):
        time.sleep(0.25)
        t = corriendo(a)
        if t:
            extra = "" if int(t["puerto"]) == a.puerto else f" (el {a.puerto} estaba ocupado)"
            print(f"Orquestador iniciado en http://127.0.0.1:{t['puerto']}{extra}")
            return 0
    print(f"El orquestador no respondió. Revisa {a.archivo_log}")
    return 1


def apagar(a) -> int:
    if not leer_token(a):
        print("El orquestador no está corriendo.")
        return 0
    try:
        llamar(a, "POST", "/api/apagar", {})
        print("Orquestador apagado.")
    except Exception as e:  # noqa: BLE001
        print(f"No respondió ({type(e).__name__}); quizá ya estaba detenido.")
        try:
            a.archivo_token.unlink()
        except OSError:
            pass
    return 0


def estado(a) -> int:
    t = corriendo(a)
    if not t:
        print("detenido")
        return 0
    try:
        e = llamar(a, "GET", "/api/estado")
        cola = e["cola"]
        print(f"corriendo en http://127.0.0.1:{e['puerto']} · {e['proyectos']} proyectos · engram "
              f"{'disponible' if e['engram'] else 'no disponible'} · en cola {cola['en_cola']} · ejecutando "
              f"{', '.join(cola['ejecutando']) or 'nada'}")
    except Exception as ex:  # noqa: BLE001
        print(f"corriendo en :{t['puerto']}, pero /api/estado falló ({type(ex).__name__})")
    return 0


def main(argv: list[str]) -> int:
    a = mod_ajustes.cargar()
    a.raiz.mkdir(parents=True, exist_ok=True)
    comando = argv[0] if argv else "iniciar"
    acciones = {"iniciar": iniciar, "servir": servir, "apagar": apagar, "detener": apagar, "estado": estado}
    if comando not in acciones:
        print(__doc__)
        return 2
    return acciones[comando](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
