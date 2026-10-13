# Generada con `makemigrations` y completada a mano con los triggers de solo insercion.

import django.db.models.deletion
import django.db.models.functions.text
import uuid
from django.conf import settings
from django.db import migrations, models


# DISENO D.2.4: el registro de intentos y de acciones es inalterable. Un trigger por fila rechaza
# UPDATE y DELETE; uno por sentencia rechaza TRUNCATE (un trigger por fila no lo ve).
SQL_SOLO_INSERCION = """
CREATE FUNCTION "identidad".rechazar_modificacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'La tabla % es de solo inserción', TG_TABLE_NAME;
END
$$;
CREATE TRIGGER intento_ingreso_solo_insercion BEFORE UPDATE OR DELETE
    ON "identidad"."intento_ingreso" FOR EACH ROW EXECUTE FUNCTION "identidad".rechazar_modificacion();
CREATE TRIGGER accion_cuenta_solo_insercion BEFORE UPDATE OR DELETE
    ON "identidad"."accion_cuenta" FOR EACH ROW EXECUTE FUNCTION "identidad".rechazar_modificacion();
CREATE TRIGGER intento_ingreso_sin_truncate BEFORE TRUNCATE
    ON "identidad"."intento_ingreso" FOR EACH STATEMENT EXECUTE FUNCTION "identidad".rechazar_modificacion();
CREATE TRIGGER accion_cuenta_sin_truncate BEFORE TRUNCATE
    ON "identidad"."accion_cuenta" FOR EACH STATEMENT EXECUTE FUNCTION "identidad".rechazar_modificacion();
"""
SQL_QUITAR_SOLO_INSERCION = """
DROP TRIGGER accion_cuenta_sin_truncate ON "identidad"."accion_cuenta";
DROP TRIGGER intento_ingreso_sin_truncate ON "identidad"."intento_ingreso";
DROP TRIGGER accion_cuenta_solo_insercion ON "identidad"."accion_cuenta";
DROP TRIGGER intento_ingreso_solo_insercion ON "identidad"."intento_ingreso";
DROP FUNCTION "identidad".rechazar_modificacion();
"""


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('identidad', '0001_esquema'),
    ]

    operations = [
        migrations.CreateModel(
            name='Usuario',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('correo', models.CharField(max_length=254, unique=True)),
                ('nombre', models.CharField(blank=True, max_length=150)),
                ('activo', models.BooleanField(default=True)),
                ('debe_cambiar_contrasena', models.BooleanField(default=False)),
                ('contrasena_cambiada_en', models.DateTimeField(blank=True, null=True)),
                ('fallos_contrasena', models.PositiveSmallIntegerField(default=0)),
                ('fallos_codigo', models.PositiveSmallIntegerField(default=0)),
                ('bloqueada_hasta', models.DateTimeField(blank=True, null=True)),
                ('aviso_reuso_visto_hasta_id', models.BigIntegerField(blank=True, null=True)),
                ('sello_sesion', models.UUIDField(default=uuid.uuid4)),
                ('creado_en', models.DateTimeField()),
            ],
            options={
                'db_table': 'identidad"."usuario',
            },
        ),
        migrations.CreateModel(
            name='Rol',
            fields=[
                ('codigo', models.CharField(max_length=40, primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=80)),
                ('exige_segundo_factor', models.BooleanField(default=False)),
            ],
            options={
                'db_table': 'identidad"."rol',
            },
        ),
        migrations.CreateModel(
            name='AccionCuenta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('accion', models.CharField(choices=[('alta', 'ALTA'), ('cambio_de_contrasena', 'CAMBIO_DE_CONTRASENA'), ('bloqueo', 'BLOQUEO'), ('enrolamiento_segundo_factor', 'ENROLAMIENTO_SEGUNDO_FACTOR'), ('reinicio_segundo_factor', 'REINICIO_SEGUNDO_FACTOR'), ('sesion_iniciada', 'SESION_INICIADA'), ('sesion_cerrada_salida', 'SESION_CERRADA_SALIDA'), ('sesion_cerrada_tope_absoluto', 'SESION_CERRADA_TOPE_ABSOLUTO'), ('restablecimiento_contrasena', 'RESTABLECIMIENTO_CONTRASENA'), ('desbloqueo', 'DESBLOQUEO'), ('desactivacion', 'DESACTIVACION'), ('reactivacion', 'REACTIVACION'), ('cambio_de_roles', 'CAMBIO_DE_ROLES'), ('cambio_de_usuario', 'CAMBIO_DE_USUARIO')], max_length=40)),
                ('usuario_objetivo_id', models.UUIDField()),
                ('hecha_por_id', models.UUIDField(blank=True, null=True)),
                ('ocurrido_en', models.DateTimeField()),
                ('detalle', models.JSONField(blank=True, default=dict)),
            ],
            options={
                'db_table': 'identidad"."accion_cuenta',
                'indexes': [models.Index(fields=['usuario_objetivo_id', 'ocurrido_en'], name='accion_usuario_fecha')],
            },
        ),
        migrations.CreateModel(
            name='IntentoIngreso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('usuario_id', models.UUIDField(blank=True, null=True)),
                ('huella_correo', models.CharField(max_length=64)),
                ('factor', models.CharField(choices=[('contrasena', 'CONTRASENA'), ('codigo', 'CODIGO')], max_length=12)),
                ('resultado', models.CharField(choices=[('correcto', 'CORRECTO'), ('fallido', 'FALLIDO')], max_length=10)),
                ('motivo', models.CharField(choices=[('correcto', 'CORRECTO'), ('correo_inexistente', 'CORREO_INEXISTENTE'), ('contrasena_incorrecta', 'CONTRASENA_INCORRECTA'), ('usuario_desactivado', 'USUARIO_DESACTIVADO'), ('cuenta_bloqueada', 'CUENTA_BLOQUEADA'), ('requiere_segundo_factor', 'REQUIERE_SEGUNDO_FACTOR'), ('cambio_de_contrasena_incorrecta', 'CAMBIO_DE_CONTRASENA_INCORRECTA'), ('codigo_invalido', 'CODIGO_INVALIDO'), ('codigo_repetido', 'CODIGO_REPETIDO')], max_length=40)),
                ('ip', models.GenericIPAddressField()),
                ('ocurrido_en', models.DateTimeField()),
            ],
            options={
                'db_table': 'identidad"."intento_ingreso',
                'indexes': [models.Index(fields=['usuario_id', 'ocurrido_en'], name='intento_usuario_fecha')],
            },
        ),
        migrations.CreateModel(
            name='UsuarioRol',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asignado_por', models.UUIDField(blank=True, null=True)),
                ('asignado_en', models.DateTimeField()),
                ('rol', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='asignaciones', to='identidad.rol')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asignaciones', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'identidad"."usuario_rol',
            },
        ),
        migrations.AddField(
            model_name='usuario',
            name='roles',
            field=models.ManyToManyField(related_name='usuarios', through='identidad.UsuarioRol', to='identidad.rol'),
        ),
        migrations.CreateModel(
            name='SegundoFactor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('secreto_cifrado', models.TextField()),
                ('llave_id', models.CharField(max_length=16)),
                ('creado_en', models.DateTimeField()),
                ('confirmado_en', models.DateTimeField(blank=True, null=True)),
                ('ultimo_paso_aceptado', models.BigIntegerField(blank=True, null=True)),
                ('usuario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='segundo_factor', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'identidad"."segundo_factor',
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('confirmado_en__isnull', True), ('ultimo_paso_aceptado__isnull', True)), models.Q(('confirmado_en__isnull', False), ('ultimo_paso_aceptado__isnull', False)), _connector='OR'), name='segundo_factor_confirmado_con_paso')],
            },
        ),
        migrations.AddConstraint(
            model_name='usuariorol',
            constraint=models.UniqueConstraint(fields=('usuario', 'rol'), name='usuario_rol_unico'),
        ),
        migrations.AddConstraint(
            model_name='usuario',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('correo'), name='usuario_correo_unico_sin_mayusculas'),
        ),
        migrations.RunSQL(
            sql=SQL_SOLO_INSERCION,
            reverse_sql=SQL_QUITAR_SOLO_INSERCION,
        ),
    ]
