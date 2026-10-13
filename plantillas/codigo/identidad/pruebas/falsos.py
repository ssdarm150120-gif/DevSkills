"""Falsos en memoria de los puertos de `identidad` (las pruebas no tocan base ni hashers reales)."""

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from identidad.aplicacion.puertos import Cuenta, Enrolamiento, RolDelCatalogo
from identidad.dominio.acceso import AccionDeCuenta, Factor, Motivo, Resultado
from identidad.dominio.aviso_reuso import IntentoDeReuso
from identidad.dominio.roles import CATALOGO_DE_ROLES, ROLES_CON_SEGUNDO_FACTOR
from identidad.dominio.segundo_factor import ResultadoCodigo

AHORA = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


class RelojFalso:
    def __init__(self, ahora: datetime = AHORA) -> None:
        self.valor = ahora

    def ahora(self) -> datetime:
        return self.valor

    def avanzar(self, **delta: float) -> None:
        self.valor += timedelta(**delta)


class ContrasenasFalsas:
    """Hash reversible y barato: `hash$<texto>`. Cuenta cuantas veces se verifico."""

    def __init__(self, filtradas: frozenset[str] = frozenset({"contrasena1234"})) -> None:
        self.filtradas = filtradas
        self.verificaciones = 0
        self.ficticias = 0

    def hashear(self, contrasena: str) -> str:
        return f"hash${contrasena}"

    def verificar(self, contrasena: str, hash_contrasena: str) -> bool:
        self.verificaciones += 1
        return hash_contrasena == f"hash${contrasena}"

    def verificar_ficticia(self, contrasena: str) -> None:
        self.ficticias += 1

    def requiere_rehash(self, hash_contrasena: str) -> bool:
        return hash_contrasena.startswith("viejo$")

    def generar_temporal(self) -> str:
        return "Temporal-Falsa-0001"


class CuentasEnMemoria:
    def __init__(self) -> None:
        self.cuentas: dict[str, Cuenta] = {}
        self.sellos: dict[str, int] = {}

    def agregar(self, cuenta: Cuenta) -> Cuenta:
        self.cuentas[cuenta.id] = cuenta
        self.sellos[cuenta.id] = 0
        return cuenta

    def actualizar_hash(self, usuario_id: str, hash_contrasena: str) -> None:
        # Sin tocar el sello (ni `sellos`): las sesiones siguen vivas.
        self.cuentas[usuario_id] = dataclasses.replace(
            self.cuentas[usuario_id], hash_contrasena=hash_contrasena
        )

    def trabajo_equivalente_sin_cuenta(self) -> None:
        self.trabajos_sin_cuenta = getattr(self, "trabajos_sin_cuenta", 0) + 1

    def por_correo(self, correo: str) -> Cuenta | None:
        return next((c for c in self.cuentas.values() if c.correo == correo), None)

    def por_id(self, usuario_id: str) -> Cuenta | None:
        return self.cuentas.get(usuario_id)

    def guardar_conteo(
        self, usuario_id: str, fallos: int, bloqueada_hasta: datetime | None
    ) -> None:
        self.cuentas[usuario_id] = dataclasses.replace(
            self.cuentas[usuario_id], fallos_contrasena=fallos, bloqueada_hasta=bloqueada_hasta
        )

    def guardar_conteo_codigo(
        self, usuario_id: str, fallos: int, bloqueada_hasta: datetime | None
    ) -> None:
        self.cuentas[usuario_id] = dataclasses.replace(
            self.cuentas[usuario_id], fallos_codigo=fallos, bloqueada_hasta=bloqueada_hasta
        )

    def rotar_sello(self, usuario_id: str) -> None:
        self.sellos[usuario_id] += 1
        self.cuentas[usuario_id] = dataclasses.replace(
            self.cuentas[usuario_id], sello_sesion=f"sello-{self.sellos[usuario_id]}"
        )

    def guardar_contrasena(
        self, usuario_id: str, hash_contrasena: str, *, temporal: bool, ahora: datetime
    ) -> None:
        self.cuentas[usuario_id] = dataclasses.replace(
            self.cuentas[usuario_id],
            hash_contrasena=hash_contrasena,
            debe_cambiar_contrasena=temporal,
            sello_sesion=f"sello-{self.sellos[usuario_id] + 1}",
        )
        self.sellos[usuario_id] += 1

    def crear(
        self,
        *,
        correo: str,
        hash_contrasena: str,
        roles: frozenset[str],
        temporal: bool,
        ahora: datetime,
        nombre: str = "",
    ) -> Cuenta:
        return self.agregar(
            Cuenta(
                id=f"u-{len(self.cuentas) + 1}",
                correo=correo,
                activo=True,
                roles=roles,
                exige_segundo_factor=bool(roles & ROLES_CON_SEGUNDO_FACTOR),
                debe_cambiar_contrasena=temporal,
                fallos_contrasena=0,
                bloqueada_hasta=None,
                hash_contrasena=hash_contrasena,
                sello_sesion="sello-0",
                nombre=nombre,
            )
        )

    def listar(self) -> Sequence[Cuenta]:
        return sorted(self.cuentas.values(), key=lambda c: c.correo)

    def guardar_datos(self, usuario_id: str, *, nombre: str) -> None:
        self.cuentas[usuario_id] = dataclasses.replace(self.cuentas[usuario_id], nombre=nombre)

    def guardar_roles(
        self, usuario_id: str, roles: frozenset[str], *, asignado_por: str, ahora: datetime
    ) -> None:
        self.cuentas[usuario_id] = dataclasses.replace(
            self.cuentas[usuario_id],
            roles=roles,
            exige_segundo_factor=bool(roles & ROLES_CON_SEGUNDO_FACTOR),
        )

    def bloquear_administradores_activos(self) -> frozenset[str]:
        return frozenset(
            c.id for c in self.cuentas.values() if c.activo and "administrador" in c.roles
        )

    def fijar_activo(self, usuario_id: str, activo: bool) -> None:
        self.cuentas[usuario_id] = dataclasses.replace(self.cuentas[usuario_id], activo=activo)


