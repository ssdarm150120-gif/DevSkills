"""Rol de BD sin ownership (DISENO D.6.3): la aplicacion no es duena del esquema.

Corre contra un PostgreSQL real (el embebido o el `DATABASE_URL` de CI) en una base y con roles
TEMPORALES de nombre unico, que se borran al terminar.
"""

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from herramientas import roles_bd
from herramientas.roles_bd import ErrorDeRoles, aprovisionar

CODIGO = Path(__file__).resolve().parents[2]
CLAVE_MIGRACIONES = "a1" * 16
CLAVE_APP = "b2" * 16
CREAR_VENTA = 'CREATE TABLE "ventas"."venta" (id serial PRIMARY KEY, estado text NOT NULL)'


def _url_con(url: str, *, usuario: str, clave: str, base: str) -> str:
    """Misma direccion del servidor, con otro usuario, otra clave y otra base."""
    partes = urlsplit(url)
    servidor = partes.netloc.rpartition("@")[2]
    return urlunsplit(
        (partes.scheme, f"{usuario}:{clave}@{servidor}", f"/{base}", partes.query, "")
    )


@dataclass(frozen=True)
class Entorno:
    url_admin: str
    url_migraciones: str
    url_app: str
    base: str
    rol_migraciones: str
    rol_app: str


@pytest.fixture
def entorno(url_base_de_datos: str) -> Iterator[Entorno]:
    sufijo = uuid.uuid4().hex[:8]
    base, mig, app = f"app_roles_{sufijo}", f"app_mig_{sufijo}", f"app_web_{sufijo}"
    with psycopg.connect(url_base_de_datos, autocommit=True) as servidor:
        servidor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(base)))
    admin = urlsplit(url_base_de_datos)
    try:
        yield Entorno(
            url_admin=_url_con(
                url_base_de_datos,
                usuario=admin.username or "postgres",
                clave=admin.password or "",
                base=base,
            ),
            url_migraciones=_url_con(
                url_base_de_datos, usuario=mig, clave=CLAVE_MIGRACIONES, base=base
            ),
            url_app=_url_con(url_base_de_datos, usuario=app, clave=CLAVE_APP, base=base),
            base=base,
            rol_migraciones=mig,
            rol_app=app,
        )
    finally:
        with psycopg.connect(url_base_de_datos, autocommit=True) as servidor:
            servidor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(base))
            )
            for rol in (app, mig):
                servidor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(rol)))


def _aprovisionar(e: Entorno) -> None:
    aprovisionar(
        e.url_admin,
        CLAVE_MIGRACIONES,
        CLAVE_APP,
        rol_migraciones=e.rol_migraciones,
        rol_app=e.rol_app,
    )


def _ejecutar(url: str, *sentencias: str) -> None:
    with psycopg.connect(url, autocommit=True) as conexion:
        for sentencia in sentencias:
            conexion.execute(sentencia)  # type: ignore[call-overload]


def test_los_roles_no_son_superusuarios_ni_pueden_crear_roles_ni_bases(entorno: Entorno) -> None:
    _aprovisionar(entorno)
    with psycopg.connect(entorno.url_admin) as conexion:
        filas = conexion.execute(
            "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, "
            "rolcanlogin FROM pg_roles WHERE rolname IN (%s, %s) ORDER BY rolname",
            (entorno.rol_app, entorno.rol_migraciones),
        ).fetchall()
    assert len(filas) == 2
    for _, superusuario, crear_bases, crear_roles, replicacion, saltar_rls, login in filas:
        assert (superusuario, crear_bases, crear_roles, replicacion, saltar_rls) == (False,) * 5
        assert login is True


def test_el_rol_de_migraciones_es_el_dueno_de_la_base(entorno: Entorno) -> None:
    _aprovisionar(entorno)
    with psycopg.connect(entorno.url_admin) as conexion:
        dueno = conexion.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"
        ).fetchone()
    assert dueno == (entorno.rol_migraciones,)


