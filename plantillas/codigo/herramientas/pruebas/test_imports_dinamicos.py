"""Los imports dinamicos esquivan import-linter: ruff los prohibe y una prueba AST vigila.

import-linter solo ve imports ESTATICOS. `importlib.import_module("otro.dominio")` o
`__import__("otro.dominio")` cruzarian un limite entre modulos sin romper ningun contrato.
- `importlib.import_module` y `django.utils.module_loading.import_string`: regla TID251 de ruff
  (`[tool.ruff.lint.flake8-tidy-imports.banned-api]` en `pyproject.toml`).
- `__import__` y cualquier uso de `importlib`: ruff no los detecta; los cubre la prueba AST.
Solo `<modulo>/pruebas/` de PRIMER nivel queda exento de la prueba AST; en ruff, unicamente
`configuracion/pruebas/test_settings.py` (recarga settings con `importlib.import_module`). Un
`auditoria/dominio/pruebas/x.py` NO esta exento en ninguno de los dos.
"""

import ast
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from configuracion.modulos import MODULO_NUCLEO, MODULOS_HEXAGONALES
from herramientas.contratos_importlinter import RAIZ_SRC

# Codigo de negocio y de configuracion: todo salvo `pruebas/` (que no se publica).
PAQUETES_VIGILADOS = (*MODULOS_HEXAGONALES, MODULO_NUCLEO, "configuracion", "herramientas")


def es_codigo_vigilado(ruta_relativa: Path) -> bool:
    """Falso solo para `<modulo>/pruebas/...` de primer nivel (`parts[1] == "pruebas"`)."""
    partes = ruta_relativa.parts
    return not (len(partes) > 2 and partes[1] == "pruebas")


def archivos_vigilados(raiz: Path) -> Iterator[Path]:
    for paquete in PAQUETES_VIGILADOS:
        for ruta in sorted((raiz / paquete).rglob("*.py")):
            if es_codigo_vigilado(ruta.relative_to(raiz)):
                yield ruta


def _archivos_de_negocio() -> Iterator[Path]:
    yield from archivos_vigilados(RAIZ_SRC)


def usos_de_import_dinamico(codigo: str) -> list[str]:
    """Descripcion de cada uso de `__import__` o `importlib` que haya en `codigo`."""
    hallazgos: list[str] = []
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import):
            hallazgos += [
                f"linea {nodo.lineno}: import {alias.name}"
                for alias in nodo.names
                if alias.name.split(".")[0] == "importlib"
            ]
        elif isinstance(nodo, ast.ImportFrom):
            if (nodo.module or "").split(".")[0] == "importlib":
                hallazgos.append(f"linea {nodo.lineno}: from {nodo.module} import ...")
        elif isinstance(nodo, ast.Name) and nodo.id in {"__import__", "importlib"}:
            hallazgos.append(f"linea {nodo.lineno}: {nodo.id}")
        elif isinstance(nodo, ast.Attribute) and nodo.attr == "__import__":
            hallazgos.append(f"linea {nodo.lineno}: .__import__")
        elif isinstance(nodo, ast.Constant) and nodo.value == "__import__":
            hallazgos.append(f"linea {nodo.lineno}: '__import__' (getattr/builtins)")
    return hallazgos


def test_hay_codigo_de_negocio_que_vigilar() -> None:
    assert len(list(_archivos_de_negocio())) > 20  # evita que la prueba pase en vacio


def test_ningun_modulo_de_negocio_usa_import_dinamico() -> None:
    hallazgos = {
        str(ruta.relative_to(RAIZ_SRC)): usos
        for ruta in _archivos_de_negocio()
        if (usos := usos_de_import_dinamico(ruta.read_text(encoding="utf-8")))
    }
    assert not hallazgos, f"Imports dinamicos (esquivan import-linter): {hallazgos}"


@pytest.mark.parametrize(
    "codigo",
    [
        "__import__('identidad.dominio')",
        "import importlib",
        "import importlib.util",
        "from importlib import import_module",
        "from importlib.util import find_spec",
        "x = importlib",
        "import builtins\nbuiltins.__import__('os')",
        "getattr(__builtins__, '__import__')",
    ],
)
def test_el_detector_ast_reconoce_cada_forma_de_import_dinamico(codigo: str) -> None:
    assert usos_de_import_dinamico(codigo)


