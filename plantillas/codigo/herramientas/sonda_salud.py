"""Sonda de salud del contenedor (`HEALTHCHECK` del Dockerfile): consulta `/salud` de `web`.

    python -m herramientas.sonda_salud                # sale con 0 si /salud responde 200

La sonda llega al proceso por el loopback del propio contenedor, SIN pasar por nginx, asi que
reproduce lo que nginx agrega: un `Host` permitido (el primero de `ALLOWED_HOSTS`, sin el punto de
un comodin `.dominio`) y `X-Forwarded-Proto: https` para que `SECURE_SSL_REDIRECT` no la redirija.
Usa solo la biblioteca estandar: la imagen no instala `curl`.
"""

import http.client
import os
import sys
from collections.abc import Mapping, Sequence

PUERTO_POR_DEFECTO = 8000
TIEMPO_MAXIMO_S = 4.0


def host_de_la_sonda(entorno: Mapping[str, str]) -> str:
    """Primer host de `ALLOWED_HOSTS` (un comodin `.dominio` se usa como `dominio`)."""
    hosts = [h.strip() for h in entorno.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
    return hosts[0].lstrip(".") if hosts else "localhost"


def consultar(entorno: Mapping[str, str], puerto: int = PUERTO_POR_DEFECTO) -> int:
    """Devuelve el codigo HTTP de `/salud`, o 0 si no hubo respuesta (rechazo o tiempo agotado)."""
    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=TIEMPO_MAXIMO_S)
    try:
        conexion.request(
            "GET",
            "/salud",
            headers={"Host": host_de_la_sonda(entorno), "X-Forwarded-Proto": "https"},
        )
        return conexion.getresponse().status
    except (OSError, http.client.HTTPException):
        return 0
    finally:
        conexion.close()


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    puerto = int(os.environ.get("PUERTO_WEB", PUERTO_POR_DEFECTO))
    return 0 if consultar(os.environ, puerto) == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
