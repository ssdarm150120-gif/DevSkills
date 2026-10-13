"""Roles de PostgreSQL sin ownership para la aplicacion (DISENO D.6.3).

"La aplicacion no es duena del esquema": el proceso que atiende peticiones no puede crear, alterar
ni borrar tablas. Se separan dos roles:

* `app_migraciones`: DUENO de la base y de todo lo que crean las migraciones. Solo lo usa
  `manage.py migrate` (`configuracion.settings.migraciones`).
* `app_web`: rol de EJECUCION (`web`, `worker`). Solo SELECT, INSERT, UPDATE y DELETE sobre las
  tablas, y USAGE sobre esquemas y secuencias. Sin CREATE, sin TRUNCATE, sin ownership.

Esta herramienta es idempotente y corre con una cuenta administradora (`DATABASE_ADMIN_URL`) ANTES
de las migraciones (los privilegios por defecto cubren las tablas que se creen despues) y puede
repetirse despues (tambien concede sobre lo que ya exista):

    python -m herramientas.roles_bd

Variables: `DATABASE_ADMIN_URL`, `APP_MIGRACIONES_PASSWORD`, `APP_WEB_PASSWORD` y, si se quiere,
`APP_ROL_MIGRACIONES` y `APP_ROL_WEB` (por defecto `app_migraciones` y `app_web`). Con un
PostgreSQL administrado (RDS, Azure) esto lo hace el equipo de TI o la infraestructura como codigo.
"""

import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any

import psycopg
from django.core.exceptions import ImproperlyConfigured
from psycopg import sql

from configuracion.entorno import sin_marcador_de_ejemplo

ROL_MIGRACIONES = "app_migraciones"
ROL_WEB = "app_web"
LARGO_MINIMO_CLAVE = 16
_PRIVILEGIOS_TABLA = sql.SQL("SELECT, INSERT, UPDATE, DELETE")
_PRIVILEGIOS_SECUENCIA = sql.SQL("USAGE, SELECT")
# Catalogos que solo cambian por migracion: la aplicacion los lee y nada mas. Los privilegios
# por defecto no pueden excluir una tabla, asi que se quitan al repartir lo que YA existe; por eso
# esta herramienta corre tambien DESPUES de `migrate` (ver el paso `migrar` del Compose).
TABLAS_SOLO_LECTURA = (("identidad", "rol"),)
# Registros de solo insercion para la aplicacion: el evento del outbox no se
# modifica ni se borra desde la aplicacion; solo lo borra la funcion `purgar_eventos_outbox`
# (SECURITY DEFINER, del rol dueno) y solo cuando cumple el plazo de retencion. De `entrega_outbox`
# la aplicacion no borra: el despachador solo la actualiza.
PRIVILEGIOS_QUITADOS: tuple[tuple[str, str, str], ...] = (
    ("nucleo", "evento_outbox", "UPDATE, DELETE"),
    ("nucleo", "entrega_outbox", "DELETE"),
)
# Funciones que la aplicacion puede ejecutar (se crean en migraciones sin permiso para PUBLIC).
FUNCIONES_PARA_LA_APP = (("nucleo", "purgar_eventos_outbox(timestamptz, integer)"),)


class ErrorDeRoles(Exception):
    """Configuracion invalida de los roles (clave debil, nombres iguales, variable faltante)."""


def _validar(rol_migraciones: str, rol_app: str, claves: Mapping[str, str]) -> None:
    if rol_migraciones == rol_app:
        raise ErrorDeRoles("el rol de migraciones y el de la aplicacion deben ser distintos")
    for nombre, clave in claves.items():
        if len(clave) < LARGO_MINIMO_CLAVE:
            raise ErrorDeRoles(f"{nombre} debe tener al menos {LARGO_MINIMO_CLAVE} caracteres")
        try:
            sin_marcador_de_ejemplo(nombre, clave)
        except ImproperlyConfigured as error:
            raise ErrorDeRoles(str(error)) from None


def _crear_o_actualizar_rol(conexion: psycopg.Connection, rol: str, clave: str) -> None:
    existe = conexion.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rol,)).fetchone()
    verbo = sql.SQL("ALTER ROLE") if existe else sql.SQL("CREATE ROLE")
    conexion.execute(
        sql.SQL(
            "{verbo} {rol} WITH LOGIN PASSWORD {clave} NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS"
        ).format(verbo=verbo, rol=sql.Identifier(rol), clave=sql.Literal(clave))
    )


