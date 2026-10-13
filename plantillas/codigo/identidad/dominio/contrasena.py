"""Politica de contrasenas ("Contrasena robusta"). Python puro, sin IO.

La lista de contrasenas filtradas la entrega el adaptador (es un archivo incluido en el sistema,
sin consultas a servicios externos): aqui solo se pregunta si el valor esta en ella.
"""

from collections.abc import Container

LONGITUD_MINIMA = 12

MENSAJE_CORTA = f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres"
MENSAJE_FILTRADA = "Esa contraseña aparece en listas de contraseñas filtradas"


def validar_contrasena(contrasena: str, filtradas: Container[str]) -> tuple[str, ...]:
    """Motivos por los que la contrasena NO cumple; vacio si cumple.

    Los espacios de los bordes no cuentan para la longitud. La comparacion con la lista no
    distingue mayusculas (la lista guarda las contrasenas en minusculas).
    """
    if not isinstance(contrasena, str):
        raise TypeError("La contraseña debe ser un texto")
    errores: list[str] = []
    if len(contrasena.strip()) < LONGITUD_MINIMA:
        errores.append(MENSAJE_CORTA)
    if contrasena.strip().lower() in filtradas:
        errores.append(MENSAJE_FILTRADA)
    return tuple(errores)
