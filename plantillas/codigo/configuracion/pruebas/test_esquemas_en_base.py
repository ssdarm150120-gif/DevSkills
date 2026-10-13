import pytest
from django.db import connection

from configuracion.modulos import ESQUEMAS


@pytest.mark.django_db
def test_las_migraciones_crean_un_esquema_por_modulo() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT schema_name FROM information_schema.schemata")
        existentes = {fila[0] for fila in cursor.fetchall()}
    assert set(ESQUEMAS.values()) <= existentes
