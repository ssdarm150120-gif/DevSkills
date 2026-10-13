"""Raíz de composición: qué adaptador se conecta a cada puerto (D.1.4, D.6.2).

Cada puerto compartido de `nucleo.puertos` que habla con un sistema externo tiene un adaptador real
y uno falso. El entorno elige por variable (`APP_ADAPTADOR_<PUERTO>`), y cada puerto elegible se
declara en `PUERTOS_ELEGIBLES`. El esqueleto no trae ninguno: el proyecto agrega los suyos (el
README del código trae la receta, con su adaptador falso y su prueba de contrato).

En desarrollo y pruebas el valor por defecto es `falso` (D.6.2: sistemas externos simulados). En
**producción** la aplicación se niega a arrancar con un adaptador falso. Un valor que aún no tiene
implementación deja el puerto sin conectar: pedirlo falla con `PuertoSinAdaptador`, no con un falso
silencioso.

Excepción de desarrollo: el Compose de dev corre con `settings.prod` (endurecido) pero necesita los
falsos. Para eso y solo para eso existe `APP_PERMITIR_ADAPTADORES_FALSOS`, que **solo vale si todos
los `ALLOWED_HOSTS` son de la propia máquina** (`localhost`, `127.0.0.1`, `[::1]`). Un servidor real
tiene su nombre público, así que la variable ahí también hace fallar el arranque.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured

from configuracion import entorno
from nucleo.puertos import FabricaDePublicadores, RegistroDeConsumidores, registro

FALSO = "falso"
HOSTS_DE_LA_MAQUINA = frozenset({"localhost", "127.0.0.1", "[::1]"})


@dataclass(frozen=True, slots=True)
class PuertoElegible:
    """Un puerto cuyo adaptador se elige por variable de entorno."""

    variable: str  # por ejemplo `APP_ADAPTADOR_ERP`
    validos: tuple[str, ...]  # siempre incluye `falso`
    por_defecto_en_produccion: str  # el adaptador real


# El proyecto declara aquí sus puertos con adaptador elegible. Ejemplo (no es parte del esqueleto):
#     PuertoElegible("APP_ADAPTADOR_ERP", (FALSO, "real"), "real"),
PUERTOS_ELEGIBLES: tuple[PuertoElegible, ...] = ()


def elegir(variable: str, por_defecto: str, validos: Sequence[str]) -> str:
    """El adaptador que pide la variable de entorno; falla si no es uno de los conocidos."""
    valor = entorno.texto(variable, por_defecto).strip().lower()
    if valor not in validos:
        raise ImproperlyConfigured(f"{variable} debe ser uno de {', '.join(validos)}: {valor!r}")
    return valor


def elegir_en_desarrollo() -> dict[str, str]:
    """Adaptador de cada puerto elegible para `settings.dev`: `falso` salvo que la variable diga
    otra cosa."""
    return {p.variable: elegir(p.variable, FALSO, p.validos) for p in PUERTOS_ELEGIBLES}


def falsos() -> dict[str, str]:
    """Todos los puertos elegibles con su adaptador falso (`settings.pruebas`)."""
    return {puerto.variable: FALSO for puerto in PUERTOS_ELEGIBLES}


def elegir_en_produccion(hosts_permitidos: Sequence[str]) -> dict[str, str]:
    """Adaptador de cada puerto para `settings.prod`: rechaza los falsos salvo en la propia máquina.

    `hosts_permitidos` debe ser una secuencia NO vacía de textos. Un `str` suelto (`"localhost"` se
    leería letra por letra) lanza `TypeError`; una lista vacía lanza `ImproperlyConfigured`, porque
    `set() <= HOSTS_DE_LA_MAQUINA` es verdadero y daría permiso a los falsos sin ningún host.
    """
    if isinstance(hosts_permitidos, str | bytes):
        raise TypeError(
            f"hosts_permitidos debe ser una lista de hosts, no un texto: {hosts_permitidos!r}"
        )
    if not hosts_permitidos:
        raise ImproperlyConfigured(
            "elegir_en_produccion necesita al menos un host en ALLOWED_HOSTS para decidir si "
            "admite adaptadores falsos"
        )
    falsos_permitidos = entorno.booleana("APP_PERMITIR_ADAPTADORES_FALSOS", False)
    if falsos_permitidos and not set(hosts_permitidos) <= HOSTS_DE_LA_MAQUINA:
        raise ImproperlyConfigured(
            "APP_PERMITIR_ADAPTADORES_FALSOS solo se admite si ALLOWED_HOSTS son de la propia "
            "máquina (localhost, 127.0.0.1, [::1]): un servidor real nunca usa adaptadores falsos"
        )
    elegidos = {
        puerto.variable: elegir(puerto.variable, puerto.por_defecto_en_produccion, puerto.validos)
        for puerto in PUERTOS_ELEGIBLES
    }
    if not falsos_permitidos:
        for variable, valor in elegidos.items():
            if valor == FALSO:
                raise ImproperlyConfigured(
                    f"{variable}=falso no se admite en producción: la aplicación se niega a "
                    "arrancar con un adaptador falso (DISENO D.1.4)"
                )
    return elegidos


def conectar(elegidos: Mapping[str, str]) -> None:
    """Conecta a cada puerto elegible el adaptador elegido.

    El esqueleto no tiene puertos elegibles, así que no conecta nada. El proyecto agrega aquí un
    bloque por puerto: con `falso`, conecta el adaptador falso de su módulo (por su `api_publica`);
    con el real, el adaptador real; si el real aún no existe, deja el puerto SIN conectar y lo
    registra como advertencia (nunca un falso silencioso).
    """
    desconocidos = set(elegidos) - {puerto.variable for puerto in PUERTOS_ELEGIBLES}
    if desconocidos:
        raise ImproperlyConfigured(
            f"Adaptadores elegidos para puertos no declarados: {', '.join(sorted(desconocidos))}"
        )


def conectar_segundo_factor() -> None:
    """Conecta el verificador TOTP de `identidad` al puerto `VerificadorSegundoFactor`.

    No tiene versión falsa que elegir: la llave de cifrado sale de `APP_LLAVE_SEGUNDO_FACTOR`
    (obligatoria en producción). Si el puerto no estuviera conectado, `identidad` falla cerrado: un
    rol sensible no entra solo con la contraseña (ADR del segundo factor).
    """
    from identidad.adaptadores.salida.segundo_factor import VerificadorTotp
    from identidad.aplicacion.puertos import VerificadorSegundoFactor

    registro.conectar(VerificadorSegundoFactor, VerificadorTotp())


def conectar_bus_de_eventos() -> None:
    """Conecta el bus de eventos (ADR del outbox, D.5.1): el registro de consumidores y la fábrica
    de publicadores (uno por módulo: cada módulo solo publica sus eventos).

    El registro nace vacío; cada módulo suscribe a sus consumidores desde aquí (por ejemplo,
    `auditoria` cuando exista su bitácora). Un evento sin consumidores se guarda y no genera
    entregas.
    """
    from nucleo.adaptadores.publicador import FabricaDePublicadoresDjango

    consumidores = RegistroDeConsumidores()
    registro.conectar(RegistroDeConsumidores, consumidores)
    registro.conectar(FabricaDePublicadores, FabricaDePublicadoresDjango(consumidores))
