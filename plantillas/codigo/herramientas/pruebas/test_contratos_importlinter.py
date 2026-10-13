"""Los contratos de import-linter (D.1.3 y D.1.5) existen, estan sincronizados y FALLAN al violarse.

Para demostrar que los contratos muerden, cada caso arma un mini proyecto en un directorio
temporal con la MISMA configuracion generada para el proyecto real (pero con modulos de juguete)
y ejecuta `lint-imports` sobre el.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from configuracion.modulos import DEPENDENCIAS, MODULO_IDENTIDAD, MODULOS_HEXAGONALES
from herramientas.contratos_importlinter import ARCHIVO, RAIZ_SRC, generar, orden_sin_ciclos

DISENO = RAIZ_SRC.parent / "documentacion" / "DISENO.md"

# Mini proyecto: gama usa a beta, y beta usa a alfa (D.1.3 de juguete). Nada mas esta permitido.
# `identidad` (hoja del grafo real) hace aqui de `hoja`: el modulo que NADIE puede importar.
MODULOS_JUGUETE = ("alfa", "beta", "gama", "hoja")
DEPENDENCIAS_JUGUETE = {"beta": ("alfa",), "gama": ("beta",)}
ARRANQUE = "from importlinter.cli import lint_imports_command; lint_imports_command()"
USA_ALFA = "from alfa.api_publica import consultar\n"
USA_BETA = "from beta.api_publica import consultar\n"
USA_GAMA = "from gama.api_publica import consultar\n"
USA_HOJA = "from hoja.api_publica import consultar\n"


def _contratos_de_juguete() -> str:
    return generar(modulos=MODULOS_JUGUETE, dependencias=DEPENDENCIAS_JUGUETE, hoja="hoja")


def _crear_proyecto(raiz: Path, archivos_extra: dict[str, str]) -> None:
    paquetes = ["nucleo", "nucleo/puertos", "configuracion"]
    for modulo in MODULOS_JUGUETE:
        paquetes += [
            modulo,
            f"{modulo}/dominio",
            f"{modulo}/aplicacion",
            f"{modulo}/adaptadores",
            f"{modulo}/pruebas",
        ]
    for paquete in paquetes:
        (raiz / paquete).mkdir(parents=True, exist_ok=True)
        (raiz / paquete / "__init__.py").write_text("", encoding="utf-8")
    for modulo in MODULOS_JUGUETE:
        (raiz / modulo / "api_publica.py").write_text("def consultar() -> int:\n    return 1\n")
        (raiz / modulo / "apps.py").write_text("")
    for ruta, contenido in archivos_extra.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
    (raiz / ".importlinter").write_text(_contratos_de_juguete(), encoding="utf-8")


def _lint(raiz: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", ARRANQUE, "--no-cache"],
        cwd=raiz,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_el_archivo_importlinter_esta_sincronizado_con_el_mapa_de_modulos() -> None:
    # Comparacion en BYTES: con `read_text` un CRLF pasaria desapercibido.
    assert ARCHIVO.read_bytes() == generar().encode("utf-8"), (
        "Regenerar con: python -m herramientas.contratos_importlinter --escribir"
    )


def test_el_generador_imprime_exactamente_el_archivo_sin_traducir_el_fin_de_linea() -> None:
    """el CI compara `generador | diff -.importlinter` sin `--strip-trailing-cr`."""
    resultado = subprocess.run(
        [sys.executable, "-m", "herramientas.contratos_importlinter"],
        cwd=RAIZ_SRC,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert b"\r" not in resultado.stdout
    assert resultado.stdout == ARCHIVO.read_bytes()


@pytest.mark.lento
def test_proyecto_valido_con_las_flechas_permitidas_pasa(tmp_path: Path) -> None:
    _crear_proyecto(
        tmp_path,
        {
            "beta/aplicacion/caso.py": USA_ALFA + "X = consultar\n",
            "gama/aplicacion/caso.py": USA_BETA + "X = consultar\n",
        },
    )
    resultado = _lint(tmp_path)
    assert resultado.returncode == 0, resultado.stdout


# (descripcion, archivos del mini proyecto, contratos que DEBEN romperse, contratos que NO)
CASOS_DE_VIOLACION = [
    (
        "importar adaptadores de otro modulo",
        {
            "beta/adaptadores/x.py": "from alfa.adaptadores import y\n",
            "alfa/adaptadores/y.py": "",
        },
        ("aislamiento-beta",),
        (),
    ),
    (
        "importar el dominio de otro modulo",
        {"beta/aplicacion/x.py": "from alfa.dominio import m\n", "alfa/dominio/m.py": ""},
        ("aislamiento-beta",),
        (),
    ),
    # la flecha esta permitida (beta -> alfa), pero un submodulo que NO es api_publica ni una
    # de las capas conocidas (`alfa/servicios.py`) tampoco se puede importar.
    (
        "importar un submodulo suelto de otro modulo (flecha permitida)",
        {"beta/aplicacion/x.py": "from alfa.servicios import s\n", "alfa/servicios.py": "s = 1\n"},
        ("aislamiento-beta",),
        ("dependencias-beta",),
    ),
    (
        "el __init__ de un modulo importa un submodulo suelto de otro",
        {"beta/__init__.py": "from alfa.servicios import s\n", "alfa/servicios.py": "s = 1\n"},
        ("aislamiento-beta",),
        ("dependencias-beta",),
    ),
    ("dominio importa Django", {"alfa/dominio/m.py": "import django\n"}, ("dominio-puro",), ()),
    (
        "dominio importa el ORM",
        {"alfa/dominio/m.py": "from django.db import models\n"},
        ("dominio-puro",),
        (),
    ),
    ("dominio importa psycopg", {"alfa/dominio/m.py": "import psycopg\n"}, ("dominio-puro",), ()),
    # H11: `nucleo.puertos` es Python puro como el dominio, aunque no sea un `dominio/`.
    (
        "nucleo.puertos importa Django",
        {"nucleo/puertos/m.py": "import django\n"},
        ("dominio-puro",),
        (),
    ),
    (
        "nucleo.puertos importa el ORM",
        {"nucleo/puertos/m.py": "from django.db import models\n"},
        ("dominio-puro",),
        (),
    ),
    (
        "nucleo.puertos importa un cliente de base de datos",
        {"nucleo/puertos/m.py": "import psycopg\n"},
        ("dominio-puro",),
        (),
    ),
    (
        "nucleo.puertos importa un cliente de red (urllib)",
        {"nucleo/puertos/m.py": "import urllib.request\n"},
        ("dominio-puro",),
        (),
    ),
    (
        "nucleo.puertos importa Django por una cadena de imports",
        {"nucleo/puertos/m.py": "from nucleo import ayuda\n", "nucleo/ayuda.py": "import django\n"},
        ("dominio-puro",),
        (),
    ),
    (
        "dominio importa la capa de aplicacion",
        {
            "alfa/dominio/m.py": "from alfa.aplicacion import caso\n",
            "alfa/aplicacion/caso.py": "",
        },
        ("capas-hexagonales",),
        (),
    ),
    (
        "el nucleo importa un modulo",
        {"nucleo/x.py": "from alfa import api_publica\n"},
        ("nucleo-independiente",),
        (),
    ),
    (
        "un modulo importa la configuracion",
        {"alfa/aplicacion/x.py": "import configuracion\n"},
        ("modulos-sin-configuracion",),
        (),
    ),
    # D.1.3: solo las flechas del grafo, siempre por la api_publica.
    (
        "flecha no permitida: alfa usa a beta (sentido contrario)",
        {"alfa/aplicacion/x.py": USA_BETA},
        ("dependencias-alfa",),
        ("aislamiento-alfa",),  # usa la api_publica: la regla de los internos no se rompe
    ),
    (
        "flecha no permitida: gama salta a alfa sin pasar por beta",
        {"gama/aplicacion/x.py": USA_ALFA},
        ("dependencias-gama",),
        ("sin-ciclos", "aislamiento-gama"),  # baja de nivel: no hay ciclo
    ),
    # D.1.3 (Actor): ningun modulo importa `identidad` (aqui `hoja`), ni el nucleo.
    (
        "un modulo importa la hoja (identidad) por su api_publica",
        {"gama/aplicacion/x.py": USA_HOJA},
        ("nadie-importa-hoja", "dependencias-gama"),
        ("aislamiento-gama",),  # va por la api_publica: la regla de los internos no se rompe
    ),
    (
        "el nucleo importa la hoja (identidad)",
        {"nucleo/x.py": USA_HOJA},
        ("nadie-importa-hoja", "nucleo-independiente"),
        (),
    ),
    # D.1.3: sin ciclos.
    (
        "ciclo directo: beta -> alfa (permitida) y alfa -> beta",
        {"beta/aplicacion/x.py": USA_ALFA, "alfa/aplicacion/x.py": USA_BETA},
        ("sin-ciclos", "dependencias-alfa"),
        ("dependencias-beta",),
    ),
    (
        "ciclo largo: gama -> beta -> alfa -> gama",
        {
            "gama/aplicacion/x.py": USA_BETA,
            "beta/aplicacion/x.py": USA_ALFA,
            "alfa/aplicacion/x.py": USA_GAMA,
        },
        ("sin-ciclos", "dependencias-alfa"),
        ("dependencias-beta", "dependencias-gama"),
    ),
]


@pytest.mark.lento
@pytest.mark.parametrize(
    ("violacion", "archivos", "rotos", "intactos"),
    CASOS_DE_VIOLACION,
    ids=[caso[0] for caso in CASOS_DE_VIOLACION],
)
def test_el_contrato_falla_ante_una_violacion(
    tmp_path: Path,
    violacion: str,
    archivos: dict[str, str],
    rotos: tuple[str, ...],
    intactos: tuple[str, ...],
) -> None:
    _crear_proyecto(tmp_path, archivos)
    resultado = _lint(tmp_path)
    assert resultado.returncode != 0, f"No detecto: {violacion}\n{resultado.stdout}"
    assert "BROKEN" in resultado.stdout
    seccion_rota = resultado.stdout.split("Broken contracts")[-1]
    for contrato in rotos:
        assert _nombre_del_contrato(contrato, resultado.stdout) in seccion_rota, contrato
    for contrato in intactos:
        assert _nombre_del_contrato(contrato, resultado.stdout) not in seccion_rota, contrato


def _nombre_del_contrato(identificador: str, salida: str) -> str:
    """El nombre legible del contrato (`name = ...`) tal como sale en el informe."""
    for linea in _contratos_de_juguete().split("[importlinter:contract:"):
        if linea.startswith(identificador + "]"):
            return next(
                parte.removeprefix("name = ")
                for parte in linea.splitlines()
                if parte.startswith("name = ")
            )
    raise AssertionError(f"Contrato inexistente: {identificador}\n{salida}")


@pytest.mark.lento
def test_el_proyecto_real_cumple_todos_los_contratos() -> None:
    resultado = _lint(RAIZ_SRC)
    assert resultado.returncode == 0, resultado.stdout


def test_el_contrato_dominio_puro_real_cubre_nucleo_puertos_y_cada_dominio() -> None:
    seccion = generar().split("[importlinter:contract:dominio-puro]")[1].split("\n[")[0]
    origenes = seccion.split("source_modules =")[1].split("forbidden_modules =")[0].split()
    assert sorted(origenes) == sorted(
        [*(f"{modulo}.dominio" for modulo in MODULOS_HEXAGONALES), "nucleo.puertos"]
    )


# --- El grafo D.1.3 y su generacion -------------------------------------------------------------


def test_el_grafo_no_tiene_ciclos_y_solo_nombra_modulos_existentes() -> None:
    orden = orden_sin_ciclos(MODULOS_HEXAGONALES, DEPENDENCIAS)
    assert sorted(orden) == sorted(MODULOS_HEXAGONALES)
    posicion = {modulo: indice for indice, modulo in enumerate(orden)}
    for origen, destinos in DEPENDENCIAS.items():
        assert all(posicion[origen] < posicion[destino] for destino in destinos)


def test_generar_rechaza_un_ciclo_en_el_grafo() -> None:
    with pytest.raises(ValueError, match="ciclos"):
        generar(modulos=MODULOS_JUGUETE, dependencias={"alfa": ("beta",), "beta": ("alfa",)})
    with pytest.raises(ValueError, match="ciclos"):
        generar(modulos=MODULOS_JUGUETE, dependencias={"alfa": ("alfa",)})


def test_generar_rechaza_modulos_inexistentes_en_el_grafo() -> None:
    with pytest.raises(ValueError, match="inexistentes"):
        generar(modulos=MODULOS_JUGUETE, dependencias={"alfa": ("fantasma",)})


def test_un_modulo_sin_flechas_no_puede_importar_a_ninguno() -> None:
    seccion = generar().split("[importlinter:contract:dependencias-identidad]")[1].split("\n[")[0]
    prohibidos = seccion.split("forbidden_modules =")[1].split("allow_indirect_imports")[0].split()
    assert sorted(prohibidos) == sorted(m for m in MODULOS_HEXAGONALES if m != "identidad")


def _flechas_de_diseno() -> dict[str, set[str]] | None:
    """Lee las flechas `A --> B & C` del diagrama de D.1.3 en `documentacion/DISENO.md`.

    Devuelve `None` si el DISENO todavia no tiene la seccion D.1.3 con su diagrama Mermaid (un
    proyecto recien creado): el nombre de cada nodo va entre corchetes, `ID[identidad]`.
    """
    texto = DISENO.read_text(encoding="utf-8")
    if "### D.1.3" not in texto or "### D.1.4" not in texto:
        return None
    d13 = texto.split("### D.1.3")[1].split("### D.1.4")[0]
    if "```mermaid" not in d13:
        return None
    diagrama = d13.split("```mermaid")[1].split("```")[0]
    alias = dict(re.findall(r"^\s+(\w+)\[(\w+)\]", diagrama, re.MULTILINE))
    flechas: dict[str, set[str]] = {}
    for origen, destinos in re.findall(r"^\s+(\w+) --> (.+)$", diagrama, re.MULTILINE):
        # Las flechas hacia `nucleo` no cuentan: todo modulo puede usar el nucleo compartido y
        # `DEPENDENCIAS` solo lista las flechas entre modulos.
        usados = {alias[destino.strip()] for destino in destinos.split("&")} - {"nucleo"}
        if usados:
            flechas.setdefault(alias[origen], set()).update(usados)
    return flechas


@pytest.mark.skipif(not DISENO.exists(), reason="documentacion/DISENO.md no esta en este arbol")
def test_las_dependencias_coinciden_con_el_diagrama_de_diseno_d13() -> None:
    flechas = _flechas_de_diseno()
    if flechas is None:
        pytest.skip("El DISENO todavia no tiene el diagrama de dependencias de D.1.3")
    assert {origen: set(destinos) for origen, destinos in DEPENDENCIAS.items()} == flechas


def test_identidad_es_hoja_del_grafo_nadie_la_importa_ni_ella_importa() -> None:
    assert all(MODULO_IDENTIDAD not in destinos for destinos in DEPENDENCIAS.values())
    assert MODULO_IDENTIDAD not in DEPENDENCIAS


def test_el_contrato_real_prohibe_importar_identidad_desde_cualquier_modulo_y_el_nucleo() -> None:
    seccion = generar().split("[importlinter:contract:nadie-importa-identidad]")[1].split("[")[0]
    origenes = seccion.split("source_modules =")[1].split("forbidden_modules =")[0].split()
    prohibidos = seccion.split("forbidden_modules =")[1].split()
    esperados = [*(m for m in MODULOS_HEXAGONALES if m != MODULO_IDENTIDAD), "nucleo"]
    assert sorted(origenes) == sorted(esperados)
    assert prohibidos == ["identidad"]
