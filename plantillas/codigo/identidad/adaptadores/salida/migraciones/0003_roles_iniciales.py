"""Catalogo inicial de roles (DISENO D.2.3).

Los datos van congelados aqui (una migracion no debe importar el codigo vivo); una prueba verifica
que coincidan con `identidad.dominio.roles`.

Para agregar los roles de tu proyecto NO edites esta migracion: crea una nueva migracion de datos
(`0004_roles_del_proyecto.py`) con el mismo patron, y suma los codigos en `identidad.dominio.roles`
y en `nucleo.permisos`. Su reversa debe detenerse con un mensaje claro si algun usuario tiene el rol
(`UsuarioRol.rol` es PROTECT).
"""

from django.db import migrations

# (codigo, nombre, exige_segundo_factor)
ROLES = [
    ("administrador", "Administrador", True),
    ("auditor", "Auditor", True),
    ("usuario", "Usuario", False),
]


def cargar_roles(apps, schema_editor):
    Rol = apps.get_model("identidad", "Rol")
    for codigo, nombre, exige in ROLES:
        Rol.objects.update_or_create(
            codigo=codigo, defaults={"nombre": nombre, "exige_segundo_factor": exige}
        )


def quitar_roles(apps, schema_editor):
    apps.get_model("identidad", "Rol").objects.filter(codigo__in=[r[0] for r in ROLES]).delete()


class Migration(migrations.Migration):
    dependencies = [("identidad", "0002_usuarios_roles_y_registros")]

    operations = [migrations.RunPython(cargar_roles, quitar_roles)]
