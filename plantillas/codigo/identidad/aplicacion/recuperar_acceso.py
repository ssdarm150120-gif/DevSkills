"""Recuperar el acceso de un usuario: restablecer la contrasena y desbloquear la cuenta
(DISENO D.3.10). Reiniciar el segundo factor es `ReiniciarSegundoFactor`.

No hay autoservicio por correo: lo hace el Administrador.

* Restablecer: genera OTRA contrasena temporal que se devuelve UNA sola vez, la anterior deja de
  servir, el usuario debe cambiarla al ingresar y el sello de sesion cambia (sus sesiones caen).
  NADIE restablece su propia contrasena como Administrador: lo hace otro.
* Desbloquear: pone en cero los dos contadores y quita el bloqueo, sin esperar los 15 minutos.

Cada accion queda en el registro con quien la hizo, sobre que usuario y cuando; nunca la
contrasena. `ContrasenaTemporalEmitida` y `CuentaDesbloqueada` salen al bus con el registro.
"""

from dataclasses import dataclass, field

from identidad.aplicacion.errores import CuentaNoDisponible
from identidad.aplicacion.permisos import exigir_administrador, exigir_otro_administrador
from identidad.aplicacion.puertos import (
    RegistroDeAccesos,
    Reloj,
    RepositorioCuentas,
    ServicioContrasenas,
)
from identidad.dominio.acceso import AccionDeCuenta
from nucleo.actor import Actor


@dataclass(frozen=True, slots=True)
class ContrasenaRestablecida:
    """La contrasena temporal nueva (solo existe en esta respuesta; fuera del `repr`)."""

    correo: str
    temporal: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class RestablecerContrasena:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    contrasenas: ServicioContrasenas
    reloj: Reloj

    def __call__(self, actor: Actor, usuario_id: str) -> ContrasenaRestablecida:
        exigir_administrador(actor)
        objetivo = self.cuentas.por_id(usuario_id)
        if objetivo is None:
            raise CuentaNoDisponible
        exigir_otro_administrador(actor, objetivo)
        ahora = self.reloj.ahora()
        temporal = self.contrasenas.generar_temporal()
        # Guarda el hash nuevo (la anterior deja de servir), marca la temporal y cambia el sello.
        self.cuentas.guardar_contrasena(
            objetivo.id, self.contrasenas.hashear(temporal), temporal=True, ahora=ahora
        )
        self.accesos.registrar_accion(
            accion=AccionDeCuenta.RESTABLECIMIENTO_CONTRASENA,
            usuario_objetivo_id=objetivo.id,
            hecha_por_id=actor.id,
            momento=ahora,
        )
        return ContrasenaRestablecida(correo=objetivo.correo, temporal=temporal)


@dataclass(frozen=True, slots=True)
class DesbloquearCuenta:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    reloj: Reloj

    def __call__(self, actor: Actor, usuario_id: str) -> None:
        exigir_administrador(actor)
        objetivo = self.cuentas.por_id(usuario_id)
        if objetivo is None:
            raise CuentaNoDisponible
        self.cuentas.guardar_conteo(objetivo.id, 0, None)
        self.cuentas.guardar_conteo_codigo(objetivo.id, 0, None)
        self.accesos.registrar_accion(
            accion=AccionDeCuenta.DESBLOQUEO,
            usuario_objetivo_id=objetivo.id,
            hecha_por_id=actor.id,
            momento=self.reloj.ahora(),
        )
