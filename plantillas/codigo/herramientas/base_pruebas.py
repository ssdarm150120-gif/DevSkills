"""Nombre de la base de datos de pruebas, unico por sesion de pytest.

pytest-django crea `test_<nombre>` (por ejemplo `test_postgres`) en el servidor y la borra al
terminar. Dos sesiones de pytest sobre el MISMO servidor (el embebido de `.pgdata_pruebas`, o el
`DATABASE_URL` de CI) pisaban ese nombre: la segunda fallaba con `database "test_postgres" already
exists` o, peor, borraba la base de la primera. Con un sufijo unico por sesion no comparten nada.
"""

import os
import uuid

LIMITE_IDENTIFICADOR_POSTGRESQL = 63  # bytes de un nombre de base de datos


def nombre_unico(base: str, *, pid: int | None = None, azar: str | None = None) -> str:
    """`test_<base>_<pid>_<azar>`, siempre dentro del limite de 63 caracteres de PostgreSQL.

    `pid` y `azar` se inyectan solo en las pruebas; por defecto salen del proceso y de `uuid4`.
    El `pid` ayuda a rastrear una base huerfana; el azar evita el choque si el SO reutiliza el pid.
    """
    sufijo = f"_{os.getpid() if pid is None else pid}_{azar or uuid.uuid4().hex[:8]}"
    prefijo = f"test_{base}"
    return prefijo[: LIMITE_IDENTIFICADOR_POSTGRESQL - len(sufijo)] + sufijo
