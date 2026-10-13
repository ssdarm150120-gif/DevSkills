"""Codigo QR del enrolamiento, generado en el SERVIDOR.

La CSP del sitio es estricta (`default-src 'self'`, sin `unsafe-inline` y sin `data:`), y no se
relaja. Por eso el QR no es una imagen `data:` ni se dibuja con JavaScript: la plantilla pone un
`<svg>` con un unico `<path>` cuyo trazo (`d`) calcula esta funcion. No lleva `style` ni atributos
de evento, asi que la CSP lo admite tal cual. Y como la plantilla escapa el trazo (son solo
digitos, letras de comando y espacios), no hay que marcar nada como seguro.

`segno` solo se usa para armar la matriz de modulos del QR (Python puro, sin dependencias).
"""

from dataclasses import dataclass

import segno

# Zona en blanco alrededor del QR, en modulos. La especificacion pide 4 para que cualquier lector
# lo encuentre, tambien en el modo oscuro (el fondo del SVG es blanco).
BORDE_EN_MODULOS = 4


@dataclass(frozen=True, slots=True)
class TrazoQR:
    """`trazo` va en el atributo `d` del `<path>`; `lado` en el `viewBox="0 0 lado lado"`."""

    trazo: str
    lado: int


def trazo_del_qr(contenido: str, borde: int = BORDE_EN_MODULOS) -> TrazoQR:
    """Trazo SVG de los modulos oscuros del QR de `contenido` (nivel de correccion M)."""
    matriz = segno.make(contenido, error="m", boost_error=False).matrix
    ordenadas = [list(fila) for fila in matriz]
    comandos: list[str] = []
    for y, fila in enumerate(ordenadas):
        x = 0
        while x < len(fila):
            if not fila[x]:
                x += 1
                continue
            inicio = x
            while x < len(fila) and fila[x]:
                x += 1
            # Una corrida horizontal de modulos oscuros: un rectangulo de `x - inicio` por 1.
            comandos.append(f"M{inicio + borde} {y + borde}h{x - inicio}v1h-{x - inicio}z")
    return TrazoQR(trazo="".join(comandos), lado=len(ordenadas) + 2 * borde)
