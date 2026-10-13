"""Esquema de PostgreSQL por modulo (DISENO D.2.1).

Mecanismo:

1. Cada modulo es dueno de un esquema con su mismo nombre (`pedidos`, `clientes`...);
   `nucleo` usa `nucleo` (outbox).
2. El esquema se crea en la migracion `0001_esquema` de cada modulo, con `crear_esquema`.
   Las migraciones viven en `<modulo>/adaptadores/salida/migraciones` (ver `MIGRATION_MODULES`).
3. Los modelos de Django declaran su tabla calificada con `nombre_tabla`:

       class Meta:
           db_table = nombre_tabla("pedidos", "pedido")   # -> "pedidos"."pedido"

   No se usa `search_path`: la tabla siempre va calificada, asi que un modulo no puede tocar
   por accidente las tablas de otro y no depende de la configuracion de la conexion.
4. Referencias entre modulos: columnas de ID sin clave foranea (D.2.1).
"""

import re

from django.db.migrations.operations.special import RunSQL

_PATRON_IDENTIFICADOR = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def validar_identificador(valor: str) -> str:
    """Valida un nombre de esquema o tabla (minusculas, digitos y guion bajo)."""
    if not _PATRON_IDENTIFICADOR.fullmatch(valor):
        raise ValueError(f"Identificador SQL invalido: {valor!r}")
    return valor


def nombre_tabla(esquema: str, tabla: str) -> str:
    """Valor para `Meta.db_table` que califica la tabla con su esquema.

    Django cita el nombre completo como un solo identificador (`"<valor>"`); intercalar las
    comillas hace que PostgreSQL lo lea como `"esquema"."tabla"`.
    """
    return f'{validar_identificador(esquema)}"."{validar_identificador(tabla)}'


def crear_esquema(esquema: str) -> RunSQL:
    """Operacion de migracion que crea el esquema del modulo (idempotente y reversible)."""
    esquema = validar_identificador(esquema)
    return RunSQL(
        sql=f'CREATE SCHEMA IF NOT EXISTS "{esquema}"',
        reverse_sql=f'DROP SCHEMA IF EXISTS "{esquema}"',
    )
