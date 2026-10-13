"""Eventos de dominio y puerto publicador (DISENO, D.5.1). Python puro.

Un evento informa algo que YA ocurrió (nombre en pasado) y es autosuficiente: lleva los datos que
sus consumidores necesitan. Lo publica el caso de uso por el puerto `PublicadorDeEventos`; el
adaptador lo guarda en la tabla del outbox, en la MISMA transacción que el cambio de negocio, y un
despachador lo entrega después a cada consumidor, al menos una vez (los consumidores son
idempotentes por `evento_id`).
"""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from nucleo.puertos.catalogo_eventos import (
    CATALOGO,
    CLAVES_PERMITIDAS,
    CLAVES_PERMITIDAS_POR_EVENTO,
    CUALQUIER_MODULO,
    LARGO_MAXIMO_TERMINACION,
    PATRON_DE_CORREO,
    PATRON_DE_TELEFONO,
    PROHIBIDAS_COMO_PALABRA,
    PROHIBIDAS_COMO_SUBCADENA,
)

LARGO_MAXIMO_PAYLOAD = 16_384  # caracteres: un evento es un aviso, no un documento
LARGO_MAXIMO_AGREGADO = 64


class EventoInvalido(Exception):
    """El evento no cumple el contrato del bus (nombre, campos, valores o momento)."""


class EventoDesconocido(EventoInvalido):
    """El nombre no está en el catálogo de D.5.2."""


class EmisorNoAutorizado(EventoInvalido):
    """El módulo que publica no es el emisor del evento en el catálogo (D.5.2)."""


