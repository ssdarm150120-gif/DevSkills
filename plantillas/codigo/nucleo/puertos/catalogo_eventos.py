"""Catálogo de eventos de dominio (DISENO D.5.2). Python puro.

Es el contrato del bus: un evento que no está aquí no se puede publicar, y uno publicado debe traer
al menos los campos requeridos. Agregar un evento o un campo requerido es un cambio de diseño (va
primero a D.5.2). Los campos de `campos` son el mínimo que el DISENO pide en "Payload principal";
cada módulo emisor puede agregar campos opcionales (solo se agregan, D.5.1 "Evolución").

`motivos_emitidos` y `nota` dejan escrito qué valores de un campo con motivos se emiten HOY, para
que lo que el diseño prevé y aún no se emite quede a la vista y no como un faltante escondido.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EspecificacionEvento:
    emisores: tuple[str, ...]
    campos: tuple[str, ...] = ()
    version_esquema: int = 1
    motivos_emitidos: tuple[str, ...] = ()
    nota: str = ""
    # Grupos de campos de los que debe venir AL MENOS uno (p. ej. `clave` o `seccion`).
    una_de: tuple[tuple[str, ...], ...] = ()


# Quien puede publicar un evento que "el modulo duenio" de algo emite (configuracion, exportacion).
# Por ahora lo puede publicar cualquier modulo (decision del orquestador): se enumeraran los
# duenios cuando existan los modulos que cambian configuracion o exportan.
CUALQUIER_MODULO: tuple[str, ...] = ("*",)

_ACTOR = ("usuario_id", "hecho_por", "motivo")

CATALOGO: dict[str, EspecificacionEvento] = {
    # --- Integraciones y operacion ---
    # Cada modulo que tenga un adaptador hacia un sistema externo se agrega como emisor.
    "ErrorIntegracionRegistrado": EspecificacionEvento(
        ("nucleo",), ("origen", "codigo", "mensaje", "id_correlacion")
    ),
    # Lo emite el modulo duenio de la retencion de datos (en el esqueleto, `nucleo`). Cuando el
    # proyecto tenga su modulo de retencion, se cambia el emisor aqui (cambio de diseno, D.5.2).
    "PurgaEjecutada": EspecificacionEvento(("nucleo",), ("categoria", "cantidad")),
    # --- Autenticacion y cuenta ---
    "SesionIniciada": EspecificacionEvento(("identidad",), ("usuario_id",)),
    "SesionFallida": EspecificacionEvento(
        ("identidad",),
        ("usuario_id", "motivo", "factor"),
        nota=(
            "Motivo real: credenciales, desactivado, bloqueada, requiere_segundo_factor, "
            "codigo_invalido o codigo_repetido. Sin usuario (correo inexistente) viaja solo la "
            "huella del correo. `codigo_repetido` es el aviso de reuso de un código (ASVS V2.8.5)"
        ),
    ),
    "SesionCerrada": EspecificacionEvento(
        ("identidad",),
        ("usuario_id", "motivo"),
        motivos_emitidos=("salida", "tope_absoluto"),
        nota=(
            "Solo `salida` y `tope_absoluto`. El cierre por inactividad o por sello NO se emite: "
            "con sesiones en Redis no se sabe de quién era la sesión al vencer, y Django invalida "
            "la del sello antes de que corra el middleware de `identidad`"
        ),
    ),
    "UsuarioCambiado": EspecificacionEvento(
        ("identidad",),
        ("usuario_id", "cambio", "hecho_por"),
        motivos_emitidos=("alta", "datos", "roles", "reactivacion"),
    ),
    "UsuarioDesactivado": EspecificacionEvento(("identidad",), ("usuario_id",)),
    "ConfiguracionCambiada": EspecificacionEvento(
        CUALQUIER_MODULO, ("usuario_id",), una_de=(("clave", "seccion"),)
    ),
    "ExportacionRealizada": EspecificacionEvento(
        CUALQUIER_MODULO, ("usuario_id", "filtros"), una_de=(("tipo", "reporte"),)
    ),
    "CodigoSegundoFactorRepetido": EspecificacionEvento(
        ("identidad",),
        ("usuario_id", "intento_id", "ocurrido_en"),
        nota="Nunca lleva el código. El aviso al dueño sale del registro de intentos (D.3.10)",
    ),
    "CuentaBloqueada": EspecificacionEvento(("identidad",), _ACTOR),
    "CuentaDesbloqueada": EspecificacionEvento(("identidad",), _ACTOR),
    "ContrasenaTemporalEmitida": EspecificacionEvento(("identidad",), _ACTOR),
    "ContrasenaCambiada": EspecificacionEvento(("identidad",), _ACTOR),
    "SegundoFactorEnrolado": EspecificacionEvento(("identidad",), _ACTOR),
    "SegundoFactorReiniciado": EspecificacionEvento(("identidad",), _ACTOR),
    # --- Eventos del dominio del proyecto ---
    # Cada historia agrega aqui los eventos de su modulo, tal como los define el DISENO (D.5.2).
}

# Datos que nunca viajan en un evento (D.5.2: "Nunca viajan contraseñas, códigos ni secretos"; el
# número completo y los datos de contacto tampoco). Cada CLAVE se normaliza antes de compararla
# (NFKD, sin acentos ni caracteres de formato o de ancho cero, ancho completo a ASCII, minúsculas, y
# `-`, `_`, espacios y camelCase unificados en `_`) y se revisa a cualquier profundidad: una palabra
# larga prohíbe cualquier clave que la contenga (`correo_cliente`, `e_mail` -> `email`, `api_key`
# -> `apikey`); una corta solo cuando es una palabra completa de la clave (`ip`, `direccion_ip`,
# pero no `tipo`). Las listas van ya normalizadas (minúsculas, sin acentos).
PROHIBIDAS_COMO_SUBCADENA = (
    "correo",
    "email",
    "mail",
    "telefono",
    "celular",
    "movil",
    "phone",
    "contrasena",
    "password",
    "passwd",
    "secret",
    "secreto",
    "token",
    "clave",
    "apikey",
    "authorization",
    "cookie",
    "sessionid",
    "sesionid",
    "csrf",
    "totp",
)
PROHIBIDAS_COMO_PALABRA = frozenset({"ip", "otp", "pwd", "codigo", "numero", "pin"})
# Claves legítimas del catálogo que contienen alguna de las anteriores (revisadas contra D.5.2):
# la huella del correo no es el correo.
# Se comparan normalizadas. Las `terminacion_*` (y `*_terminacion`) también se permiten, pero su
# valor solo puede ser texto de hasta 4 caracteres (los últimos 4 del dato).
CLAVES_PERMITIDAS = frozenset({"huella_correo"})
LARGO_MAXIMO_TERMINACION = 4
# Excepciones por evento, tal como D.5.2 las define: el `codigo` del error de integración es un
# código de error, no un código de acceso.
CLAVES_PERMITIDAS_POR_EVENTO: dict[str, frozenset[str]] = {
    "ErrorIntegracionRegistrado": frozenset({"codigo"}),
    # `clave` es la clave de configuracion que cambio (p. ej. `zona_horaria`), no una contrasena.
    "ConfiguracionCambiada": frozenset({"clave"}),
}
# Un valor de texto (o clave, agregado o correlación) con forma de correo electrónico o de teléfono
# internacional (`+` y 10 o más dígitos, con o sin separadores) tampoco viaja. Se revisa ya
# normalizado (`＠` y los dígitos de ancho completo valen como los normales).
PATRON_DE_CORREO = r"[^@\s]+@[^@\s]+\.[^@\s]+"
PATRON_DE_TELEFONO = r"\+\s*\d(?:[\s.\-()]*\d){9,}"

# Eventos auditables mínimos (RF de bitácora, DISENO D.5.2): inicios de sesión correctos y fallidos,
# cambios de configuración, de usuarios y de roles, y exportaciones. Cada proyecto agrega los suyos
# (aprobaciones, autorizaciones...). Una prueba falla si alguno no está en el catálogo.
EVENTOS_AUDITABLES_MINIMOS = (
    "SesionIniciada",
    "SesionFallida",
    "ConfiguracionCambiada",
    "UsuarioCambiado",
    "ExportacionRealizada",
)
