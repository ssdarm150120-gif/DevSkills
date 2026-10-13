"""Confirmar el codigo del segundo factor (DISENO D.3.10).

Sirve a las dos etapas que piden un codigo:

* `enrolando=True` (EnrolamientoPendiente): el usuario registro su aplicacion y captura un codigo
  para confirmarla. Si es valido, el segundo factor queda confirmado y el enrolamiento se registra.
* `enrolando=False` (CodigoPendiente): el codigo de cada ingreso.

En los dos casos revalida la etapa con la cuenta de AHORA y cuenta los fallos con un contador
SEPARADO del de la contrasena (`fallos_codigo`): 5 seguidos bloquean la cuenta 15 minutos (el mismo
bloqueo de la cuenta). Un codigo mal escrito, incorrecto o ya usado cuenta como fallo y deja su
intento registrado con el motivo real. Un codigo valido pone el contador en cero.

El permiso de abrir la sesion NO se da aqui: solo se contesta si el codigo es bueno. Abrirla es del
adaptador de entrada, que lo hace unicamente con `ACEPTADO`.
"""

from dataclasses import dataclass
from enum import StrEnum

from identidad.aplicacion.etapa_segundo_factor import revalidar_etapa
from identidad.aplicacion.puertos import (
    RegistroDeAccesos,
    Reloj,
    RepositorioCuentas,
    VerificadorSegundoFactor,
)
from identidad.dominio.acceso import (
    AccionDeCuenta,
    Factor,
    Motivo,
    Resultado,
    esta_bloqueada,
    tras_fallo,
)
from identidad.dominio.segundo_factor import ResultadoCodigo, normalizar_codigo


class ResultadoConfirmacion(StrEnum):
    ACEPTADO = "aceptado"
    INCORRECTO = "incorrecto"  # sigue en la misma etapa: puede volver a intentar
    BLOQUEADA = "bloqueada"  # la cuenta esta bloqueada (ya lo estaba, o este fue el quinto fallo)


@dataclass(frozen=True, slots=True)
class ConfirmarCodigo:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    reloj: Reloj
    verificador: VerificadorSegundoFactor | None = None

    def __call__(
        self,
        usuario_id: str,
        codigo: str,
        *,
        sello_esperado: str | None,
        enrolando: bool,
        ip: str,
    ) -> ResultadoConfirmacion:
        cuenta, verificador = revalidar_etapa(
            cuentas=self.cuentas,
            accesos=self.accesos,
            reloj=self.reloj,
            verificador=self.verificador,
            usuario_id=usuario_id,
            sello_esperado=sello_esperado,
            enrolando=enrolando,
            ip=ip,
            bloqueada_es_error=False,
        )
        ahora = self.reloj.ahora()

        def intento(resultado: Resultado, motivo: Motivo) -> None:
            self.accesos.registrar_intento(
                correo_capturado=cuenta.correo,
                usuario_id=cuenta.id,
                factor=Factor.CODIGO,
                resultado=resultado,
                motivo=motivo,
                ip=ip,
                momento=ahora,
            )

        if esta_bloqueada(cuenta.bloqueada_hasta, ahora):
            intento(Resultado.FALLIDO, Motivo.CUENTA_BLOQUEADA)
            return ResultadoConfirmacion.BLOQUEADA

        normalizado = normalizar_codigo(codigo)
        resultado_codigo = (
            ResultadoCodigo.INCORRECTO
            if normalizado is None
            else verificador.verificar(cuenta.id, normalizado, ahora, confirmando=enrolando)
        )

        if resultado_codigo is ResultadoCodigo.ACEPTADO:
            if cuenta.fallos_codigo:
                # Si hubiera un bloqueo, ya paso (arriba se descarto): queda sin bloqueo.
                self.cuentas.guardar_conteo_codigo(cuenta.id, 0, None)
            intento(Resultado.CORRECTO, Motivo.CORRECTO)
            if enrolando:
                self.accesos.registrar_accion(
                    accion=AccionDeCuenta.ENROLAMIENTO_SEGUNDO_FACTOR,
                    usuario_objetivo_id=cuenta.id,
                    hecha_por_id=cuenta.id,
                    momento=ahora,
                )
            return ResultadoConfirmacion.ACEPTADO

        fallos, hasta = tras_fallo(cuenta.fallos_codigo, cuenta.bloqueada_hasta, ahora)
        self.cuentas.guardar_conteo_codigo(cuenta.id, fallos, hasta)
        intento(
            Resultado.FALLIDO,
            Motivo.CODIGO_REPETIDO
            if resultado_codigo is ResultadoCodigo.REPETIDO
            else Motivo.CODIGO_INVALIDO,
        )
        if hasta is None:
            return ResultadoConfirmacion.INCORRECTO
        self.accesos.registrar_accion(
            accion=AccionDeCuenta.BLOQUEO,
            usuario_objetivo_id=cuenta.id,
            hecha_por_id=None,
            momento=ahora,
        )
        return ResultadoConfirmacion.BLOQUEADA
