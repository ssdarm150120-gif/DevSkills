"""Lectura de configuracion desde variables de entorno (nada de secretos en el codigo)."""

import ipaddress
import os
import re
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ImproperlyConfigured
from publicsuffixlist import PublicSuffixList

_VERDADEROS = {"1", "true", "yes", "si", "on"}
_FALSOS = {"0", "false", "no", "off", ""}

# Valor por defecto de `SECRET_KEY` en desarrollo. Esta aqui (y no en `dev.py`) para que `prod.py`
# pueda rechazarlo sin importar `dev`, que exige `DATABASE_URL` al cargarse.
SECRET_KEY_DE_DESARROLLO = "dev-solo-para-desarrollo-no-usar-en-produccion"  # noqa: S105  # nosec B105
# Valor por defecto de `APP_LLAVE_HUELLA` en desarrollo y pruebas (en produccion se rechaza).
LLAVE_HUELLA_DE_DESARROLLO = "dev-llave-de-huella-solo-para-desarrollo"
# Valor por defecto de `APP_LLAVE_SEGUNDO_FACTOR` en dev y pruebas (en produccion se rechaza).
LLAVE_SEGUNDO_FACTOR_DE_DESARROLLO = "dev-llave-del-segundo-factor-solo-para-desarrollo"
LARGO_MINIMO_SECRET_KEY = 50  # el mismo umbral de `manage.py check --deploy` (security.W009)


def requerida(nombre: str, ayuda: str = "") -> str:
    """Devuelve la variable o falla rapido si falta (se usa para secretos en produccion).

    `ayuda` se agrega al mensaje de error para indicar como definirla (por ejemplo en desarrollo).
    """
    valor = os.environ.get(nombre)
    if valor is None or valor.strip() == "":
        mensaje = f"Falta la variable de entorno obligatoria {nombre}"
        raise ImproperlyConfigured(f"{mensaje}. {ayuda}" if ayuda else mensaje)
    return valor


def texto(nombre: str, por_defecto: str) -> str:
    valor = os.environ.get(nombre)
    return por_defecto if valor is None or valor.strip() == "" else valor


def booleana(nombre: str, por_defecto: bool) -> bool:
    valor = os.environ.get(nombre)
    if valor is None:
        return por_defecto
    normalizado = valor.strip().lower()
    if normalizado in _VERDADEROS:
        return True
    if normalizado in _FALSOS:
        return False
    raise ImproperlyConfigured(f"Valor booleano invalido en {nombre}: {valor!r}")


def entero(nombre: str, por_defecto: int, *, minimo: int, maximo: int | None = None) -> int:
    """Lee un entero del entorno, dentro de `[minimo, maximo]`; si no, falla al arrancar."""
    valor = os.environ.get(nombre)
    if valor is None or valor.strip() == "":
        return por_defecto
    try:
        numero = int(valor.strip())
    except ValueError:
        raise ImproperlyConfigured(f"{nombre} debe ser un entero: {valor!r}") from None
    if numero < minimo or (maximo is not None and numero > maximo):
        rango = f">= {minimo}" if maximo is None else f"entre {minimo} y {maximo}"
        raise ImproperlyConfigured(f"{nombre} debe ser {rango}: {numero}")
    return numero


MARCADOR_DE_EJEMPLO = "cambiar"  # los valores ficticios de `.env.ejemplo` llevan CAMBIAR


def sin_marcador_de_ejemplo(nombre: str, valor: str) -> str:
    """Rechaza un secreto copiado tal cual de `.env.ejemplo` (contiene `CAMBIAR`).

    Sirve tambien para URLs con clave (`postgres://usuario:CAMBIAR...@host/base`). Un secreto
    real (hexadecimal o aleatorio) no contiene esa palabra.

    El archivo de ejemplo lleva valores ficticios: si alguien lo copia a `.env` sin reemplazarlos,
    el arranque falla en vez de levantar un servicio con una clave publica en el repositorio.
    """
    if MARCADOR_DE_EJEMPLO in valor.strip().casefold():
        raise ImproperlyConfigured(
            f"{nombre} conserva el valor de ejemplo de .env.ejemplo: usa un secreto real"
        )
    return valor


def lista(valor: str) -> list[str]:
    """Separa una lista por comas, sin elementos vacios."""
    return [elemento.strip() for elemento in valor.split(",") if elemento.strip()]


