"""Resolución del proyecto a partir de texto libre (voz o un asistente), determinista y sin LLM.

Para cada proyecto del registro se arman sus nombres: id (con guiones como espacios), nombre del registro y los alias
de config.json (`alias_proyectos`). Puntaje por nombre:
- aparece completo en el texto (como frase, sin acentos): 0.85 + 0.15 × (palabras del alias / 3, máx. 1);
- todas sus palabras aparecen pero separadas ("kpis de acme"): 0.82 + 0.15 × (palabras / 3, máx. 1);
- si no, similitud difusa (difflib) entre el alias y la ventana del texto del mismo número de palabras, × 0.8.
Si el alias encontrado de un proyecto está contenido en el alias encontrado de otro ("kpis" dentro de "kpis
acme"), el más corto se descarta. Resultado: el mejor si supera `minimo` y le saca `margen` al segundo; si no,
`ambiguo: true` con los candidatos.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from . import texto as tx

MINIMO = 0.6
MARGEN = 0.1


def _forma(t: str) -> list[str]:
    return tx.sin_acentos((t or "").lower()).replace("/", " ").replace("-", " ").replace("_", " ").replace("·", " ") \
        .translate(str.maketrans({c: " " for c in ".,;:!?¿¡()[]{}\"'"})).split()


def _puntaje(alias: list[str], palabras: list[str]) -> tuple[float, tuple[int, int] | None]:
    n = len(alias)
    if not n or not palabras:
        return 0.0, None
    for i in range(len(palabras) - n + 1):
        if palabras[i:i + n] == alias:
            return 0.85 + 0.15 * min(1.0, n / 3), (i, i + n)
    if n >= 2 and all(w in palabras for w in alias):  # todas las palabras, no contiguas ("kpis de acme")
        pos = [palabras.index(w) for w in alias]
        return 0.82 + 0.15 * min(1.0, n / 3), (min(pos), max(pos) + 1)
    mejor, span = 0.0, None
    a = " ".join(alias)
    for i in range(max(1, len(palabras) - n + 1)):
        ventana = " ".join(palabras[i:i + n])
        r = SequenceMatcher(None, a, ventana).ratio()
        if r > mejor:
            mejor, span = r, (i, i + n)
    return (mejor * 0.8 if mejor >= 0.75 else 0.0), span


def resolver(texto: str, proyectos: dict, alias: dict[str, list[str]], minimo: float = MINIMO,
             margen: float = MARGEN) -> dict:
    palabras = _forma(texto)
    candidatos = []
    for pid, p in proyectos.items():
        nombres = {pid.replace("-", " "), p.nombre, *alias.get(pid, [])}
        mejor = (0.0, None, "")
        for nombre in nombres:
            forma = _forma(nombre)
            s, span = _puntaje(forma, palabras)
            if s > mejor[0] or (s == mejor[0] and span and mejor[1] and (span[1] - span[0]) > (mejor[1][1] - mejor[1][0])):
                mejor = (s, span, " ".join(forma))
        if mejor[0] > 0:
            candidatos.append({"proyecto": pid, "nombre": p.nombre, "puntaje": round(mejor[0], 3),
                               "coincidencia": mejor[2], "_span": mejor[1], "_exacta": mejor[0] >= 0.85})
    # un alias exacto contenido dentro del alias exacto (más largo) de otro proyecto no cuenta
    for c in candidatos:
        for o in candidatos:
            if o is c or not (c["_exacta"] and o["_exacta"]):
                continue
            (a0, a1), (b0, b1) = c["_span"], o["_span"]
            if b0 <= a0 and a1 <= b1 and (b1 - b0) > (a1 - a0):
                c["puntaje"] = round(c["puntaje"] * 0.5, 3)
                c["coincidencia"] += f" (contenida en «{o['coincidencia']}»)"
                break
    candidatos.sort(key=lambda c: (-c["puntaje"], c["proyecto"]))
    for c in candidatos:
        c.pop("_span"), c.pop("_exacta")
    top = candidatos[:5]
    if not top or top[0]["puntaje"] < minimo:
        return {"proyecto": None, "puntaje": top[0]["puntaje"] if top else 0.0, "ambiguo": bool(top),
                "motivo": "ningún proyecto alcanza el puntaje mínimo", "candidatos": top}
    if len(top) > 1 and top[0]["puntaje"] - top[1]["puntaje"] < margen:
        return {"proyecto": None, "puntaje": top[0]["puntaje"], "ambiguo": True,
                "motivo": "dos o más proyectos tienen puntajes parecidos", "candidatos": top}
    return {"proyecto": top[0]["proyecto"], "puntaje": top[0]["puntaje"], "ambiguo": False,
            "coincidencia": top[0]["coincidencia"], "candidatos": top}
