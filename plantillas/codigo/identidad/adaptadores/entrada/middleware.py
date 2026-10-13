"""Middleware de `identidad`: deja `request.actor` y restringe las etapas del ingreso.

DISENO D.1.3 y D.3.10. Ningun otro modulo importa `identidad`, asi que las vistas de los demas
modulos leen `request.actor` (un `Actor` de `nucleo`) y se lo pasan al caso de uso.

* La sesion guarda SOLO el id del usuario: un cambio de roles o una desactivacion aplican en la
  siguiente peticion, porque aqui se vuelve a leer al usuario y sus roles.
* Sin sesion completa no hay `request.actor` (es `None`).
* Con una etapa del ingreso pendiente (cambio obligatorio de contrasena, enrolamiento o codigo del
  segundo factor) solo se admite la ruta de esa etapa, la salida y las rutas publicas; cualquier
  otra redirige al paso pendiente. La etapa vence a los 15 minutos.
* Tope absoluto de la sesion (12 horas por defecto, `APP_SESION_DURACION_MAXIMA`): se compara
  `iniciada_en` (guardado al COMPLETAR el ingreso) con el reloj en cada peticion, sin depender de
  la cookie. Una sesion sin `iniciada_en` se trata como vencida. Al vencer se destruye la sesion,
  se registra el cierre y se redirige a `/ingresar`. Emite `SesionCerrada` con motivo
  `tope_absoluto` al bus.
"""

from collections.abc import Callable
from datetime import datetime

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from identidad.adaptadores.salida.modelos import Usuario, UsuarioRol
from identidad.adaptadores.salida.registro import registro_de_accesos
from identidad.adaptadores.salida.repositorios import RelojDelSistema
from identidad.dominio.acceso import (
    AccionDeCuenta,
    Etapa,
    etapa_pendiente_vencida,
    sesion_vencida,
)
from nucleo.actor import Actor

CLAVE_ETAPA = "ingreso_pendiente"
# Momento (ISO 8601, con zona) en que se COMPLETO el ingreso; no se guarda en etapas intermedias.
CLAVE_INICIADA_EN = "iniciada_en"

RUTA_INGRESAR = "/ingresar"
RUTA_CAMBIO_OBLIGATORIO = "/ingresar/contrasena"
RUTA_ENROLAR = "/ingresar/enrolar"
RUTA_CODIGO = "/ingresar/codigo"
RUTA_CAMBIAR_CONTRASENA = "/cuenta/contrasena"
RUTA_SALIR = "/salir"
RUTA_ESTILOS = "/estilos/identidad.css"

# Siempre disponibles, con cualquier etapa.
RUTAS_PUBLICAS = frozenset({"/salud", RUTA_INGRESAR, RUTA_SALIR, RUTA_ESTILOS})
# La unica ruta de cada etapa pendiente (D.5.4): es lo que admite, ademas de las publicas, y a donde
# se redirige cualquier otra peticion.
RUTA_POR_ETAPA: dict[str, str] = {
    Etapa.CAMBIO_OBLIGATORIO.value: RUTA_CAMBIO_OBLIGATORIO,
    Etapa.ENROLAMIENTO_PENDIENTE.value: RUTA_ENROLAR,
    Etapa.CODIGO_PENDIENTE.value: RUTA_CODIGO,
}


def leer_momento(valor: object) -> datetime | None:
    """Lee un momento guardado en la sesion; un valor ausente o ilegible es `None`."""
    if not isinstance(valor, str):
        return None
    try:
        momento = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return momento if momento.tzinfo is not None else None


def actor_de(usuario: Usuario) -> Actor:
    """Construye el `Actor` de un usuario autenticado (roles vigentes en este momento).

    Se lee en cada peticion, asi que un cambio de roles o una desactivacion aplican en la
    siguiente.
    """
    roles = frozenset(UsuarioRol.objects.filter(usuario=usuario).values_list("rol_id", flat=True))
    return Actor.de(str(usuario.id), roles)


class ActorMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.actor = None  # type: ignore[attr-defined]
        ahora = RelojDelSistema().ahora()
        pendiente = request.session.get(CLAVE_ETAPA)
        if pendiente is not None and etapa_pendiente_vencida(
            leer_momento(pendiente.get("creada_en")), ahora
        ):
            request.session.pop(CLAVE_ETAPA, None)  # la etapa expiro: hay que ingresar de nuevo
            pendiente = None
            if request.path not in RUTAS_PUBLICAS:
                return redirect(RUTA_INGRESAR)
        if pendiente is not None:
            propia = RUTA_POR_ETAPA.get(pendiente["etapa"])
            if request.path != propia and request.path not in RUTAS_PUBLICAS:
                return redirect(propia or RUTA_INGRESAR)
        elif request.user.is_authenticated:
            if sesion_vencida(
                leer_momento(request.session.get(CLAVE_INICIADA_EN)),
                ahora,
                settings.APP_SESION_DURACION_MAXIMA,
            ):
                registro_de_accesos().registrar_accion(
                    accion=AccionDeCuenta.SESION_CERRADA_TOPE_ABSOLUTO,
                    usuario_objetivo_id=str(request.user.pk),
                    hecha_por_id=None,
                    momento=ahora,
                )
                logout(request)  # destruye la sesion
                return redirect(RUTA_INGRESAR)
            request.actor = actor_de(request.user)  # type: ignore[attr-defined,arg-type]
        return self.get_response(request)
