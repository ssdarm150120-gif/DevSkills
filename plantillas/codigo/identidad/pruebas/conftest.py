"""Fixtures de las pruebas de `identidad`: usuarios de prueba y un reloj que se puede adelantar.

Los usuarios y roles de las pruebas se crean aqui (sin pasar por la pantalla de administracion).
"""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client

from identidad.adaptadores.salida.cifrado import CifradoDeSecretos
from identidad.adaptadores.salida.modelos import Rol, SegundoFactor, Usuario, UsuarioRol
from identidad.adaptadores.salida.repositorios import RelojDelSistema
from identidad.dominio.segundo_factor import paso_de

CONTRASENA = "caballo-grapa-9Lunar"


@pytest.fixture
def crear_usuario(db: Any) -> Callable[..., Usuario]:
    """Crea un usuario con roles del catalogo (sembrado por la migracion 0003)."""

    def _crear(
        correo: str = "ana@empresa.example",
        contrasena: str = CONTRASENA,
        roles: tuple[str, ...] = ("usuario",),
        **campos: Any,
    ) -> Usuario:
        ahora = datetime.now(UTC)
        usuario = Usuario.objects.create(
            correo=correo,
            password=make_password(contrasena),
            creado_en=ahora,
            **campos,
        )
        for rol in Rol.objects.filter(codigo__in=roles):
            UsuarioRol.objects.create(usuario=usuario, rol=rol, asignado_en=ahora)
        return usuario

    return _crear


@pytest.fixture
def registrar_segundo_factor(db: Any) -> Callable[..., bytes]:
    """Deja a un usuario con su aplicacion de codigos YA registrada (como si se hubiera enrolado).

    Devuelve el secreto, para calcular los codigos que daria su aplicacion. El secreto se guarda
    cifrado con la llave de la configuracion, igual que el enrolamiento real.
    """

    def _registrar(
        usuario: Usuario, secreto: bytes | None = None, ahora: datetime | None = None
    ) -> bytes:
        secreto = secreto or secrets.token_bytes(20)
        cifrado = CifradoDeSecretos(settings.APP_LLAVE_SEGUNDO_FACTOR)
        # `ahora` permite situar el registro un dia antes de un reloj fijo (sin depender de hoy).
        hace_un_dia = (ahora or datetime.now(UTC)) - timedelta(days=1)
        SegundoFactor.objects.create(
            usuario=usuario,
            secreto_cifrado=cifrado.cifrar(secreto, str(usuario.id)),
            llave_id=cifrado.llave_id,
            creado_en=hace_un_dia,
            confirmado_en=hace_un_dia,
            ultimo_paso_aceptado=paso_de(hace_un_dia),
        )
        return secreto

    return _registrar


@pytest.fixture
def cliente() -> Client:
    return Client()


def entrar(usuario: Usuario) -> Client:
    """Un navegador con la sesion YA completa de `usuario` (el ingreso se prueba aparte)."""
    navegador = Client()
    navegador.force_login(usuario)
    sesion = navegador.session
    sesion["iniciada_en"] = datetime.now(UTC).isoformat()
    sesion.save()
    return navegador


@pytest.fixture
def admin_cliente(crear_usuario: Callable[..., Usuario]) -> Client:
    """El navegador de un Administrador con la sesion completa (gestion de usuarios)."""
    return entrar(
        crear_usuario(correo="admin@empresa.example", nombre="Admin", roles=("administrador",))
    )


class RelojAdelantable:
    """Fuente de tiempo falsa para la hora del caso de uso y para el vencimiento de la sesion."""

    def __init__(self) -> None:
        self.desfase = timedelta(0)

    def ahora(self) -> datetime:
        return datetime.now(UTC) + self.desfase

    def time(self) -> float:
        return self.ahora().timestamp()

    def adelantar(self, **delta: float) -> None:
        self.desfase += timedelta(**delta)

    def situar_en(self, instante: datetime) -> None:
        """Deja el reloj en `instante` (y sigue corriendo): para codigos de un paso conocido."""
        self.desfase = instante - datetime.now(UTC)


@pytest.fixture
def reloj(monkeypatch: pytest.MonkeyPatch) -> RelojAdelantable:
    falso = RelojAdelantable()
    monkeypatch.setattr(RelojDelSistema, "ahora", lambda self: falso.ahora())
    # La cache de sesiones (memoria local) fija y revisa el vencimiento con `time.time()`.
    monkeypatch.setattr("django.core.cache.backends.base.time", falso)
    monkeypatch.setattr("django.core.cache.backends.locmem.time", falso)
    return falso
