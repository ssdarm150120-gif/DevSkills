"""Crea la carpeta de un proyecto nuevo a partir de las plantillas de DevSkills.

    python crear_proyecto.py --destino <ruta> --nombre "<Nombre>" --slug <slug> --puerto-base <N>
        [--puertos-reservados 5432,...] [--autor "<Autor>"] [--sin-git]

Qué hace:

1. Copia `plantillas/raiz/*` (incluidos los archivos ocultos) a la raíz del proyecto,
   `plantillas/codigo` a `codigo/`, `plantillas/documentacion` a `documentacion/` y
   `plantillas/analisis` a `documentacion/analisis/`.
2. Sustituye los marcadores `{{...}}` en todos los archivos de texto (ver `MARCADORES`).
3. Salvo con `--sin-git`: `git init -b main`, `git add -A` y un primer commit.

Reglas del host que valida: el proyecto recibe un rango propio de 50 puertos, `[N, N+49]`, que no
puede incluir puertos privilegiados (menores a 1024), pasar de 65535 ni contener ninguno de los
puertos reservados del host (por defecto 5432, donde suele vivir el PostgreSQL de otro sistema).

Solo usa la biblioteca estándar (Python 3.12). Escribe en UTF-8 y con fin de línea LF.
"""

import argparse
import datetime
import re
import shutil
import subprocess
import sys
import unicodedata
from collections.abc import Sequence
from pathlib import Path

PLANTILLAS = Path(__file__).resolve().parents[3] / "plantillas"
TAMANO_DEL_RANGO = 50
PUERTO_MINIMO = 1024
PUERTO_MAXIMO = 65535
PATRON_SLUG = re.compile(r"[a-z][a-z0-9-]*")
# Carpetas y archivos que nunca se copian (residuos de haber corrido algo dentro de las plantillas).
IGNORADOS = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pgdata", ".pgdata_pruebas", ".venv", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".import_linter_cache",
)
MENSAJE_DEL_COMMIT = "chore: bootstrap project from devskills"
# El nombre y el autor se escriben tal cual en archivos de varios formatos (TOML, JSON, YAML, `.env`,
# Markdown, Mermaid). En vez de escapar por tipo de archivo, se rechaza lo que rompería alguno:
# comillas dobles y barra invertida (cadenas de TOML y JSON), `$`, `{` y `}` (interpolación de Compose y
# marcadores `{{...}}`), `#` (comentarios de YAML y `.env`) y el acento grave.
CARACTERES_PROHIBIDOS = '"\\$#{}`'
LARGO_MAXIMO_DEL_TEXTO = 100


class ErrorDeCreacion(Exception):
    """Un dato no es válido o el destino no se puede usar; el mensaje se le muestra a quien llama."""


def leer_puertos(texto: str) -> tuple[int, ...]:
    """`"5432, 8080"` -> `(5432, 8080)`. Vacío es una lista vacía."""
    puertos: list[int] = []
    for parte in texto.split(","):
        limpio = parte.strip()
        if not limpio:
            continue
        if not limpio.isascii() or not limpio.isdecimal():
            raise ErrorDeCreacion(f"Puerto reservado inválido: {limpio!r} (se esperan números)")
        puerto = int(limpio)
        if not 1 <= puerto <= PUERTO_MAXIMO:
            raise ErrorDeCreacion(f"Puerto reservado fuera de rango (1 a {PUERTO_MAXIMO}): {puerto}")
        puertos.append(puerto)
    return tuple(sorted(set(puertos)))


def validar_texto(etiqueta: str, valor: str, *, obligatorio: bool) -> str:
    """El nombre o el autor, sin espacios en los extremos, o `ErrorDeCreacion` si algún formato se rompería."""
    limpio = valor.strip()
    if obligatorio and not limpio:
        raise ErrorDeCreacion(f"El {etiqueta} es obligatorio")
    if len(limpio) > LARGO_MAXIMO_DEL_TEXTO:
        raise ErrorDeCreacion(f"El {etiqueta} no puede pasar de {LARGO_MAXIMO_DEL_TEXTO} caracteres")
    for caracter in limpio:
        categoria = unicodedata.category(caracter)
        if categoria.startswith("C") or categoria in ("Zl", "Zp"):
            raise ErrorDeCreacion(
                f"El {etiqueta} no puede llevar saltos de línea, tabuladores ni otros caracteres de control "
                f"(se encontró U+{ord(caracter):04X})"
            )
        if caracter in CARACTERES_PROHIBIDOS:
            raise ErrorDeCreacion(
                f"El {etiqueta} no puede llevar {caracter!r}: se escribe sin escapar en archivos TOML, JSON, "
                f"YAML y .env, y rompería alguno. Prohibidos: {' '.join(CARACTERES_PROHIBIDOS)}"
            )
    return limpio


