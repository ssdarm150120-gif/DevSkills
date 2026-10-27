"""Consulta de engram en SOLO LECTURA.

Se abre la base SQLite de engram con `mode=ro` (URI), así este proceso no puede escribir aunque quisiera. Se usa la
tabla FTS5 `observations_fts` (la misma que usa `engram search`) con los términos citados para que la consulta del
usuario nunca se interprete como sintaxis FTS. Solo se devuelven observaciones con scope 'project' no borradas y de
los proyectos de engram asociados al proyecto del registro (config.json → engram.alias; por omisión, el mismo id).

Alternativas evaluadas: `engram search` (CLI, salida de texto sin formato estable y avisa de actualizaciones por red),
`engram serve` (HTTP en 7437: otro proceso residente) y `engram mcp` (stdio; pensado para agentes). La lectura directa
en `mode=ro` es la más simple y la única que garantiza no escribir; el costo es depender del esquema (si cambia, la
API responde 'engram no disponible' en lugar de fallar).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

RE_TERMINO = re.compile(r"[\wáéíóúüñÁÉÍÓÚÜÑ][\w.\-áéíóúüñÁÉÍÓÚÜÑ]*", re.UNICODE)


def terminos_fts(q: str, maximo: int = 8) -> str:
    """'deploy; DROP' -> '"deploy" "DROP"' (cada término citado = sin operadores FTS)."""
    ts = RE_TERMINO.findall(q or "")[:maximo]
    return " ".join('"' + t.replace('"', "") + '"' for t in ts)


class Engram:
    def __init__(self, db: Path, alias: dict[str, list[str]]):
        self.db = db
        self._alias = alias

    def alias(self, pid: str) -> list[str]:
        return list(self._alias.get(pid, [pid]))

    def _conectar(self) -> sqlite3.Connection:
        uri = "file:" + self.db.resolve().as_posix() + "?mode=ro"
        c = sqlite3.connect(uri, uri=True, timeout=2)
        c.row_factory = sqlite3.Row
        return c

    def disponible(self) -> bool:
        if not self.db.exists():
            return False
        try:
            with self._conectar() as c:
                c.execute("select id, title, content, project, scope, deleted_at from observations limit 1")
            return True
        except sqlite3.Error:
            return False

    def contar(self, proyectos: list[str]) -> int | None:
        if not proyectos or not self.db.exists():
            return 0 if not proyectos else None
        marcas = ",".join("?" * len(proyectos))
        try:
            with self._conectar() as c:
                r = c.execute(f"select count(*) from observations where project in ({marcas}) "
                              f"and scope='project' and deleted_at is null", proyectos).fetchone()
                return int(r[0])
        except sqlite3.Error:
            return None

    def buscar(self, proyectos: list[str], q: str = "", limite: int = 10, largo: int = 600) -> list[dict]:
        if not proyectos:
            return []
        marcas = ",".join("?" * len(proyectos))
        filtro = f"o.project in ({marcas}) and o.scope='project' and o.deleted_at is null"
        fts = terminos_fts(q)
        with self._conectar() as c:
            if fts:
                filas = c.execute(
                    f"select o.id, o.type, o.title, o.content, o.project, o.topic_key, o.updated_at "
                    f"from observations_fts f join observations o on o.id = f.rowid "
                    f"where observations_fts match ? and {filtro} order by rank limit ?",
                    [fts, *proyectos, limite]).fetchall()
            else:
                filas = c.execute(
                    f"select o.id, o.type, o.title, o.content, o.project, o.topic_key, o.updated_at "
                    f"from observations o where {filtro} order by o.updated_at desc limit ?",
                    [*proyectos, limite]).fetchall()
        return [{"id": f["id"], "tipo": f["type"], "titulo": tapar(f["title"]), "proyecto": f["project"],
                 "topic_key": f["topic_key"], "actualizada": f["updated_at"],
                 "extracto": tapar((f["content"] or "")[:largo])} for f in filas]


_SECRETOS = [
    re.compile(r"(?i)\b(password|passwd|pwd|secret|client_secret|token|api[_-]?key|access_key|contraseña)"
               r"(\s*[:=]\s*)(\"?)[^\s\"',;]{6,}"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|"
               r"\d{8,10}:[A-Za-z0-9_-]{30,})"),
]


def tapar(texto: str) -> str:
    """Defensa en profundidad: oculta valores con forma de secreto que alguien haya guardado en la memoria."""
    t = _SECRETOS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}••••", texto or "")
    return _SECRETOS[1].sub("••••", t)
