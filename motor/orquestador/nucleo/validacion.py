"""Validación estricta de las entradas de la API.

Reglas: el proyecto debe estar en la lista blanca del registro; el texto tiene longitud máxima y sin caracteres de
control; los campos desconocidos se rechazan; ningún parámetro acepta rutas de archivo (las carpetas salen siempre
del registro, nunca de la petición).
"""
from __future__ import annotations

import re

MODOS = ("lectura", "cambios")
CONTEXTOS = ("auto", "sesion", "grafo")
MODELOS = ("haiku", "sonnet", "opus")
RE_PROYECTO = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
RE_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ErrorValidacion(ValueError):
    """Entrada inválida; el mensaje se devuelve tal cual al cliente (no contiene datos internos)."""


def proyecto(valor, permitidos) -> str:
    if not isinstance(valor, str) or not RE_PROYECTO.match(valor):
        raise ErrorValidacion("proyecto inválido")
    if valor not in permitidos:
        raise ErrorValidacion("proyecto no registrado")
    return valor


def texto(valor, maximo: int) -> str:
    if not isinstance(valor, str):
        raise ErrorValidacion("texto debe ser una cadena")
    t = valor.replace("\r\n", "\n").strip()
    if not t:
        raise ErrorValidacion("texto vacío")
    if len(t) > maximo:
        raise ErrorValidacion(f"texto demasiado largo (máximo {maximo} caracteres)")
    if _CONTROL.search(t):
        raise ErrorValidacion("texto con caracteres de control")
    return t


def modo(valor) -> str:
    if valor not in MODOS:
        raise ErrorValidacion("modo debe ser 'lectura' o 'cambios'")
    return valor


def id_instruccion(valor) -> str:
    if not isinstance(valor, str) or not RE_ID.match(valor):
        raise ErrorValidacion("id inválido")
    return valor


def consulta(valor, maximo: int) -> str:
    if valor is None:
        return ""
    if not isinstance(valor, str) or len(valor) > maximo or _CONTROL.search(valor):
        raise ErrorValidacion(f"consulta inválida (máximo {maximo} caracteres)")
    return valor.strip()


def solo_campos(cuerpo, obligatorios: set[str], opcionales: set[str] = frozenset()) -> dict:
    if not isinstance(cuerpo, dict):
        raise ErrorValidacion("el cuerpo debe ser un objeto JSON")
    sobran = set(cuerpo) - obligatorios - set(opcionales)
    if sobran:
        raise ErrorValidacion("campos no permitidos: " + ", ".join(sorted(sobran)))
    faltan = obligatorios - set(cuerpo)
    if faltan:
        raise ErrorValidacion("faltan campos: " + ", ".join(sorted(faltan)))
    return cuerpo


def instruccion(cuerpo, permitidos, maximo_texto: int) -> dict:
    c = solo_campos(cuerpo, {"proyecto", "texto", "modo"}, {"nueva_sesion", "contexto", "modelo"})
    nueva = c.get("nueva_sesion", False)
    if not isinstance(nueva, bool):
        raise ErrorValidacion("nueva_sesion debe ser booleano")
    ctx = c.get("contexto", "auto")
    if ctx not in CONTEXTOS:
        raise ErrorValidacion("contexto debe ser 'auto', 'sesion' o 'grafo'")
    if nueva and ctx == "sesion":
        raise ErrorValidacion("nueva_sesion: true contradice contexto 'sesion' (que reanuda la última sesión)")
    modelo = c.get("modelo")
    if modelo is not None and modelo not in MODELOS:
        raise ErrorValidacion("modelo debe ser 'haiku', 'sonnet' u 'opus'")
    salida = {"proyecto": proyecto(c["proyecto"], permitidos), "texto": texto(c["texto"], maximo_texto),
              "modo": modo(c["modo"]), "nueva_sesion": nueva, "contexto": ctx}
    if modelo is not None:
        salida["modelo"] = modelo
    return salida


def confirmacion(cuerpo, id_esperado: str) -> None:
    """Confirmar exige repetir el id en el campo `confirmacion`: un POST vacío o reenviado por error no basta."""
    c = solo_campos(cuerpo, {"confirmacion"})
    if c["confirmacion"] != id_esperado:
        raise ErrorValidacion("confirmacion debe ser exactamente el id de la instrucción")
