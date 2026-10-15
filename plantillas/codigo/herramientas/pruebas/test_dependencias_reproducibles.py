"""Dependencias reproducibles: si el proyecto ya genero su lockfile, trae hashes en cada paquete.

`requirements.txt` y `requirements-dev.txt` declaran RANGOS (lo que el equipo acepta). El
lockfile con hashes (`requirements.lock`, generado con pip-tools; ver "Dependencias reproducibles"
en el README) fija las versiones exactas y los hashes de lo que de verdad se instala. El lock se
genera en la Entrega 0, en el sistema donde corre el CI (los hashes dependen de la plataforma) y
se versiona. Mientras no exista, esta prueba no exige nada.
"""

import re
from pathlib import Path

CODIGO = Path(__file__).resolve().parents[2]
LOCK = CODIGO / "requirements.lock"
README = (CODIGO / "README.md").read_text(encoding="utf-8")


def _paquetes_del_lock(texto: str) -> list[str]:
    """Cada requisito del lock, con sus continuaciones `--hash` unidas en una sola linea."""
    juntas = re.sub(r"\\\s*\n\s*", " ", texto)
    return [
        linea.strip()
        for linea in juntas.splitlines()
        if linea.strip() and not linea.lstrip().startswith(("#", "-"))
    ]


def test_el_lock_si_existe_fija_la_version_y_trae_hashes_de_cada_paquete() -> None:
    if not LOCK.exists():
        return  # todavia no se genero: la Entrega 0 lo crea
    paquetes = _paquetes_del_lock(LOCK.read_text(encoding="utf-8"))
    assert paquetes, "requirements.lock esta vacio"
    for linea in paquetes:
        assert "==" in linea, f"version sin fijar: {linea[:60]}"
        assert "--hash=sha256:" in linea, f"sin hash: {linea[:60]}"


def test_pip_tools_esta_entre_las_herramientas_de_desarrollo() -> None:
    dev = (CODIGO / "requirements-dev.txt").read_text(encoding="utf-8")
    assert re.search(r"^pip-tools>=", dev, re.MULTILINE)


def test_el_readme_documenta_como_generar_y_usar_el_lock() -> None:
    seccion = README.split("### Dependencias reproducibles", 1)[1].split("\n## ", 1)[0]
    assert "pip-compile --generate-hashes" in seccion
    assert "pip install --require-hashes" in seccion
