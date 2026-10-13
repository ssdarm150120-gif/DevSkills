"""Errores comunes de los puertos hacia sistemas externos (DISENO D.1.4). Python puro.

Los adaptadores de salida traducen los fallos del proveedor a estas excepciones tipadas. El outbox
(`nucleo.puertos.entrega`) usa `reintentable` para decidir si reintenta o deja la entrega en error,
y `reintentar_en_segundos` cuando el proveedor sugiere cuánto esperar.

Cada puerto puede definir errores más específicos heredando de `ErrorDeIntegracion`.
"""

MAXIMO_REINTENTO_EN_SEGUNDOS = 86_400  # un día


class ErrorDeIntegracion(Exception):
    """Base común de los fallos al hablar con un sistema externo."""

    # El outbox reintenta solo los errores reintentables.
    reintentable: bool = False


class ErrorTemporalDeIntegracion(ErrorDeIntegracion):
    """El proveedor no respondió o devolvió un fallo pasajero (red, 5xx, tiempo agotado)."""

    reintentable = True


class SolicitudRechazada(ErrorDeIntegracion):
    """El proveedor rechazó la solicitud por su contenido (no existe, no está aprobada o sus
    parámetros no cuadran).

    Reintentar no sirve: queda en error hasta que alguien corrija lo que se envía.
    """

    reintentable = False


class LimiteDeSolicitudes(ErrorDeIntegracion):
    """El proveedor limitó la tasa o la cuota; se puede reintentar más tarde."""

    reintentable = True

    def __init__(self, mensaje: str = "", *, reintentar_en_segundos: int | None = None) -> None:
        """`reintentar_en_segundos`: espera sugerida por el proveedor, de 0 a 86 400 (un día).

        Un valor fuera de rango, un `bool` o un número no entero lanza `ValueError`: el outbox
        programa el reintento con este número y no debe recibir basura del proveedor.
        """
        super().__init__(mensaje)
        if reintentar_en_segundos is not None and (
            type(reintentar_en_segundos) is not int
            or not 0 <= reintentar_en_segundos <= MAXIMO_REINTENTO_EN_SEGUNDOS
        ):
            raise ValueError(
                "reintentar_en_segundos debe ser un entero entre 0 y "
                f"{MAXIMO_REINTENTO_EN_SEGUNDOS}: {reintentar_en_segundos!r}"
            )
        self.reintentar_en_segundos = reintentar_en_segundos
