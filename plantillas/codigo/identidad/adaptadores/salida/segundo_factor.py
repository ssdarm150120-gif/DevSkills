"""Adaptador TOTP del puerto `VerificadorSegundoFactor` (DISENO D.3.10).

El algoritmo es el de `django-otp` (`django_otp.oath.hotp`, RFC 4226/6238), pero el secreto NO vive
en un `TOTPDevice`: `TOTPDevice` lo guarda en claro, y el requisito de seguridad pide cifrarlo. Va
en el modelo propio `SegundoFactor`, cifrado con la llave del entorno (ver `cifrado.py`).

Falla cerrado: sin llave, o con un secreto que la llave actual no descifra, `disponible_para` es
falso y el usuario con un rol sensible no entra (el caso de uso lo trata como "sin segundo factor").

Concurrencia: `verificar` e `iniciar_enrolamiento` abren su PROPIA transaccion y leen
la fila con `select_for_update`, asi que el un-solo-uso del codigo no depende de que quien llama ya
hubiera abierto una (dentro de una transaccion externa, `atomic()` solo crea un punto de guardado y
el bloqueo se mantiene hasta que ella termine).
"""

import base64
import hmac
import secrets
from datetime import datetime
from urllib.parse import quote

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django_otp.oath import hotp

from identidad.adaptadores.salida.cifrado import CifradoDeSecretos, SecretoIlegible
from identidad.adaptadores.salida.modelos import SegundoFactor
from identidad.aplicacion.errores import EtapaInvalida
from identidad.aplicacion.puertos import Enrolamiento
from identidad.dominio.segundo_factor import (
    BYTES_DEL_SECRETO,
    DIGITOS,
    PASO_SEGUNDOS,
    ResultadoCodigo,
    decidir_codigo,
    pasos_de_la_ventana,
)


def _cifrado() -> CifradoDeSecretos | None:
    """El cifrado con la llave actual, o `None` si no hay llave."""
    try:
        return CifradoDeSecretos(getattr(settings, "APP_LLAVE_SEGUNDO_FACTOR", ""))
    except SecretoIlegible:
        return None


def _filas(usuario_id: str) -> QuerySet[SegundoFactor]:
    """La fila del usuario, BLOQUEADA hasta el fin de la transaccion (quien llama ya esta en una).

    Dos peticiones con el mismo codigo no pasan: la segunda espera y ve el paso ya usado.
    """
    return SegundoFactor.objects.select_for_update().filter(usuario_id=usuario_id)


def codigo_del_paso(secreto: bytes, paso: int) -> str:
    """El codigo de 6 digitos del paso `paso` (con ceros a la izquierda)."""
    return f"{hotp(secreto, paso, digits=DIGITOS):0{DIGITOS}d}"


def uri_de_enrolamiento(secreto: bytes, correo: str) -> str:
    """URI `otpauth://` que leen las aplicaciones de codigos. El emisor sale de la configuracion."""
    emisor = quote(settings.APP_NOMBRE_APLICACION, safe="")
    clave = base64.b32encode(secreto).decode("ascii").rstrip("=")
    return (
        f"otpauth://totp/{emisor}:{quote(correo, safe='')}"
        f"?secret={clave}&issuer={emisor}&algorithm=SHA1&digits={DIGITOS}&period={PASO_SEGUNDOS}"
    )


class VerificadorTotp:
    def disponible_para(self, usuario_id: str) -> bool:
        cifrado = _cifrado()
        if cifrado is None:
            return False
        fila = SegundoFactor.objects.filter(usuario_id=usuario_id).first()
        if fila is None:
            return True  # aun no se enrola: se le generara un secreto con la llave actual
        if fila.llave_id != cifrado.llave_id:
            return False
        try:
            cifrado.descifrar(fila.secreto_cifrado, usuario_id)
        except SecretoIlegible:
            return False
        return True

    def esta_enrolado(self, usuario_id: str) -> bool:
        return SegundoFactor.objects.filter(
            usuario_id=usuario_id, confirmado_en__isnull=False
        ).exists()

    def iniciar_enrolamiento(self, usuario_id: str, correo: str, ahora: datetime) -> Enrolamiento:
        cifrado = _cifrado()
        if cifrado is None:
            raise SecretoIlegible("no hay llave del segundo factor")
        with transaction.atomic():
            fila = _filas(usuario_id).first()
            if fila is None:
                secreto = secrets.token_bytes(BYTES_DEL_SECRETO)
                try:
                    with transaction.atomic():  # punto de guardado: el choque no rompe la externa
                        SegundoFactor.objects.create(
                            usuario_id=usuario_id,
                            secreto_cifrado=cifrado.cifrar(secreto, usuario_id),
                            llave_id=cifrado.llave_id,
                            creado_en=ahora,
                        )
                except IntegrityError:
                    # Otra peticion creo la fila primero (dos GET a la vez): se usa SU secreto.
                    fila = _filas(usuario_id).first()
                    if fila is None:
                        raise  # no era ese choque (por ejemplo, el usuario no existe)
            if fila is not None:
                if fila.confirmado_en is not None:
                    raise EtapaInvalida  # ya confirmo su aplicacion: esta etapa ya no le toca
                # Se recargo la pantalla: el mismo secreto, para que su aplicacion siga sirviendo.
                secreto = cifrado.descifrar(fila.secreto_cifrado, usuario_id)
        return Enrolamiento(
            clave=base64.b32encode(secreto).decode("ascii").rstrip("="),
            uri=uri_de_enrolamiento(secreto, correo),
        )

    def verificar(
        self, usuario_id: str, codigo: str, ahora: datetime, *, confirmando: bool
    ) -> ResultadoCodigo:
        cifrado = _cifrado()
        with transaction.atomic():
            fila = _filas(usuario_id).first()
            if cifrado is None or fila is None or (fila.confirmado_en is None) != confirmando:
                return ResultadoCodigo.INCORRECTO
            try:
                secreto = cifrado.descifrar(fila.secreto_cifrado, usuario_id)
            except SecretoIlegible:
                return ResultadoCodigo.INCORRECTO
            # Se comparan TODOS los pasos de la ventana (sin cortar al primero) y en tiempo
            # constante.
            coinciden = [
                paso
                for paso in pasos_de_la_ventana(ahora)
                if hmac.compare_digest(codigo_del_paso(secreto, paso).encode(), codigo.encode())
            ]
            resultado, paso = decidir_codigo(coinciden, fila.ultimo_paso_aceptado)
            if resultado is ResultadoCodigo.ACEPTADO:
                fila.ultimo_paso_aceptado = paso
                if confirmando:
                    fila.confirmado_en = ahora
                fila.save(update_fields=["ultimo_paso_aceptado", "confirmado_en"])
            return resultado

    def reiniciar(self, usuario_id: str) -> bool:
        borradas, _ = SegundoFactor.objects.filter(usuario_id=usuario_id).delete()
        return borradas > 0
