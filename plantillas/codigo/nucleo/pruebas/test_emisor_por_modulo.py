"""Un módulo no puede hacerse pasar por otro al pedir su publicador (DISENO D.5.2).

La fábrica entrega `.de("modulo")`; ningún código de producción puede pedir el publicador de un
nombre que no es el del módulo que lo contiene. Esta prueba recorre el código (AST) y lo exige.
"""

import ast
from pathlib import Path

CODIGO = Path(__file__).resolve().parents[2]
EXCLUIDOS = {".venv", "pruebas", "migraciones", "__pycache__"}


def _archivos_de_produccion() -> list[Path]:
    return [
        ruta
        for ruta in CODIGO.rglob("*.py")
        if not EXCLUIDOS & set(ruta.relative_to(CODIGO).parts) and ruta.name != "conftest.py"
    ]


def _llamadas_a_de() -> list[tuple[Path, int, ast.expr | None]]:
    """Cada `<algo>.de(<primer argumento>)` cuyo receptor es una fabrica de publicadores."""
    encontradas = []
    for ruta in _archivos_de_produccion():
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "de"
                and isinstance(nodo.func.value, ast.Call)
                and ast.unparse(nodo.func.value).startswith("obtener(FabricaDePublicadores")
            ):
                encontradas.append((ruta, nodo.lineno, nodo.args[0] if nodo.args else None))
    return encontradas


def test_el_codigo_de_produccion_pide_el_publicador_de_su_propio_modulo() -> None:
    llamadas = _llamadas_a_de()
    modulos = {ruta.relative_to(CODIGO).parts[0] for ruta, _, _ in llamadas}
    assert {"identidad", "nucleo"} <= modulos  # no es una prueba vacia: hay llamadas reales
    for ruta, linea, argumento in llamadas:
        modulo = ruta.relative_to(CODIGO).parts[0]
        donde = f"{ruta.relative_to(CODIGO)}:{linea}"
        assert isinstance(argumento, ast.Constant), f"{donde}: el nombre del modulo va literal"
        assert argumento.value == modulo, f"{donde}: {argumento.value!r} no es el modulo {modulo!r}"


def test_el_detector_encuentra_una_suplantacion() -> None:
    codigo = 'obtener(FabricaDePublicadores).de("ejemplo")'
    nodo = ast.parse(codigo).body[0]
    assert isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Call)
    func = nodo.value.func
    assert isinstance(func, ast.Attribute) and func.attr == "de"
    assert ast.unparse(func.value).startswith("obtener(FabricaDePublicadores")
    argumento = nodo.value.args[0]
    assert isinstance(argumento, ast.Constant) and argumento.value != "identidad"