def validar_slug(slug: str) -> str:
    if not PATRON_SLUG.fullmatch(slug) or slug.endswith("-") or "--" in slug:
        raise ErrorDeCreacion(
            f"Slug inválido: {slug!r}. Usa minúsculas, dígitos y guiones, empezando con una letra "
            "(por ejemplo `inventario` o `mesa-de-ayuda`)"
        )
    return slug


def validar_rango(puerto_base: int, reservados: Sequence[int]) -> range:
    """El rango `[puerto_base, puerto_base + 49]` del proyecto, si cumple las reglas del host."""
    rango = range(puerto_base, puerto_base + TAMANO_DEL_RANGO)
    if rango.start < PUERTO_MINIMO:
        raise ErrorDeCreacion(
            f"El puerto base debe ser {PUERTO_MINIMO} o mayor (los menores son privilegiados): "
            f"{puerto_base}"
        )
    if rango[-1] > PUERTO_MAXIMO:
        raise ErrorDeCreacion(
            f"El rango {rango.start}-{rango[-1]} pasa del último puerto válido ({PUERTO_MAXIMO})"
        )
    chocan = [puerto for puerto in reservados if puerto in rango]
    if chocan:
        raise ErrorDeCreacion(
            f"El rango {rango.start}-{rango[-1]} contiene puertos reservados del host: "
            f"{', '.join(map(str, chocan))}. Elige otro puerto base"
        )
    return rango


def validar_destino(destino: Path) -> Path:
    if destino.exists() and not destino.is_dir():
        raise ErrorDeCreacion(f"El destino existe y no es una carpeta: {destino}")
    if destino.is_dir() and any(destino.iterdir()):
        raise ErrorDeCreacion(f"El destino ya existe y no está vacío: {destino}")
    return destino


def marcadores(
    *, nombre: str, slug: str, rango: range, reservados: Sequence[int], autor: str, fecha: str
) -> dict[str, str]:
    """Los marcadores `{{...}}` y su valor para este proyecto."""
    return {
        "{{NOMBRE_PROYECTO}}": nombre,
        "{{SLUG}}": slug,
        "{{SLUG_GUION_BAJO}}": slug.replace("-", "_"),
        "{{PUERTO_BASE}}": str(rango.start),
        # Derivados del puerto base: los dos primeros del rango son los de nginx.
        "{{PUERTO_HTTP}}": str(rango.start),
        "{{PUERTO_HTTPS}}": str(rango.start + 1),
        "{{PUERTO_FINAL}}": str(rango[-1]),
        "{{PUERTOS_RESERVADOS}}": ", ".join(map(str, reservados)) or "ninguno",
        "{{FECHA}}": fecha,
        "{{AUTOR}}": autor,
    }


def sustituir_en(carpeta: Path, valores: dict[str, str]) -> int:
    """Sustituye los marcadores en los archivos de texto de `carpeta`. Devuelve cuántos cambió."""
    cambiados = 0
    for ruta in sorted(carpeta.rglob("*")):
        if not ruta.is_file() or ".git" in ruta.relative_to(carpeta).parts:
            continue
        try:
            texto = ruta.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue  # binario: se copia tal cual
        nuevo = texto
        for marcador, valor in valores.items():
            nuevo = nuevo.replace(marcador, valor)
        if nuevo != texto:
            # En bytes y con LF: el modo texto de Windows escribiría CRLF.
            ruta.write_bytes(nuevo.replace("\r\n", "\n").encode("utf-8"))
            cambiados += 1
    return cambiados


def copiar(origen: Path, destino: Path) -> int:
    """Copia `origen` dentro de `destino` (lo crea). Si `origen` no existe o está vacía, no hace
    nada. Devuelve cuántos archivos copió."""
    if not origen.is_dir() or not any(origen.iterdir()):
        return 0
    shutil.copytree(origen, destino, dirs_exist_ok=True, ignore=IGNORADOS)
    return sum(1 for ruta in destino.rglob("*") if ruta.is_file())


