"""Iniciar el enrolamiento del segundo factor (DISENO D.3.10).

Es la pantalla del QR y de la clave. Revalida la etapa con la cuenta de AHORA (sello, roles, falla
cerrado) y pide al adaptador el secreto: lo genera la primera vez y, mientras no se confirme,
devuelve el mismo (si el usuario recarga la pantalla, su aplicacion sigue sirviendo). El secreto no
se guarda en claro ni se registra en ningun lado.
"""

from dataclasses import dataclass

from identidad.aplicacion.etapa_segundo_factor import revalidar_etapa
from identidad.aplicacion.puertos import (
    Enrolamiento,
    RegistroDeAccesos,
    Reloj,
    RepositorioCuentas,
    VerificadorSegundoFactor,
)


@dataclass(frozen=True, slots=True)
class IniciarEnrolamiento:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    reloj: Reloj
    verificador: VerificadorSegundoFactor | None = None

    def __call__(self, usuario_id: str, *, sello_esperado: str | None, ip: str) -> Enrolamiento:
        cuenta, verificador = revalidar_etapa(
            cuentas=self.cuentas,
            accesos=self.accesos,
            reloj=self.reloj,
            verificador=self.verificador,
            usuario_id=usuario_id,
            sello_esperado=sello_esperado,
            enrolando=True,
            ip=ip,
        )
        return verificador.iniciar_enrolamiento(cuenta.id, cuenta.correo, self.reloj.ahora())
