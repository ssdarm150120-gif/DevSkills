"""Vistas de `identidad` (DISENO D.5.4): ingresar, cambio obligatorio, enrolamiento, codigo, cambiar
la propia contrasena y salir.

Son adaptadores delgados: leen el formulario, llaman al caso de uso y traducen la etapa a una
respuesta. Toda la regla (bloqueo, mensaje unico, falla cerrado) vive en `aplicacion/`.
"""

import ipaddress
from collections.abc import Callable
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from identidad.adaptadores.entrada import composicion
from identidad.adaptadores.entrada.codigo_qr import trazo_del_qr
from identidad.adaptadores.entrada.middleware import (
    CLAVE_ETAPA,
    CLAVE_INICIADA_EN,
    RUTA_CAMBIAR_CONTRASENA,
    RUTA_CAMBIO_OBLIGATORIO,
    RUTA_INGRESAR,
    RUTA_POR_ETAPA,
)
from identidad.adaptadores.salida.modelos import Usuario
from identidad.adaptadores.salida.registro import registro_de_accesos
from identidad.adaptadores.salida.repositorios import RelojDelSistema
from identidad.aplicacion.confirmar_codigo import ResultadoConfirmacion
from identidad.aplicacion.definir_contrasena import (
    MENSAJE_ACTUAL_INCORRECTA,
    ContrasenaActualIncorrecta,
    ContrasenaInvalida,
    ResultadoDefinicion,
)
from identidad.aplicacion.errores import (
    CuentaBloqueada,
    CuentaNoDisponible,
    EtapaInvalida,
    RequiereSegundoFactor,
)
from identidad.dominio.acceso import (
    MENSAJE_CODIGO_BLOQUEADO,
    MENSAJE_CODIGO_INCORRECTO,
    MENSAJE_CREDENCIALES_INCORRECTAS,
    MENSAJE_REQUIERE_SEGUNDO_FACTOR,
    AccionDeCuenta,
    Etapa,
    Intencion,
    correo_valido,
    normalizar_correo,
)
from nucleo.actor import Actor
from nucleo.permisos import DESCRIPCIONES, Capacidad, capacidades_de

MENSAJE_NO_COINCIDEN = "La confirmación no coincide con la contraseña nueva"
MENSAJE_ETAPA_VENCIDA = "Tu ingreso ya no es válido. Ingresa de nuevo."
MENSAJE_CAMBIADA = "Tu contraseña cambió. Cerramos tus demás sesiones."
RUTA_ESTILOS_ARCHIVO = Path(__file__).parent / "estilos" / "identidad.css"
# Longitud maxima que se lee de un codigo capturado (el valido mide 6): lo demas es basura.
LARGO_MAXIMO_CODIGO = 64
# Lo que invalida una etapa pendiente: la cuenta cambio mientras estaba abierta, o ya no se puede.
_ETAPA_ROTA = (CuentaNoDisponible, EtapaInvalida, RequiereSegundoFactor, CuentaBloqueada)


def _ip_del_cliente(request: HttpRequest) -> str:
    """IP de quien hace la peticion. Detras de nginx viene en `X-Real-IP` (la fija nginx)."""
    candidata = request.META.get("REMOTE_ADDR", "")
    if getattr(settings, "APP_IP_DESDE_PROXY", False):
        candidata = request.META.get("HTTP_X_REAL_IP", candidata)
    try:
        return str(ipaddress.ip_address(candidata))
    except ValueError:
        return "0.0.0.0"  # noqa: S104  # nosec B104  # marcador de "origen desconocido", no un bind


def _abrir_sesion(request: HttpRequest, usuario: Usuario) -> None:
    """Completa el ingreso: rota la sesion y guarda cuando empezo (para el tope absoluto)."""
    login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
    ahora = RelojDelSistema().ahora()
    request.session[CLAVE_INICIADA_EN] = ahora.isoformat()
    registro_de_accesos().registrar_accion(
        accion=AccionDeCuenta.SESION_INICIADA,
        usuario_objetivo_id=str(usuario.pk),
        hecha_por_id=str(usuario.pk),
        momento=ahora,
    )


