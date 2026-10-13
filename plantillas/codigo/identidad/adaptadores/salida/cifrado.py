"""Cifrado del secreto del segundo factor (DISENO D.6.3).

AES-256-GCM (`cryptography`) con una llave derivada con HKDF-SHA256 de `APP_LLAVE_SEGUNDO_FACTOR`,
la variable de entorno que nunca va en el codigo ni en la base. Tres decisiones que importan:

* El HKDF lleva una sal fija propia de la aplicacion (`_SAL`): sin ella (`salt=None`) HKDF usa una
  sal de ceros, y la llave derivada seria la misma en cualquier otra aplicacion que derive con el
  mismo `info`. La sal no es secreta; solo separa el dominio de esta aplicacion.

* El `usuario_id` va como dato asociado (AAD) del cifrado: quien pudiera escribir en la base no
  puede copiar el secreto cifrado de una fila a otra, porque no descifraria.
* `llave_id` es una huella corta de la llave (derivada aparte, no revela la llave): el registro
  guarda cual la cifro, asi se puede rotar la llave sin adivinar con cual se cifro cada secreto.

Versionado: el prefijo del texto guardado (`v2.`) dice como se derivo la llave. `v1.` (HKDF sin sal)
ya no se acepta: no hubo datos productivos, asi que se descarta en vez de mantener dos derivaciones;
un `v1.` en la base falla cerrado (`SecretoIlegible`) y el usuario se enrola de nuevo (reinicio).

Lo que no se puede descifrar (llave distinta, dato alterado) lanza `SecretoIlegible`: quien llama
trata el segundo factor como no disponible y falla cerrado.
"""

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VERSION = "v2"
_TAMANO_NONCE = 12
_SAL = b"app.identidad.segundo_factor.sal.v2"
_INFO_CIFRADO = b"app.identidad.segundo_factor.cifrado.v2"
_INFO_ID = b"app.identidad.segundo_factor.llave_id.v2"


class SecretoIlegible(Exception):
    """El secreto no se puede descifrar con la llave actual."""


def _derivar(llave: str, info: bytes, largo: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=largo, salt=_SAL, info=info).derive(
        llave.encode("utf-8")
    )


class CifradoDeSecretos:
    def __init__(self, llave: str) -> None:
        if not llave.strip():
            raise SecretoIlegible("no hay llave del segundo factor")
        self._aes = AESGCM(_derivar(llave, _INFO_CIFRADO, 32))
        self.llave_id = _derivar(llave, _INFO_ID, 8).hex()

    @staticmethod
    def _asociado(usuario_id: str) -> bytes:
        return f"segundo_factor:{usuario_id}".encode()

    def cifrar(self, secreto: bytes, usuario_id: str) -> str:
        nonce = os.urandom(_TAMANO_NONCE)
        cifrado = self._aes.encrypt(nonce, secreto, self._asociado(usuario_id))
        return f"{VERSION}.{base64.urlsafe_b64encode(nonce + cifrado).decode('ascii')}"

    def descifrar(self, texto: str, usuario_id: str) -> bytes:
        version, separador, cuerpo = texto.partition(".")
        if version != VERSION or not separador:
            raise SecretoIlegible("version desconocida del secreto")
        try:
            crudo = base64.urlsafe_b64decode(cuerpo.encode("ascii"))
            if len(crudo) <= _TAMANO_NONCE:
                raise SecretoIlegible("secreto truncado")
            return self._aes.decrypt(
                crudo[:_TAMANO_NONCE], crudo[_TAMANO_NONCE:], self._asociado(usuario_id)
            )
        except (InvalidTag, binascii.Error, UnicodeEncodeError, ValueError) as error:
            raise SecretoIlegible("el secreto no se puede descifrar con la llave actual") from error
