"""Lectura (nunca escritura) del registro central de proyectos (_servicios/proyectos.json).

El registro lo editan servicios.ps1, el panel y otros agentes; aquí solo se toman id, nombre, carpeta y las carpetas
de transcripts, y se ignora todo lo demás para tolerar campos nuevos.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import validacion


@dataclass(frozen=True)
class Proyecto:
    id: str
    nombre: str
    carpeta: Path
    transcripts: tuple[str, ...]
    enrutamiento_activo: bool = False  # proyectos.json → enrutamiento.activo (lo escribe el panel; aquí solo se lee)


def cargar(ruta: Path) -> dict[str, Proyecto]:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    proyectos: dict[str, Proyecto] = {}
    for p in datos.get("proyectos", []):
        pid = p.get("id")
        carpeta = p.get("carpeta")
        if not isinstance(pid, str) or not validacion.RE_PROYECTO.match(pid) or not isinstance(carpeta, str):
            continue  # entrada mal formada: no entra a la lista blanca
        ruta_carpeta = Path(carpeta)
        if not ruta_carpeta.is_absolute():
            continue
        extra = tuple(t for t in (p.get("transcripts") or []) if isinstance(t, str) and Path(t).is_absolute())
        enr = p.get("enrutamiento")
        activo = isinstance(enr, dict) and enr.get("activo") is True
        proyectos[pid] = Proyecto(pid, str(p.get("nombre") or pid)[:120], ruta_carpeta, extra, activo)
    return proyectos


class Registro:
    """Recarga el archivo cuando cambia su fecha de modificación (otro agente lo edita en paralelo)."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self._mtime = None
        self._proyectos: dict[str, Proyecto] = {}

    def proyectos(self) -> dict[str, Proyecto]:
        try:
            m = self.ruta.stat().st_mtime_ns
        except OSError:
            return self._proyectos
        if m != self._mtime:
            try:
                self._proyectos = cargar(self.ruta)
                self._mtime = m
            except (OSError, ValueError):
                pass  # escritura a medias del otro proceso: se conserva la última versión válida
        return self._proyectos