def _iniciar_etapa(
    request: HttpRequest, etapa: Etapa, usuario_id: str, sello: str | None
) -> HttpResponse:
    """Deja el ingreso en una etapa pendiente (D.3.10): sin `Actor` y con vigencia de 15 minutos."""
    request.session.cycle_key()
    request.session[CLAVE_ETAPA] = {
        "etapa": etapa.value,
        "usuario_id": usuario_id,
        "sello": sello,
        "creada_en": RelojDelSistema().ahora().isoformat(),
    }
    return redirect(RUTA_POR_ETAPA[etapa.value])


def _continuar(
    request: HttpRequest, usuario_id: str, etapa: Etapa, sello: str | None
) -> HttpResponse:
    """Abre la sesion si ya no falta nada; si no, deja la siguiente etapa pendiente."""
    if etapa is Etapa.SESION_COMPLETA:
        request.session.pop(CLAVE_ETAPA, None)
        _abrir_sesion(request, Usuario.objects.get(pk=usuario_id))
        return redirect(settings.LOGIN_REDIRECT_URL)
    return _iniciar_etapa(request, etapa, usuario_id, sello)


def _en_transaccion[T](accion: Callable[[], T]) -> tuple[T | None, Exception | None]:
    """Corre `accion` en una transaccion; devuelve `(resultado, etapa_rota)`.

    Si la etapa se rompio (la cuenta cambio), la excepcion se devuelve DESPUES de cerrar la
    transaccion para que lo que el caso de uso alcanzo a registrar (el intento) se conserve.
    """
    rota: Exception | None = None
    resultado: T | None = None
    with transaction.atomic():
        try:
            resultado = accion()
        except _ETAPA_ROTA as motivo:
            rota = motivo
    return resultado, rota


def _etapa_pendiente(request: HttpRequest, etapa: Etapa) -> dict[str, str] | None:
    pendiente = request.session.get(CLAVE_ETAPA)
    if not pendiente or pendiente.get("etapa") != etapa.value:
        return None
    return dict(pendiente)


def _etapa_rota(request: HttpRequest, motivo: Exception) -> HttpResponse:
    """La cuenta cambio con la etapa abierta: no se abre sesion y hay que ingresar de nuevo."""
    request.session.pop(CLAVE_ETAPA, None)
    if isinstance(motivo, RequiereSegundoFactor):
        error, estado = MENSAJE_REQUIERE_SEGUNDO_FACTOR, 403
    elif isinstance(motivo, CuentaBloqueada):
        error, estado = MENSAJE_CODIGO_BLOQUEADO, 403
    else:
        error, estado = MENSAJE_ETAPA_VENCIDA, 200
    return render(request, "identidad/ingresar.html", {"error": error}, status=estado)


@require_safe
def estilos(request: HttpRequest) -> FileResponse:
    """La CSP estricta (`default-src 'self'`) no admite estilos en linea: va como archivo propio."""
    respuesta = FileResponse(
        RUTA_ESTILOS_ARCHIVO.open("rb"), content_type="text/css; charset=utf-8"
    )
    respuesta["Cache-Control"] = "public, max-age=3600"
    return respuesta


