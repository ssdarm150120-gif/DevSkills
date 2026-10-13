"""CU de alta de usuario (HU de gestion de usuarios y roles).

El Administrador da de alta con el correo corporativo (unico sin distinguir mayusculas), el nombre
y uno o varios roles. El sistema GENERA la contrasena
temporal, la devuelve UNA sola vez y guarda solo su hash; el usuario tiene que cambiarla en su
primer ingreso (D.3.10). El alta queda en el registro de acciones con quien la hizo, sin la
contrasena.

`UsuarioCambiado` y `ContrasenaTemporalEmitida` salen al bus con el registro de la accion, en la
misma transaccion (D.5.1).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from identidad.aplicacion.crear_administrador import AltaInvalida
from identidad.aplicacion.errores import ConflictoDeUsuario
from identidad.aplicacion.permisos import exigir_administrador
from identidad.aplicacion.puertos import (
    RegistroDeAccesos,
    Reloj,
    RepositorioCuentas,
    ServicioContrasenas,
)
from identidad.dominio.acceso import AccionDeCuenta
from identidad.dominio.usuarios import (
    MENSAJE_CORREO_REPETIDO,
    validar_datos,
)
from nucleo.actor import Actor


@dataclass(frozen=True, slots=True)
class UsuarioCreado:
    """Lo que el Administrador ve UNA vez: el correo ya normalizado y la contrasena temporal.

    La contrasena no sale en el `repr` (trazas, logs, mensajes de pytest).
    """

    id: str
    correo: str
    temporal: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class CrearUsuario:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    contrasenas: ServicioContrasenas
    reloj: Reloj

    def __call__(
        self,
        actor: Actor,
        *,
        correo: str,
        nombre: str,
        roles: Iterable[str],
    ) -> UsuarioCreado:
        """Da de alta al usuario.

        Lanza `PermisoDenegado` si el actor no es Administrador, `UsuarioInvalido` si los datos no
        cumplen las reglas y `ConflictoDeUsuario` si el correo ya esta en uso.
        """
        exigir_administrador(actor)
        datos = validar_datos(correo=correo, nombre=nombre, roles=roles)
        if self.cuentas.por_correo(datos.correo) is not None:
            raise ConflictoDeUsuario(MENSAJE_CORREO_REPETIDO)
        ahora = self.reloj.ahora()
        temporal = self.contrasenas.generar_temporal()
        try:
            cuenta = self.cuentas.crear(
                correo=datos.correo,
                hash_contrasena=self.contrasenas.hashear(temporal),
                roles=datos.roles,
                temporal=True,
                ahora=ahora,
                nombre=datos.nombre,
            )
        except AltaInvalida as error:  # alta simultanea del mismo correo
            raise ConflictoDeUsuario(MENSAJE_CORREO_REPETIDO) from error
        self.accesos.registrar_accion(
            accion=AccionDeCuenta.ALTA,
            usuario_objetivo_id=cuenta.id,
            hecha_por_id=actor.id,
            momento=ahora,
            detalle={"roles": sorted(datos.roles)},
        )
        return UsuarioCreado(id=cuenta.id, correo=cuenta.correo, temporal=temporal)
