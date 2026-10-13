"""Errores comunes de los casos de uso de `identidad`."""


class CuentaNoDisponible(Exception):
    """La cuenta no existe o esta desactivada."""


class EtapaInvalida(Exception):
    """La etapa pendiente ya no corresponde a la cuenta (sello distinto, o ya no aplica)."""


class RequiereSegundoFactor(Exception):
    """Los roles de la cuenta exigen segundo factor y no esta disponible (falla cerrado)."""


class CuentaBloqueada(Exception):
    """La cuenta esta bloqueada (por contrasenas o por codigos): no se sigue con el ingreso."""


class PermisoDenegado(Exception):
    """El actor no puede hacer esto (codigo de error: PERMISO_DENEGADO, DISENO D.5.6)."""

    codigo = "PERMISO_DENEGADO"

    def __init__(self, motivo: str = "No tienes permiso para esta acción") -> None:
        super().__init__(motivo)
        self.motivo = motivo


class ConflictoDeUsuario(Exception):
    """La accion choca con otro registro (correo repetido...).

    El mensaje es para el Administrador y no revela nada que el no deba ver.
    """
