"""Reiniciar el segundo factor (y; DISENO D.3.10).

El Administrador lo hace cuando un usuario perdio su dispositivo. Borra el segundo factor (el
registro anterior ya no sirve) y cambia el sello de sesion: se cierran todas sus sesiones y
cualquier etapa pendiente. En su siguiente ingreso el usuario se enrola de nuevo. Queda en el
registro de acciones, sin el secreto.

 La pantalla de la gestion de usuarios lo ofrece al Administrador. El evento
`SegundoFactorReiniciado` sale al bus con el registro de la accion.

Permisos (D.5.6): solo un Administrador, y NADIE reinicia el segundo factor de su propia cuenta de
Administrador: lo hace otro Administrador.
"""

from dataclasses import dataclass

from identidad.aplicacion.errores import CuentaNoDisponible, PermisoDenegado, RequiereSegundoFactor
from identidad.aplicacion.permisos import exigir_administrador, exigir_otro_administrador
from identidad.aplicacion.puertos import (
    RegistroDeAccesos,
    Reloj,
    RepositorioCuentas,
    VerificadorSegundoFactor,
)
from identidad.dominio.acceso import AccionDeCuenta
from nucleo.actor import Actor

__all__ = ["PermisoDenegado", "ReiniciarSegundoFactor"]  # `PermisoDenegado` vive en `errores`


@dataclass(frozen=True, slots=True)
class ReiniciarSegundoFactor:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    reloj: Reloj
    verificador: VerificadorSegundoFactor | None = None

    def __call__(self, actor: Actor, usuario_objetivo_id: str) -> bool:
        """Devuelve si el usuario tenia un segundo factor que se borro."""
        exigir_administrador(actor)
        objetivo = self.cuentas.por_id(usuario_objetivo_id)
        if objetivo is None:
            raise CuentaNoDisponible
        exigir_otro_administrador(actor, objetivo)
        if self.verificador is None:
            # Sin adaptador no hay nada que borrar: no se finge que se reinicio.
            raise RequiereSegundoFactor
        habia = self.verificador.reiniciar(objetivo.id)
        self.cuentas.rotar_sello(objetivo.id)
        # Un reinicio deja el contador del codigo en cero: el usuario empieza de nuevo.
        self.cuentas.guardar_conteo_codigo(objetivo.id, 0, objetivo.bloqueada_hasta)
        self.accesos.registrar_accion(
            accion=AccionDeCuenta.REINICIO_SEGUNDO_FACTOR,
            usuario_objetivo_id=objetivo.id,
            hecha_por_id=actor.id,
            momento=self.reloj.ahora(),
        )
        return habia
