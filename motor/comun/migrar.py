"""Migra los DATOS de una instalación previa del panel (carpeta estilo ``_servicios``) al directorio de datos del motor.

  python migrar.py --desde <carpeta> [--destino <datos>] [--forzar]

Copia (nunca mueve ni borra nada del origen) y no sobrescribe lo que ya exista en el destino salvo con --forzar:

  <desde>/proyectos.json                       -> <datos>/proyectos.json
  <desde>/preferencias*.json  (o panel/...)    -> <datos>/preferencias*.json
  <desde>/panel/estado*/                       -> <datos>/panel/estado*/
  <desde>/orquestador/historial/               -> <datos>/orquestador/historial/
  <desde>/orquestador/propuestas/              -> <datos>/orquestador/propuestas/
  <desde>/orquestador/{config.json, sesiones_propias.json, enrutamiento-fallos.jsonl}

NO se copian tokens (``.token*``), logs, entornos virtuales ni cachés: se regeneran. Solo biblioteca estándar.
"""
from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import rutas  # noqa: E402

EXCLUIDOS = (".token*", "*.log", "*.tmp", "__pycache__", ".venv", ".pytest_cache", ".git")


def _excluido(nombre: str) -> bool:
    return any(fnmatch.fnmatch(nombre, patron) for patron in EXCLUIDOS)


def _copiar_archivo(origen: Path, destino: Path, forzar: bool, informe: dict) -> None:
    if destino.exists() and not forzar:
        informe["omitidos"].append(str(destino))
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origen, destino)
    informe["copiados"].append(str(destino))


def _copiar_carpeta(origen: Path, destino: Path, forzar: bool, informe: dict) -> None:
    for ruta in sorted(origen.rglob("*")):
        relativa = ruta.relative_to(origen)
        if any(_excluido(parte) for parte in relativa.parts) or not ruta.is_file():
            continue
        _copiar_archivo(ruta, destino / relativa, forzar, informe)


def migrar(desde: Path, destino: Path, forzar: bool = False) -> dict:
    desde, destino = Path(desde).resolve(), Path(destino).resolve()
    if not desde.is_dir():
        raise SystemExit(f"No existe la carpeta de origen: {desde}")
    if desde == destino:
        raise SystemExit("El origen y el destino son la misma carpeta.")
    informe: dict = {"copiados": [], "omitidos": []}

    if (desde / "proyectos.json").is_file():
        _copiar_archivo(desde / "proyectos.json", destino / "proyectos.json", forzar, informe)
    for base in (desde, desde / "panel"):
        for archivo in sorted(base.glob("preferencias*.json")):
            _copiar_archivo(archivo, destino / archivo.name, forzar, informe)
    panel = desde / "panel"
    if panel.is_dir():
        for carpeta in sorted(panel.glob("estado*")):
            if carpeta.is_dir():
                _copiar_carpeta(carpeta, destino / "panel" / carpeta.name, forzar, informe)
    orq = desde / "orquestador"
    if orq.is_dir():
        for nombre in ("historial", "propuestas"):
            if (orq / nombre).is_dir():
                _copiar_carpeta(orq / nombre, destino / "orquestador" / nombre, forzar, informe)
        for nombre in ("config.json", "sesiones_propias.json", "enrutamiento-fallos.jsonl"):
            if (orq / nombre).is_file():
                _copiar_archivo(orq / nombre, destino / "orquestador" / nombre, forzar, informe)
    return informe


def main(argv: list[str]) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--desde", required=True, help="carpeta de la instalación previa")
    ap.add_argument("--destino", help="directorio de datos (por omisión DEVSKILLS_DATOS o ~/.devskills)")
    ap.add_argument("--forzar", action="store_true", help="sobrescribe lo que ya exista en el destino")
    a = ap.parse_args(argv)
    destino = Path(a.destino) if a.destino else rutas.datos()
    informe = migrar(Path(a.desde), destino, a.forzar)
    print(f"Destino: {destino}")
    print(f"Copiados: {len(informe['copiados'])}")
    print(f"Omitidos (ya existían; usa --forzar para sobrescribir): {len(informe['omitidos'])}")
    if not informe["copiados"] and not informe["omitidos"]:
        print("No encontré datos que migrar (¿es la carpeta correcta?).")
        return 1
    print("El origen no se tocó: puedes seguir usándolo o borrarlo cuando confirmes que todo funciona.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
