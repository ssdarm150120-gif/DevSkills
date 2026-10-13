"""CU de desactivar y reactivar a un usuario (HU de gestion de usuarios; DISENO D.3.10).

Un usuario NO se borra: se desactiva. Desactivarlo cambia el sello de sesion (sus sesiones abiertas
caen y ya no puede ingresar) y deja su historia intacta: sus acciones pasadas siguen en el registro
con su identificador, y su correo y su nombre siguen en la tabla de usuarios.

Lo que NO ocurre aqui, porque pertenece a otros modulos que consumen los eventos del bus: lo que
cada modulo haga con lo asignado a un usuario desactivado lo decide al consumir el evento
`UsuarioDesactivado`, que se emite al desactivar a CUALQUIER usuario, en la misma transaccion
(D.5.1).

Reglas heredadas del proyecto de referencia: nadie se desactiva a si mismo y siempre queda al menos
un Administrador activo, aunque dos se desactiven a la vez.
"""

from dataclasses import dataclass

from identidad.aplicacion.errores import CuentaNoDisponible, PermisoDenegado
from identidad.aplicacion.permisos import (
    MENSAJE_PROPIA_CUENTA,
    exigir_administrador,
    exigir_que_quede_administrador,
)
from identidad.aplicacion.puertos import RegistroDeAccesos, Reloj, RepositorioCuentas
from identidad.dominio.acceso import AccionDeCuenta
from identidad.dominio.roles import ADMINISTRADOR
from nucleo.actor import Actor


@dataclass(frozen=True, slots=True)
class DesactivarUsuario:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    reloj: Reloj

    def __call__(self, actor: Actor, usuario_id: str) -> bool:
        """Desactiva al usuario. Devuelve si estaba activo (si ya no lo estaba, no cambia nada)."""
        exigir_administrador(actor)
        # Bloqueo de los Administradores primero y del objetivo despues (mismo orden siempre).
        administradores = self.cuentas.bloquear_administradores_activos()
        objetivo = self.cuentas.por_id(usuario_id)
        if objetivo is None:
            raise CuentaNoDisponible
        if objetivo.id == actor.id:
            raise PermisoDenegado(MENSAJE_PROPIA_CUENTA)
        if not objetivo.activo:
            return False
        if ADMINISTRADOR in objetivo.roles:
            exigir_que_quede_administrador(administradores, objetivo.id)
        self.cuentas.fijar_activo(objetivo.id, False)
        self.cuentas.rotar_sello(objetivo.id)  # sus sesiones caen y ya no puede entrar
        self.accesos.registrar_accion(
            accion=AccionDeCuenta.DESACTIVACION,
            usuario_objetivo_id=objetivo.id,
            hecha_por_id=actor.id,
            momento=self.reloj.ahora(),
            detalle={"roles": sorted(objetivo.roles)},
        )
        return True


@dataclass(frozen=True, slots=True)
class ReactivarUsuario:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    reloj: Reloj

    def __call__(self, actor: Actor, usuario_id: str) -> bool:
        """Reactiva al usuario. Devuelve si estaba desactivado."""
        exigir_administrador(actor)
        objetivo = self.cuentas.por_id(usuario_id)
        if objetivo is None:
            raise CuentaNoDisponible
        if objetivo.activo:
            return False
        self.cuentas.fijar_activo(objetivo.id, True)
        self.accesos.registrar_accion(
            accion=AccionDeCuenta.REACTIVACION,
            usuario_objetivo_id=objetivo.id,
            hecha_por_id=actor.id,
            momento=self.reloj.ahora(),
            detalle={"roles": sorted(objetivo.roles)},
        )
        return True
