"""El esqueleto de D.1.2 / D.1.5 esta completo y cada modulo es una app Django registrada."""

from pathlib import Path

import pytest
from django.apps import apps

from configuracion.modulos import (
    APPS_PROPIAS,
    ESQUEMAS,
    MIGRATION_MODULES,
    MODULOS_HEXAGONALES,
    MODULOS_NEGOCIO,
)

RAIZ = Path(__file__).resolve().parent.parent.parent
CARPETAS = (
    "dominio",
    "aplicacion",
    "adaptadores/entrada",
    "adaptadores/salida",
    "adaptadores/salida/migraciones",
    "pruebas",
)


def test_los_modulos_de_negocio_no_se_repiten_e_incluyen_los_cimientos() -> None:
    assert len(set(MODULOS_NEGOCIO)) == len(MODULOS_NEGOCIO)
    assert {"identidad", "auditoria"} <= set(MODULOS_NEGOCIO)


@pytest.mark.parametrize("modulo", MODULOS_HEXAGONALES)
def test_modulo_tiene_estructura_hexagonal(modulo: str) -> None:
    base = RAIZ / modulo
    assert (base / "api_publica.py").is_file()
    assert (base / "apps.py").is_file()
    for carpeta in CARPETAS:
        assert (base / carpeta / "__init__.py").is_file(), f"falta {modulo}/{carpeta}"


ENTRADAS_PERMITIDAS = {
    "__init__.py",
    "__pycache__",
    "api_publica.py",
    "apps.py",
    "dominio",
    "aplicacion",
    "adaptadores",
    "pruebas",
}


@pytest.mark.parametrize("modulo", MODULOS_HEXAGONALES)
def test_modulo_no_tiene_submodulos_fuera_de_los_contratos_de_import_linter(modulo: str) -> None:
    """Los contratos prohíben importar solo las capas listadas en `INTERNOS`: un archivo extra
    (`ventas/modelos.py`) quedaría importable desde otro módulo sin que CI lo detecte."""
    entradas = {ruta.name for ruta in (RAIZ / modulo).iterdir()}
    assert entradas <= ENTRADAS_PERMITIDAS, f"sobran en {modulo}: {entradas - ENTRADAS_PERMITIDAS}"
    # `__init__.py` vacío: un re-export (`from .dominio import X`) es un camino indirecto permitido.
    assert (RAIZ / modulo / "__init__.py").read_text(encoding="utf-8").strip() == ""


@pytest.mark.parametrize("modulo", APPS_PROPIAS)
def test_modulo_esta_registrado_como_app_de_django(modulo: str) -> None:
    assert apps.get_app_config(modulo).name == modulo


def test_cada_modulo_tiene_esquema_y_migraciones_propias() -> None:
    assert set(ESQUEMAS) == set(APPS_PROPIAS) == set(MIGRATION_MODULES)
    assert len(set(ESQUEMAS.values())) == len(ESQUEMAS)  # sin esquemas compartidos