def test_el_detector_ast_no_da_falsos_positivos() -> None:
    assert not usos_de_import_dinamico("import os\nfrom pathlib import Path\nprint(os, Path)")


# --- ruff (TID251) con la configuracion REAL del proyecto -------------------------------------


def _ruff(codigo: str, nombre_de_archivo: str) -> subprocess.CompletedProcess[str]:
    """Corre ruff con `pyproject.toml` sobre `codigo`, como si viviera en `nombre_de_archivo`."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--output-format=concise",
            f"--stdin-filename={nombre_de_archivo}",
            "-",
        ],
        cwd=RAIZ_SRC,
        input=codigo,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


CODIGO_IMPORTLIB = (
    "import importlib\n\n\ndef cargar() -> object:\n    return importlib.import_module('x')\n"
)
CODIGO_IMPORT_STRING = (
    "from django.utils.module_loading import import_string\n\n\n"
    "def cargar() -> object:\n    return import_string('x.y')\n"
)


@pytest.mark.parametrize(
    ("ruta", "vigilada"),
    [
        ("auditoria/pruebas/test_x.py", False),
        ("nucleo/pruebas/test_x.py", False),
        ("auditoria/dominio/pruebas/x.py", True),
        ("auditoria/aplicacion/pruebas/x.py", True),
        ("auditoria/dominio/x.py", True),
        ("configuracion/pruebas/test_settings.py", False),
    ],
)
def test_el_filtro_ast_solo_exime_pruebas_de_primer_nivel(ruta: str, vigilada: bool) -> None:
    assert es_codigo_vigilado(Path(ruta)) is vigilada


def test_la_prueba_ast_falla_ante_importlib_en_pruebas_anidadas(tmp_path: Path) -> None:
    anidado = tmp_path / "auditoria" / "dominio" / "pruebas" / "x.py"
    exento = tmp_path / "auditoria" / "pruebas" / "test_y.py"
    for archivo in (anidado, exento):
        archivo.parent.mkdir(parents=True)
        archivo.write_text(
            "import importlib" + chr(10) + "importlib.import_module('x')" + chr(10),
            encoding="utf-8",
        )
    vigilados = list(archivos_vigilados(tmp_path))
    assert vigilados == [anidado]
    assert usos_de_import_dinamico(anidado.read_text(encoding="utf-8"))


@pytest.mark.lento
@pytest.mark.parametrize(
    ("codigo", "regla"),
    [(CODIGO_IMPORTLIB, "importlib.import_module"), (CODIGO_IMPORT_STRING, "import_string")],
)
def test_ruff_rompe_un_import_dinamico_en_un_modulo_de_negocio(codigo: str, regla: str) -> None:
    resultado = _ruff(codigo, "auditoria/dominio/intruso.py")
    assert resultado.returncode != 0, resultado.stdout
    assert "TID251" in resultado.stdout
    assert regla in resultado.stdout


@pytest.mark.lento
def test_ruff_tambien_lo_rompe_en_la_configuracion_y_en_el_nucleo() -> None:
    for destino in ("configuracion/intruso.py", "nucleo/intruso.py", "identidad/api_publica.py"):
        resultado = _ruff(CODIGO_IMPORTLIB, destino)
        assert "TID251" in resultado.stdout, destino


@pytest.mark.lento
def test_ruff_solo_exime_a_test_settings() -> None:
    resultado = _ruff(CODIGO_IMPORTLIB, "configuracion/pruebas/test_settings.py")
    assert "TID251" not in resultado.stdout, resultado.stdout


@pytest.mark.lento
@pytest.mark.parametrize(
    "destino",
    [
        "auditoria/dominio/pruebas/x.py",
        "auditoria/pruebas/test_recarga.py",
        "configuracion/pruebas/otro.py",
    ],
)
def test_ruff_no_exime_ningun_otro_directorio_pruebas(destino: str) -> None:
    resultado = _ruff(CODIGO_IMPORTLIB, destino)
    assert resultado.returncode != 0, resultado.stdout
    assert "TID251" in resultado.stdout, destino