# Areas de la base IANA con zonas geograficas (`Area/Ciudad`). Todo lo demas es legado o ambiguo:
# `US/Eastern`, `Canada/...`, `Mexico/General`, `EST5EDT`, `posixrules`, `Etc/GMT+5` (signo
# invertido), `Cuba`, `Japan`...
_AREAS_IANA = frozenset(
    {
        "Africa",
        "America",
        "Antarctica",
        "Arctic",
        "Asia",
        "Atlantic",
        "Australia",
        "Europe",
        "Indian",
        "Pacific",
    }
)
# Alias legados dentro de `Australia/` (la ciudad es el nombre canonico, no el estado).
_ALIAS_LEGADOS_DE_AUSTRALIA = frozenset(
    {"ACT", "Canberra", "LHI", "NSW", "North", "Queensland", "South", "Tasmania", "Victoria"}
    | {"West", "Yancowinna"}
)


def zona_horaria(nombre: str, *, variable: str) -> str:
    """Valida un nombre de zona horaria IANA (`America/Mexico_City`) y lo devuelve sin espacios.

    Falla al arrancar, no al mostrar la primera fecha: una zona mal escrita no debe descubrirse
    cuando un usuario abre su pantalla de inicio. Solo se admiten `UTC` y las zonas geograficas
    `Area/Ciudad`: los nombres legados o ambiguos (`US/Eastern`, `EST5EDT`, `posixrules`, las
    abreviaturas sin `/`, `Etc/...`) se rechazan aunque `zoneinfo` los conozca.
    """
    limpio = nombre.strip()
    area, _, ciudad = limpio.partition("/")
    canonica = limpio == "UTC" or (
        area in _AREAS_IANA
        and bool(ciudad)
        and not (area == "Australia" and ciudad in _ALIAS_LEGADOS_DE_AUSTRALIA)
    )
    if canonica:
        try:
            ZoneInfo(limpio)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            canonica = False
    if not canonica:
        raise ImproperlyConfigured(
            f"{variable}: zona horaria desconocida, legada o ambigua: {nombre!r} "
            "(usa UTC o una zona Area/Ciudad como America/Mexico_City)"
        )
    return limpio


HSTS_MINIMO_SEGUNDOS = 31536000  # un ano: lo que exige la precarga de HSTS
_MODOS_SSL_CON_CIFRADO = frozenset({"require", "verify-ca", "verify-full"})


def debilidades_de_transporte(*, redireccion_https: bool, hsts_segundos: int) -> list[str]:
    """Que ajustes de transporte debilitan la configuracion de produccion (lista vacia: ninguno)."""
    debilidades: list[str] = []
    if not redireccion_https:
        debilidades.append("SECURE_SSL_REDIRECT esta apagado (nada redirige HTTP a HTTPS)")
    if hsts_segundos < HSTS_MINIMO_SEGUNDOS:
        debilidades.append(
            f"HSTS_SEGUNDOS={hsts_segundos} es menor a un ano ({HSTS_MINIMO_SEGUNDOS})"
        )
    return debilidades


def exigir_tls_en_datos(base: dict[str, Any], url_redis: str) -> None:
    """Falla si la base o Redis viajan sin cifrar (`APP_EXIGIR_TLS_DATOS=true`).

    La base debe pedir `sslmode=require`, `verify-ca` o `verify-full` en `DATABASE_URL`, y Redis
    debe usar el esquema `rediss://`. Se recomienda `verify-full`: `require` cifra pero no
    comprueba que el servidor sea quien dice ser.
    """
    modo = str(base.get("OPTIONS", {}).get("sslmode", "")).lower()
    if modo not in _MODOS_SSL_CON_CIFRADO:
        raise ImproperlyConfigured(
            "APP_EXIGIR_TLS_DATOS exige TLS hacia la base: agrega ?sslmode=verify-full (o "
            f"verify-ca / require) a DATABASE_URL; sslmode actual: {modo or 'sin definir'}"
        )
    if not url_redis.lower().startswith("rediss://"):
        raise ImproperlyConfigured(
            "APP_EXIGIR_TLS_DATOS exige TLS hacia Redis: REDIS_URL debe usar el esquema rediss://"
        )


_PATRON_IDIOMA = re.compile(r"[a-z]{2,3}(-[a-z0-9]{2,8})*")


def idioma(valor: str, *, variable: str) -> str:
    """Valida un codigo de idioma de Django (`es`, `en`, `pt-br`) y lo devuelve en minusculas.

    Falla al arrancar: un codigo mal escrito haria que Django use el ingles sin avisar.
    """
    limpio = valor.strip().lower().replace("_", "-")
    if not _PATRON_IDIOMA.fullmatch(limpio):
        raise ImproperlyConfigured(
            f"{variable}: idioma invalido: {valor!r} (usa un codigo como es, en o es-mx)"
        )
    return limpio


PREFIJO_SECRET_KEY_INSEGURA = "django-insecure-"  # noqa: S105  # nosec B105  # lo rechazamos
# W009 de `check --deploy` pide 5; aqui se exigen 16: son llaves de cifrado y de HMAC, y
# `secrets.token_urlsafe(48)` (la forma documentada de generarlas) da ~40 distintos de 64.
CARACTERES_DISTINTOS_MINIMOS = 16


