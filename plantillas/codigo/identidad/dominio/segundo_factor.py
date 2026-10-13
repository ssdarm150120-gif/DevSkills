"""Segundo factor TOTP (DISENO D.3.10). Python puro.

Aqui viven las reglas que no dependen de ninguna biblioteca: cuantos pasos de tiempo se aceptan, que
un codigo ya usado no se acepta otra vez y como se escribe un codigo. El calculo del codigo (HMAC) y
el cifrado del secreto son de los adaptadores de salida.

TOTP (RFC 6238) con los valores que entienden todas las aplicaciones de codigos: SHA-1, 6 digitos y
pasos de 30 segundos. Un "paso" es el numero entero de intervalos de 30 s desde el 1 de enero de
1970.
"""

import re
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum

DIGITOS = 6
PASO_SEGUNDOS = 30
# Pasos de tolerancia a cada lado del actual (relojes desfasados): con 1 se acepta el del paso
# anterior, el vigente y el siguiente, o sea una ventana de 90 segundos como maximo.
TOLERANCIA_EN_PASOS = 1
# Tamano del secreto en bytes (RFC 4226 recomienda 160 bits).
BYTES_DEL_SECRETO = 20

# `[0-9]` y no `\d`: `\d` acepta digitos de otros alfabetos, que nunca coinciden con un codigo.
_CODIGO = re.compile("[0-9]{" + str(DIGITOS) + "}")
# Lo que una aplicacion de codigos muestra a veces con un espacio o un guion en medio ("123 456").
_SEPARADORES = re.compile(r"[ \-]")


class ResultadoCodigo(StrEnum):
    """Que paso con un codigo capturado."""

    ACEPTADO = "aceptado"
    INCORRECTO = "incorrecto"  # no coincide con ningun paso de la ventana, o esta mal escrito
    REPETIDO = "repetido"  # coincide, pero ese paso (o uno posterior) ya se acepto antes


def paso_de(momento: datetime) -> int:
    """Paso de tiempo de `momento` (que debe llevar zona horaria)."""
    if momento.tzinfo is None:
        raise ValueError("el momento debe llevar zona horaria")
    return int(momento.timestamp()) // PASO_SEGUNDOS


def pasos_de_la_ventana(momento: datetime) -> tuple[int, ...]:
    """Los pasos cuyo codigo se acepta en `momento`, del mas viejo al mas nuevo."""
    actual = paso_de(momento)
    return tuple(range(actual - TOLERANCIA_EN_PASOS, actual + TOLERANCIA_EN_PASOS + 1))


def normalizar_codigo(texto: str) -> str | None:
    """El codigo de 6 digitos sin separadores, o `None` si no tiene esa forma.

    Un codigo mal escrito no se compara con nada, pero cuenta como intento fallido (el limite de
    intentos no se puede esquivar mandando basura).
    """
    sin_separadores = _SEPARADORES.sub("", texto.strip())
    return sin_separadores if _CODIGO.fullmatch(sin_separadores) else None


def decidir_codigo(
    pasos_que_coinciden: Iterable[int], ultimo_paso_aceptado: int | None
) -> tuple[ResultadoCodigo, int | None]:
    """Decide un codigo a partir de los pasos de la ventana cuyo codigo coincide con el capturado.

    Un codigo se acepta una sola vez: solo vale si su paso es MAYOR que el ultimo
    aceptado, aunque siga dentro de su vigencia. Devuelve el resultado y, si se acepta, el paso que
    hay que guardar como `ultimo_paso_aceptado`.
    """
    coincidencias = sorted(set(pasos_que_coinciden))
    if not coincidencias:
        return ResultadoCodigo.INCORRECTO, None
    nuevos = [p for p in coincidencias if ultimo_paso_aceptado is None or p > ultimo_paso_aceptado]
    if not nuevos:
        return ResultadoCodigo.REPETIDO, None
    return ResultadoCodigo.ACEPTADO, nuevos[0]
