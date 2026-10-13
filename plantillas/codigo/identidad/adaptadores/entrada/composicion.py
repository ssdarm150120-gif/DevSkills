"""Arma los casos de uso de `identidad` con sus adaptadores (raiz de composicion del modulo)."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from django.db import transaction

from identidad.adaptadores.salida.avisos_reuso import (
    AvisosDeReusoDjango,
    ZonaHorariaDeConfiguracion,
)
from identidad.adaptadores.salida.contrasenas import ServicioContrasenasDjango
from identidad.adaptadores.salida.registro import registro_de_accesos
from identidad.adaptadores.salida.repositorios import (
    CatalogoDeRolesDjango,
    RelojDelSistema,
    RepositorioCuentasDjango,
)
from identidad.aplicacion.avisos_pendientes import AvisosPendientes
from identidad.aplicacion.confirmar_codigo import ConfirmarCodigo
from identidad.aplicacion.consultar_usuarios import ConsultarUsuarios
from identidad.aplicacion.crear_administrador import CrearAdministrador
from identidad.aplicacion.crear_usuario import CrearUsuario, UsuarioCreado
from identidad.aplicacion.definir_contrasena import DefinirContrasena
from identidad.aplicacion.editar_usuario import EditarUsuario, ResultadoEdicion
from identidad.aplicacion.estado_de_usuario import DesactivarUsuario, ReactivarUsuario
from identidad.aplicacion.iniciar_enrolamiento import IniciarEnrolamiento
from identidad.aplicacion.iniciar_sesion import IniciarSesion
from identidad.aplicacion.puertos import VerificadorSegundoFactor
from identidad.aplicacion.recuperar_acceso import (
    ContrasenaRestablecida,
    DesbloquearCuenta,
    RestablecerContrasena,
)
from identidad.aplicacion.reiniciar_segundo_factor import ReiniciarSegundoFactor
from nucleo.actor import Actor
from nucleo.puertos.registro import PuertoSinAdaptador, obtener


def _verificador_del_segundo_factor() -> VerificadorSegundoFactor | None:
    """El adaptador del segundo factor, o `None` si no esta conectado: falla cerrado.

    Es una red de seguridad: `configuracion` lo conecta al arrancar, pero si por un error de
    configuracion no estuviera, un rol sensible NO entra solo con la contrasena.
    """
    try:
        return obtener(VerificadorSegundoFactor)
    except PuertoSinAdaptador:
        return None


def iniciar_sesion() -> IniciarSesion:
    return IniciarSesion(
        RepositorioCuentasDjango(),
        registro_de_accesos(),
        ServicioContrasenasDjango(),
        RelojDelSistema(),
        _verificador_del_segundo_factor(),
    )


def definir_contrasena() -> DefinirContrasena:
    return DefinirContrasena(
        RepositorioCuentasDjango(),
        registro_de_accesos(),
        ServicioContrasenasDjango(),
        RelojDelSistema(),
        _verificador_del_segundo_factor(),
    )


def iniciar_enrolamiento() -> IniciarEnrolamiento:
    return IniciarEnrolamiento(
        RepositorioCuentasDjango(),
        registro_de_accesos(),
        RelojDelSistema(),
        _verificador_del_segundo_factor(),
    )


def confirmar_codigo() -> ConfirmarCodigo:
    return ConfirmarCodigo(
        RepositorioCuentasDjango(),
        registro_de_accesos(),
        RelojDelSistema(),
        _verificador_del_segundo_factor(),
    )


@dataclass(frozen=True, slots=True)
class ReinicioAtomico:
    """El reinicio del segundo factor dentro de UNA transaccion (unidad de trabajo).

    El caso de uso hace cuatro escrituras (borrar el factor, rotar el sello, poner el contador en
    cero y registrar la accion): o quedan todas o ninguna. Si una falla, no se queda a medias (por
    ejemplo, sin registro de auditoria o con el sello rotado y el factor aun vigente). La
    transaccion vive aqui, en la composicion, para que `aplicacion/` siga sin importar Django.
    """

    caso: ReiniciarSegundoFactor

    def __call__(self, actor: Actor, usuario_objetivo_id: str) -> bool:
        with transaction.atomic():
            return self.caso(actor, usuario_objetivo_id)


def reiniciar_segundo_factor() -> ReinicioAtomico:
    return ReinicioAtomico(
        ReiniciarSegundoFactor(
            RepositorioCuentasDjango(),
            registro_de_accesos(),
            RelojDelSistema(),
            _verificador_del_segundo_factor(),
        )
    )


def crear_administrador() -> CrearAdministrador:
    return CrearAdministrador(
        RepositorioCuentasDjango(),
        registro_de_accesos(),
        ServicioContrasenasDjango(),
        RelojDelSistema(),
    )


def _atomico[**P, R](caso: Callable[P, R]) -> Callable[P, R]:
    """Corre un caso de uso de la gestion de usuarios dentro de UNA transaccion (unidad de trabajo).

    Cada accion del Administrador hace varias escrituras (el cambio, el sello de sesion, el registro
    de la accion): o quedan todas o ninguna. La transaccion vive aqui, en la composicion, para que
    `aplicacion/` siga sin importar Django. Conserva la firma del caso de uso (`ParamSpec`) y cada
    fabrica la declara con su tipo: mypy revisa los argumentos y el resultado de cada llamada.
    """

    def en_transaccion(*args: P.args, **kwargs: P.kwargs) -> R:
        with transaction.atomic():
            return caso(*args, **kwargs)

    return en_transaccion


class CasoCrearUsuario(Protocol):
    def __call__(
        self,
        actor: Actor,
        *,
        correo: str,
        nombre: str,
        roles: Iterable[str],
    ) -> UsuarioCreado: ...


class CasoEditarUsuario(Protocol):
    def __call__(
        self,
        actor: Actor,
        usuario_id: str,
        *,
        nombre: str,
        roles: Iterable[str],
    ) -> ResultadoEdicion: ...


def crear_usuario() -> CasoCrearUsuario:
    return _atomico(
        CrearUsuario(
            RepositorioCuentasDjango(),
            registro_de_accesos(),
            ServicioContrasenasDjango(),
            RelojDelSistema(),
        )
    )


def editar_usuario() -> CasoEditarUsuario:
    return _atomico(
        EditarUsuario(
            RepositorioCuentasDjango(),
            registro_de_accesos(),
            RelojDelSistema(),
        )
    )


def desactivar_usuario() -> Callable[[Actor, str], bool]:
    return _atomico(
        DesactivarUsuario(
            RepositorioCuentasDjango(),
            registro_de_accesos(),
            RelojDelSistema(),
        )
    )


def reactivar_usuario() -> Callable[[Actor, str], bool]:
    return _atomico(
        ReactivarUsuario(RepositorioCuentasDjango(), registro_de_accesos(), RelojDelSistema())
    )


def restablecer_contrasena() -> Callable[[Actor, str], ContrasenaRestablecida]:
    return _atomico(
        RestablecerContrasena(
            RepositorioCuentasDjango(),
            registro_de_accesos(),
            ServicioContrasenasDjango(),
            RelojDelSistema(),
        )
    )


def desbloquear_cuenta() -> Callable[[Actor, str], None]:
    return _atomico(
        DesbloquearCuenta(RepositorioCuentasDjango(), registro_de_accesos(), RelojDelSistema())
    )


def consultar_usuarios() -> ConsultarUsuarios:
    return ConsultarUsuarios(
        RepositorioCuentasDjango(),
        CatalogoDeRolesDjango(),
        RelojDelSistema(),
        _verificador_del_segundo_factor(),
    )


def avisos_pendientes() -> AvisosPendientes:
    """. La transaccion es de quien lo llama: la vista la abre alrededor del caso y de la
    respuesta, para que el aviso no quede marcado como visto si la pantalla no se arma."""
    return AvisosPendientes(AvisosDeReusoDjango(), ZonaHorariaDeConfiguracion())
