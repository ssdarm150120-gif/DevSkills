"""Corre gitleaks sobre los archivos versionados y los nuevos no ignorados.

Uso (desde cualquier carpeta dentro del repositorio):
    python gitleaks_archivos.py [--repo RUTA] [--modo auto|nativo|docker] [--imagen IMAGEN]

Toma la lista de `git ls-files -co --exclude-standard` (versionados más nuevos que no
ignora `.gitignore`), la copia a una carpeta temporal y la escanea con `gitleaks dir`.
Así no se escanean `.venv/`, `.pgdata/` ni otros archivos ignorados, y tampoco se lee
ningún `.env` ignorado. Sale con el código de gitleaks: 0 sin hallazgos, 1 con hallazgos.

Modos:
- `auto` (por defecto): usa el gitleaks nativo si está en el PATH; si no, Docker.
- `nativo`: exige el binario `gitleaks` (winget, brew o la release de GitHub).
- `docker`: exige Docker; es la alternativa cuando no quieres instalar nada.

Docker NO es requisito: con el binario nativo basta. Sin ninguno de los dos, el script
falla con un mensaje que dice cómo instalarlo (nunca da el escaneo por bueno).

Un falso positivo se suprime con `gitleaks:allow` en la MISMA línea, con el motivo; nunca
se excluyen carpetas ni archivos del escaneo.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404: se invocan git, gitleaks y docker con listas de argumentos
import sys
import tempfile
from pathlib import Path

IMAGEN_PREDETERMINADA = "zricethezav/gitleaks:v8.21.2"
COMO_INSTALAR = (
    "Instala gitleaks: Windows `winget install Gitleaks.Gitleaks`, macOS `brew install gitleaks`, "
    "Linux la release de https://github.com/gitleaks/gitleaks/releases; o usa Docker (--modo docker)."
)


def archivos_del_repo(repo: Path) -> list[str]:
    salida = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    return [r for r in salida.decode("utf-8").split("\0") if r]


def elegir_modo(modo: str) -> str:
    """Devuelve `nativo` o `docker`, o termina con un mensaje si no hay con qué escanear."""
    hay_nativo = shutil.which("gitleaks") is not None
    hay_docker = shutil.which("docker") is not None
    if modo == "nativo" and not hay_nativo:
        raise SystemExit(f"No encuentro el binario gitleaks. {COMO_INSTALAR}")
    if modo == "docker" and not hay_docker:
        raise SystemExit(f"No encuentro docker. {COMO_INSTALAR}")
    if modo in ("nativo", "docker"):
        return modo
    if hay_nativo:
        return "nativo"
    if hay_docker:
        return "docker"
    raise SystemExit(f"No hay con qué escanear: ni gitleaks ni Docker. {COMO_INSTALAR}")


def comando_de(modo: str, copia: Path, imagen: str) -> list[str]:
    if modo == "nativo":
        return ["gitleaks", "dir", str(copia), "--no-banner", "--redact"]
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
    modo = elegir_modo(args.modo)

    raiz = Path(
        subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "--show-toplevel"],
            cwd=args.repo,
            check=True,
            capture_output=True,
            text=True,
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
            comando_de(modo, copia, args.imagen), check=False
        )
    if resultado.returncode == 0:
        print("gitleaks: sin hallazgos.")
    else:
        print("gitleaks: HAY HALLAZGOS. No hagas commit hasta resolverlos.", file=sys.stderr)
    return resultado.returncode


if __name__ == "__main__":
    sys.exit(main())