class AccesosEnMemoria:
    def __init__(self) -> None:
        self.intentos: list[dict[str, object]] = []
        self.acciones: list[dict[str, object]] = []

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
        self.intentos.append(
            {"usuario_id": usuario_id, "resultado": resultado, "motivo": motivo, "ip": ip}
        )
        return len(self.intentos)

    def registrar_accion(
        self,
        *,
        accion: AccionDeCuenta,
        usuario_objetivo_id: str,
        hecha_por_id: str | None,
        momento: datetime,
        detalle: Mapping[str, object] | None = None,
    ) -> int:
        registro: dict[str, object] = {
            "accion": accion,
            "objetivo": usuario_objetivo_id,
            "hecha_por": hecha_por_id,
        }
        if detalle:  # solo cuando hay detalle: las pruebas anteriores comparan el registro exacto
            registro["detalle"] = dict(detalle)
        self.acciones.append(registro)
        return len(self.acciones)


class VerificadorEnMemoria:
    """Segundo factor falso: un solo codigo bueno por usuario, que se puede usar una vez.

    No calcula TOTP (eso lo prueba el adaptador real): solo deja armar los casos de uso.
    """

    CODIGO_BUENO = "123456"

    def __init__(self, *, disponible: bool = True, enrolados: frozenset[str] = frozenset()) -> None:
        self.disponible = disponible
        self.enrolados: set[str] = set(enrolados)
        self.usados: set[tuple[str, str]] = set()
        self.reinicios: list[str] = []
        self.enrolamientos: list[tuple[str, datetime]] = []

    def disponible_para(self, usuario_id: str) -> bool:
        return self.disponible

    def esta_enrolado(self, usuario_id: str) -> bool:
        return usuario_id in self.enrolados

    def iniciar_enrolamiento(self, usuario_id: str, correo: str, ahora: datetime) -> Enrolamiento:
        self.enrolamientos.append((usuario_id, ahora))
        return Enrolamiento(clave="ABCDEFGH", uri=f"otpauth://totp/Falso:{correo}?secret=ABCDEFGH")

    def verificar(
        self, usuario_id: str, codigo: str, ahora: datetime, *, confirmando: bool
    ) -> ResultadoCodigo:
        if codigo != self.CODIGO_BUENO:
            return ResultadoCodigo.INCORRECTO
        if (usuario_id, codigo) in self.usados:
            return ResultadoCodigo.REPETIDO
        self.usados.add((usuario_id, codigo))
        if confirmando:
            self.enrolados.add(usuario_id)
        return ResultadoCodigo.ACEPTADO

    def reiniciar(self, usuario_id: str) -> bool:
        self.reinicios.append(usuario_id)
        habia = usuario_id in self.enrolados
        self.enrolados.discard(usuario_id)
        return habia


