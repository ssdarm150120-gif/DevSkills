"""Pantallas de gestion de usuarios para el Administrador (DISENO D.5.4).

Lista, alta, edicion de roles, desactivar y reactivar, restablecer la contrasena, reiniciar el
segundo factor y desbloquear. Son
adaptadores delgados: leen el formulario, llaman al caso de uso y traducen el resultado. TODA regla
(quien puede, que se valida, que se registra) vive en `aplicacion/`: pedir una ruta a mano con otro
rol no cambia nada porque cada caso de uso exige el rol Administrador (D.5.6).

Todas las acciones son POST con CSRF y las respuestas llevan `Cache-Control: no-store`
(`never_cache`).
La contrasena temporal se muestra UNA sola vez, en la respuesta del propio POST: no se guarda en la
sesion, ni en un mensaje, ni en la bitacora, y recargar la pagina no la vuelve a mostrar.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any
from uuid import UUID

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from identidad.adaptadores.entrada import composicion
from identidad.adaptadores.salida.modelos import Usuario
from identidad.aplicacion.errores import (
    ConflictoDeUsuario,
    CuentaNoDisponible,
    PermisoDenegado,
    RequiereSegundoFactor,
)
from identidad.dominio.usuarios import UsuarioInvalido
from nucleo.actor import Actor

MENSAJE_PANTALLA_CERRADA = "No tienes permiso para esta pantalla"


def _actor(request: HttpRequest) -> Actor:
    return request.actor  # type: ignore[attr-defined,no-any-return]


def _administracion(vista: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Sin cache, con sesion completa y con los errores de permiso traducidos a una pagina.

    `login_required` deja pasar solo a quien tiene sesion completa; el permiso real lo exige el caso
    de uso (D.5.6). Un usuario sin el rol ve la pagina de "acceso denegado" (403), no la pantalla.
    """

    @wraps(vista)
    def envuelta(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            return vista(request, *args, **kwargs)
        except PermisoDenegado as error:
            return render(
                request, "identidad/acceso_denegado.html", {"motivo": error.motivo}, status=403
            )
        except CuentaNoDisponible:
            raise Http404("No existe ese usuario") from None

    return never_cache(login_required(redirect_field_name=None)(envuelta))


def _formulario_de_usuario(request: HttpRequest) -> dict[str, Any]:
    """Lo capturado en el formulario de alta o de edicion, para volver a mostrarlo si hay error."""
    return {
        "correo": request.POST.get("correo", ""),
        "nombre": request.POST.get("nombre", ""),
        "roles": request.POST.getlist("roles"),
    }


@_administracion
@require_safe
def lista_usuarios(request: HttpRequest) -> HttpResponse:
    consulta = composicion.consultar_usuarios()
    actor = _actor(request)
    contexto = {
        "filas": consulta.listar(actor),
        # Con un solo Administrador activo, nadie podria recuperar su cuenta.
        "solo_un_administrador": consulta.solo_un_administrador(actor),
    }
    return render(request, "identidad/usuarios_lista.html", contexto)


@_administracion
@require_http_methods(["GET", "HEAD", "POST"])
def nuevo_usuario(request: HttpRequest) -> HttpResponse:
    actor = _actor(request)
    consulta = composicion.consultar_usuarios()
    contexto: dict[str, Any] = {
        "catalogo": consulta.catalogo_de_roles(actor),
        "formulario": {"roles": []},
        "errores": [],
    }
    if request.method in ("GET", "HEAD"):
        return render(request, "identidad/usuario_nuevo.html", contexto)

    formulario = _formulario_de_usuario(request)
    contexto["formulario"] = formulario
    try:
        nuevo = composicion.crear_usuario()(
            actor,
            correo=formulario["correo"],
            nombre=formulario["nombre"],
            roles=formulario["roles"],
        )
    except (UsuarioInvalido, ConflictoDeUsuario) as error:
        contexto["errores"] = [str(error)]
        return render(request, "identidad/usuario_nuevo.html", contexto, status=422)
    # La contrasena temporal sale SOLO en esta respuesta (D.3.10): no se redirige ni se guarda.
    return render(
        request,
        "identidad/contrasena_temporal.html",
        {
            "usuario_id": nuevo.id,
            "correo": nuevo.correo,
            "temporal": nuevo.temporal,
            "motivo": "alta",
        },
    )


@_administracion
@require_safe
def detalle_usuario(request: HttpRequest, usuario_id: UUID) -> HttpResponse:
    detalle = composicion.consultar_usuarios().detalle(_actor(request), str(usuario_id))
    roles_del_usuario = set(detalle.cuenta.roles)
    return render(
        request,
        "identidad/usuario_detalle.html",
        {
            "d": detalle,
            "roles_del_usuario": roles_del_usuario,
        },
    )


def _volver_al_detalle(request: HttpRequest, usuario_id: UUID) -> HttpResponse:
    return redirect("detalle_usuario", usuario_id=usuario_id)


def _ejecutar(
    request: HttpRequest,
    usuario_id: UUID,
    accion: Callable[[Actor], str],
) -> HttpResponse:
    """Corre una accion del Administrador; avisa el resultado y vuelve al detalle del usuario.

    La accion devuelve el aviso de exito. Los errores de reglas (datos invalidos, choques con otro
    usuario) se muestran como aviso de error; el permiso lo atiende `_administracion`.
    """
    try:
        resultado = accion(_actor(request))
    except (UsuarioInvalido, ConflictoDeUsuario) as error:
        messages.error(request, str(error))
    except RequiereSegundoFactor:
        messages.error(request, "El segundo factor no está disponible en este momento")
    else:
        messages.success(request, resultado)
    return _volver_al_detalle(request, usuario_id)


@_administracion
@require_POST
def editar_usuario(request: HttpRequest, usuario_id: UUID) -> HttpResponse:
    formulario = _formulario_de_usuario(request)

    def accion(actor: Actor) -> str:
        resultado = composicion.editar_usuario()(
            actor,
            str(usuario_id),
            nombre=formulario["nombre"],
            roles=formulario["roles"],
        )
        if resultado.roles_cambiados and str(usuario_id) == actor.id:
            # Cambiaste tus propios roles: se rota tu sello, pero esta sesion se vuelve a firmar
            # para que no te saque en medio de la gestion. Tus demas sesiones si se cierran.
            update_session_auth_hash(request, Usuario.objects.get(pk=usuario_id))
            return (
                "Guardamos los cambios. Tus demás sesiones se cerraron y los roles aplican al "
                "ingresar"
            )
        if resultado.roles_cambiados:
            return (
                "Guardamos los cambios. Sus sesiones se cerraron y aplicará sus roles al ingresar"
            )
        return "Guardamos los cambios" if resultado.datos_cambiados else "No había cambios"

    return _ejecutar(request, usuario_id, accion)


@_administracion
@require_POST
def desactivar_usuario(request: HttpRequest, usuario_id: UUID) -> HttpResponse:
    def accion(actor: Actor) -> str:
        cambio = composicion.desactivar_usuario()(actor, str(usuario_id))
        return (
            "Desactivamos al usuario: ya no puede entrar y sus sesiones se cerraron"
            if cambio
            else "El usuario ya estaba desactivado"
        )

    return _ejecutar(request, usuario_id, accion)


@_administracion
@require_POST
def reactivar_usuario(request: HttpRequest, usuario_id: UUID) -> HttpResponse:
    def accion(actor: Actor) -> str:
        cambio = composicion.reactivar_usuario()(actor, str(usuario_id))
        return "Reactivamos al usuario" if cambio else "El usuario ya estaba activo"

    return _ejecutar(request, usuario_id, accion)


@_administracion
@require_POST
def restablecer_contrasena(request: HttpRequest, usuario_id: UUID) -> HttpResponse:
    actor = _actor(request)
    restablecida = composicion.restablecer_contrasena()(actor, str(usuario_id))
    # Como en el alta: la contrasena temporal sale solo en esta respuesta.
    return render(
        request,
        "identidad/contrasena_temporal.html",
        {
            "usuario_id": str(usuario_id),
            "correo": restablecida.correo,
            "temporal": restablecida.temporal,
            "motivo": "restablecimiento",
        },
    )


@_administracion
@require_POST
def reiniciar_segundo_factor(request: HttpRequest, usuario_id: UUID) -> HttpResponse:
    def accion(actor: Actor) -> str:
        habia = composicion.reiniciar_segundo_factor()(actor, str(usuario_id))
        if habia:
            return "Reiniciamos su segundo factor: se enrolará de nuevo en su siguiente ingreso"
        return "No tenía un segundo factor registrado; se enrolará en su siguiente ingreso"

    return _ejecutar(request, usuario_id, accion)


@_administracion
@require_POST
def desbloquear_cuenta(request: HttpRequest, usuario_id: UUID) -> HttpResponse:
    def accion(actor: Actor) -> str:
        composicion.desbloquear_cuenta()(actor, str(usuario_id))
        return "Desbloqueamos la cuenta: ya puede ingresar"

    return _ejecutar(request, usuario_id, accion)
