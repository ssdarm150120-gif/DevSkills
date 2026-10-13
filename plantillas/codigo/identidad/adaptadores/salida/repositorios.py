"""Adaptadores de salida de `identidad` sobre el ORM de Django (implementan los puertos)."""

import hashlib
import hmac
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import QuerySet
from django.db.models.functions import Lower
from django.utils import timezone

from identidad.adaptadores.salida.modelos import (
    AccionCuenta,
    IntentoIngreso,
    Rol,
    Usuario,
    UsuarioRol,
)
from identidad.aplicacion.crear_administrador import AltaInvalida
from identidad.aplicacion.puertos import Cuenta, RolDelCatalogo
from identidad.dominio.acceso import AccionDeCuenta, Factor, Motivo, Resultado, normalizar_correo
from identidad.dominio.roles import ADMINISTRADOR


def _a_cuenta(usuario: Usuario) -> Cuenta:
    roles = list(usuario.roles.all())
    return Cuenta(
        id=str(usuario.id),
        correo=usuario.correo,
        activo=usuario.activo,
        roles=frozenset(rol.codigo for rol in roles),
        exige_segundo_factor=any(rol.exige_segundo_factor for rol in roles),
        debe_cambiar_contrasena=usuario.debe_cambiar_contrasena,
        fallos_contrasena=usuario.fallos_contrasena,
        bloqueada_hasta=usuario.bloqueada_hasta,
        hash_contrasena=usuario.password,
        sello_sesion=str(usuario.sello_sesion),
        fallos_codigo=usuario.fallos_codigo,
        nombre=usuario.nombre,
    )


def _consulta() -> QuerySet[Usuario]:
    # Dentro de una transaccion, bloquea la fila: dos intentos en paralelo no pierden el conteo.
    consulta = Usuario.objects.all()
    return consulta.select_for_update() if connection.in_atomic_block else consulta