def iniciar_git(destino: Path) -> str:
    """`git init -b main`, `git add -A` y el primer commit. Devuelve el hash corto."""

    def git(*argumentos: str) -> str:
        resultado = subprocess.run(  # noqa: S603
            ["git", *argumentos],  # noqa: S607
            cwd=destino,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if resultado.returncode != 0:
            raise ErrorDeCreacion(
                f"git {' '.join(argumentos)} falló: {resultado.stderr.strip() or resultado.stdout}"
            )
        return resultado.stdout.strip()

    if shutil.which("git") is None:
        raise ErrorDeCreacion("No se encontró `git`; instálalo o usa --sin-git")
    git("init", "-b", "main")
    git("add", "-A")
    git("commit", "-m", MENSAJE_DEL_COMMIT)
    return git("rev-parse", "--short", "HEAD")


def crear(
    *,
    destino: Path,
    nombre: str,
    slug: str,
    puerto_base: int,
    reservados: Sequence[int],
    autor: str,
    con_git: bool,
    plantillas: Path = PLANTILLAS,
    fecha: str | None = None,
) -> dict[str, object]:
    """Crea el proyecto y devuelve un resumen. Lanza `ErrorDeCreacion` si algo no es válido."""
    nombre = validar_texto("nombre del proyecto", nombre, obligatorio=True)
    autor = validar_texto("autor", autor, obligatorio=False)
    validar_slug(slug)
    rango = validar_rango(puerto_base, reservados)
    if not plantillas.is_dir():
        raise ErrorDeCreacion(f"No se encontraron las plantillas en {plantillas}")
    validar_destino(destino)
    destino.mkdir(parents=True, exist_ok=True)

    copiados = {
        "raiz": copiar(plantillas / "raiz", destino),
        "codigo": copiar(plantillas / "codigo", destino / "codigo"),
        "documentacion": copiar(plantillas / "documentacion", destino / "documentacion"),
        "analisis": copiar(plantillas / "analisis", destino / "documentacion" / "analisis"),
    }
    valores = marcadores(
        nombre=nombre,
        slug=slug,
        rango=rango,
        reservados=reservados,
        autor=autor,
        fecha=fecha or datetime.date.today().isoformat(),
    )
    sustituidos = sustituir_en(destino, valores)
    commit = iniciar_git(destino) if con_git else None
    return {
        "destino": destino,
        "copiados": copiados,
        "sustituidos": sustituidos,
        "rango": rango,
        "commit": commit,
    }


def main(argv: Sequence[str] | None = None) -> int:
    for flujo in (sys.stdout, sys.stderr):  # acentos legibles tambien en la consola de Windows
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Crea un proyecto nuevo a partir de las plantillas de DevSkills."
    )
    parser.add_argument("--destino", required=True, type=Path, help="carpeta del proyecto nuevo")
    parser.add_argument("--nombre", required=True, help="nombre legible del proyecto")
    parser.add_argument(
        "--slug",
        required=True,
        help="identificador en minúsculas: prefijo de Docker, proyecto de Compose y de engram",
    )
    parser.add_argument(
        "--puerto-base",
        required=True,
        type=int,
        help=f"inicio del rango de {TAMANO_DEL_RANGO} puertos del host propio del proyecto",
    )
    parser.add_argument(
        "--puertos-reservados",
        default="5432",
        help="puertos del host que el proyecto nunca debe usar, separados por comas (5432)",
    )
    parser.add_argument("--autor", default="", help="autor de los documentos")
    parser.add_argument("--sin-git", action="store_true", help="no inicializa el repositorio")
    args = parser.parse_args(argv)

    try:
        resumen = crear(
            destino=args.destino.expanduser().resolve(),
            nombre=args.nombre,
            slug=args.slug,
            puerto_base=args.puerto_base,
            reservados=leer_puertos(args.puertos_reservados),
            autor=args.autor,
            con_git=not args.sin_git,
        )
    except ErrorDeCreacion as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    rango = resumen["rango"]
    assert isinstance(rango, range)  # noqa: S101
    print(f"Proyecto creado en {resumen['destino']}")
    copiados = resumen["copiados"]
    assert isinstance(copiados, dict)  # noqa: S101
    for parte, cantidad in copiados.items():
        estado = f"{cantidad} archivos" if cantidad else "sin plantilla (se omitió)"
        print(f"  {parte}: {estado}")
    print(f"  marcadores sustituidos en {resumen['sustituidos']} archivos")
    print(f"  prefijo de Docker y proyecto de engram: {args.slug}")
    print(f"  rango de puertos del host: {rango.start}-{rango[-1]}")
    if resumen["commit"]:
        print(f"  primer commit: {resumen['commit']} ({MENSAJE_DEL_COMMIT})")
    else:
        print("  sin repositorio de git (--sin-git)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
