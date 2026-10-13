"""Contrato D.1.3: `nucleo` expone el `Actor` sin depender de ningun modulo ni de Django.

Vive en `configuracion/pruebas` porque `nucleo` no puede importar `configuracion` (ni siquiera
en sus pruebas): es justo lo que protege el contrato `nucleo-independiente`.
"""

import subprocess
import sys
from pathlib import Path

from configuracion.modulos import MODULOS_HEXAGONALES

RAIZ_SRC = Path(__file__).resolve().parents[2]


def test_el_actor_se_importa_desde_nucleo_sin_cargar_ningun_modulo_ni_django() -> None:
    """En un interprete limpio, importar `nucleo.actor` no carga modulos, config ni Django."""
    prohibidos = [*MODULOS_HEXAGONALES, "configuracion", "django"]
    codigo = (
        "import sys\n"
        f"sys.path.insert(0, {str(RAIZ_SRC)!r})\n"
        "from nucleo.actor import Actor\n"
        f"cargados = [m for m in {prohibidos!r} if m in sys.modules "
        "or any(n.startswith(m + '.') for n in sys.modules)]\n"
        "assert Actor.__module__ == 'nucleo.actor', Actor.__module__\n"
        "assert not cargados, cargados\n"
    )
    resultado = subprocess.run(
        [sys.executable, "-I", "-c", codigo],
        cwd=RAIZ_SRC,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
