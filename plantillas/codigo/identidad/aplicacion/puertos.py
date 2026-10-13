"""Puertos de `identidad` (DISENO D.1.4): lo que los casos de uso necesitan de afuera.

Sin Django: los adaptadores de `adaptadores/salida` los implementan y las pruebas usan falsos.
"""

from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from identidad.dominio.acceso import AccionDeCuenta, Factor, Motivo, Resultado
from identidad.dominio.aviso_reuso import IntentoDeReuso
from identidad.dominio.segundo_factor import ResultadoCodigo


@dataclass(frozen=True, slots=True)
class Cuenta:
    """Lo que el ingreso necesita saber de un usuario (sin el modelo de Django)."""

    id: str
    correo: str
    activo: bool
    roles: frozenset[str]
    exige_segundo_factor: bool
    debe_cambiar_contrasena: bool
    fallos_contrasena: int
    bloqueada_hasta: datetime | None
    hash_contrasena: str
    # Cambia con la contrasena (y con lo que cierre las sesiones del usuario): una etapa pendiente
    # del ingreso lo guarda y lo compara al completarse.
    sello_sesion: str
    # Contador del segundo factor, SEPARADO del de la contrasena (D.3.10).
    fallos_codigo: int = 0
    # Gestion de usuarios: nombre para mostrar.
    nombre: str = ""

    @property
    def etiqueta(self) -> str:
        """Como se nombra al usuario en pantalla y en los avisos: su nombre o, sin el, su correo."""
        return self.nombre or self.correo


class Reloj(Protocol):
    def ahora(self) -> datetime: ...


class RepositorioCuentas(Protocol):
    def por_correo(self, correo: str) -> Cuenta | None: ...

    def por_id(self, usuario_id: str) -> Cuenta | None: ...

    def guardar_conteo(
        self, usuario_id: str, fallos: int, bloqueada_hasta: datetime | None
    ) -> None: ...

    def trabajo_equivalente_sin_cuenta(self) -> None:
        """Hace el mismo trabajo de base de datos que un intento con cuenta existente (leer sus
        roles y guardar el conteo de fallos) sobre un usuario que no existe, para que el tiempo de
        respuesta no distinga "correo inexistente" de "contrasena incorrecta"."""
        ...

    def guardar_conteo_codigo(
        self, usuario_id: str, fallos: int, bloqueada_hasta: datetime | None
    ) -> None:
        """Guarda el contador de fallos del codigo. El bloqueo (`bloqueada_hasta`) es el mismo de la
        cuenta: cinco fallos de codigo bloquean igual que cinco de contrasena."""
        ...

    def rotar_sello(self, usuario_id: str) -> None:
        """Cambia el sello de sesion: cierra todas las sesiones y las etapas pendientes del usuario
        (por ejemplo, al reiniciar su segundo factor)."""
        ...

    def actualizar_hash(self, usuario_id: str, hash_contrasena: str) -> None:
        """Reemplaza el hash por uno con parametros vigentes SIN cambiar el sello de sesion
        (cambiarlo cerraria todas las sesiones del usuario)."""
        ...

    def guardar_contrasena(
        self, usuario_id: str, hash_contrasena: str, *, temporal: bool, ahora: datetime
    ) -> None:
        """Guarda el hash, pone o quita la marca de temporal y cambia el sello de sesion."""
        ...

    def crear(
        self,
        *,
        correo: str,
        hash_contrasena: str,
        roles: frozenset[str],
        temporal: bool,
        ahora: datetime,
        nombre: str = "",
    ) -> Cuenta: ...

    def listar(self) -> Sequence[Cuenta]:
        """Todas las cuentas (activas y desactivadas), ordenadas por correo."""
        ...

    def guardar_datos(self, usuario_id: str, *, nombre: str) -> None: ...

    def guardar_roles(
        self, usuario_id: str, roles: frozenset[str], *, asignado_por: str, ahora: datetime
    ) -> None:
        """Deja exactamente esos roles (agrega los nuevos y quita los que sobran)."""
        ...

    def fijar_activo(self, usuario_id: str, activo: bool) -> None: ...

    def bloquear_administradores_activos(self) -> frozenset[str]:
        """Ids de los Administradores ACTIVOS, bloqueando sus filas (orden estable por id) hasta
        que termine la transaccion: dos cambios simultaneos no pueden dejar al sistema sin
        ninguno."""
        ...


@dataclass(frozen=True, slots=True)
class RolDelCatalogo:
    codigo: str
    nombre: str
    exige_segundo_factor: bool


class CatalogoDeRoles(Protocol):
    def roles(self) -> Sequence[RolDelCatalogo]: ...