def test_la_aplicacion_hace_dml_sobre_lo_que_migra_el_otro_rol(entorno: Entorno) -> None:
    _aprovisionar(entorno)
    # Lo crea el rol de migraciones DESPUES del aprovisionamiento: lo cubren los privilegios por
    # defecto (`ALTER DEFAULT PRIVILEGES`).
    _ejecutar(entorno.url_migraciones, 'CREATE SCHEMA "ventas"', CREAR_VENTA)
    with psycopg.connect(entorno.url_app, autocommit=True) as app:
        assert app.execute("SELECT current_user").fetchone() == (entorno.rol_app,)
        app.execute("INSERT INTO ventas.venta (estado) VALUES ('borrador')")  # usa la secuencia
        app.execute("UPDATE ventas.venta SET estado = 'confirmado'")
        assert app.execute("SELECT estado FROM ventas.venta").fetchall() == [("confirmado",)]
        app.execute("DELETE FROM ventas.venta")


@pytest.mark.parametrize(
    "sentencia",
    [
        "CREATE TABLE public.intruso (i int)",
        'CREATE TABLE "ventas"."intruso" (i int)',
        "CREATE SCHEMA intruso",
        'DROP TABLE "ventas"."venta"',
        'ALTER TABLE "ventas"."venta" ADD COLUMN extra int',
        'TRUNCATE "ventas"."venta"',
        'DROP SCHEMA "ventas" CASCADE',
        'CREATE INDEX ON "ventas"."venta" (estado)',
        "CREATE ROLE otro",
    ],
)
def test_la_aplicacion_no_puede_alterar_el_esquema(entorno: Entorno, sentencia: str) -> None:
    _aprovisionar(entorno)
    _ejecutar(entorno.url_migraciones, 'CREATE SCHEMA "ventas"', CREAR_VENTA)
    with (
        psycopg.connect(entorno.url_app, autocommit=True) as app,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        app.execute(sentencia)  # type: ignore[call-overload]


def test_la_aplicacion_no_es_duena_de_nada(entorno: Entorno) -> None:
    _aprovisionar(entorno)
    _ejecutar(
        entorno.url_migraciones, 'CREATE SCHEMA "ventas"', 'CREATE TABLE "ventas"."t" (i int)'
    )
    with psycopg.connect(entorno.url_admin) as conexion:
        propios = conexion.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner "
            "WHERE r.rolname = %s",
            (entorno.rol_app,),
        ).fetchone()
        esquemas = conexion.execute(
            "SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner "
            "WHERE r.rolname = %s",
            (entorno.rol_app,),
        ).fetchone()
        privilegios = conexion.execute(
            "SELECT has_schema_privilege(%s, 'public', 'CREATE'), "
            "has_schema_privilege(%s, 'ventas', 'CREATE'), "
            "has_schema_privilege(%s, 'ventas', 'USAGE'), "
            "has_database_privilege(%s, current_database(), 'CREATE')",
            (entorno.rol_app,) * 4,
        ).fetchone()
    assert propios == (0,)
    assert esquemas == (0,)
    assert privilegios == (False, False, True, False)


def test_otros_roles_no_entran_a_la_base_por_defecto(entorno: Entorno) -> None:
    _aprovisionar(entorno)
    with psycopg.connect(entorno.url_admin) as conexion:
        fila = conexion.execute(
            "SELECT has_database_privilege('public', current_database(), 'CONNECT')"
        ).fetchone()
    assert fila == (False,)


