"""Normalización y enmascarado de texto, deterministas y sin dependencias (los usan el resolver y las propuestas).

- `sin_acentos`/`normalizar`: minúsculas, sin acentos, sin rutas, URLs, correos, IDs ni números concretos.
- `enmascarar`: deja el texto legible pero oculta rutas, URLs, correos, IDs, números largos y valores con forma de
  secreto (reutiliza `engram.tapar`). Se usa en todo texto que sale por la API o se guarda en una propuesta.
"""
from __future__ import annotations

import re
import unicodedata

from .engram import tapar

RE_URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.I)
RE_CORREO = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
RE_RUTA_WIN = re.compile(r"(?:\b[a-zA-Z]:|\\\\[\w.$-]+)[\\/][^\s\"'<>|]*")
RE_RUTA_UNIX = re.compile(r"(?<![\w.])(?:~|\.{1,2})?/(?:[\w.@+-]+/)+[\w.@+-]*")
RE_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
RE_HEX = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b", re.I)
RE_NUM_LARGO = re.compile(r"\b\d[\d,.]{4,}\b")
RE_ALFANUM_ID = re.compile(r"\b(?=\w*\d)(?=\w*[a-zA-Z])\w{4,}\b")  # GL0005, HU01, AB12CD...
RE_NUMERO = re.compile(r"\d+")
RE_NO_PALABRA = re.compile(r"[^a-z0-9ñ]+")

# Palabras vacías del español (y relleno típico de los mensajes del usuario) que no ayudan a agrupar.
VACIAS = frozenset("""
a al algo algun alguna algunas alguno algunos ante antes aqui asi aun bien cada como con contra cual cuales cuando
de del desde donde dos e el ella ellas ello ellos en entre era eres es esa esas ese eso esos esta estas este esto
estos estoy fue fueron ha hace hacer han has hay he la las le les lo los mas me mi mis mucho muy nada ni no nos
nosotros o otra otras otro otros para pero poco por porque que quien se sea ser si sin sobre solo son su sus tambien
te ti tu tus un una unas uno unos y ya yo the to of and is it in on for with this that
pls plis porfa porfavor favor gracias papi chiqui bro hermano mi bro ok okay oye va dale sale porfis
necesito quiero puedes podrias ayuda ayudame hazlo haz por favor vale bueno entonces ahora tambien igual
""".split())


def sin_acentos(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c) or c == "̃")
    return t.replace("ñ", "ñ").replace("Ñ", "Ñ").replace("̃", "")


def enmascarar(t: str, largo: int | None = None) -> str:
    t = RE_URL.sub("<url>", t or "")
    t = RE_CORREO.sub("<correo>", t)
    t = RE_RUTA_WIN.sub("<ruta>", t)
    t = RE_RUTA_UNIX.sub("<ruta>", t)
    t = RE_UUID.sub("<id>", t)
    t = RE_HEX.sub("<id>", t)
    t = RE_NUM_LARGO.sub("<n>", t)
    t = tapar(t)
    t = re.sub(r"\s+", " ", t).strip()
    if largo and len(t) > largo:
        t = t[: largo - 1].rstrip() + "…"
    return t


def normalizar(t: str) -> str:
    """Forma canónica para comparar: minúsculas, sin acentos, sin rutas/URLs/IDs/números, solo palabras."""
    t = RE_URL.sub(" ", t or "")
    t = RE_CORREO.sub(" ", t)
    t = RE_RUTA_WIN.sub(" ", t)
    t = RE_RUTA_UNIX.sub(" ", t)
    t = RE_UUID.sub(" ", t)
    t = RE_HEX.sub(" ", t)
    t = sin_acentos(t.lower())
    t = RE_ALFANUM_ID.sub(" ", t)
    t = RE_NUMERO.sub(" ", t)
    return " ".join(RE_NO_PALABRA.sub(" ", t).split())


def palabras(t_normalizado: str) -> list[str]:
    return [w for w in t_normalizado.split() if len(w) > 1 and w not in VACIAS]


def raiz(w: str) -> str:
    """Raíz burda y determinista para el español: quita plurales y corta a 6 letras (cambia/cambios/cambiar → cambi)."""
    if len(w) > 4 and w.endswith("es"):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s"):
        w = w[:-1]
    return w[:6]
