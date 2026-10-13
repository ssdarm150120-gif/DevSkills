"""Revalidacion de las etapas del segundo factor (enrolamiento y codigo; DISENO D.3.10).

Una etapa pendiente vive en la sesion: guarda el usuario y el sello con el que se abrio. Mientras
esta abierta, la cuenta puede cambiar (roles, contrasena, desactivacion, reinicio del segundo
factor). Por eso, cada vez que se usa, el caso de uso VUELVE a comprobar todo contra la cuenta de
AHORA y falla cerrado ante cualquier diferencia.
"""

from identidad.aplicacion.errores import (
    CuentaBloqueada,
    CuentaNoDisponible,
    EtapaInvalida,
    RequiereSegundoFactor,
)
from identidad.aplicacion.puertos import (
    Cuenta,
    RegistroDeAccesos,
    Reloj,
    RepositorioCuentas,
    VerificadorSegundoFactor,
)
from identidad.dominio.acceso import Factor, Motivo, Resultado, esta_bloqueada


def revalidar_etapa(
    *,
    cuentas: RepositorioCuentas,
    accesos: RegistroDeAccesos,
    reloj: Reloj,
    verificador: VerificadorSegundoFactor | None,
    usuario_id: str,
    sello_esperado: str | None,
    enrolando: bool,
    ip: str,
    bloqueada_es_error: bool = True,
) -> tuple[Cuenta, VerificadorSegundoFactor]:
    """Devuelve la cuenta y el verificador si la etapa sigue siendo valida.

    Lanza `CuentaNoDisponible` (no existe o esta desactivada), `EtapaInvalida` (cambio el sello, ya
    no exige segundo factor, o la etapa no corresponde a su estado de enrolamiento),
    `RequiereSegundoFactor` (falla cerrado: sin adaptador o sin poder verificarlo) y, si
    `bloqueada_es_error`, `CuentaBloqueada`.
    """
    cuenta = cuentas.por_id(usuario_id)
    if cuenta is None or not cuenta.activo:
        raise CuentaNoDisponible
    if sello_esperado is None or sello_esperado != cuenta.sello_sesion:
        raise EtapaInvalida
    if not cuenta.exige_segundo_factor:
        raise EtapaInvalida
    ahora = reloj.ahora()
    if verificador is None or not verificador.disponible_para(cuenta.id):
        accesos.registrar_intento(
            correo_capturado=cuenta.correo,
            usuario_id=cuenta.id,
            factor=Factor.CODIGO,
            resultado=Resultado.FALLIDO,
            motivo=Motivo.REQUIERE_SEGUNDO_FACTOR,
            ip=ip,
            momento=ahora,
        )
        raise RequiereSegundoFactor
    # Enrolar solo a quien no tiene segundo factor; pedir el codigo solo a quien ya lo tiene.
    if verificador.esta_enrolado(cuenta.id) == enrolando:
        raise EtapaInvalida
    if bloqueada_es_error and esta_bloqueada(cuenta.bloqueada_hasta, ahora):
        raise CuentaBloqueada
    return cuenta, verificador
