"""Un correo inexistente hace el mismo trabajo de base de datos que una contraseña incorrecta
sin eso respondía unos milisegundos antes y el tiempo delataba qué correos existen."""

from collections.abc import Callable

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from identidad.adaptadores.salida.modelos import Usuario
from identidad.adaptadores.salida.repositorios import RepositorioCuentasDjango
from identidad.pruebas.test_iniciar_sesion import CORREO, Entorno


def test_el_caso_de_uso_hace_el_trabajo_equivalente_cuando_el_correo_no_existe() -> None:
    e = Entorno()
    e.ingresar(correo="nadie@empresa.example", contrasena="x" * 12)
    assert e.cuentas.trabajos_sin_cuenta == 1  # type: ignore[attr-defined]
    e.ingresar(correo=CORREO, contrasena="x" * 12)  # tampoco existe en este entorno vacio
    assert e.cuentas.trabajos_sin_cuenta == 2  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_el_trabajo_equivalente_hace_las_mismas_consultas_que_con_cuenta(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario(correo="c@empresa.example")
    repositorio = RepositorioCuentasDjango()
    with CaptureQueriesContext(connection) as con_cuenta:
        cuenta = repositorio.por_correo("c@empresa.example")
        assert cuenta is not None
        repositorio.guardar_conteo(cuenta.id, 1, None)
    with CaptureQueriesContext(connection) as sin_cuenta:
        assert repositorio.por_correo("nadie@empresa.example") is None
        repositorio.trabajo_equivalente_sin_cuenta()

    def tipos(consultas: CaptureQueriesContext) -> list[str]:
        return [q["sql"].split()[0].upper() for q in consultas.captured_queries]

    assert tipos(con_cuenta) == tipos(sin_cuenta) == ["SELECT", "SELECT", "UPDATE"]
    Usuario.objects.get(pk=usuario.pk)  # la cuenta real no se toco por el trabajo ficticio
    assert Usuario.objects.get(pk=usuario.pk).fallos_contrasena == 1


@pytest.mark.django_db
def test_un_ingreso_con_correo_inexistente_no_cambia_ninguna_cuenta(
    crear_usuario: Callable[..., Usuario],
) -> None:
    usuario = crear_usuario(correo="c@empresa.example")
    Client().post("/ingresar", {"correo": "nadie@empresa.example", "contrasena": "x" * 12})
    assert Usuario.objects.get(pk=usuario.pk).fallos_contrasena == 0