class RepositorioCuentasDjango:
    def por_correo(self, correo: str) -> Cuenta | None:
        # `lower(correo)` coincide con el indice unico: la busqueda lo usa. Recibe el correo
        # YA normalizado (`normalizar_correo`).
        usuario = (
            _consulta()
            .alias(correo_en_minusculas=Lower("correo"))
            .filter(correo_en_minusculas=correo)
            .first()
        )
        return _a_cuenta(usuario) if usuario else None

    def trabajo_equivalente_sin_cuenta(self) -> None:
        # Mismas dos consultas que el camino con cuenta: los roles y el UPDATE del conteo. Una
        # cuenta con id nulo no existe, asi que no cambia nada.
        sin_cuenta = uuid.UUID(int=0)
        list(Usuario(pk=sin_cuenta).roles.all())
        Usuario.objects.filter(pk=sin_cuenta).update(fallos_contrasena=0, bloqueada_hasta=None)

    def por_id(self, usuario_id: str) -> Cuenta | None:
        try:
            identificador = uuid.UUID(usuario_id)
        except ValueError:
            return None
        usuario = _consulta().filter(pk=identificador).first()
        return _a_cuenta(usuario) if usuario else None

    def guardar_conteo(
        self, usuario_id: str, fallos: int, bloqueada_hasta: datetime | None
    ) -> None:
        Usuario.objects.filter(pk=usuario_id).update(
            fallos_contrasena=fallos, bloqueada_hasta=bloqueada_hasta
        )

    def guardar_conteo_codigo(
        self, usuario_id: str, fallos: int, bloqueada_hasta: datetime | None
    ) -> None:
        Usuario.objects.filter(pk=usuario_id).update(
            fallos_codigo=fallos, bloqueada_hasta=bloqueada_hasta
        )

    def rotar_sello(self, usuario_id: str) -> None:
        # Cierra todas las sesiones del usuario y cualquier etapa pendiente (D.6.3).
        Usuario.objects.filter(pk=usuario_id).update(sello_sesion=uuid.uuid4())

    def actualizar_hash(self, usuario_id: str, hash_contrasena: str) -> None:
        # Sin tocar `sello_sesion`: las sesiones abiertas siguen vivas.
        Usuario.objects.filter(pk=usuario_id).update(password=hash_contrasena)

    def guardar_contrasena(
        self, usuario_id: str, hash_contrasena: str, *, temporal: bool, ahora: datetime
    ) -> None:
        Usuario.objects.filter(pk=usuario_id).update(
            password=hash_contrasena,
            debe_cambiar_contrasena=temporal,
            contrasena_cambiada_en=ahora,
            sello_sesion=uuid.uuid4(),  # cierra las demas sesiones (D.6.3)
        )

    def crear(
        self,
        *,
        correo: str,
        hash_contrasena: str,
        roles: frozenset[str],
        temporal: bool,
        ahora: datetime,
        nombre: str = "",
    ) -> Cuenta:
        try:
            with transaction.atomic():
                usuario = Usuario.objects.create(
                    correo=correo,
                    nombre=nombre,
                    password=hash_contrasena,
                    debe_cambiar_contrasena=temporal,
                    creado_en=ahora,
                )
                for rol in Rol.objects.filter(codigo__in=roles):
                    UsuarioRol.objects.create(usuario=usuario, rol=rol, asignado_en=ahora)
        except IntegrityError as error:  # alta simultanea del mismo correo
            raise AltaInvalida("Ya existe un usuario con ese correo") from error
        return _a_cuenta(usuario)

    def listar(self) -> Sequence[Cuenta]:
        usuarios = Usuario.objects.prefetch_related("roles").order_by(Lower("correo"))
        return [_a_cuenta(usuario) for usuario in usuarios]

    def guardar_datos(self, usuario_id: str, *, nombre: str) -> None:
        Usuario.objects.filter(pk=usuario_id).update(nombre=nombre)

    def guardar_roles(
        self, usuario_id: str, roles: frozenset[str], *, asignado_por: str, ahora: datetime
    ) -> None:
        asignaciones = UsuarioRol.objects.filter(usuario_id=usuario_id)
        actuales = set(asignaciones.values_list("rol_id", flat=True))
        asignaciones.exclude(rol_id__in=roles).delete()
        for rol in Rol.objects.filter(codigo__in=roles - actuales):
            UsuarioRol.objects.create(
                usuario_id=usuario_id, rol=rol, asignado_por=asignado_por, asignado_en=ahora
            )

    def fijar_activo(self, usuario_id: str, activo: bool) -> None:
        Usuario.objects.filter(pk=usuario_id).update(activo=activo)

    def bloquear_administradores_activos(self) -> frozenset[str]:
        # 1) Quienes son hoy; 2) se bloquean sus filas SIN unir tablas (`FOR UPDATE OF` no admite
        # las tablas con esquema), en el mismo orden por id en toda transaccion, para que dos
        # cambios simultaneos no se bloqueen mutuamente; 3) se lee de nuevo, ya con los bloqueos:
        # lo que otra transaccion haya confirmado mientras esperabamos ya se ve.
        administradores = Usuario.objects.filter(activo=True, asignaciones__rol_id=ADMINISTRADOR)
        candidatos = list(administradores.order_by("id").values_list("id", flat=True))
        list(
            Usuario.objects.filter(pk__in=candidatos)
            .order_by("id")
            .select_for_update()
            .values_list("id", flat=True)
        )
        return frozenset(str(id_) for id_ in administradores.values_list("id", flat=True))


class CatalogoDeRolesDjango:
    def roles(self) -> Sequence[RolDelCatalogo]:
        return [
            RolDelCatalogo(rol.codigo, rol.nombre, rol.exige_segundo_factor)
            for rol in Rol.objects.order_by("nombre")
        ]


def huella_de_correo(correo: str) -> str:
    """HMAC del correo capturado: permite correlacionar intentos sin guardar el texto.

    En el campo de correo a veces se escribe la contrasena por error: el texto no se guarda.
    """
    return hmac.new(
        settings.APP_LLAVE_HUELLA.encode(), normalizar_correo(correo).encode(), hashlib.sha256
    ).hexdigest()


class RegistroDeAccesosDjango:
    def registrar_intento(
        self,
        *,
        correo_capturado: str,
        usuario_id: str | None,
        factor: Factor,
        resultado: Resultado,
        motivo: Motivo,
        ip: str,
        momento: datetime,
    ) -> int:
        return IntentoIngreso.objects.create(
            usuario_id=usuario_id,
            huella_correo=huella_de_correo(correo_capturado),
            factor=factor.value,
            resultado=resultado.value,
            motivo=motivo.value,
            ip=ip,
            ocurrido_en=momento,
        ).pk

    def registrar_accion(
        self,
        *,
        accion: AccionDeCuenta,
        usuario_objetivo_id: str,
        hecha_por_id: str | None,
        momento: datetime,
        detalle: Mapping[str, object] | None = None,
    ) -> int:
        return AccionCuenta.objects.create(
            accion=accion.value,
            usuario_objetivo_id=usuario_objetivo_id,
            hecha_por_id=hecha_por_id,
            ocurrido_en=momento,
            detalle=dict(detalle or {}),
        ).pk


class RelojDelSistema:
    def ahora(self) -> datetime:
        return timezone.now()
