"""Ingreso y bloqueo de la cuenta (DISENO D.3.10). Python puro.

Reglas: 5 fallos seguidos de contrasena, o 5 seguidos de codigo (contadores separados), bloquean la
cuenta 15 minutos. El bloqueo es por cuenta, sin importar el origen. Un fallo dentro del
bloqueo no lo extiende, y cumplido el bloqueo el conteo empieza de cero. El reloj no se lee aqui:
llega como argumento.
"""

from datetime import datetime, timedelta
from enum import StrEnum

MAXIMO_DE_FALLOS = 5
# Tope absoluto de la sesion por defecto; el valor real es configurable.
DURACION_MAXIMA_SESION = timedelta(hours=12)
# Vigencia de cada etapa pendiente del ingreso (cambio obligatorio, enrolamiento y codigo).
VIGENCIA_ETAPA_PENDIENTE = timedelta(minutes=15)
DURACION_BLOQUEO = timedelta(minutes=15)
LONGITUD_MAXIMA_CORREO = 254

# Mensajes al usuario (SRS). El primero es el MISMO en todos los fallos.
MENSAJE_CREDENCIALES_INCORRECTAS = "Correo o contraseña incorrectos"
MENSAJE_REQUIERE_SEGUNDO_FACTOR = "Tu rol requiere un segundo factor para ingresar"
# Segundo factor. Quien llega a pedir el codigo ya dio su contrasena correcta, asi que ahi
# si se puede decir que la cuenta quedo bloqueada: no revela nada a quien no la conoce.
MENSAJE_CODIGO_INCORRECTO = (
    "El código no es correcto. Revisa que sea el vigente e inténtalo de nuevo"
)
MENSAJE_CODIGO_BLOQUEADO = "Demasiados códigos incorrectos. Tu cuenta quedó bloqueada 15 minutos"


class Etapa(StrEnum):
    """Resultado del paso de contrasena en la maquina del ingreso (D.3.10)."""

    FALLO = "fallo"
    RECHAZADO_POR_SEGUNDO_FACTOR = "rechazado_por_segundo_factor"
    CAMBIO_OBLIGATORIO = "cambio_obligatorio"
    ENROLAMIENTO_PENDIENTE = "enrolamiento_pendiente"  # rol sensible sin segundo factor
    CODIGO_PENDIENTE = "codigo_pendiente"  # rol sensible con segundo factor confirmado
    SESION_COMPLETA = "sesion_completa"


class Intencion(StrEnum):
    """Para que se define la contrasena: lo dice quien llama, no se deduce del estado."""

    CAMBIO_OBLIGATORIO = "cambio_obligatorio"  # contrasena temporal: no pide la actual
    CAMBIO_PROPIO = "cambio_propio"  # siempre pide la actual


class Factor(StrEnum):
    CONTRASENA = "contrasena"
    CODIGO = "codigo"  # segundo factor


class Resultado(StrEnum):
    CORRECTO = "correcto"
    FALLIDO = "fallido"


class Motivo(StrEnum):
    """Motivo REAL del intento: se guarda aunque al usuario se le muestre un mensaje unico."""

    CORRECTO = "correcto"
    CORREO_INEXISTENTE = "correo_inexistente"
    CONTRASENA_INCORRECTA = "contrasena_incorrecta"
    USUARIO_DESACTIVADO = "usuario_desactivado"
    CUENTA_BLOQUEADA = "cuenta_bloqueada"
    REQUIERE_SEGUNDO_FACTOR = "requiere_segundo_factor"
    CAMBIO_DE_CONTRASENA_INCORRECTA = "cambio_de_contrasena_incorrecta"
    CODIGO_INVALIDO = "codigo_invalido"  # no coincide, o esta mal escrito
    CODIGO_REPETIDO = "codigo_repetido"  # ya se uso: no se acepta dos veces