def _clave_de_produccion(nombre: str, valor: str) -> str:
    """Valida una clave secreta de produccion (`SECRET_KEY`, huella y segundo factor).

    Se rechaza si, tras `strip()`: mide menos de 50 caracteres; empieza con `django-insecure-`;
    CONTIENE la clave de desarrollo (aunque este rellenada hasta los 50); ambas comparaciones
    ignoran mayusculas (`casefold()`); o tiene menos de 16 caracteres distintos (mas estricto que
    `security.W009`, que pide 5): `"k" * 50` y `"abcde" * 10` cumplen el largo pero no son secreto.
    Aplica igual a `SECRET_KEY`, `APP_LLAVE_HUELLA` y `APP_LLAVE_SEGUNDO_FACTOR`.
    """
    clave = sin_marcador_de_ejemplo(nombre, valor.strip())
    if len(clave) < LARGO_MINIMO_SECRET_KEY:
        raise ImproperlyConfigured(
            f"{nombre} debe tener al menos {LARGO_MINIMO_SECRET_KEY} caracteres en produccion"
        )
    comparable = (
        clave.casefold()
    )  # "DJANGO-INSECURE-" y las mezclas de mayusculas tambien se rechazan
    if comparable.startswith(PREFIJO_SECRET_KEY_INSEGURA):
        raise ImproperlyConfigured(
            f"{nombre} no puede empezar con {PREFIJO_SECRET_KEY_INSEGURA!r} en produccion"
        )
    if SECRET_KEY_DE_DESARROLLO.casefold() in comparable:
        raise ImproperlyConfigured(f"{nombre} no puede contener la clave de desarrollo")
    if LLAVE_HUELLA_DE_DESARROLLO.casefold() in comparable:
        raise ImproperlyConfigured(f"{nombre} no puede contener la llave de desarrollo")
    if LLAVE_SEGUNDO_FACTOR_DE_DESARROLLO.casefold() in comparable:
        raise ImproperlyConfigured(f"{nombre} no puede contener la llave de desarrollo")
    if len(set(clave)) < CARACTERES_DISTINTOS_MINIMOS:
        raise ImproperlyConfigured(
            f"{nombre} debe tener al menos {CARACTERES_DISTINTOS_MINIMOS} caracteres distintos"
        )
    return clave


def secret_key_de_produccion(valor: str) -> str:
    """`SECRET_KEY` de produccion. Devuelve el valor ya sin espacios en los extremos."""
    return _clave_de_produccion("SECRET_KEY", valor)


def llave_de_huella_de_produccion(valor: str) -> str:
    """`APP_LLAVE_HUELLA` de produccion: la llave del HMAC de la huella del correo.

    Mismas reglas que `SECRET_KEY`; ademas debe ser DISTINTA de ella, para que una fuga de una no
    comprometa a la otra (se compara en `settings/prod.py`).
    """
    return _clave_de_produccion("APP_LLAVE_HUELLA", valor)


def llave_segundo_factor_de_produccion(valor: str) -> str:
    """`APP_LLAVE_SEGUNDO_FACTOR` de produccion: la llave que cifra el secreto del segundo factor.

    Mismas reglas que `SECRET_KEY`; ademas debe ser DISTINTA de ella y de `APP_LLAVE_HUELLA` (se
    compara en `settings/prod.py`). Si se pierde o se cambia, los secretos ya guardados no se pueden
    descifrar: los usuarios con rol sensible tendrian que enrolarse de nuevo (reinicio por el
    Administrador).
    """
    return _clave_de_produccion("APP_LLAVE_SEGUNDO_FACTOR", valor)


def _ip_sin_especificar(texto_ip: str) -> bool | None:
    """`True` si es una IP no especificada, `False` si es otra IP, `None` si no es IP."""
    try:
        return ipaddress.ip_address(texto_ip).is_unspecified
    except ValueError:
        return None


# Public Suffix List COMPLETA (incluidos los sufijos privados: `github.io`, `herokuapp.com`...). La
# lista viaja EMPAQUETADA con la dependencia `publicsuffixlist` (archivo `public_suffix_list.dat`
# dentro del paquete): se lee del disco, SIN red, al importar este modulo. Nunca se llama a
# `publicsuffixlist.update`, que es lo unico del paquete que descarga.
_LISTA_DE_SUFIJOS_PUBLICOS = PublicSuffixList()


def _es_sufijo_publico(dominio: str) -> bool:
    """`True` si `dominio` ES un sufijo publico (`com`, `com.mx`, `co.uk`, `github.io`...)."""
    return bool(_LISTA_DE_SUFIJOS_PUBLICOS.publicsuffix(dominio) == dominio.casefold())


