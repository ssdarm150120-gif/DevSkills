"""Alta del primer Administrador desde el servidor (DISENO D.6.3, "Recuperacion del acceso").

Es la unica via fuera de la interfaz: sin ella nadie podria entrar la primera vez (no hay quien
de de alta desde la aplicacion). Genera una contrasena temporal que se muestra una sola vez, guarda
solo su hash y deja el alta en el registro de acciones. El resto del alta de usuarios
es de la HU de gestion de usuarios.
"""

from dataclasses import dataclass

from identidad.aplicacion.puertos import (
    RegistroDeAccesos,
    Reloj,
    RepositorioCuentas,
    ServicioContrasenas,
)
from identidad.dominio.acceso import AccionDeCuenta
from identidad.dominio.roles import ADMINISTRADOR
from identidad.dominio.usuarios import UsuarioInvalido, validar_correo


class AltaInvalida(ValueError):
    """El correo no es valido o ya existe."""


@dataclass(frozen=True, slots=True)
class CrearAdministrador:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    contrasenas: ServicioContrasenas
    reloj: Reloj

    def __call__(self, correo: str) -> tuple[str, str]:
        """Crea al Administrador. Devuelve `(id, contrasena_temporal)`."""
        try:
            correo = validar_correo(correo)
        except UsuarioInvalido as error:
            raise AltaInvalida(str(error)) from error
        if self.cuentas.por_correo(correo) is not None:
            raise AltaInvalida("Ya existe un usuario con ese correo")
        ahora = self.reloj.ahora()
        temporal = self.contrasenas.generar_temporal()
        cuenta = self.cuentas.crear(
            correo=correo,
            hash_contrasena=self.contrasenas.hashear(temporal),
            roles=frozenset({ADMINISTRADOR}),
            temporal=True,
            ahora=ahora,
        )
        self.accesos.registrar_accion(
            accion=AccionDeCuenta.ALTA,
            usuario_objetivo_id=cuenta.id,
            hecha_por_id=None,
            momento=ahora,
            detalle={"roles": [ADMINISTRADOR]},
        )
        return cuenta.id, temporal
