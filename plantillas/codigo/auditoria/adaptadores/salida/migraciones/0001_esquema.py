from django.db import migrations

from nucleo.adaptadores.esquemas import crear_esquema


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [crear_esquema("auditoria")]