class AccionDeCuenta(StrEnum):
    """Acciones sobre una cuenta que se registran. Nunca guardan la contrasena."""

    ALTA = "alta"
    CAMBIO_DE_CONTRASENA = "cambio_de_contrasena"
    BLOQUEO = "bloqueo"
    ENROLAMIENTO_SEGUNDO_FACTOR = "enrolamiento_segundo_factor"
    REINICIO_SEGUNDO_FACTOR = "reinicio_segundo_factor"
    # Ingreso completado: de aqui sale `SesionIniciada`.
    SESION_INICIADA = "sesion_iniciada"
    # Cierre de sesion con su motivo (D.3.10). `inactividad` y `sello` no se registran ni se emiten:
    # la sesion ya no existe cuando se detecta y no se sabe de quien era (decide el Product Owner).
    SESION_CERRADA_SALIDA = "sesion_cerrada_salida"
    SESION_CERRADA_TOPE_ABSOLUTO = "sesion_cerrada_tope_absoluto"
    # Gestion de usuarios: las hace el Administrador sobre otra cuenta.
    RESTABLECIMIENTO_CONTRASENA = "restablecimiento_contrasena"  # otra temporal
    DESBLOQUEO = "desbloqueo"
    DESACTIVACION = "desactivacion"  # el usuario nunca se borra
    REACTIVACION = "reactivacion"
    CAMBIO_DE_ROLES = "cambio_de_roles"
    CAMBIO_DE_USUARIO = "cambio_de_usuario"  # datos del usuario (nombre)


def normalizar_correo(correo: str) -> str:
    """El correo es unico sin distinguir mayusculas: se compara en minusculas.

    No recorta: un correo demasiado largo no se trunca (coincidiria con otro), se rechaza con
    `correo_valido`.
    """
    return correo.strip().lower()


def correo_valido(correo_normalizado: str) -> bool:
    """Un correo con caracteres de control (NUL incluido), vacio o de mas de 254 caracteres no
    puede existir: se trata como "no existe", con el mismo mensaje y el mismo tiempo."""
    return 0 < len(correo_normalizado) <= LONGITUD_MAXIMA_CORREO and not any(
        ord(c) < 32 or ord(c) == 127 for c in correo_normalizado
    )


def sesion_vencida(
    iniciada_en: datetime | None,
    ahora: datetime,
    duracion_maxima: timedelta = DURACION_MAXIMA_SESION,
) -> bool:
    """Verdadero si la sesion paso el tope absoluto (12 horas por defecto) desde el ingreso.

    Sin marca de ingreso (sesion anterior a esta regla o manipulada) cuenta como vencida.
    """
    return iniciada_en is None or ahora - iniciada_en >= duracion_maxima


def etapa_pendiente_vencida(creada_en: datetime | None, ahora: datetime) -> bool:
    """Verdadero si la etapa pendiente del ingreso ya paso su vigencia de 15 minutos."""
    return creada_en is None or ahora - creada_en >= VIGENCIA_ETAPA_PENDIENTE


def esta_bloqueada(bloqueada_hasta: datetime | None, ahora: datetime) -> bool:
    return bloqueada_hasta is not None and ahora < bloqueada_hasta


def tras_fallo(
    fallos: int, bloqueada_hasta: datetime | None, ahora: datetime
) -> tuple[int, datetime | None]:
    """Conteo y bloqueo resultantes de un fallo (de contrasena o de codigo) en `ahora`.

    Devuelve `(fallos, bloqueada_hasta)`. Al quinto fallo seguido fija el bloqueo y el conteo
    vuelve a cero, para que el siguiente ciclo empiece limpio cuando el bloqueo termine.
    """
    if esta_bloqueada(bloqueada_hasta, ahora):
        return fallos, bloqueada_hasta
    # Bloqueo ya cumplido: se parte de cero (un fallo viejo no cuenta para el nuevo ciclo).
    previos = 0 if bloqueada_hasta is not None else fallos
    nuevos = previos + 1
    if nuevos >= MAXIMO_DE_FALLOS:
        return 0, ahora + DURACION_BLOQUEO
    return nuevos, None
