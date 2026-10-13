"""Eventos que `identidad` emite al bus (DISENO D.5.2, nota "Orden de llegada de la autenticación").

Cada intento de ingreso y cada acción sobre una cuenta que ya se registran (`IntentoIngreso` y
`AccionCuenta`) producen, ADEMÁS, sus eventos: el evento se suma a la fila, no la sustituye. Las
funciones son puras: reciben lo mismo que `RegistroDeAccesos` y devuelven los eventos.

El `evento_id` sale de la fila de origen (uuid5 de tabla, id de fila e índice): cada evento se
puede rastrear hasta su fila.

Nunca viajan contraseñas, códigos ni secretos; del
correo capturado, solo su huella y solo cuando no corresponde a ninguna cuenta. Tampoco viaja la IP.

`SesionCerrada` solo se emite con motivo `salida` o `tope_absoluto` (D.3.10).
"""

from collections.abc import Mapping
from datetime import datetime
from uuid import NAMESPACE_DNS, UUID, uuid5

from identidad.dominio.acceso import AccionDeCuenta, Factor, Motivo, Resultado
from nucleo.puertos.eventos import EventoDeDominio

_ESPACIO = uuid5(NAMESPACE_DNS, "eventos.identidad.app")

_MOTIVO_DE_SESION_FALLIDA: dict[Motivo, str] = {
    Motivo.CORREO_INEXISTENTE: "credenciales",
    Motivo.CONTRASENA_INCORRECTA: "credenciales",
    Motivo.CAMBIO_DE_CONTRASENA_INCORRECTA: "credenciales",
    Motivo.USUARIO_DESACTIVADO: "desactivado",
    Motivo.CUENTA_BLOQUEADA: "bloqueada",
    Motivo.REQUIERE_SEGUNDO_FACTOR: "requiere_segundo_factor",
    Motivo.CODIGO_INVALIDO: "codigo_invalido",
    Motivo.CODIGO_REPETIDO: "codigo_repetido",
}


def identificador_de_evento(origen: str, fila_id: int, indice: int) -> UUID:
    """`evento_id` determinista de un evento derivado de una fila (`intento` o `accion`)."""
    return uuid5(_ESPACIO, f"{origen}:{fila_id}:{indice}")


def _lista(detalle: Mapping[str, object], clave: str) -> list[str]:
    valor = detalle.get(clave)
    return [str(elemento) for elemento in valor] if isinstance(valor, list | tuple) else []


def eventos_de_intento(
    fila_id: int,
    *,
    usuario_id: str | None,
    huella_correo: str,
    factor: Factor,
    resultado: Resultado,
    motivo: Motivo,
    momento: datetime,
) -> list[EventoDeDominio]:
    """Un intento fallido es `SesionFallida` con el motivo real. Uno correcto no emite nada: la
    sesión se inicia cuando el ingreso se completa (`AccionDeCuenta.SESION_INICIADA`)."""
    if resultado is not Resultado.FALLIDO:
        return []
    payload: dict[str, object] = {
        "usuario_id": usuario_id,
        "motivo": _MOTIVO_DE_SESION_FALLIDA[motivo],
        "factor": factor.value,
    }
    if usuario_id is None:
        payload["huella_correo"] = huella_correo
    eventos = [
        EventoDeDominio(
            nombre="SesionFallida",
            agregado_id=usuario_id or f"huella:{huella_correo[:12]}",
            ocurrido_en=momento,
            payload=payload,
            evento_id=identificador_de_evento("intento", fila_id, 0),
        )
    ]
    if motivo is Motivo.CODIGO_REPETIDO and usuario_id is not None:
        # Reuso de un codigo (ASVS V2.8.5): nunca lleva el codigo. Con, el aviso al dueno
        # sale del registro de intentos, no de este evento.
        eventos.append(
            EventoDeDominio(
                nombre="CodigoSegundoFactorRepetido",
                agregado_id=usuario_id,
                ocurrido_en=momento,
                payload={
                    "usuario_id": usuario_id,
                    "intento_id": fila_id,
                    "ocurrido_en": momento.isoformat(),
                },
                evento_id=identificador_de_evento("intento", fila_id, 1),
            )
        )
    return eventos


def eventos_de_accion(
    fila_id: int,
    *,
    accion: AccionDeCuenta,
    usuario_objetivo_id: str,
    hecha_por_id: str | None,
    momento: datetime,
    detalle: Mapping[str, object] | None = None,
) -> list[EventoDeDominio]:
    d: Mapping[str, object] = detalle or {}
    uid = usuario_objetivo_id
    eventos: list[EventoDeDominio] = []

    def agregar(nombre: str, payload: Mapping[str, object], agregado_id: str = uid) -> None:
        eventos.append(
            EventoDeDominio(
                nombre=nombre,
                agregado_id=agregado_id,
                ocurrido_en=momento,
                payload=payload,
                evento_id=identificador_de_evento("accion", fila_id, len(eventos)),
            )
        )

    quien = {"usuario_id": uid, "hecho_por": hecha_por_id}
    if accion is AccionDeCuenta.ALTA:
        agregar("UsuarioCambiado", {**quien, "cambio": "alta", "roles": _lista(d, "roles")})
        agregar("ContrasenaTemporalEmitida", {**quien, "motivo": "alta"})
    elif accion is AccionDeCuenta.DESACTIVACION:
        agregar("UsuarioDesactivado", dict(quien))
    elif accion is AccionDeCuenta.REACTIVACION:
        agregar("UsuarioCambiado", {**quien, "cambio": "reactivacion"})
    elif accion is AccionDeCuenta.CAMBIO_DE_USUARIO:
        agregar("UsuarioCambiado", {**quien, "cambio": "datos", "campos": _lista(d, "campos")})
    elif accion is AccionDeCuenta.CAMBIO_DE_ROLES:
        antes, despues = _lista(d, "antes"), _lista(d, "despues")
        agregar(
            "UsuarioCambiado",
            {**quien, "cambio": "roles", "roles_antes": antes, "roles_despues": despues},
        )
    elif accion is AccionDeCuenta.CAMBIO_DE_CONTRASENA:
        agregar("ContrasenaCambiada", {**quien, "motivo": "cambio_de_contrasena"})
    elif accion is AccionDeCuenta.RESTABLECIMIENTO_CONTRASENA:
        agregar("ContrasenaTemporalEmitida", {**quien, "motivo": "restablecimiento"})
    elif accion is AccionDeCuenta.BLOQUEO:
        agregar("CuentaBloqueada", {**quien, "motivo": "intentos_fallidos"})
    elif accion is AccionDeCuenta.DESBLOQUEO:
        agregar("CuentaDesbloqueada", {**quien, "motivo": "desbloqueo_por_administrador"})
    elif accion is AccionDeCuenta.ENROLAMIENTO_SEGUNDO_FACTOR:
        agregar("SegundoFactorEnrolado", {**quien, "motivo": "enrolamiento"})
    elif accion is AccionDeCuenta.REINICIO_SEGUNDO_FACTOR:
        agregar("SegundoFactorReiniciado", {**quien, "motivo": "reinicio_por_administrador"})
    elif accion is AccionDeCuenta.SESION_INICIADA:
        agregar("SesionIniciada", {"usuario_id": uid})
    elif accion is AccionDeCuenta.SESION_CERRADA_SALIDA:
        agregar("SesionCerrada", {"usuario_id": uid, "motivo": "salida"})
    elif accion is AccionDeCuenta.SESION_CERRADA_TOPE_ABSOLUTO:
        agregar("SesionCerrada", {"usuario_id": uid, "motivo": "tope_absoluto"})
    return eventos