def _host_invalido_en_produccion(host: str) -> str | None:
    """Motivo por el que `host` no es admisible en produccion, o `None` si lo es."""
    if host.startswith("*"):
        return "no puede empezar con '*' (Django solo admite '*' solo, y aqui esta prohibido)"
    if host.startswith("["):
        # IPv6 entre corchetes: Django la compara tal cual, sin puerto (`[::1]:80` nunca empareja).
        if not host.endswith("]"):
            return "una IPv6 entre corchetes no admite puerto ni texto despues del ']'"
        sin_especificar = _ip_sin_especificar(host[1:-1])
        if sin_especificar is None or ":" not in host[1:-1]:
            return "los corchetes solo admiten una direccion IPv6 valida"
    else:
        sin_especificar = _ip_sin_especificar(host)  # IPv4 o IPv6 sin corchetes
        if ":" in host and not sin_especificar:
            return "no puede llevar ':' fuera de corchetes (un puerto, o una IPv6 sin corchetes)"
    if sin_especificar:
        return "no puede ser una direccion no especificada (0.0.0.0, ::)"
    if host.startswith("."):
        etiquetas = host[1:].split(".")
        if len(etiquetas) < 2 or not all(etiquetas):
            return "un comodin '.dominio' necesita al menos dos etiquetas (p. ej. .empresa.example)"
        if _es_sufijo_publico(host[1:]):
            return (
                "un comodin como '.com.mx', '.co.uk' o '.github.io' es un sufijo publico (Public "
                "Suffix List): habilita CUALQUIER dominio bajo el; usa un comodin que cuelgue de "
                "un dominio registrado (por ejemplo .empresa.example)"
            )
    return None


def hosts_permitidos_de_produccion(valor: str) -> list[str]:
    """Valida `ALLOWED_HOSTS` de produccion.

    Debe haber al menos un host (una lista vacia, como la de `","`, oculta un error) y se rechaza
    todo host que empiece con `*` (`"*"` acepta cualquier `Host`; `*.dominio` ni siquiera existe en
    Django), las direcciones no especificadas (`0.0.0.0`, `::`, `[::]`, `[0:0:0:0:0:0:0:0]`: se
    detectan con `ipaddress`, con o sin corchetes), todo host con puerto
    (`app.empresa.example:8000`, `[::]:80`: Django nunca empareja un patron con puerto) y los
    comodines `.dominio` demasiado amplios (`.`, `.com`). Se aceptan `app.empresa.example`,
    `.empresa.example`, una IPv4 especifica
    (`10.0.0.5`) y una IPv6 especifica entre corchetes (`[2001:db8::1]`).

    SUFIJOS PUBLICOS: un comodin `.x` se rechaza si `x` ES un sufijo publico segun la Public Suffix
    List completa (`.com`, `.com.mx`, `.gob.mx`, `.co.uk`, `.nom.es`, `.ne.jp` y los privados
    como `.github.io` o `.herokuapp.com`): habilitaria CUALQUIER host bajo el. Se aceptan los que
    cuelgan de un dominio registrado (`.empresa.example`, `.empresa.com.mx`). La lista va
    empaquetada con
    `publicsuffixlist` y se consulta sin red; se actualiza al subir la version de la dependencia.
    """
    hosts = lista(valor)
    if not hosts:
        raise ImproperlyConfigured("ALLOWED_HOSTS no tiene ningun host valido en produccion")
    for host in hosts:
        if motivo := _host_invalido_en_produccion(host):
            raise ImproperlyConfigured(f"ALLOWED_HOSTS: {host!r} {motivo}")
    return hosts


def parsear_url_base_de_datos(url: str) -> dict[str, Any]:
    """Convierte `postgres://usuario:clave@host:puerto/nombre?opcion=valor` en un `DATABASES[...]`.

    Solo acepta PostgreSQL. Las opciones de la consulta (por ejemplo `host=/ruta` o
    `sslmode=require`) pasan a `OPTIONS`; el host de la consulta reemplaza al de la autoridad.
    """
    partes = urlsplit(url)
    if partes.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured("DATABASE_URL debe usar el esquema postgres:// o postgresql://")
    opciones = dict(parse_qsl(partes.query))
    host = opciones.pop("host", None) or partes.hostname or ""
    config: dict[str, Any] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(partes.path.lstrip("/")),
        "USER": unquote(partes.username or ""),
        "PASSWORD": unquote(partes.password or ""),
        "HOST": host,
        "PORT": str(partes.port) if partes.port else "",
    }
    if opciones:
        config["OPTIONS"] = opciones
    return config
