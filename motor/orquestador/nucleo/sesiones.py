"""Sesiones de Claude Code por proyecto y detección de "sesión abierta en una terminal".

- Listado: `claude_agent_sdk.list_sessions(directory=...)` (API oficial; lee los transcripts sin modificarlos).
- Sesión principal: la que abrió el usuario (entrypoint `cli`, escritorio o IDE). Se excluyen las sesiones creadas
  por un SDK (entrypoint `sdk-*`) y las que creó este orquestador (sesiones_propias.json).
- Abierta: aparece en `claude agents --json` (sesiones interactivas y en segundo plano activas) o su transcript se
  modificó hace menos de `umbral_actividad_s` segundos. Si `claude agents` falla, solo queda la heurística y la
  respuesta lo indica.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

RE_SID_CHARS = set("0123456789abcdef-")


@dataclass
class Sesion:
    session_id: str
    titulo: str
    modificada_ms: int
    tamano: int
    cwd: str
    entrypoint: str | None = None

    def resumen(self) -> dict:
        return {"session_id": self.session_id, "titulo": self.titulo[:100],
                "modificada": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.modificada_ms / 1000)),
                "tamano_mb": round(self.tamano / 1_048_576, 2), "entrypoint": self.entrypoint}


def _listar_sdk(directorio: str) -> list:
    from claude_agent_sdk import list_sessions  # import diferido: las pruebas no necesitan el SDK
    return list_sessions(directory=directorio, include_worktrees=True)


def carpetas_de(proyecto) -> list[str]:
    """Carpeta del proyecto más las del campo `transcripts` del registro (los comodines se expanden en disco)."""
    salida = [str(proyecto.carpeta)]
    for patron in proyecto.transcripts:
        if any(c in patron for c in "*?["):
            base = Path(patron).parent
            if base.is_dir():
                nombre = Path(patron).name.lower()
                salida += [str(d) for d in base.iterdir() if d.is_dir() and fnmatch.fnmatch(d.name.lower(), nombre)]
        else:
            salida.append(patron)
    vistos, unicos = set(), []
    for c in salida:
        k = os.path.normcase(os.path.normpath(c))
        if k not in vistos:
            vistos.add(k)
            unicos.append(c)
    return unicos


def entrypoint_de(claude_home: Path, session_id: str, max_lineas: int = 60, max_bytes: int = 1_000_000) -> str | None:
    """Lee solo el principio del transcript para saber quién lo creó (cli, sdk-py, ...)."""
    if not session_id or set(session_id) - RE_SID_CHARS:
        return None
    for archivo in (claude_home / "projects").glob(f"*/{session_id}.jsonl"):
        try:
            with open(archivo, "rb") as h:
                leidos = 0
                for _ in range(max_lineas):
                    linea = h.readline(max_bytes)
                    if not linea:
                        break
                    leidos += len(linea)
                    if b'"entrypoint"' in linea:
                        try:
                            return json.loads(linea).get("entrypoint")
                        except ValueError:
                            return None
                    if leidos > max_bytes:
                        break
        except OSError:
            continue
    return None


def transcript_de(claude_home: Path, session_id: str) -> Path | None:
    if not session_id or set(session_id.lower()) - RE_SID_CHARS:
        return None
    return next(iter((claude_home / "projects").glob(f"*/{session_id}.jsonl")), None)


def tokens_contexto(claude_home: Path, session_id: str, cola_bytes: int = 512 * 1024) -> int | None:
    """Tamaño del contexto de la sesión en tokens según el `usage` del ÚLTIMO mensaje del asistente (entrada + caché
    leída + caché creada): es lo que se volvería a mandar al reanudarla. Solo lee el final del transcript."""
    ruta = transcript_de(claude_home, session_id)
    if ruta is None:
        return None
    try:
        with open(ruta, "rb") as h:
            h.seek(0, os.SEEK_END)
            tam = h.tell()
            h.seek(max(0, tam - cola_bytes))
            lineas = h.read().splitlines()
    except OSError:
        return None
    for linea in reversed(lineas):
        if b'"usage"' not in linea or b'"assistant"' not in linea:
            continue
        try:
            u = (json.loads(linea).get("message") or {}).get("usage") or {}
        except ValueError:
            continue
        total = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                   "cache_creation_input_tokens"))
        if total:
            return total
    return None


class Propias:
    """IDs de sesiones creadas por el orquestador (nunca cuentan como 'última sesión principal')."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self._lock = threading.Lock()

    def todas(self) -> set[str]:
        try:
            return set(json.loads(self.ruta.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return set()

    def agregar(self, session_id: str) -> None:
        with self._lock:
            ids = self.todas()
            ids.add(session_id)
            tmp = self.ruta.with_suffix(".tmp")
            tmp.write_text(json.dumps(sorted(ids)), encoding="utf-8")
            os.replace(tmp, self.ruta)


class Activas:
    """Sesiones activas según `claude agents --json`, con caché corta para no lanzar el CLI en cada petición."""

    def __init__(self, ejecutar: Callable[[], list[dict] | None] | None = None, ttl: float = 10.0):
        self._ejecutar = ejecutar or self._claude_agents
        self._ttl = ttl
        self._cache: tuple[float, list[dict] | None] = (0.0, None)
        self._lock = threading.Lock()

    @staticmethod
    def _claude_agents() -> list[dict] | None:
        exe = shutil.which("claude")
        if not exe:
            return None
        try:
            r = subprocess.run([exe, "agents", "--json"], capture_output=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                return None
            datos = json.loads(r.stdout.decode("utf-8", "replace"))
            return datos if isinstance(datos, list) else None
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None

    def listar(self) -> list[dict] | None:
        with self._lock:
            t, datos = self._cache
            if time.monotonic() - t < self._ttl:
                return datos
            datos = self._ejecutar()
            self._cache = (time.monotonic(), datos)
            return datos

    def por_sesion(self) -> dict[str, dict] | None:
        datos = self.listar()
        if datos is None:
            return None
        return {str(d.get("sessionId", "")).lower(): d for d in datos if d.get("sessionId")}


def estado_apertura(sesion: Sesion, activas: dict[str, dict] | None, umbral_s: int,
                    ahora: float | None = None) -> dict:
    ahora = time.time() if ahora is None else ahora
    motivos = []
    if activas is not None and sesion.session_id.lower() in activas:
        a = activas[sesion.session_id.lower()]
        motivos.append(f"claude agents la reporta activa ({a.get('kind', '?')}, "
                       f"{a.get('status') or a.get('state') or 'sin estado'})")
    hace = ahora - sesion.modificada_ms / 1000
    if hace < umbral_s:
        motivos.append(f"transcript modificado hace {int(hace)} s (umbral {umbral_s} s)")
    return {"abierta": bool(motivos), "motivos": motivos,
            "deteccion": "claude agents + actividad" if activas is not None else "solo actividad (claude agents no disponible)"}


class Catalogo:
    def __init__(self, claude_home: Path, propias: Propias, activas: Activas, umbral_s: int,
                 protegidas: Iterable[str] = (), listar: Callable[[str], list] | None = None):
        self.claude_home = claude_home
        self.propias = propias
        self.activas = activas
        self.umbral_s = umbral_s
        self.protegidas = {p.lower() for p in protegidas}
        self._listar = listar or _listar_sdk

    def sesiones(self, proyecto) -> list[Sesion]:
        vistas: dict[str, Sesion] = {}
        for carpeta in carpetas_de(proyecto):
            try:
                infos = self._listar(carpeta)
            except Exception:  # noqa: BLE001 - un directorio ilegible no debe tumbar el inventario
                continue
            for i in infos:
                sid = str(getattr(i, "session_id", "") or "")
                if not sid or sid in vistas:
                    continue
                titulo = getattr(i, "custom_title", None) or getattr(i, "summary", None) or ""
                vistas[sid] = Sesion(sid, str(titulo), int(getattr(i, "last_modified", 0) or 0),
                                     int(getattr(i, "file_size", 0) or 0), str(getattr(i, "cwd", "") or ""))
        lista = sorted(vistas.values(), key=lambda s: s.modificada_ms, reverse=True)
        for s in lista[:10]:  # solo las recientes: leer el principio de cada transcript cuesta E/S
            s.entrypoint = entrypoint_de(self.claude_home, s.session_id)
        return lista

    def es_principal(self, s: Sesion, propias: set[str]) -> bool:
        if s.session_id in propias:
            return False
        return not (s.entrypoint or "").startswith("sdk")

    def ultima_principal(self, proyecto, sesiones: list[Sesion] | None = None) -> Sesion | None:
        sesiones = self.sesiones(proyecto) if sesiones is None else sesiones
        propias = self.propias.todas()
        for s in sesiones[:10]:
            if self.es_principal(s, propias):
                return s
        return None

    def apertura(self, s: Sesion) -> dict:
        """Devuelve abierta/protegida/reanudable con sus motivos. Solo se reanuda si `reanudable` es True."""
        info = estado_apertura(s, self.activas.por_sesion(), self.umbral_s)
        info["protegida"] = s.session_id.lower() in self.protegidas
        if info["protegida"]:
            info["motivos"].append("sesión protegida en config.json (nunca se reanuda)")
        info["reanudable"] = not info["abierta"] and not info["protegida"]
        return info
