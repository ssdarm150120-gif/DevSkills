"""Corre gitleaks sobre los archivos versionados y los nuevos no ignorados.

Uso (desde cualquier carpeta dentro del repositorio):
    python gitleaks_archivos.py [--repo RUTA] [--modo auto|nativo|docker] [--imagen IMAGEN]

Toma la lista de `git ls-files -co --exclude-standard` (versionados más nuevos que no
ignora `.gitignore`), la copia a una carpeta temporal y la escanea con `gitleaks dir`.
Así no se escanean `.venv/`, `.pgdata/` ni otros archivos ignorados, y tampoco se lee
ningún `.env` ignorado.

Códigos de salida:
- 0: sin hallazgos.
- 1: gitleaks encontró secretos (no hagas commit hasta resolverlos).
- 2: la herramienta NO está disponible o no pudo correr (sin binario, sin Docker, o el
  demonio de Docker apagado). No es un hallazgo ni un escaneo bueno: instálala y repite.

Modos:
- `auto` (por defecto): usa el gitleaks nativo (en el PATH o en las rutas típicas de winget);
  si no, Docker.
- `nativo`: exige el binario `gitleaks` (winget, brew o la release de GitHub).
- `docker`: exige Docker; es la alternativa cuando no quieres instalar nada.

Docker NO es requisito: con el binario nativo basta. Sin ninguno de los dos, el script
falla con un mensaje que dice cómo instalarlo (nunca da el escaneo por bueno).

Un falso positivo se suprime con `gitleaks:allow` en la MISMA línea, con el motivo; nunca
se excluyen carpetas ni archivos del escaneo.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess  # nosec B404: se invocan git, gitleaks y docker con listas de argumentos
import sys
import tempfile
from pathlib import Path

# En Windows la consola y las tuberías usan la página de códigos local (cp1252): sin esto los acentos
# salen corruptos. La salida de DevSkills siempre es UTF-8.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8")

IMAGEN_PREDETERMINADA = "zricethezav/gitleaks:v8.21.2@sha256:0e99e8821643ea5b235718642b93bb32486af9c8162c8b8731f7cbdc951a7f46"
COMO_INSTALAR = (
    "Instala gitleaks: Windows `winget install Gitleaks.Gitleaks`, macOS `brew install gitleaks`, "
    "Linux la release de https://github.com/gitleaks/gitleaks/releases; o usa Docker (--modo docker)."
)


SALIDA_SIN_HALLAZGOS = 0
SALIDA_HALLAZGOS = 1
SALIDA_HERRAMIENTA_NO_DISPONIBLE = 2


def buscar_gitleaks() -> str | None:
    """Ruta del binario nativo: primero el PATH y luego las rutas típicas de winget.

    winget a veces instala gitleaks sin agregarlo al PATH de la sesión; en ese caso vive en
    LOCALAPPDATA/Microsoft/WinGet/Links o en LOCALAPPDATA/Microsoft/WinGet/Packages/Gitleaks.Gitleaks_*.
    """
    en_path = shutil.which("gitleaks")
    if en_path:
        return en_path
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    winget = Path(local) / "Microsoft" / "WinGet"
    candidatos = [winget / "Links" / "gitleaks.exe"]
    candidatos += sorted((winget / "Packages").glob("Gitleaks.Gitleaks_*/gitleaks.exe"))
    for candidato in candidatos:
        if candidato.is_file():
            return str(candidato)
    return None


def docker_responde() -> bool:
    """True si hay Docker y su demonio contesta (el binario solo no basta)."""
    if shutil.which("docker") is None:
        return False
    try:
        return (
            subprocess.run(  # nosec B603 B607
                ["docker", "info"], check=False, capture_output=True, timeout=30
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def no_disponible(mensaje: str) -> SystemExit:
    print(f"gitleaks: HERRAMIENTA NO DISPONIBLE (no es un hallazgo). {mensaje}", file=sys.stderr)
    return SystemExit(SALIDA_HERRAMIENTA_NO_DISPONIBLE)


def archivos_del_repo(repo: Path) -> list[str]:
    salida = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    return [r for r in salida.decode("utf-8").split("\0") if r]


def elegir_modo(modo: str) -> tuple[str, str]:
    """Devuelve (`nativo`|`docker`, ejecutable) o termina con código 2 si no hay con qué escanear."""
    nativo = buscar_gitleaks() if modo in ("auto", "nativo") else None
    if modo == "nativo":
        if nativo is None:
            raise no_disponible(f"No encuentro el binario gitleaks. {COMO_INSTALAR}")
        return "nativo", nativo
    if modo == "auto" and nativo is not None:
        return "nativo", nativo
    if docker_responde():
        return "docker", "docker"
    razon = "Docker no está instalado o su demonio está apagado"
    if modo == "docker":
        raise no_disponible(f"{razon}. {COMO_INSTALAR}")
    raise no_disponible(f"No hay con qué escanear: no hay gitleaks y {razon}. {COMO_INSTALAR}")


def comando_de(modo: str, ejecutable: str, copia: Path, imagen: str) -> list[str]:
    if modo == "nativo":
        return [ejecutable, "dir", str(copia), "--no-banner", "--redact"]
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "-v",
        f"{copia}:/repo:ro",
        imagen,
        "dir",
        "/repo",
        "--no-banner",
        "--redact",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="Ruta dentro del repositorio (por defecto, la actual)")
    parser.add_argument("--modo", choices=["auto", "nativo", "docker"], default="auto")
    parser.add_argument("--imagen", default=IMAGEN_PREDETERMINADA, help="Imagen de Docker de gitleaks")
    args = parser.parse_args()
    modo, ejecutable = elegir_modo(args.modo)

    raiz = Path(
        subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "--show-toplevel"],
            cwd=args.repo,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    )
    rutas = archivos_del_repo(raiz)
    with tempfile.TemporaryDirectory(prefix="gitleaks_") as temporal:
        copia = Path(temporal) / "repo"
        copia.mkdir(parents=True, exist_ok=True)
        for relativa in rutas:
            origen = raiz / relativa
            if not origen.is_file():
                continue  # borrado en el árbol de trabajo
            destino = copia / relativa
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, destino)
        print(f"Escaneando {len(rutas)} archivos de {raiz} con gitleaks ({modo})...")
        resultado = subprocess.run(  # nosec B603
            comando_de(modo, ejecutable, copia, args.imagen), check=False
        )
    if resultado.returncode == 0:
        print("gitleaks: sin hallazgos.")
        return SALIDA_SIN_HALLAZGOS
    if resultado.returncode == 1:
        print("gitleaks: HAY HALLAZGOS. No hagas commit hasta resolverlos.", file=sys.stderr)
        return SALIDA_HALLAZGOS
    print(
        f"gitleaks: la herramienta falló (código {resultado.returncode}) sin informar hallazgos; "
        "el escaneo NO cuenta como bueno. Revisa la salida de arriba.",
        file=sys.stderr,
    )
    return SALIDA_HERRAMIENTA_NO_DISPONIBLE


if __name__ == "__main__":
    sys.exit(main())
