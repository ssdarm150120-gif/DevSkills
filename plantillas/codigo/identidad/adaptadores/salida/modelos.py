"""Modelos de `identidad` (DISENO D.2.3): usuario propio, roles, intentos y acciones.

`Usuario` es el `AUTH_USER_MODEL` y NO usa `PermissionsMixin`: el acceso lo deciden los roles que
viajan en el `Actor` y se verifican en el caso de uso, no los permisos por tabla de Django.
Las tablas viven en el esquema `identidad` (D.2.1). `IntentoIngreso` y `AccionCuenta` son de solo
insercion: un trigger rechaza UPDATE y DELETE (ver la migracion).
"""

import uuid
from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils.crypto import salted_hmac

from identidad.dominio.acceso import AccionDeCuenta, Factor, Motivo, Resultado
from nucleo.adaptadores.esquemas import nombre_tabla


class AdministradorDeUsuarios(BaseUserManager["Usuario"]):
    def por_correo(self, correo: str) -> "Usuario | None":
        return self.filter(correo__iexact=correo).first()


class Rol(models.Model):
    """Catalogo de roles. Se carga por migracion de datos; no se edita desde la aplicacion."""

    codigo = models.CharField(max_length=40, primary_key=True)
    nombre = models.CharField(max_length=80)
    exige_segundo_factor = models.BooleanField(default=False)

    class Meta:
        db_table = nombre_tabla("identidad", "rol")

    def __str__(self) -> str:
        return self.codigo


class Usuario(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # `unique` lo exige el chequeo de Django para `USERNAME_FIELD`; la unicidad SIN distinguir
    # mayusculas la garantiza la restriccion sobre `lower(correo)` de `Meta`.
    correo = models.CharField(max_length=254, unique=True)
    nombre = models.CharField(max_length=150, blank=True)
    activo = models.BooleanField(default=True)
    debe_cambiar_contrasena = models.BooleanField(default=False)
    contrasena_cambiada_en = models.DateTimeField(null=True, blank=True)
    fallos_contrasena = models.PositiveSmallIntegerField(default=0)
    # Contador del segundo factor, SEPARADO de `fallos_contrasena`.
    fallos_codigo = models.PositiveSmallIntegerField(default=0)
    bloqueada_hasta = models.DateTimeField(null=True, blank=True)
    # Id del ultimo `IntentoIngreso` de reuso de un codigo cuyo aviso ya vio el dueno (
    # , D.3.10). Nulo: nunca ha visto uno. Es un id y no una fecha: no depende del reloj.
    # Sin FK: `IntentoIngreso` es de solo insercion y no admite marcar una fila como vista, por eso
    # la marca vive aqui.
    aviso_reuso_visto_hasta_id = models.BigIntegerField(null=True, blank=True)
    # Entra en el hash de la sesion: cambiarlo cierra todas las sesiones del usuario (D.6.3).
    sello_sesion = models.UUIDField(default=uuid.uuid4)
    creado_en = models.DateTimeField()
    roles: "models.ManyToManyField[Rol, UsuarioRol]" = models.ManyToManyField(
        Rol, through="UsuarioRol", related_name="usuarios"
    )

    USERNAME_FIELD = "correo"
    REQUIRED_FIELDS: ClassVar[list[str]] = []
    objects = AdministradorDeUsuarios()

    class Meta:
        db_table = nombre_tabla("identidad", "usuario")
        constraints: ClassVar[list[Any]] = [
            # El correo es unico sin distinguir mayusculas.
            models.UniqueConstraint(Lower("correo"), name="usuario_correo_unico_sin_mayusculas"),
        ]

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return self.activo

    def set_password(self, raw_password: str | None) -> None:
        """Fija la contrasena Y rota el sello: cambiar la contrasena cierra todas las sesiones.

        Como el hash de la sesion depende solo del sello, sin esto `set_password()` + `save()` y
        `manage.py changepassword` (el camino de un operador que recupera una cuenta comprometida)
        dejarian vivas las sesiones del atacante hasta 12 horas.

        NO lo "unifiques" con el rehash de Argon2: `RepositorioCuentasDjango.actualizar_hash` usa
        `.update(password=...)` a proposito, SIN pasar por aqui, porque un rehash cambia los
        parametros del hash pero no la contrasena y no debe cerrar sesiones.
        """
        super().set_password(raw_password)
        self.sello_sesion = uuid.uuid4()

    def _get_session_auth_hash(self, secret: str | None = None) -> str:
        """Hash de la sesion: depende SOLO del sello. Si el sello cambia, la sesion deja de valer.

        No incluye el hash de la contrasena: asi un rehash de Argon2 (parametros nuevos, misma
        contrasena) no cierra las sesiones. Cambiar la contrasena SI cambia el sello.
        """
        return salted_hmac(
            "identidad.Usuario.get_session_auth_hash",
            str(self.sello_sesion),
            secret=secret,
            algorithm="sha256",
        ).hexdigest()

    def __str__(self) -> str:
        return self.correo


class UsuarioRol(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="asignaciones")
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name="asignaciones")
    asignado_por = models.UUIDField(null=True, blank=True)
    asignado_en = models.DateTimeField()

    class Meta:
        db_table = nombre_tabla("identidad", "usuario_rol")
        constraints: ClassVar[list[Any]] = [
            models.UniqueConstraint(fields=["usuario", "rol"], name="usuario_rol_unico"),
        ]