def test_aprovisionar_es_idempotente_y_repara_lo_que_ya_existe(entorno: Entorno) -> None:
    _aprovisionar(entorno)
    _ejecutar(
        entorno.url_migraciones,
        'CREATE SCHEMA "ventas"',
        'CREATE TABLE "ventas"."venta" (id serial PRIMARY KEY)',
    )
    # Alguien le quito permisos a mano: volver a correr la herramienta los devuelve.
    rol = sql.Identifier(entorno.rol_app).as_string()
    _ejecutar(
        entorno.url_admin,
        f'REVOKE ALL ON TABLE "ventas"."venta" FROM {rol}',
        f'REVOKE ALL ON SEQUENCE "ventas"."venta_id_seq" FROM {rol}',
    )
    with (
        psycopg.connect(entorno.url_app, autocommit=True) as app,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        app.execute("SELECT * FROM ventas.venta")
    _aprovisionar(entorno)
    _aprovisionar(entorno)  # y repetirla no falla
    with psycopg.connect(entorno.url_app, autocommit=True) as app:
        app.execute("INSERT INTO ventas.venta DEFAULT VALUES")


@pytest.mark.parametrize(
    ("clave_migraciones", "clave_app", "mensaje"),
    [
        ("corta", CLAVE_APP, "APP_MIGRACIONES_PASSWORD"),
        (CLAVE_MIGRACIONES, "corta", "APP_WEB_PASSWORD"),
        ("CAMBIAR_clave_del_rol_de_migraciones", CLAVE_APP, "APP_MIGRACIONES_PASSWORD"),
        (CLAVE_MIGRACIONES, "CAMBIAR_clave_del_rol_de_la_aplicacion", "APP_WEB_PASSWORD"),
    ],
)
def test_aprovisionar_rechaza_claves_debiles_o_de_ejemplo(
    clave_migraciones: str, clave_app: str, mensaje: str
) -> None:
    with pytest.raises(ErrorDeRoles, match=mensaje):
        aprovisionar("postgres://x@h.invalid/d", clave_migraciones, clave_app)


@pytest.mark.parametrize("clave", ["corta", "CAMBIAR_clave_de_redis_de_ejemplo"])
def test_aprovisionar_rechaza_una_clave_de_redis_debil_o_de_ejemplo(clave: str) -> None:
    with pytest.raises(ErrorDeRoles, match="REDIS_PASSWORD"):
        aprovisionar("postgres://x@h.invalid/d", CLAVE_MIGRACIONES, CLAVE_APP, clave_redis=clave)


def test_main_rechaza_una_clave_de_redis_debil(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_ADMIN_URL", "postgres://x@h.invalid/d")
    monkeypatch.setenv("APP_MIGRACIONES_PASSWORD", CLAVE_MIGRACIONES)
    monkeypatch.setenv("APP_WEB_PASSWORD", CLAVE_APP)
    monkeypatch.setenv("REDIS_PASSWORD", "corta")
    assert roles_bd.main() == 2
    assert "REDIS_PASSWORD" in capsys.readouterr().err


def test_aprovisionar_rechaza_una_url_de_administracion_de_ejemplo() -> None:
    with pytest.raises(ErrorDeRoles, match="DATABASE_ADMIN_URL"):
        aprovisionar(
            "postgres://app_admin:CAMBIAR_clave@postgres:5432/app", CLAVE_MIGRACIONES, CLAVE_APP
        )


def test_aprovisionar_exige_dos_roles_distintos() -> None:
    with pytest.raises(ErrorDeRoles, match="distintos"):
        aprovisionar(
            "postgres://x@h.invalid/d",
            CLAVE_MIGRACIONES,
            CLAVE_APP,
            rol_migraciones="app",
            rol_app="app",
        )


def test_main_avisa_que_variables_faltan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for nombre in ("DATABASE_ADMIN_URL", "APP_MIGRACIONES_PASSWORD", "APP_WEB_PASSWORD"):
        monkeypatch.delenv(nombre, raising=False)
    assert roles_bd.main() == 2
    assert "DATABASE_ADMIN_URL" in capsys.readouterr().err


def test_main_aprovisiona_con_las_variables_de_entorno(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_ADMIN_URL", entorno.url_admin)
    monkeypatch.setenv("APP_MIGRACIONES_PASSWORD", CLAVE_MIGRACIONES)
    monkeypatch.setenv("APP_WEB_PASSWORD", CLAVE_APP)
    monkeypatch.setenv("APP_ROL_MIGRACIONES", entorno.rol_migraciones)
    monkeypatch.setenv("APP_ROL_WEB", entorno.rol_app)
    assert roles_bd.main() == 0
    salida = capsys.readouterr().out
    assert entorno.rol_app in salida
    assert CLAVE_APP not in salida  # nunca se imprimen las claves


@pytest.mark.lento
def test_de_punta_a_punta_migra_con_el_rol_dueno_y_la_aplicacion_solo_hace_dml(
    entorno: Entorno,
) -> None:
    """roles_bd -> `migrate` con `settings.migraciones` -> la aplicacion usa lo migrado."""
    _aprovisionar(entorno)
    variables = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "configuracion.settings.migraciones",
        "SECRET_KEY": "ci-clave-de-prueba-no-secreta-solo-para-check-deploy-0123456789",
        "DATABASE_MIGRACIONES_URL": entorno.url_migraciones,
    }
    variables.pop("DATABASE_URL", None)
    resultado = subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=CODIGO,
        env=variables,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    with psycopg.connect(entorno.url_app, autocommit=True) as app:
        app.execute(
            "INSERT INTO public.django_content_type (app_label, model) VALUES ('prueba', 'roles')"
        )
        privilegios = app.execute(
            "SELECT has_schema_privilege(current_user, 'auditoria', 'USAGE'), "
            "has_schema_privilege(current_user, 'auditoria', 'CREATE')"
        ).fetchone()
        assert privilegios == (True, False)  # el esquema del modulo lo creo la migracion
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("DROP TABLE public.django_migrations")


# --- Catalogos de solo lectura para la aplicacion -------------------------------------------


def test_la_aplicacion_no_escribe_en_el_catalogo_de_roles_pero_si_en_lo_demas(
    entorno: Entorno,
) -> None:
    """`identidad.rol` solo cambia por migracion: se aprovisiona de nuevo DESPUES de migrar."""
    _aprovisionar(entorno)
    _ejecutar(
        entorno.url_migraciones,
        'CREATE SCHEMA "identidad"',
        'CREATE TABLE "identidad"."rol" (codigo text PRIMARY KEY)',
        'CREATE TABLE "identidad"."accion_cuenta" (id serial PRIMARY KEY, accion text)',
        "INSERT INTO identidad.rol VALUES ('usuario')",
    )
    # Sin repetir el aprovisionamiento, los privilegios por defecto aun dan DML sobre `rol`.
    _aprovisionar(entorno)  # el paso `migrar` del Compose lo repite despues de `migrate`
    with psycopg.connect(entorno.url_app, autocommit=True) as app:
        assert app.execute("SELECT codigo FROM identidad.rol").fetchall() == [("usuario",)]
        for sentencia in (
            "INSERT INTO identidad.rol VALUES ('intruso')",
            "UPDATE identidad.rol SET codigo = 'otro'",
            "DELETE FROM identidad.rol",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(sentencia)  # type: ignore[call-overload]
        app.execute("INSERT INTO identidad.accion_cuenta (accion) VALUES ('alta')")


def test_aprovisionar_sin_la_tabla_del_catalogo_no_falla(entorno: Entorno) -> None:
    _aprovisionar(entorno)  # `identidad.rol` aun no existe (primer paso de `migrar`)
    _aprovisionar(entorno)


def test_el_paso_migrar_del_compose_repite_roles_bd_despues_de_migrate() -> None:
    compose = (CODIGO / "despliegue" / "docker-compose.yml").read_text(encoding="utf-8")
    linea = next(fila for fila in compose.splitlines() if "herramientas.roles_bd" in fila)
    assert linea.count("herramientas.roles_bd") == 2
    assert linea.index("migrate") < linea.rindex("herramientas.roles_bd")


# --- Outbox de eventos: inmutable para la aplicacion, purga por funcion del rol dueno -----


@pytest.mark.lento
def test_la_aplicacion_no_modifica_ni_borra_eventos_del_outbox_y_solo_la_funcion_purga(
    entorno: Entorno,
) -> None:
    """Con los roles REALES: INSERT si; UPDATE y DELETE no; la purga solo borra lo de 30+ dias."""
    _aprovisionar(entorno)
    variables = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "configuracion.settings.migraciones",
        "SECRET_KEY": "ci-clave-de-prueba-no-secreta-solo-para-check-deploy-0123456789",
        "DATABASE_MIGRACIONES_URL": entorno.url_migraciones,
    }
    variables.pop("DATABASE_URL", None)
    resultado = subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=CODIGO,
        env=variables,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    _aprovisionar(entorno)  # el paso `migrar` del Compose lo repite despues de `migrate`

    insertar_evento = (
        "INSERT INTO nucleo.evento_outbox (evento_id, nombre, version_esquema, agregado_id, "
        "ocurrido_en, registrado_en, payload, id_correlacion) VALUES "
        "(%s::uuid, 'PurgaEjecutada', 1, 'x', now() - %s::interval, now() - %s::interval, "
        "'{}', '') RETURNING id"
    )
    insertar_entrega = (
        "INSERT INTO nucleo.entrega_outbox (evento_id, consumidor, estado, intentos, "
        "proximo_intento_en, entregada_en, creada_en, ultimo_error) VALUES "
        "(%s, 'c', 'entregada', 1, now(), now() - %s::interval, now(), '')"
    )
    with psycopg.connect(entorno.url_app, autocommit=True) as app:
        ids = []
        for evento_id, edad in (
            ("00000000-0000-0000-0000-000000000001", "40 days"),
            ("00000000-0000-0000-0000-000000000002", "5 days"),
        ):
            fila = app.execute(insertar_evento, (evento_id, edad, edad)).fetchone()  # type: ignore[arg-type]
            assert fila is not None
            ids.append(fila[0])
            app.execute(insertar_entrega, (fila[0], edad))  # type: ignore[arg-type]
        for sentencia in (
            "UPDATE nucleo.evento_outbox SET nombre = 'otro'",
            "DELETE FROM nucleo.evento_outbox",
            "DELETE FROM nucleo.entrega_outbox",
            "TRUNCATE nucleo.evento_outbox CASCADE",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(sentencia)  # type: ignore[call-overload]
        app.execute("UPDATE nucleo.entrega_outbox SET intentos = 2")  # el despachador la actualiza
        # La funcion se niega a borrar lo reciente aunque la aplicacion se lo pida...
        with pytest.raises(psycopg.errors.RaiseException, match="purga_fuera_de_plazo"):
            app.execute("SELECT nucleo.purgar_eventos_outbox(now(), 10)")
        # ...y borra solo lo que cumple el plazo.
        borrados = app.execute(
            "SELECT nucleo.purgar_eventos_outbox(now() - interval '30 days', 10)"
        ).fetchone()
        assert borrados == (1,)
        quedan = app.execute("SELECT id FROM nucleo.evento_outbox").fetchall()
        assert quedan == [(ids[1],)]
    # Un rol que no es la aplicacion ni el dueno no puede ejecutar la funcion.
    _ejecutar(entorno.url_admin, "CREATE ROLE intruso_outbox NOLOGIN")
    try:
        with psycopg.connect(entorno.url_admin, autocommit=True) as admin:
            admin.execute("SET ROLE intruso_outbox")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                admin.execute("SELECT nucleo.purgar_eventos_outbox(now() - interval '31 days', 1)")
    finally:
        _ejecutar(
            entorno.url_admin,
            "DROP OWNED BY intruso_outbox",
            "DROP ROLE intruso_outbox",
        )