class RegistroDeAccesos(Protocol):
    """Registro de solo insercion de intentos y acciones. Devuelve el id de la fila."""

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
    ) -> int: ...

    def registrar_accion(
        self,
        *,
        accion: AccionDeCuenta,
        usuario_objetivo_id: str,
        hecha_por_id: str | None,
        momento: datetime,
        detalle: Mapping[str, object] | None = None,
    ) -> int:
        """`detalle` guarda lo que cambio (roles, campos...); NUNCA una contrasena, un secreto ni
        un dato personal completo."""
        ...


class ServicioContrasenas(Protocol):
    @property
    def filtradas(self) -> Container[str]: ...

    def hashear(self, contrasena: str) -> str: ...

    def verificar(self, contrasena: str, hash_contrasena: str) -> bool: ...

    def requiere_rehash(self, hash_contrasena: str) -> bool:
        """Verdadero si el hash usa un algoritmo o parametros que ya no son los vigentes."""
        ...

    def verificar_ficticia(self, contrasena: str) -> None:
        """Gasta el mismo tiempo que `verificar` (el correo no existe) y no devuelve nada."""
        ...

    def generar_temporal(self) -> str: ...


@dataclass(frozen=True, slots=True)
class Enrolamiento:
    """Lo que el usuario necesita para registrar su aplicacion de codigos.

    Es el secreto EN CLARO: se muestra en pantalla, nunca se guarda ni se registra.
    """

    # `repr=False`: el secreto no debe salir en un `repr` (trazas, logs, mensajes de pytest).
    clave: str = field(repr=False)  # Base32, para teclearla en la aplicacion
    uri: str = field(repr=False)  # `otpauth://totp/...`, lo que lleva el codigo QR


@runtime_checkable
class VerificadorSegundoFactor(Protocol):
    """Segundo factor de. Sin adaptador conectado, un rol sensible no entra.

    El adaptador es dueno del secreto y de su cifrado; los casos de uso solo ven resultados.
    """

    def disponible_para(self, usuario_id: str) -> bool:
        """Falso si no se puede verificar a este usuario (sin llave, o su secreto no se puede
        descifrar con la llave actual): el caso de uso falla cerrado."""
        ...

    def esta_enrolado(self, usuario_id: str) -> bool:
        """Verdadero si el usuario ya confirmo su aplicacion de codigos."""
        ...

    def iniciar_enrolamiento(self, usuario_id: str, correo: str, ahora: datetime) -> Enrolamiento:
        """Genera (o recupera, si aun no se confirma) el secreto y devuelve lo que se muestra.

        `ahora` (el reloj inyectado) es el momento de creacion del secreto. Lanza `EtapaInvalida`
        si el usuario ya confirmo su segundo factor: enrolarlo otra vez no le corresponde."""
        ...

    def verificar(
        self, usuario_id: str, codigo: str, ahora: datetime, *, confirmando: bool
    ) -> ResultadoCodigo:
        """Revisa el codigo. Si se acepta, guarda el paso usado (un codigo no se acepta dos veces)
        y, con `confirmando`, deja confirmado el enrolamiento. Si no, no cambia nada."""
        ...

    def reiniciar(self, usuario_id: str) -> bool:
        """Borra el segundo factor del usuario. Devuelve si habia uno."""
        ...


class AvisosDeReuso(Protocol):
    """Lo que el aviso por reuso de un codigo necesita de la base (D.3.10).

    La marca es el ID del ultimo `IntentoIngreso` mostrado (no una fecha: no depende del reloj).
    Se llama DENTRO de una transaccion: primero se lee sin bloqueo (`marca`); solo si hay un aviso
    pendiente se bloquea la fila del usuario (`bloquear_marca`) y se vuelve a comprobar.
    """

    def marca(self, usuario_id: str) -> int | None:
        """Id del ultimo intento cuyo aviso ya vio el usuario (`None`: nunca), SIN bloqueo.

        Lanza `CuentaNoDisponible` si el usuario no existe."""
        ...

    def bloquear_marca(self, usuario_id: str) -> int | None:
        """Como `marca`, pero bloquea la fila del usuario hasta el fin de la transaccion. Dos
        lecturas simultaneas se turnan: la segunda ve la marca que dejo la primera."""
        ...

    def ultimo_intento_de_reuso(
        self, usuario_id: str, *, despues_de: int | None
    ) -> IntentoDeReuso | None:
        """El intento de mayor id con motivo `codigo_repetido` del usuario, solo entre los de id
        mayor que `despues_de` (si lo hay). `None` si no hay ninguno."""
        ...

    def marcar_visto(self, usuario_id: str, *, hasta_id: int) -> None:
        """Deja la marca en `hasta_id` (el intento mostrado). Nunca retrocede: una marca mayor se
        conserva."""
        ...


class ZonaHoraria(Protocol):
    def zona(self) -> ZoneInfo:
        """Zona horaria con la que se muestran las fechas al usuario (se guardan en UTC). Nunca
        falla: sale de la configuracion, validada al arrancar."""
        ...