class CatalogoEnMemoria:
    def roles(self) -> Sequence[RolDelCatalogo]:
        return [
            RolDelCatalogo(
                codigo, codigo.replace("_", " ").title(), codigo in ROLES_CON_SEGUNDO_FACTOR
            )
            for codigo in CATALOGO_DE_ROLES
        ]


def cuenta(
    id: str = "u-1",
    correo: str = "ana@empresa.example",
    contrasena: str = "caballo-grapa-9Lunar",
    roles: frozenset[str] = frozenset({"usuario"}),
    **cambios: Any,
) -> Cuenta:
    base = Cuenta(
        id=id,
        correo=correo,
        activo=True,
        roles=roles,
        exige_segundo_factor=False,
        debe_cambiar_contrasena=False,
        fallos_contrasena=0,
        bloqueada_hasta=None,
        hash_contrasena=f"hash${contrasena}",
        sello_sesion="sello-0",
    )
    return dataclasses.replace(base, **cambios)


class AvisosEnMemoria:
    """Marca de "visto" e intentos de reuso en memoria.

    La marca es el id del ultimo intento mostrado. `intento` agrega un intento de reuso y devuelve
    su id (crecen en el orden en que se agregan, como en la base). `al_marcar` corre justo antes de
    dejar la marca: sirve para simular un intento nuevo que llega ENTRE la lectura y la marca.
    `bloqueos` cuenta cuantas veces se bloqueo la fila y `lecturas` cuantas veces se leyo sin
    bloqueo; `antes_de_bloquear` corre justo antes de tomar el bloqueo (otra pestaña que gana).
    """

    def __init__(self) -> None:
        self.visto_hasta: dict[str, int | None] = {}
        self.reusos: list[tuple[str, IntentoDeReuso]] = []
        self.bloqueos = 0
        self.lecturas = 0
        self.marcas: list[int] = []
        self.al_marcar: Callable[[], object] | None = None
        self.antes_de_bloquear: Callable[[], object] | None = None

    def intento(self, usuario_id: str, momento: datetime) -> int:
        identificador = len(self.reusos) + 1
        self.reusos.append((usuario_id, IntentoDeReuso(identificador, momento)))
        return identificador

    def marca(self, usuario_id: str) -> int | None:
        self.lecturas += 1
        return self.visto_hasta.get(usuario_id)

    def bloquear_marca(self, usuario_id: str) -> int | None:
        if self.antes_de_bloquear is not None:
            self.antes_de_bloquear()
        self.bloqueos += 1
        return self.visto_hasta.get(usuario_id)

    def ultimo_intento_de_reuso(
        self, usuario_id: str, *, despues_de: int | None
    ) -> IntentoDeReuso | None:
        pendientes = [
            intento
            for dueno, intento in self.reusos
            if dueno == usuario_id and (despues_de is None or intento.id > despues_de)
        ]
        return max(pendientes, key=lambda intento: intento.id, default=None)

    def marcar_visto(self, usuario_id: str, *, hasta_id: int) -> None:
        if self.al_marcar is not None:
            self.al_marcar()
        self.marcas.append(hasta_id)
        actual = self.visto_hasta.get(usuario_id)
        if actual is None or actual < hasta_id:
            self.visto_hasta[usuario_id] = hasta_id


class ZonaFalsa:
    """La zona horaria de la configuracion, fija para la prueba."""

    def __init__(self, nombre: str = "America/Mexico_City") -> None:
        self.nombre = nombre

    def zona(self) -> ZoneInfo:
        return ZoneInfo(self.nombre)
