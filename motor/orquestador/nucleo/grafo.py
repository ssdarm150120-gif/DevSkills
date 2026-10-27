"""Grafo de conocimiento del proyecto (Graphify) en SOLO LECTURA y sin LLM.

- El grafo vive en `<carpeta>/graphify-out/graph.json` (con `GRAPH_REPORT.md` al lado). Puede no existir: todo
  degrada a "sin grafo".
- Consultas con `graphify query "<pregunta>" --graph <ruta> --budget N`, siempre con `GRAPHIFY_BACKEND=none` para que
  graphify nunca llame a un modelo. Sin shell (lista de argumentos), con tiempo límite y la salida recortada y
  enmascarada.
- Estado: fecha del grafo, commit con el que se construyó (lo dice GRAPH_REPORT.md) y si está desactualizado
  respecto a git (archivos cambiados desde ese commit, sin contar graphify-out). Se guarda en caché unos segundos
  porque el inventario lo pide para todos los proyectos.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from . import texto as tx

RE_COMMIT = re.compile(r"Built from commit:\s*`?([0-9a-f]{7,40})`?", re.I)
RE_RESUMEN = re.compile(r"(\d+)\s+nodes\s+·\s+(\d+)\s+edges\s+·\s+(\d+)\s+communities", re.I)
RE_SHA = re.compile(r"^[0-9a-f]{7,40}$")
# lo que no cambia el grafo de código: la propia salida y los archivos de configuración de git/graphify
EXCLUIR = [":(exclude)graphify-out", ":(exclude).gitignore", ":(exclude).gitattributes", ":(exclude).graphifyignore"]
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

Ejecutar = Callable[[list[str], Path, int, dict | None], tuple[int, str]]


def _ejecutar_real(cmd: list[str], cwd: Path, timeout: int, env_extra: dict | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "NO_COLOR": "1"})
    env.update(env_extra or {})
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode, r.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, type(e).__name__


def enmascarar_lineas(t: str) -> str:
    return "\n".join(tx.enmascarar(l) for l in (t or "").splitlines() if l.strip())


def recortar(t: str, maximo: int) -> tuple[str, bool]:
    if len(t) <= maximo:
        return t, False
    corte = t.rfind("\n", 0, maximo)
    corte = corte if corte > maximo * 0.6 else maximo
    return t[:corte].rstrip() + "\n[… recortado por el presupuesto de caracteres]", True


class Grafo:
    def __init__(self, ajustes, ejecutar: Ejecutar | None = None):
        self.a = ajustes
        self.cfg = ajustes.grafo
        self._ejecutar = ejecutar or _ejecutar_real
        self._cache: dict[str, tuple[float, int, dict]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ rutas
    def ejecutable(self) -> str | None:
        if self.cfg.get("ejecutable"):
            return str(self.cfg["ejecutable"])
        exe = shutil.which("graphify")
        if exe:
            return exe
        for nombre in ("graphify.exe", "graphify"):
            p = Path.home() / ".local" / "bin" / nombre
            if p.exists():
                return str(p)
        return None

    @staticmethod
    def ruta(carpeta: Path) -> Path | None:
        """graph.json dentro de la carpeta del proyecto (un enlace que saque el archivo de la carpeta no cuenta)."""
        g = carpeta / "graphify-out" / "graph.json"
        try:
            if g.is_file() and g.resolve().is_relative_to(carpeta.resolve()):
                return g
        except OSError:
            pass
        return None

    # ------------------------------------------------------------ estado
    def estado(self, carpeta: Path, ruta_grafo: Path | None = None) -> dict:
        g = ruta_grafo or self.ruta(carpeta)
        if g is None:
            return {"tiene_grafo": False}
        try:
            mtime = g.stat().st_mtime_ns
        except OSError:
            return {"tiene_grafo": False}
        clave = str(g)
        with self._lock:
            c = self._cache.get(clave)
            if c and c[1] == mtime and time.monotonic() - c[0] < float(self.cfg.get("cache_estado_s", 60)):
                return dict(c[2])
        info = self._calcular_estado(carpeta, g, mtime)
        with self._lock:
            self._cache[clave] = (time.monotonic(), mtime, info)
        return dict(info)

    def _reporte(self, g: Path) -> str:
        try:
            return (g.parent / "GRAPH_REPORT.md").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def _calcular_estado(self, carpeta: Path, g: Path, mtime: int) -> dict:
        rep = self._reporte(g)
        info: dict = {"tiene_grafo": True, "fecha": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime / 1e9)),
                      "tamano_kb": round(g.stat().st_size / 1024), "reporte": bool(rep)}
        if m := RE_RESUMEN.search(rep):
            info.update(nodos=int(m.group(1)), aristas=int(m.group(2)), comunidades=int(m.group(3)))
        m = RE_COMMIT.search(rep)
        commit = m.group(1).lower() if m else None
        info["commit_grafo"] = commit
        to = int(self.cfg.get("tiempo_limite_s", 30))
        cod, head = self._ejecutar(["git", "-C", str(carpeta), "rev-parse", "HEAD"], carpeta, to, None)
        head = head.strip().lower()
        if cod != 0 or not RE_SHA.match(head):
            info.update(commit_git=None, desactualizado=None, motivo="la carpeta no es un repositorio git (no se puede comparar)")
            return info
        info["commit_git"] = head[:12]
        cod, sucio = self._ejecutar(["git", "-C", str(carpeta), "status", "--porcelain", "--", ".",
                                     *EXCLUIR], carpeta, to, None)
        info["cambios_sin_commit"] = len([l for l in sucio.splitlines() if l.strip()]) if cod == 0 else None
        if not commit:
            info.update(desactualizado=None, motivo="GRAPH_REPORT.md no indica el commit del grafo")
            return info
        if head.startswith(commit):
            info.update(desactualizado=False, motivo="construido sobre el commit actual")
            return info
        cod, dif = self._ejecutar(["git", "-C", str(carpeta), "diff", "--name-only", commit, "HEAD", "--", ".",
                                   *EXCLUIR], carpeta, to, None)
        if cod != 0:
            info.update(desactualizado=True, motivo="el commit del grafo no existe en este repositorio")
            return info
        n = len([l for l in dif.splitlines() if l.strip()])
        info["archivos_cambiados"] = n
        info.update(desactualizado=n > 0, motivo=(f"{n} archivo(s) cambiaron desde el commit del grafo" if n
                                                  else "desde el commit del grafo solo cambió graphify-out o configuración de git"))
        return info

    # ------------------------------------------------------------ consultas
    def consultar(self, carpeta: Path, pregunta: str, max_chars: int, ruta_grafo: Path | None = None) -> dict:
        g = ruta_grafo or self.ruta(carpeta)
        if g is None:
            return {"codigo": None, "texto": "", "truncado": False, "error": "sin grafo"}
        exe = self.ejecutable()
        if not exe:
            return {"codigo": None, "texto": "", "truncado": False, "error": "graphify no está instalado"}
        q = _CONTROL.sub(" ", tx.sin_acentos(pregunta or "")).strip().lstrip("-").strip()[:300]
        if not q:
            return {"codigo": None, "texto": "", "truncado": False, "error": "pregunta vacía"}
        presupuesto = max(200, int(max_chars) // 4)  # ~4 caracteres por token
        cod, salida = self._ejecutar([exe, "query", q, "--graph", str(g), "--budget", str(presupuesto)], carpeta,
                                     int(self.cfg.get("tiempo_limite_s", 30)), {"GRAPHIFY_BACKEND": "none"})
        if cod not in (0, 3, 4):
            return {"codigo": cod, "texto": "", "truncado": False, "error": "graphify query falló"}
        texto, truncado = recortar(enmascarar_lineas(salida), int(max_chars))
        return {"codigo": cod, "texto": texto if cod != 4 else "", "truncado": truncado,
                "sin_coincidencias": cod == 4, "ambiguo": cod == 3}

    def resumen(self, carpeta: Path, max_chars: int, ruta_grafo: Path | None = None) -> str:
        """Resumen de GRAPH_REPORT.md: tamaño, nodos centrales (god nodes) y comunidades principales."""
        g = ruta_grafo or self.ruta(carpeta)
        if g is None:
            return ""
        secciones: dict[str, list[str]] = {}
        actual = None
        for linea in self._reporte(g).splitlines():
            if linea.startswith("## "):
                actual = linea[3:].strip().lower()
                secciones[actual] = []
            elif actual is not None and linea.strip():
                secciones[actual].append(linea.strip())

        def seccion(prefijo: str) -> list[str]:
            return next((v for k, v in secciones.items() if k.startswith(prefijo)), [])

        partes = []
        if s := seccion("summary"):
            partes.append("Tamaño: " + " ".join(x.lstrip("- ") for x in s[:1]))
        if s := seccion("god nodes"):
            partes.append("Nodos centrales: " + "; ".join(re.sub(r"^\d+\.\s*", "", x) for x in s[:10]))
        if s := seccion("community hubs"):
            partes.append("Comunidades principales: " + ", ".join(x.lstrip("- ") for x in s[:20]))
        texto, _ = recortar(enmascarar_lineas("\n".join(partes)), int(max_chars))
        return texto
