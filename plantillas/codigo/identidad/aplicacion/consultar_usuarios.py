"""CU de consulta de usuarios (lista y detalle) para la pantalla de gestion.

Solo el Administrador. Arma lo que la pantalla muestra: estado de cada cuenta (activa, desactivada,
bloqueada, con contrasena temporal), roles con su nombre y estado del segundo factor. El estado
"bloqueada" se deduce de `bloqueada_hasta` con el reloj inyectado (D.3.10).
"""

from dataclasses import dataclass
from enum import StrEnum

from identidad.aplicacion.errores import CuentaNoDisponible
from identidad.aplicacion.permisos import exigir_administrador
from identidad.aplicacion.puertos import (
    CatalogoDeRoles,
    Cuenta,
    Reloj,
    RepositorioCuentas,
    RolDelCatalogo,
    VerificadorSegundoFactor,
)
from identidad.dominio.acceso import esta_bloqueada
from identidad.dominio.roles import ADMINISTRADOR
from nucleo.actor import Actor


class EstadoSegundoFactor(StrEnum):
    NO_APLICA = "no_aplica"  # ningun rol del usuario lo exige
    ENROLADO = "enrolado"
    SIN_ENROLAR = "sin_enrolar"  # se enrola en su siguiente ingreso
    NO_DISPONIBLE = "no_disponible"  # falla cerrado: no podra ingresar


@dataclass(frozen=True, slots=True)
class FilaDeUsuario:
    cuenta: Cuenta
    roles: tuple[str, ...]  # nombres para mostrar, en orden
    bloqueada: bool


@dataclass(frozen=True, slots=True)
class DetalleDeUsuario:
    cuenta: Cuenta
    roles_del_catalogo: tuple[RolDelCatalogo, ...]
    roles_nombres: tuple[str, ...]
    bloqueada: bool
    segundo_factor: EstadoSegundoFactor
    # Nadie restablece ni reinicia lo suyo como Administrador: la pantalla lo oculta.
    es_el_actor: bool
    puede_recuperar: bool


@dataclass(frozen=True, slots=True)
class ConsultarUsuarios:
    cuentas: RepositorioCuentas
    catalogo: CatalogoDeRoles
    reloj: Reloj
    verificador: VerificadorSegundoFactor | None = None

    def catalogo_de_roles(self, actor: Actor) -> tuple[RolDelCatalogo, ...]:
        """Los roles que se pueden asignar (para los formularios de alta y de edicion)."""
        exigir_administrador(actor)
        return tuple(self.catalogo.roles())

    def listar(self, actor: Actor) -> tuple[FilaDeUsuario, ...]:
        exigir_administrador(actor)
        nombres = {rol.codigo: rol.nombre for rol in self.catalogo.roles()}
        ahora = self.reloj.ahora()
        return tuple(
            FilaDeUsuario(
                cuenta=cuenta,
                roles=tuple(nombres.get(rol, rol) for rol in sorted(cuenta.roles)),
                bloqueada=esta_bloqueada(cuenta.bloqueada_hasta, ahora),
            )
            for cuenta in self.cuentas.listar()
        )

    def solo_un_administrador(self, actor: Actor) -> bool:
        """Verdadero si queda un solo Administrador activo: la pantalla recomienda tener dos
        (riesgo de quedarse sin quien recupere el acceso de un Administrador)."""
        exigir_administrador(actor)
        activos = [c for c in self.cuentas.listar() if c.activo and ADMINISTRADOR in c.roles]
        return len(activos) <= 1

    def detalle(self, actor: Actor, usuario_id: str) -> DetalleDeUsuario:
        exigir_administrador(actor)
        cuenta = self.cuentas.por_id(usuario_id)
        if cuenta is None:
            raise CuentaNoDisponible
        catalogo = tuple(self.catalogo.roles())
        nombres = {rol.codigo: rol.nombre for rol in catalogo}
        return DetalleDeUsuario(
            cuenta=cuenta,
            roles_del_catalogo=catalogo,
            roles_nombres=tuple(nombres.get(rol, rol) for rol in sorted(cuenta.roles)),
            bloqueada=esta_bloqueada(cuenta.bloqueada_hasta, self.reloj.ahora()),
            segundo_factor=self._segundo_factor(cuenta),
            es_el_actor=cuenta.id == actor.id,
            puede_recuperar=not (ADMINISTRADOR in cuenta.roles and cuenta.id == actor.id),
        )

    def _segundo_factor(self, cuenta: Cuenta) -> EstadoSegundoFactor:
        if not cuenta.exige_segundo_factor:
            return EstadoSegundoFactor.NO_APLICA
        if self.verificador is None or not self.verificador.disponible_para(cuenta.id):
            return EstadoSegundoFactor.NO_DISPONIBLE
        if self.verificador.esta_enrolado(cuenta.id):
            return EstadoSegundoFactor.ENROLADO
        return EstadoSegundoFactor.SIN_ENROLAR