@sensitive_post_parameters("contrasena")
@never_cache
@require_http_methods(["GET", "POST"])
def ingresar(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    if request.method == "GET":
        return render(request, "identidad/ingresar.html")

    correo = request.POST.get("correo", "")
    with transaction.atomic():
        resultado = composicion.iniciar_sesion()(
            correo, request.POST.get("contrasena", ""), ip=_ip_del_cliente(request)
        )
    # Cualquier ingreso nuevo descarta una etapa pendiente anterior.
    request.session.pop(CLAVE_ETAPA, None)

    if resultado.usuario_id and resultado.etapa in (
        Etapa.SESION_COMPLETA,
        Etapa.CAMBIO_OBLIGATORIO,
        Etapa.ENROLAMIENTO_PENDIENTE,
        Etapa.CODIGO_PENDIENTE,
    ):
        return _continuar(request, resultado.usuario_id, resultado.etapa, resultado.sello_sesion)

    # Fallo comun: un solo mensaje. El correo escrito se conserva para reintentar SOLO si es un
    # correo posible; uno invalido (NUL, control, muy largo) no se refleja en la pagina. Se refleja
    # el correo YA normalizado (sin espacios ni caracteres de control en los extremos), el mismo
    # valor que se valido.
    normalizado = normalizar_correo(correo)
    correo_a_mostrar = normalizado if correo_valido(normalizado) else ""
    if resultado.etapa is Etapa.FALLO:
        mensaje, estado = MENSAJE_CREDENCIALES_INCORRECTAS, 200
    else:  # rechazado por segundo factor (falla cerrado)
        mensaje, estado = MENSAJE_REQUIERE_SEGUNDO_FACTOR, 403
    return render(
        request,
        "identidad/ingresar.html",
        {"error": mensaje, "correo": correo_a_mostrar},
        status=estado,
    )


def _definir(
    request: HttpRequest,
    usuario_id: str,
    intencion: Intencion,
    contrasena_actual: str | None = None,
    sello_esperado: str | None = None,
) -> tuple[ResultadoDefinicion | None, list[str]]:
    """Llama al caso de uso; devuelve `(resultado, errores)`: sin resultado, no se cambio nada.

    La transaccion conserva los fallos que el caso de uso registro.
    """
    nueva = request.POST.get("nueva", "")
    if nueva != request.POST.get("confirmar", ""):
        return None, [MENSAJE_NO_COINCIDEN]
    errores: list[str] = []
    resultado: ResultadoDefinicion | None = None
    etapa_rota: EtapaInvalida | RequiereSegundoFactor | None = None
    with transaction.atomic():
        try:
            resultado = composicion.definir_contrasena()(
                usuario_id,
                nueva,
                intencion=intencion,
                contrasena_actual=contrasena_actual,
                sello_esperado=sello_esperado,
                ip=_ip_del_cliente(request),
            )
        except ContrasenaInvalida as error:
            errores = list(error.errores)
        except ContrasenaActualIncorrecta:
            errores = [MENSAJE_ACTUAL_INCORRECTA]
        except CuentaNoDisponible:
            errores = [MENSAJE_CREDENCIALES_INCORRECTAS]
        except (EtapaInvalida, RequiereSegundoFactor) as motivo:
            etapa_rota = (
                motivo  # se vuelve a lanzar FUERA de la transaccion: el intento se conserva
            )
    if etapa_rota is not None:
        raise etapa_rota
    return resultado, errores


@sensitive_post_parameters("nueva", "confirmar")
@never_cache
@require_http_methods(["GET", "POST"])
def contrasena_obligatoria(request: HttpRequest) -> HttpResponse:
    """Etapa `CambioObligatorio`: lo unico que se puede hacer con una contrasena temporal."""
    pendiente = _etapa_pendiente(request, Etapa.CAMBIO_OBLIGATORIO)
    if pendiente is None:
        return redirect(RUTA_INGRESAR)
    contexto = {
        "titulo": "Define tu contraseña nueva",
        "accion": RUTA_CAMBIO_OBLIGATORIO,
    }
    if request.method == "POST":
        try:
            resultado, errores = _definir(
                request,
                pendiente["usuario_id"],
                Intencion.CAMBIO_OBLIGATORIO,
                sello_esperado=pendiente.get("sello"),
            )
        except (EtapaInvalida, RequiereSegundoFactor) as motivo:
            # Mientras la etapa estaba abierta cambio la cuenta (roles, temporal reiniciada...):
            # no se abre sesion y hay que ingresar de nuevo.
            return _etapa_rota(request, motivo)
        if resultado is not None:
            # D.3.10: sigue el enrolamiento, el codigo o, si ya no falta nada, la sesion.
            return _continuar(
                request, pendiente["usuario_id"], resultado.etapa, resultado.sello_sesion
            )
        contexto["errores"] = errores  # type: ignore[assignment]
        return render(request, "identidad/contrasena_obligatoria.html", contexto, status=422)
    return render(request, "identidad/contrasena_obligatoria.html", contexto)


def _pagina_de_enrolamiento(
    request: HttpRequest, pendiente: dict[str, str], errores: list[str], estado: int
) -> HttpResponse:
    """Muestra el QR y la clave (el secreto sale del adaptador, no de la sesion ni de la base)."""
    enrolamiento, rota = _en_transaccion(
        lambda: composicion.iniciar_enrolamiento()(
            pendiente["usuario_id"],
            sello_esperado=pendiente.get("sello"),
            ip=_ip_del_cliente(request),
        )
    )
    if rota is not None or enrolamiento is None:
        return _etapa_rota(request, rota or EtapaInvalida())
    qr = trazo_del_qr(enrolamiento.uri)
    contexto = {
        "qr_trazo": qr.trazo,
        "qr_lado": qr.lado,
        # La clave en grupos de 4 para teclearla sin perderse (la aplicacion ignora los espacios).
        "clave": " ".join(
            enrolamiento.clave[i : i + 4] for i in range(0, len(enrolamiento.clave), 4)
        ),
        "errores": errores,
    }
    return render(request, "identidad/enrolar.html", contexto, status=estado)


def _confirmar(
    request: HttpRequest, pendiente: dict[str, str], *, enrolando: bool
) -> ResultadoConfirmacion | HttpResponse:
    """Comprueba el codigo capturado de la etapa pendiente (enrolamiento o ingreso).

    Devuelve el resultado del caso de uso, o la respuesta de "etapa rota" si la cuenta cambio con la
    etapa abierta. Es lo unico que comparten `enrolar_segundo_factor` y `pedir_codigo`.
    """
    resultado, rota = _en_transaccion(
        lambda: composicion.confirmar_codigo()(
            pendiente["usuario_id"],
            request.POST.get("codigo", "")[:LARGO_MAXIMO_CODIGO],
            sello_esperado=pendiente.get("sello"),
            enrolando=enrolando,
            ip=_ip_del_cliente(request),
        )
    )
    if rota is not None or resultado is None:
        return _etapa_rota(request, rota or EtapaInvalida())
    return resultado


@sensitive_post_parameters("codigo")
@never_cache
@require_http_methods(["GET", "POST"])
def enrolar_segundo_factor(request: HttpRequest) -> HttpResponse:
    """Etapa `EnrolamientoPendiente`: QR y clave; termina al capturar un codigo valido."""
    pendiente = _etapa_pendiente(request, Etapa.ENROLAMIENTO_PENDIENTE)
    if pendiente is None:
        return redirect(RUTA_INGRESAR)
    if request.method == "GET":
        return _pagina_de_enrolamiento(request, pendiente, [], 200)
    resultado = _confirmar(request, pendiente, enrolando=True)
    if isinstance(resultado, HttpResponse):
        return resultado
    if resultado is ResultadoConfirmacion.INCORRECTO:
        return _pagina_de_enrolamiento(request, pendiente, [MENSAJE_CODIGO_INCORRECTO], 422)
    return _terminar_con_codigo(request, pendiente, resultado)


@sensitive_post_parameters("codigo")
@never_cache
@require_http_methods(["GET", "POST"])
def pedir_codigo(request: HttpRequest) -> HttpResponse:
    """Etapa `CodigoPendiente`: el codigo de la aplicacion en cada ingreso."""
    pendiente = _etapa_pendiente(request, Etapa.CODIGO_PENDIENTE)
    if pendiente is None:
        return redirect(RUTA_INGRESAR)
    if request.method == "GET":
        return render(request, "identidad/codigo.html")
    resultado = _confirmar(request, pendiente, enrolando=False)
    if isinstance(resultado, HttpResponse):
        return resultado
    if resultado is ResultadoConfirmacion.INCORRECTO:
        return render(
            request, "identidad/codigo.html", {"errores": [MENSAJE_CODIGO_INCORRECTO]}, status=422
        )
    return _terminar_con_codigo(request, pendiente, resultado)


def _terminar_con_codigo(
    request: HttpRequest, pendiente: dict[str, str], resultado: ResultadoConfirmacion
) -> HttpResponse:
    """Codigo aceptado: se abre la sesion. Cuenta bloqueada: se descarta la etapa."""
    if resultado is ResultadoConfirmacion.BLOQUEADA:
        request.session.pop(CLAVE_ETAPA, None)
        return render(
            request, "identidad/ingresar.html", {"error": MENSAJE_CODIGO_BLOQUEADO}, status=403
        )
    return _continuar(request, pendiente["usuario_id"], Etapa.SESION_COMPLETA, None)


@sensitive_post_parameters("actual", "nueva", "confirmar")
@never_cache
@login_required(redirect_field_name=None)  # sin `?next=`
@require_http_methods(["GET", "POST"])
def cambiar_contrasena(request: HttpRequest) -> HttpResponse:
    """cambiar la propia contrasena (pide la actual y cierra las demas sesiones)."""
    contexto = {
        "titulo": "Cambiar mi contraseña",
        "accion": RUTA_CAMBIAR_CONTRASENA,
    }
    if request.method == "POST":
        resultado, errores = _definir(
            request,
            str(request.user.pk),
            Intencion.CAMBIO_PROPIO,
            contrasena_actual=request.POST.get("actual", ""),
        )
        if resultado is not None:
            # El sello cambio: se vuelve a firmar ESTA sesion y las demas dejan de valer.
            update_session_auth_hash(request, Usuario.objects.get(pk=str(request.user.pk)))
            messages.success(request, MENSAJE_CAMBIADA)
            return redirect("cambiar_contrasena")
        contexto["errores"] = errores  # type: ignore[assignment]
        return render(request, "identidad/contrasena_propia.html", contexto, status=422)
    return render(request, "identidad/contrasena_propia.html", contexto)


@require_POST
def salir(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        registro_de_accesos().registrar_accion(
            accion=AccionDeCuenta.SESION_CERRADA_SALIDA,
            usuario_objetivo_id=str(request.user.pk),
            hecha_por_id=None,
            momento=RelojDelSistema().ahora(),
        )
    logout(request)
    return redirect(RUTA_INGRESAR)


@never_cache
@login_required(redirect_field_name=None)
@require_safe
def inicio(request: HttpRequest) -> HttpResponse:
    """Destino despues de ingresar: tus roles y las colas y acciones que te dan.

    Las capacidades salen de la matriz de permisos de `nucleo`: un usuario con varios roles ve las
    de todos. El enlace de administracion solo aparece con el rol Administrador; ocultarlo no es el
    permiso (cada caso de uso lo exige), solo evita ofrecer lo que no se puede usar.

    Si alguien intento reusar un codigo del segundo factor del usuario, muestra el aviso UNA vez
    La respuesta es `never_cache`: ni el navegador ni un proxy guardan el aviso.
    """
    actor: Actor = request.actor  # type: ignore[attr-defined]
    capacidades = capacidades_de(actor)
    # el aviso por reuso de un codigo se muestra aqui, tras el ingreso completo, y se marca
    # como visto en la misma transaccion que arma la respuesta: si la pantalla falla, no se pierde.
    with transaction.atomic():
        try:
            aviso = composicion.avisos_pendientes()(actor)
        except CuentaNoDisponible:
            # La cuenta desaparecio entre la sesion y esta lectura: el inicio se arma sin aviso y
            # la sesion deja de valer en la siguiente peticion; no es un 500.
            aviso = None
        return render(
            request,
            "identidad/inicio.html",
            {
                "roles": sorted(actor.roles),
                "capacidades": [DESCRIPCIONES[c] for c in Capacidad if c in capacidades],
                "puede_gestionar_usuarios": Capacidad.GESTIONAR_USUARIOS in capacidades,
                "aviso_reuso": aviso.mensaje if aviso else None,
            },
        )
