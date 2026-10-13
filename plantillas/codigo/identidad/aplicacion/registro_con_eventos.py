"""`RegistroDeAccesos` que ademas publica los eventos de D.5.2.

Envuelve al registro de intentos y acciones: guarda la fila y publica sus eventos en la MISMA
transaccion, que abre `unidad_de_trabajo` (la composicion inyecta `transaction.atomic`; aqui no se
importa Django). Si algo falla, no queda la fila sin su evento ni el evento sin su fila.
"""

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime

from identidad.aplicacion.eventos import eventos_de_accion, eventos_de_intento
from identidad.aplicacion.puertos import RegistroDeAccesos
from identidad.dominio.acceso import AccionDeCuenta, Factor, Motivo, Resultado
from nucleo.puertos.eventos import PublicadorDeEventos


@dataclass(frozen=True, slots=True)
class RegistroDeAccesosConEventos:
    registro: RegistroDeAccesos
    publicador: PublicadorDeEventos
    huella_de_correo: Callable[[str], str]
    unidad_de_trabajo: Callable[[], AbstractContextManager[object]]

    def registrar_intento(
        self,
        *,
        correo_capturado: str,
        usuario_id: str | None,
        factor: Factor,
        resultado: Resultado,
        motivo: Motivo,
        ip: str,
        momento: datetime,
    ) -> int:
        with self.unidad_de_trabajo():
            fila_id = self.registro.registrar_intento(
                correo_capturado=correo_capturado,
                usuario_id=usuario_id,
                factor=factor,
                resultado=resultado,
                motivo=motivo,
                ip=ip,
                momento=momento,
            )
            for evento in eventos_de_intento(
                fila_id,
                usuario_id=usuario_id,
                huella_correo=self.huella_de_correo(correo_capturado),
                factor=factor,
                resultado=resultado,
                motivo=motivo,
                momento=momento,
            ):
                self.publicador.publicar(evento)
        return fila_id

    def registrar_accion(
        self,
        *,
        accion: AccionDeCuenta,
        usuario_objetivo_id: str,
        hecha_por_id: str | None,
        momento: datetime,
        detalle: Mapping[str, object] | None = None,
    ) -> int:
        with self.unidad_de_trabajo():
            fila_id = self.registro.registrar_accion(
                accion=accion,
                usuario_objetivo_id=usuario_objetivo_id,
                hecha_por_id=hecha_por_id,
                momento=momento,
                detalle=detalle,
            )
            for evento in eventos_de_accion(
                fila_id,
                accion=accion,
                usuario_objetivo_id=usuario_objetivo_id,
                hecha_por_id=hecha_por_id,
                momento=momento,
                detalle=detalle,
            ):
                self.publicador.publicar(evento)
        return fila_id