def aprovisionar(
    url_admin: str,
    clave_migraciones: str,
    clave_app: str,
    *,
    rol_migraciones: str = ROL_MIGRACIONES,
    rol_app: str = ROL_WEB,
) -> None:
    """Crea (o actualiza) los dos roles y reparte los privilegios en la base de `url_admin`."""
    _validar(
        rol_migraciones,
        rol_app,
        {
            "DATABASE_ADMIN_URL": url_admin,
            "APP_MIGRACIONES_PASSWORD": clave_migraciones,
            "APP_WEB_PASSWORD": clave_app,
        },
    )
    migraciones, app = sql.Identifier(rol_migraciones), sql.Identifier(rol_app)
    with psycopg.connect(url_admin) as conexion:
        (nombre_base,) = conexion.execute("SELECT current_database()").fetchone() or ("",)
        base = sql.Identifier(nombre_base)
        _crear_o_actualizar_rol(conexion, rol_migraciones, clave_migraciones)
        _crear_o_actualizar_rol(conexion, rol_app, clave_app)

        # La base y lo que cree `migrate` son del rol de migraciones; nadie mas entra por defecto.
        conexion.execute(sql.SQL("ALTER DATABASE {b} OWNER TO {m}").format(b=base, m=migraciones))
        conexion.execute(sql.SQL("REVOKE ALL ON DATABASE {b} FROM PUBLIC").format(b=base))
        conexion.execute(sql.SQL("GRANT CONNECT ON DATABASE {b} TO {a}").format(b=base, a=app))
        conexion.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM PUBLIC"))
        conexion.execute(sql.SQL("ALTER SCHEMA public OWNER TO {m}").format(m=migraciones))

        # Lo que el rol de migraciones cree DE AQUI EN ADELANTE queda usable por la aplicacion.
        for objeto, privilegios in (
            (sql.SQL("SCHEMAS"), sql.SQL("USAGE")),
            (sql.SQL("TABLES"), _PRIVILEGIOS_TABLA),
            (sql.SQL("SEQUENCES"), _PRIVILEGIOS_SECUENCIA),
        ):
            conexion.execute(
                sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {m} GRANT {p} ON {o} TO {a}").format(
                    m=migraciones, p=privilegios, o=objeto, a=app
                )
            )

        # Y lo que YA exista (esquemas del rol de migraciones, mas `public`).
        esquemas = [
            fila[0]
            for fila in conexion.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname = 'public' OR nspowner = "
                "(SELECT oid FROM pg_roles WHERE rolname = %s)",
                (rol_migraciones,),
            ).fetchall()
        ]
        for nombre in esquemas:
            esquema = sql.Identifier(nombre)
            conexion.execute(sql.SQL("GRANT USAGE ON SCHEMA {e} TO {a}").format(e=esquema, a=app))
            conexion.execute(
                sql.SQL("GRANT {p} ON ALL TABLES IN SCHEMA {e} TO {a}").format(
                    p=_PRIVILEGIOS_TABLA, e=esquema, a=app
                )
            )
            conexion.execute(
                sql.SQL("GRANT {p} ON ALL SEQUENCES IN SCHEMA {e} TO {a}").format(
                    p=_PRIVILEGIOS_SECUENCIA, e=esquema, a=app
                )
            )
        _quitar_escritura_de_catalogos(conexion, app)


def _quitar_escritura_de_catalogos(conexion: psycopg.Connection[Any], app: sql.Identifier) -> None:
    quitados = [(e, t, "INSERT, UPDATE, DELETE") for e, t in TABLAS_SOLO_LECTURA]
    for esquema, tabla, privilegios in (*quitados, *PRIVILEGIOS_QUITADOS):
        existe = conexion.execute("SELECT to_regclass(%s)", (f"{esquema}.{tabla}",)).fetchone()
        if existe and existe[0]:
            conexion.execute(
                sql.SQL("REVOKE {p} ON {e}.{t} FROM {a}").format(
                    p=sql.SQL(privilegios),
                    e=sql.Identifier(esquema),
                    t=sql.Identifier(tabla),
                    a=app,
                )
            )
    for esquema, firma in FUNCIONES_PARA_LA_APP:
        existe = conexion.execute("SELECT to_regprocedure(%s)", (f"{esquema}.{firma}",)).fetchone()
        if existe and existe[0]:
            conexion.execute(
                sql.SQL("GRANT EXECUTE ON FUNCTION {e}.{f} TO {a}").format(
                    e=sql.Identifier(esquema), f=sql.SQL(firma), a=app
                )
            )


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    rol_migraciones = os.environ.get("APP_ROL_MIGRACIONES", ROL_MIGRACIONES)
    rol_app = os.environ.get("APP_ROL_WEB", ROL_WEB)
    try:
        variables = {
            nombre: os.environ.get(nombre, "").strip()
            for nombre in ("DATABASE_ADMIN_URL", "APP_MIGRACIONES_PASSWORD", "APP_WEB_PASSWORD")
        }
        faltantes = [nombre for nombre, valor in variables.items() if not valor]
        if faltantes:
            raise ErrorDeRoles(f"faltan variables de entorno: {', '.join(faltantes)}")
        aprovisionar(
            variables["DATABASE_ADMIN_URL"],
            variables["APP_MIGRACIONES_PASSWORD"],
            variables["APP_WEB_PASSWORD"],
            rol_migraciones=rol_migraciones,
            rol_app=rol_app,
        )
    except ErrorDeRoles as error:
        print(f"roles_bd: {error}", file=sys.stderr)
        return 2
    print(f"roles_bd: roles {rol_migraciones} (dueno) y {rol_app} (sin ownership) listos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
