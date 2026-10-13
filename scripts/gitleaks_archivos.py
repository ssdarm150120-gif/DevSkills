"""Corre gitleaks por Docker sobre los archivos versionados y los nuevos no ignorados.

Uso (desde cualquier carpeta dentro del repositorio):
    python gitleaks_archivos.py [--repo RUTA] [--imagen IMAGEN]

Toma la lista de `git ls-files -co --exclude-standard` (versionados más nuevos que no
ignora `.gitignore`), la copia a una carpeta temporal y la escanea con `gitleaks dir`.
Así no se escanean `.venv/`, `.pgdata/` ni otros archivos ignorados, y tampoco se lee
ningún `.env` ignorado. Sale con el código de gitleaks: 0 sin hallazgos, 1 con hallazgos.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404: se invocan git y docker con listas de argumentos
import sys
import tempfile
from pathlib import Path

IMAGEN_PREDETERMINADA = "zricethezav/gitleaks:v8.21.2"


def archivos_del_repo(repo: Path) -> list[str]:
    salida = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    return [r for r in salida.decode("utf-8").split("\0") if r]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="Ruta dentro del repositorio (por defecto, la actual)")
    parser.add_argument("--imagen", default=IMAGEN_PREDETERMINADA, help="Imagen de Docker de gitleaks")
    args = parser.parse_args()

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
        for relativa in rutas:
            origen = raiz / relativa
            if not origen.is_file():
                continue  # borrado en el árbol de trabajo
            destino = copia / relativa
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, destino)
        print(f"Escaneando {len(rutas)} archivos de {raiz} con {args.imagen}...")
        resultado = subprocess.run(  # nosec B603 B607
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-v",
                f"{copia}:/repo:ro",
                args.imagen,
                "dir",
                "/repo",
                "--no-banner",
                "--redact",
            ],
            check=False,
        )
    if resultado.returncode == 0:
        print("gitleaks: sin hallazgos.")
    else:
        print("gitleaks: HAY HALLAZGOS. No hagas commit hasta resolverlos.", file=sys.stderr)
    return resultado.returncode


if __name__ == "__main__":
    sys.exit(main())
