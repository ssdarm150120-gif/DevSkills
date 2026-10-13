"""Definir la contrasena.

Quien llama dice la INTENCION (`Intencion`); no se deduce del estado de la cuenta:

* `CAMBIO_OBLIGATORIO` (contrasena temporal): no pide la actual, porque el usuario acaba de
  ingresar con ella. Exige el sello con el que se abrio la etapa pendiente y REVALIDA el falla
  cerrado: si mientras tanto cambiaron sus roles, reiniciaron la temporal o desactivaron la cuenta,
  no se completa (el adaptador no abre sesion). Al terminar dice cual es la SIGUIENTE etapa del
  ingreso (D.3.10): enrolamiento, codigo o sesion completa.
* `CAMBIO_PROPIO` (usuario con sesion): SIEMPRE pide la actual. Una actual incorrecta
  cuenta como fallo y puede bloquear la cuenta, igual que al ingresar.

La nueva debe cumplir la politica de y ser distinta de la que tiene.
"""

from dataclasses import dataclass

from identidad.aplicacion.errores import (
    CuentaNoDisponible,
    EtapaInvalida,
    RequiereSegundoFactor,
)
from identidad.aplicacion.puertos import (
    RegistroDeAccesos,
    Reloj,
    RepositorioCuentas,
    ServicioContrasenas,
    VerificadorSegundoFactor,
)
from identidad.dominio.acceso import (
    AccionDeCuenta,
    Etapa,
    Factor,
    Intencion,
    Motivo,
    Resultado,
    esta_bloqueada,
    tras_fallo,
)
from identidad.dominio.contrasena import validar_contrasena

MENSAJE_IGUAL_A_LA_ACTUAL = "La contraseña nueva debe ser distinta de la actual"
MENSAJE_ACTUAL_INCORRECTA = "La contraseña actual no es correcta"

__all__ = [
    "MENSAJE_ACTUAL_INCORRECTA",
    "MENSAJE_IGUAL_A_LA_ACTUAL",
    "ContrasenaActualIncorrecta",
    "ContrasenaInvalida",
    "CuentaNoDisponible",
    "DefinirContrasena",
    "EtapaInvalida",
    "RequiereSegundoFactor",
    "ResultadoDefinicion",
]


class ContrasenaInvalida(ValueError):
    """La contrasena nueva no cumple la politica; `errores` lista los motivos."""

    def __init__(self, errores: tuple[str, ...]) -> None:
        super().__init__("; ".join(errores))
        self.errores = errores


class ContrasenaActualIncorrecta(Exception):
    """No se dio la contrasena actual correcta (o la cuenta esta bloqueada)."""


@dataclass(frozen=True, slots=True)
class ResultadoDefinicion:
    """Lo que sigue despues de definir la contrasena."""

    etapa: Etapa
    # Sello NUEVO de la cuenta (la contrasena lo cambio): la siguiente etapa pendiente lo guarda.
    sello_sesion: str | None = None


@dataclass(frozen=True, slots=True)
class DefinirContrasena:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    contrasenas: ServicioContrasenas
    reloj: Reloj
    # `None`: sin adaptador del segundo factor: falla cerrado para los roles que lo exigen.
    verificador: VerificadorSegundoFactor | None = None

    def __call__(
        self,
        usuario_id: str,
        nueva: str,
        *,
        intencion: Intencion,
        contrasena_actual: str | None = None,
        sello_esperado: str | None = None,
        ip: str,
    ) -> ResultadoDefinicion:
        ahora = self.reloj.ahora()
        cuenta = self.cuentas.por_id(usuario_id)
        if cuenta is None or not cuenta.activo:
            raise CuentaNoDisponible

        verificador = self.verificador
        if intencion is Intencion.CAMBIO_OBLIGATORIO:
            if not cuenta.debe_cambiar_contrasena or sello_esperado != cuenta.sello_sesion:
                raise EtapaInvalida
            # Falla cerrado revalidado con los roles de AHORA, antes de cambiar nada.
            if cuenta.exige_segundo_factor and (
                verificador is None or not verificador.disponible_para(cuenta.id)
            ):
                self.accesos.registrar_intento(
                    correo_capturado=cuenta.correo,
                    usuario_id=cuenta.id,
                    factor=Factor.CONTRASENA,
                    resultado=Resultado.FALLIDO,
                    motivo=Motivo.REQUIERE_SEGUNDO_FACTOR,
                    ip=ip,
                    momento=ahora,
                )
                raise RequiereSegundoFactor
        else:
            if esta_bloqueada(cuenta.bloqueada_hasta, ahora):
                raise ContrasenaActualIncorrecta
            if contrasena_actual is None or not self.contrasenas.verificar(
                contrasena_actual, cuenta.hash_contrasena
            ):
                fallos, hasta = tras_fallo(cuenta.fallos_contrasena, cuenta.bloqueada_hasta, ahora)
                self.cuentas.guardar_conteo(cuenta.id, fallos, hasta)
                self.accesos.registrar_intento(
                    correo_capturado=cuenta.correo,
                    usuario_id=cuenta.id,
                    factor=Factor.CONTRASENA,
                    resultado=Resultado.FALLIDO,
                    motivo=Motivo.CAMBIO_DE_CONTRASENA_INCORRECTA,
                    ip=ip,
                    momento=ahora,
                )
                if hasta is not None:
                    self.accesos.registrar_accion(
                        accion=AccionDeCuenta.BLOQUEO,
                        usuario_objetivo_id=cuenta.id,
                        hecha_por_id=None,
                        momento=ahora,
                    )
                raise ContrasenaActualIncorrecta

        errores = validar_contrasena(nueva, self.contrasenas.filtradas)
        if self.contrasenas.verificar(nueva, cuenta.hash_contrasena):
            errores = (*errores, MENSAJE_IGUAL_A_LA_ACTUAL)
        if errores:
            raise ContrasenaInvalida(errores)

        self.cuentas.guardar_contrasena(
            cuenta.id, self.contrasenas.hashear(nueva), temporal=False, ahora=ahora
        )
        if cuenta.fallos_contrasena or cuenta.bloqueada_hasta is not None:
            self.cuentas.guardar_conteo(cuenta.id, 0, None)
        self.accesos.registrar_accion(
            accion=AccionDeCuenta.CAMBIO_DE_CONTRASENA,
            usuario_objetivo_id=cuenta.id,
            hecha_por_id=cuenta.id,
            momento=ahora,
        )
        if intencion is Intencion.CAMBIO_PROPIO or not cuenta.exige_segundo_factor:
            return ResultadoDefinicion(Etapa.SESION_COMPLETA)
        # D.3.10: con un rol sensible sigue el enrolamiento o el codigo, con el sello NUEVO.
        if verificador is None:  # ya se descarto arriba; protege ante un cambio de ese orden
            raise RequiereSegundoFactor
        actualizada = self.cuentas.por_id(cuenta.id)
        etapa = (
            Etapa.CODIGO_PENDIENTE
            if verificador.esta_enrolado(cuenta.id)
            else Etapa.ENROLAMIENTO_PENDIENTE
        )
        return ResultadoDefinicion(etapa, actualizada.sello_sesion if actualizada else None)
