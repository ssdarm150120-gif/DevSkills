"""Iniciar sesion, paso de la contrasena (DISENO D.3.10).

Decide a que etapa pasa el usuario. No toca la sesion HTTP: eso es del adaptador de entrada.
El orden de las etapas es contrasena, cambio obligatorio (si la contrasena es temporal),
enrolamiento (si no tiene segundo factor) y codigo. Reglas que importan:

* El mismo mensaje y el MISMO tiempo de respuesta para correo inexistente, contrasena incorrecta,
  usuario desactivado y cuenta bloqueada: el hash se calcula siempre.
* Cada intento queda registrado con su motivo real, aunque al usuario se le muestre uno solo.
* Falla cerrado: un rol que exige segundo factor no entra con solo la contrasena. Se
  evalua ANTES del cambio obligatorio de contrasena (D.3.10).
"""

from dataclasses import dataclass

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
    Motivo,
    Resultado,
    correo_valido,
    esta_bloqueada,
    normalizar_correo,
    tras_fallo,
)


@dataclass(frozen=True, slots=True)
class ResultadoIngreso:
    etapa: Etapa
    usuario_id: str | None = None
    # Solo en las etapas pendientes: el sello con el que se abrieron (se compara al completarlas).
    sello_sesion: str | None = None


@dataclass(frozen=True, slots=True)
class IniciarSesion:
    cuentas: RepositorioCuentas
    accesos: RegistroDeAccesos
    contrasenas: ServicioContrasenas
    reloj: Reloj
    # `None`: sin adaptador del segundo factor conectado (falla cerrado para roles sensibles).
    verificador: VerificadorSegundoFactor | None = None

    def __call__(self, correo: str, contrasena: str, *, ip: str) -> ResultadoIngreso:
        ahora = self.reloj.ahora()
        correo_normalizado = normalizar_correo(correo)
        # Un correo imposible (NUL, control, demasiado largo) es "no existe": no se consulta.
        cuenta = (
            self.cuentas.por_correo(correo_normalizado)
            if correo_valido(correo_normalizado)
            else None
        )

        def intento(resultado: Resultado, motivo: Motivo) -> None:
            self.accesos.registrar_intento(
                correo_capturado=correo,
                usuario_id=cuenta.id if cuenta else None,
                factor=Factor.CONTRASENA,
                resultado=resultado,
                motivo=motivo,
                ip=ip,
                momento=ahora,
            )

        if cuenta is None:
            self.contrasenas.verificar_ficticia(contrasena)
            # Tambien el trabajo de base de datos del camino con cuenta: sin esto, "correo
            # inexistente" respondia unos milisegundos antes que "contrasena incorrecta".
            self.cuentas.trabajo_equivalente_sin_cuenta()
            intento(Resultado.FALLIDO, Motivo.CORREO_INEXISTENTE)
            return ResultadoIngreso(Etapa.FALLO)

        correcta = self.contrasenas.verificar(contrasena, cuenta.hash_contrasena)  # siempre
        if not cuenta.activo:
            intento(Resultado.FALLIDO, Motivo.USUARIO_DESACTIVADO)
            return ResultadoIngreso(Etapa.FALLO)
        if esta_bloqueada(cuenta.bloqueada_hasta, ahora):
            intento(Resultado.FALLIDO, Motivo.CUENTA_BLOQUEADA)
            return ResultadoIngreso(Etapa.FALLO)

        if not correcta:
            fallos, hasta = tras_fallo(cuenta.fallos_contrasena, cuenta.bloqueada_hasta, ahora)
            self.cuentas.guardar_conteo(cuenta.id, fallos, hasta)
            intento(Resultado.FALLIDO, Motivo.CONTRASENA_INCORRECTA)
            if hasta is not None:
                self.accesos.registrar_accion(
                    accion=AccionDeCuenta.BLOQUEO,
                    usuario_objetivo_id=cuenta.id,
                    hecha_por_id=None,
                    momento=ahora,
                )
            return ResultadoIngreso(Etapa.FALLO)

        if correcta and self.contrasenas.requiere_rehash(cuenta.hash_contrasena):
            # Parametros de Argon2 vigentes; no toca el sello, asi que las sesiones siguen vivas.
            self.cuentas.actualizar_hash(cuenta.id, self.contrasenas.hashear(contrasena))

        # Contrasena correcta: el conteo vuelve a cero (tambien si despues se rechaza el rol).
        if cuenta.fallos_contrasena or cuenta.bloqueada_hasta is not None:
            self.cuentas.guardar_conteo(cuenta.id, 0, None)

        verificador = self.verificador
        if cuenta.exige_segundo_factor and (
            verificador is None or not verificador.disponible_para(cuenta.id)
        ):
            # Falla cerrado: sin el segundo factor un rol sensible nunca entra con solo la
            # contrasena, y se evalua ANTES del cambio obligatorio (D.3.10).
            intento(Resultado.FALLIDO, Motivo.REQUIERE_SEGUNDO_FACTOR)
            return ResultadoIngreso(Etapa.RECHAZADO_POR_SEGUNDO_FACTOR)

        intento(Resultado.CORRECTO, Motivo.CORRECTO)
        if cuenta.debe_cambiar_contrasena:
            return ResultadoIngreso(Etapa.CAMBIO_OBLIGATORIO, cuenta.id, cuenta.sello_sesion)
        if cuenta.exige_segundo_factor and verificador is not None:
            etapa = (
                Etapa.CODIGO_PENDIENTE
                if verificador.esta_enrolado(cuenta.id)
                else Etapa.ENROLAMIENTO_PENDIENTE
            )
            return ResultadoIngreso(etapa, cuenta.id, cuenta.sello_sesion)
        return ResultadoIngreso(Etapa.SESION_COMPLETA, cuenta.id)
