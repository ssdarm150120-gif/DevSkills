"""Raíz de composición de los puertos compartidos (D.1.4).

`configuracion` conecta aquí el adaptador elegido al arrancar; los consumidores piden el puerto por
su contrato y nunca importan al adaptador ni a otro módulo. Si el puerto no está conectado, falla
con un error claro en vez de devolver `None`. Python puro, sin Django.

Un puerto se conecta UNA sola vez: conectar otro adaptador al mismo puerto lanza `PuertoYaConectado`
(un reemplazo silencioso escondería un error de configuración). Las pruebas que necesitan cambiar el
adaptador usan `nucleo.pruebas.aislamiento.Aislamiento`, que vacía el registro y lo restaura.
"""

from collections.abc import Callable
from typing import Any, cast

_conectados: dict[type[Any], object] = {}


class PuertoSinAdaptador(RuntimeError):
    """Se pidió un puerto al que nadie le conectó un adaptador.

    Es un error de configuración, no una búsqueda fallida: por eso hereda de `RuntimeError` y un
    `except LookupError` (`KeyError`, `IndexError`) de quien consume el puerto no lo traga.
    """


class PuertoYaConectado(RuntimeError):
    """Se intentó conectar un adaptador a un puerto que ya tiene uno."""


def conectar(puerto: type[Any], adaptador: object) -> None:
    """Conecta `adaptador` como la implementación de `puerto`, que no debe tener otra.

    Verifica en ejecución que el adaptador tenga los métodos del puerto (`runtime_checkable`).
    Lanza `PuertoYaConectado` si el puerto ya tiene un adaptador.
    """
    if not isinstance(adaptador, puerto):
        raise TypeError(f"{type(adaptador).__name__} no implementa {puerto.__name__}")
    if puerto in _conectados:
        raise PuertoYaConectado(
            f"{puerto.__name__} ya tiene un adaptador conectado "
            f"({type(_conectados[puerto]).__name__}): un puerto se conecta una sola vez"
        )
    _conectados[puerto] = adaptador


def obtener[T](puerto: Callable[..., T]) -> T:
    """El adaptador conectado a `puerto` (se pide por el contrato: `obtener(PuertoDeEjemplo)`)."""
    try:
        return cast(T, _conectados[cast(type[Any], puerto)])
    except KeyError:
        nombre = getattr(puerto, "__name__", str(puerto))
        raise PuertoSinAdaptador(
            f"{nombre} no tiene un adaptador conectado: revisa la configuración"
        ) from None
