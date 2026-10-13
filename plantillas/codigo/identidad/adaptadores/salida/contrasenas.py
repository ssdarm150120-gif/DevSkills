"""Contrasenas con Argon2 y lista de contrasenas filtradas EMPAQUETADA (D.6.3).

La lista es el archivo de contrasenas comunes que Django ya incluye en su paquete: se lee del disco
local, sin red. Ninguna contrasena sale de la aplicacion ni se consulta un servicio externo.
"""

import secrets
from functools import lru_cache

from django.contrib.auth.hashers import (
    check_password,
    get_hasher,
    identify_hasher,
    make_password,
)
from django.contrib.auth.password_validation import CommonPasswordValidator


@lru_cache(maxsize=1)
def lista_de_contrasenas_filtradas() -> frozenset[str]:
    # `CommonPasswordValidator` lee el archivo empaquetado con Django (gzip local, sin red).
    return frozenset(CommonPasswordValidator().passwords)


@lru_cache(maxsize=1)
def hash_ficticio() -> str:
    """Hash de un valor al azar: sirve para gastar el mismo tiempo cuando el correo no existe."""
    return make_password(secrets.token_urlsafe(16))


class ServicioContrasenasDjango:
    def __init__(self) -> None:
        self.filtradas = lista_de_contrasenas_filtradas()

    def hashear(self, contrasena: str) -> str:
        return make_password(contrasena)

    def verificar(self, contrasena: str, hash_contrasena: str) -> bool:
        return check_password(contrasena, hash_contrasena)

    def requiere_rehash(self, hash_contrasena: str) -> bool:
        try:
            actual = identify_hasher(hash_contrasena)
        except ValueError:  # formato desconocido: se vuelve a hashear con el vigente
            return True
        return bool(
            actual.algorithm != get_hasher().algorithm or actual.must_update(hash_contrasena)
        )

    def verificar_ficticia(self, contrasena: str) -> None:
        check_password(contrasena, hash_ficticio())

    def generar_temporal(self) -> str:
        """Contrasena temporal al azar (20 caracteres); se muestra una sola vez."""
        return secrets.token_urlsafe(15)
