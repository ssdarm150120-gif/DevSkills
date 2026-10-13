"""Levanta (o reutiliza) el PostgreSQL 16 embebido de desarrollo y muestra su `DATABASE_URL`.

La aplicacion nunca usa `localhost:5432` por defecto (ahi puede haber otro PostgreSQL), asi que en
dev `DATABASE_URL` es obligatoria. Con esta herramienta no hace falta instalar PostgreSQL:

    python -m herramientas.base_local            # imprime la URL; el servidor queda corriendo
    python -m herramientas.base_local --detener  # lo detiene

    # PowerShell:  $env:DATABASE_URL = "<la URL impresa>"
    # bash:        export DATABASE_URL="<la URL impresa>"
    python manage.py migrate && python manage.py runserver

SOLO PARA DESARROLLO LOCAL. Nunca en staging ni en produccion (alli `DATABASE_URL` apunta al
PostgreSQL real, con clave y TLS). `pgserver` inicializa el cluster con `--auth=trust`, es decir,
`pg_hba` NO pide clave a nadie que logre conectarse:
- En Windows no hay sockets Unix: el servidor escucha en `127.0.0.1` con un puerto aleatorio.
  Cualquier proceso local (de cualquier usuario de la maquina) que encuentre el puerto entra como
  superusuario `postgres`, sin clave.
- En Linux y macOS usa un socket Unix en un directorio temporal, accesible solo con los permisos
  del sistema de archivos (no abre ningun puerto TCP).

Datos de desarrollo en `.pgdata/` (raiz del repositorio). Las pruebas usan OTRO directorio
(`.pgdata_pruebas/`) para que `pytest` nunca detenga este servidor ni toque estos datos. Con
Docker Compose, define `DATABASE_URL` hacia el contenedor y no uses esta herramienta.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

_RAIZ_REPOSITORIO = Path(__file__).resolve().parent.parent.parent
DIRECTORIO_PGDATA = _RAIZ_REPOSITORIO / ".pgdata"
# Aparte del de dev: el servidor de pruebas se detiene al terminar pytest (conftest.py) y, si
# compartiera directorio, apagaria el PostgreSQL de desarrollo que levanta esta herramienta.
DIRECTORIO_PGDATA_PRUEBAS = _RAIZ_REPOSITORIO / ".pgdata_pruebas"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument("--detener", action="store_true", help="detiene el servidor embebido")
    args = parser.parse_args(argv)

    import pgserver  # dependencia solo de desarrollo local (requirements-dev.txt)

    if args.detener:
        pgserver.get_server(DIRECTORIO_PGDATA, cleanup_mode="stop").cleanup()
        print("PostgreSQL embebido detenido")
        return 0
    servidor = pgserver.get_server(DIRECTORIO_PGDATA, cleanup_mode=None)
    print(servidor.get_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
