from typing import Any

import pytest
from django.db import connection, models

from nucleo.adaptadores.esquemas import crear_esquema, nombre_tabla, validar_identificador


def test_nombre_tabla_califica_con_el_esquema() -> None:
    assert nombre_tabla("auditoria", "registro") == 'auditoria"."registro'


@pytest.mark.parametrize(
    "malo", ["", "Auditoria", "1abc", 'a"; DROP SCHEMA x; --', "a b", "a" * 64]
)
def test_rechaza_identificadores_peligrosos(malo: str) -> None:
    with pytest.raises(ValueError, match="Identificador"):
        validar_identificador(malo)
    with pytest.raises(ValueError, match="Identificador"):
        crear_esquema(malo)


def test_crear_esquema_es_idempotente_y_reversible() -> None:
    operacion = crear_esquema("auditoria")
    assert operacion.sql == 'CREATE SCHEMA IF NOT EXISTS "auditoria"'
    assert operacion.reverse_sql == 'DROP SCHEMA IF EXISTS "auditoria"'


@pytest.mark.django_db
def test_un_modelo_con_nombre_tabla_vive_en_el_esquema_de_su_modulo() -> None:
    class Prueba(models.Model):
        valor = models.CharField(max_length=10)
        objects: Any = models.Manager()  # el plugin de django-stubs no ve modelos locales

        class Meta:
            app_label = "auditoria"
            db_table = nombre_tabla("auditoria", "tabla_de_prueba")

    with connection.schema_editor() as editor:
        editor.create_model(Prueba)
    try:
        Prueba.objects.create(valor="x")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_schema FROM information_schema.tables WHERE table_name = %s",
                ["tabla_de_prueba"],
            )
            assert cursor.fetchall() == [("auditoria",)]
        assert Prueba.objects.count() == 1
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(Prueba)