class SegundoFactor(models.Model):
    """El segundo factor TOTP de un usuario (DISENO D.2.3). Uno solo por usuario.

    El secreto se guarda CIFRADO con la llave del entorno (`APP_LLAVE_SEGUNDO_FACTOR`); `llave_id`
    dice cual lo cifro, para poder rotarla. `confirmado_en` y `ultimo_paso_aceptado` nacen juntos,
    cuando el usuario confirma su aplicacion con un codigo valido: mientras no se confirma, el
    registro solo guarda el secreto que se le mostro. Reiniciar el segundo factor es borrar la fila.
    """

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name="segundo_factor")
    secreto_cifrado = models.TextField()
    llave_id = models.CharField(max_length=16)
    creado_en = models.DateTimeField()
    confirmado_en = models.DateTimeField(null=True, blank=True)
    # Ultimo paso de tiempo (TOTP) aceptado: un codigo con un paso igual o menor no se acepta.
    ultimo_paso_aceptado = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = nombre_tabla("identidad", "segundo_factor")
        constraints: ClassVar[list[Any]] = [
            models.CheckConstraint(
                condition=(
                    models.Q(confirmado_en__isnull=True, ultimo_paso_aceptado__isnull=True)
                    | models.Q(confirmado_en__isnull=False, ultimo_paso_aceptado__isnull=False)
                ),
                name="segundo_factor_confirmado_con_paso",
            ),
        ]


def _opciones(enum: Any) -> list[tuple[str, str]]:
    return [(miembro.value, miembro.name) for miembro in enum]


class IntentoIngreso(models.Model):
    """Un intento de ingreso. Solo insercion. Guarda la huella del correo."""

    usuario_id = models.UUIDField(null=True, blank=True)  # nulo si el correo no existe
    huella_correo = models.CharField(max_length=64)
    factor = models.CharField(max_length=12, choices=_opciones(Factor))
    resultado = models.CharField(max_length=10, choices=_opciones(Resultado))
    motivo = models.CharField(max_length=40, choices=_opciones(Motivo))
    ip = models.GenericIPAddressField()
    ocurrido_en = models.DateTimeField()

    class Meta:
        db_table = nombre_tabla("identidad", "intento_ingreso")
        indexes: ClassVar[list[Any]] = [
            models.Index(fields=["usuario_id", "ocurrido_en"], name="intento_usuario_fecha")
        ]


class AccionCuenta(models.Model):
    """Una accion sobre una cuenta. Solo insercion. NUNCA guarda la contrasena."""

    accion = models.CharField(max_length=40, choices=_opciones(AccionDeCuenta))
    usuario_objetivo_id = models.UUIDField()
    hecha_por_id = models.UUIDField(null=True, blank=True)  # nulo: el sistema o el comando
    ocurrido_en = models.DateTimeField()
    # Lo que cambio (roles, campos...). Nunca contrasenas ni secretos.
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = nombre_tabla("identidad", "accion_cuenta")
        indexes: ClassVar[list[Any]] = [
            models.Index(fields=["usuario_objetivo_id", "ocurrido_en"], name="accion_usuario_fecha")
        ]
