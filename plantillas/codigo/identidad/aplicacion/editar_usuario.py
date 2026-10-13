"""CU de edicion de usuario y cambio de roles (HU de gestion de usuarios y roles).

El Administrador cambia el nombre y los roles. El correo no se edita: es el identificador de
ingreso.

Un CAMBIO DE ROLES cambia el sello de sesion del usuario (D.3.10): sus sesiones abiertas caen y su
siguiente ingreso aplica los roles nuevos; si gana un rol que exige segundo factor, se enrola en ese
ingreso.

Reglas heredadas del proyecto de referencia: un Administrador SI puede cambiar sus propios roles
(queda en el registro), pero no puede quitarse el rol Administrador; y siempre queda al menos un
Administrador activo, aunque dos se degraden a la vez (se bloquean las filas de los Administradores
activos dentro de la transaccion).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from identidad.aplicacion.errores import CuentaNoDisponible, PermisoDenegado
from identidad.aplicacion.permisos import exigir_administrador, exigir_que_quede_administrador
from identidad.aplicacion.puertos import RegistroDeAccesos, Reloj, RepositorioCuentas
from identidad.dominio.acceso import AccionDeCuenta
from identidad.dominio.roles import ADMINISTRADOR
from identidad.dominio.usuarios import validar_datos
from nucleo.actor import Actor

MENSAJE_NO_QUITARTE_ADMINISTRADOR = (
    "No puedes quitarte el rol Administrador a ti mismo: lo hace otro administrador"
)


@dataclass(frozen=True, slots=True)
class ResultadoEdicion:
    datos_cambiados: bool
    roles_cambiados: bool


@dataclass(frozen=True, slots=True)
class EditarUsuario:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    reloj: Reloj

    def __call__(
        self,
        actor: Actor,
        usuario_id: str,
        *,
        nombre: str,
        roles: Iterable[str],
    ) -> ResultadoEdicion:
        exigir_administrador(actor)
        # Primero las filas de los Administradores (orden estable) y despues la del objetivo: asi
        # dos ediciones simultaneas siempre toman los bloqueos en el mismo orden.
        administradores = self.cuentas.bloquear_administradores_activos()
        objetivo = self.cuentas.por_id(usuario_id)
        if objetivo is None:
            raise CuentaNoDisponible
        datos = validar_datos(correo=objetivo.correo, nombre=nombre, roles=roles)
        pierde_administrador = ADMINISTRADOR in objetivo.roles and ADMINISTRADOR not in datos.roles
        if pierde_administrador and objetivo.id == actor.id:
            raise PermisoDenegado(MENSAJE_NO_QUITARTE_ADMINISTRADOR)
        if pierde_administrador and objetivo.activo:
            exigir_que_quede_administrador(administradores, objetivo.id)

        ahora = self.reloj.ahora()
        campos = [
            campo
            for campo, antes, despues in (("nombre", objetivo.nombre, datos.nombre),)
            if antes != despues
        ]
        if campos:
            self.cuentas.guardar_datos(objetivo.id, nombre=datos.nombre)
            self.accesos.registrar_accion(
                accion=AccionDeCuenta.CAMBIO_DE_USUARIO,
                usuario_objetivo_id=objetivo.id,
                hecha_por_id=actor.id,
                momento=ahora,
                detalle={"campos": campos},
            )

        roles_cambiados = datos.roles != objetivo.roles
        if roles_cambiados:
            self.cuentas.guardar_roles(objetivo.id, datos.roles, asignado_por=actor.id, ahora=ahora)
            # Sus sesiones caen y el siguiente ingreso aplica los roles nuevos (D.3.10).
            self.cuentas.rotar_sello(objetivo.id)
            self.accesos.registrar_accion(
                accion=AccionDeCuenta.CAMBIO_DE_ROLES,
                usuario_objetivo_id=objetivo.id,
                hecha_por_id=actor.id,
                momento=ahora,
                detalle={"antes": sorted(objetivo.roles), "despues": sorted(datos.roles)},
            )
        return ResultadoEdicion(datos_cambiados=bool(campos), roles_cambiados=roles_cambiados)