_CORREO = re.compile(PATRON_DE_CORREO)
_TELEFONO = re.compile(PATRON_DE_TELEFONO)
_PALABRAS = re.compile(r"[a-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _limpiar(texto: str) -> str:
    """NFKD (ancho completo a ASCII), sin marcas combinantes ni caracteres de formato/ancho cero."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) not in ("Mn", "Cf"))


def _palabras_de_clave(clave: str) -> list[str]:
    """`telefónoCliente`, `E-Mail` y `ＣＯＲＲＥＯ` -> sus palabras en minúsculas y sin acentos."""
    return _PALABRAS.findall(_CAMEL.sub("_", _limpiar(clave)).lower())


def _forma_prohibida(texto: str) -> str | None:
    """Si el texto parece un correo o un teléfono internacional, de qué dato se trata."""
    limpio = _limpiar(texto)
    if _CORREO.search(limpio):
        return "un correo electrónico"
    if _TELEFONO.search(limpio):
        return "un teléfono"
    return None


def _clave_prohibida(palabras: list[str], nombre_del_evento: str) -> bool:
    normalizada = "_".join(palabras)
    if normalizada in CLAVES_PERMITIDAS or normalizada in CLAVES_PERMITIDAS_POR_EVENTO.get(
        nombre_del_evento, frozenset()
    ):
        return False
    compacta = "".join(palabras)
    if any(palabra in compacta for palabra in PROHIBIDAS_COMO_SUBCADENA):
        return True
    return bool(set(palabras) & PROHIBIDAS_COMO_PALABRA)


def _validar_texto(texto: str, ruta: str) -> None:
    dato = _forma_prohibida(texto)
    if dato is not None:
        raise EventoInvalido(f"{ruta}: {dato} nunca viaja en un evento")


def _validar_valor(valor: object, ruta: str, nombre_del_evento: str) -> None:
    if isinstance(valor, str):
        _validar_texto(valor, ruta)
        return
    if valor is None or isinstance(valor, bool | int | float):
        return
    if isinstance(valor, list | tuple):
        for posicion, elemento in enumerate(valor):
            _validar_valor(elemento, f"{ruta}[{posicion}]", nombre_del_evento)
        return
    if isinstance(valor, Mapping):
        for clave, elemento in valor.items():
            if not isinstance(clave, str):
                raise EventoInvalido(f"{ruta}: las claves del payload son texto")
            _validar_texto(clave, f"{ruta}.<clave>")  # una clave tampoco puede ser un dato
            palabras = _palabras_de_clave(clave)
            if "terminacion" in palabras:
                if elemento is not None and not (
                    isinstance(elemento, str) and len(elemento) <= LARGO_MAXIMO_TERMINACION
                ):
                    raise EventoInvalido(
                        f"{ruta}.{clave}: una terminación son los últimos "
                        f"{LARGO_MAXIMO_TERMINACION} caracteres, nunca el dato completo"
                    )
                continue
            if _clave_prohibida(palabras, nombre_del_evento):
                raise EventoInvalido(f"{ruta}.{clave}: ese dato nunca viaja en un evento")
            _validar_valor(elemento, f"{ruta}.{clave}", nombre_del_evento)
        return
    raise EventoInvalido(f"{ruta}: tipo no admitido en un evento ({type(valor).__name__})")


@dataclass(frozen=True, slots=True)
class EventoDeDominio:
    """Un evento de D.5.2. `agregado_id` es la identidad de la cosa a la que le ocurrió."""

    nombre: str
    agregado_id: str
    ocurrido_en: datetime
    payload: Mapping[str, Any]
    evento_id: UUID = field(default_factory=uuid4)
    version_esquema: int = 0  # 0 = la vigente del catálogo
    id_correlacion: str = ""

    def __post_init__(self) -> None:
        especificacion = CATALOGO.get(self.nombre)
        if especificacion is None:
            raise EventoDesconocido(f"{self.nombre!r} no está en el catálogo de eventos (D.5.2)")
        if not self.agregado_id or len(self.agregado_id) > LARGO_MAXIMO_AGREGADO:
            raise EventoInvalido("agregado_id es obligatorio y de hasta 64 caracteres")
        _validar_texto(self.agregado_id, "agregado_id")
        _validar_texto(self.id_correlacion, "id_correlacion")
        if self.ocurrido_en.tzinfo is None or self.ocurrido_en.utcoffset() != timedelta(0):
            raise EventoInvalido("ocurrido_en debe venir en UTC (con zona horaria)")
        if self.ocurrido_en.tzinfo is not UTC:
            object.__setattr__(self, "ocurrido_en", self.ocurrido_en.astimezone(UTC))
        faltantes = [campo for campo in especificacion.campos if campo not in self.payload]
        if faltantes:
            raise EventoInvalido(f"{self.nombre}: faltan campos del payload: {faltantes}")
        for grupo in especificacion.una_de:
            if not any(campo in self.payload for campo in grupo):
                raise EventoInvalido(
                    f"{self.nombre}: el payload necesita al menos uno de estos campos: {grupo}"
                )
        _validar_valor(dict(self.payload), self.nombre, self.nombre)
        if len(repr(dict(self.payload))) > LARGO_MAXIMO_PAYLOAD:
            raise EventoInvalido(
                f"{self.nombre}: el payload pasa de {LARGO_MAXIMO_PAYLOAD} caracteres"
            )
        if self.version_esquema == 0:
            object.__setattr__(self, "version_esquema", especificacion.version_esquema)
        elif self.version_esquema < 1:
            raise EventoInvalido("version_esquema debe ser positiva")
        object.__setattr__(self, "payload", dict(self.payload))


class EventoFueraDeTransaccion(RuntimeError):
    """Se publicó un evento sin una transacción abierta: no iría junto con el cambio de negocio."""


def emisor_autorizado(evento: EventoDeDominio, modulo: str) -> bool:
    """Si `modulo` puede publicar ese evento según el catálogo (D.5.2)."""
    emisores = CATALOGO[evento.nombre].emisores
    return emisores == CUALQUIER_MODULO or modulo in emisores


@runtime_checkable
class PublicadorDeEventos(Protocol):
    def publicar(self, evento: EventoDeDominio) -> None:
        """Guarda el evento en el outbox, en la transacción en curso.

        Cada publicador es de UN módulo y solo publica los eventos que el catálogo le asigna: otro
        evento lanza `EmisorNoAutorizado`. La transacción la abre quien compone el caso de uso (o el
        adaptador de registro), nunca el llamador a mano; sin transacción abierta lanza
        `EventoFueraDeTransaccion`. Publicar dos veces el mismo `evento_id` no tiene efecto.
        """
        ...


@runtime_checkable
class FabricaDePublicadores(Protocol):
    def de(self, modulo: str) -> PublicadorDeEventos:
        """El publicador del módulo (`identidad`, `nucleo`...). `configuracion` lo entrega a cada
        módulo al componerlo; ningún módulo elige un nombre que no es el suyo."""
        ...
