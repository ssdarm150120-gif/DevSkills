"""Deriva entre el deber ser (grafo de la documentación) y lo que es (grafo del código).

Uso (desde la raíz del proyecto):

    python documentacion/analisis/deriva_grafos.py
        [--codigo codigo/graphify-out/graph.json]
        [--deber-ser documentacion/graphify-out/graph.json]
        [--salida documentacion/avance/S05/DERIVA-S05.md]
        [--todas-las-clases] [--con-funciones] [--ignorar-modulo <nombre>]... [--estricto]

Lee los dos `graph.json` que genera Graphify (https://github.com/Graphify-Labs/graphify):

- **Lo que es:** `graphify update codigo` (análisis AST, sin LLM y sin costo).
- **Deber ser:** `graphify update documentacion` (encabezados de SRS, DISEÑO, PLAN y CONTEXTO, sin LLM) o,
  si el Product Owner lo autorizó, `graphify extract documentacion --backend <ollama|claude-cli|claude>`
  (conceptos y relaciones extraídos por un LLM).

Compara por nombres normalizados (sin acentos, sin mayúsculas, snake_case y CamelCase partidos en palabras,
plurales simples) y escribe un reporte Markdown con:

- lo que el diseño dice y el código no tiene (elementos del deber ser sin correspondencia en el código);
- lo que el código tiene sin estar en el diseño (módulos y clases del dominio que ningún documento nombra);
- las correspondencias débiles, para revisar.

Es una heurística: cada hallazgo es un **candidato** que QA confirma (con `graphify explain`, `graphify path`
o leyendo el archivo citado) antes de reportarlo en el cierre del sprint.

Códigos de salida: 0 reporte generado; 1 hay deriva y se pidió `--estricto`; 2 uso inválido o un grafo que no
es JSON de Graphify; 3 falta algún grafo (el mensaje dice cómo generarlo; la deriva no se midió).

Solo usa la biblioteca estándar (Python 3.12).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

GRAFO_CODIGO = Path("codigo/graphify-out/graph.json")
GRAFO_DEBER_SER = Path("documentacion/graphify-out/graph.json")

SALIDA_OK = 0
SALIDA_DERIVA = 1
SALIDA_USO = 2
SALIDA_SIN_GRAFOS = 3

# Carpetas y archivos del código que no son "lo que es" del negocio: pruebas, migraciones y salidas de Graphify.
PARTES_IGNORADAS = frozenset(
    {"pruebas", "tests", "test", "migraciones", "migrations", "graphify-out", "__pycache__", "despliegue"}
)
# Módulos de infraestructura del esqueleto: el DISEÑO no tiene por qué nombrarlos como elementos del negocio.
MODULOS_IGNORADOS = ("configuracion", "herramientas")

# Palabras que no distinguen un elemento de otro (artículos, preposiciones y vocabulario genérico del método).
PALABRAS_VACIAS = frozenset(
    """
    a al con de del el en la las lo los o para por se su sus un una uno unos unas y e u que como sin sobre entre
    the of and or to for in on with by from is are be an
    modulo entidad agregado anexo seccion rf rnf hu cu adr py init self cls
    """.split()
)
# Prefijo que dice qué clase de elemento nombra un encabezado; se quita antes de comparar ("Entidad Pedido" -> pedido).
PATRON_PREFIJO = re.compile(
    r"^(modulo|entidad|agregado|caso de uso|puerto|adaptador|servicio|evento|flujo|algoritmo|maquina de estados?)\s+"
)

# Encabezados cuyo texto ya dice que nombran un elemento del diseño ("Entidad Pedido", "Módulo 1: Ventas", "HU-03 ...").
PATRON_ELEMENTO = re.compile(
    r"^(modulo|entidad|agregado|caso de uso|puerto|adaptador|servicio|evento|flujo|algoritmo)\s+(?!y\b|de\b)"
    r"|^(hu|en|cu)-\d+"
)
# Secciones cuyos hijos directos son elementos del diseño (SRS 3, 5 y anexos A y B; DISEÑO D.3, D.4 y D.7).
SECCIONES_DE_ELEMENTOS = (
    "requisitos funcionales",
    "interfaces externas",
    "historias de usuario",
    "catalogo de casos de uso",
    "maquinas de estado",
    "flujos de integracion",
    "algoritmos",
)
# Hijos de esas secciones que son reglas del documento, no elementos.
ENCABEZADOS_GENERICOS = ("convenciones", "atributos", "reglas", "interfaz de usuario")

PATRON_NUMERACION = re.compile(r"^\s*(?:[a-z]?\.?\d+(?:\.\d+|\.n)*\.?|[a-z]\.\d*|anexo [a-z]\.?)\s+")
PATRON_ID = re.compile(r"\b(?:hu|en|cu|rf|rnf|adr|p|s)-[a-z0-9]+(?:-[a-z0-9]+)*\b")
PATRON_COMENTARIO = re.compile(r"<!--.*?-->", re.DOTALL)
PATRON_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
PATRON_NO_ALFANUMERICO = re.compile(r"[^a-z0-9]+")
PROPORCION_DEBIL = 2 / 3


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def raiz(palabra: str) -> str:
    """Plural simple: `pedidos` -> `pedido`, `clientes` -> `cliente`. Igual en los dos lados de la comparación."""
    return palabra[:-1] if len(palabra) > 3 and palabra.endswith("s") else palabra


def palabras(texto: str) -> frozenset[str]:
    """Palabras significativas de un nombre o de un encabezado, normalizadas y en singular."""
    texto = PATRON_COMENTARIO.sub(" ", texto)
    texto = PATRON_CAMEL.sub(" ", texto)
    texto = sin_acentos(texto).lower()
    texto = PATRON_ID.sub(" ", texto)
    resultado = set()
    for parte in PATRON_NO_ALFANUMERICO.split(texto):
        if len(parte) < 2 or parte.isdigit():
            continue
        base = raiz(parte)
        if base not in PALABRAS_VACIAS and parte not in PALABRAS_VACIAS:
            resultado.add(base)
    return frozenset(resultado)


def normalizar_encabezado(texto: str) -> str:
    """`D.3.1 Máquinas de estado` -> `maquinas de estado` (sin numeración, acentos ni comentarios)."""
    texto = PATRON_COMENTARIO.sub(" ", texto)
    texto = sin_acentos(texto).lower().strip()
    texto = PATRON_NUMERACION.sub("", texto)
    return re.sub(r"\s+", " ", texto).strip()


@dataclass(frozen=True)
class Elemento:
    tipo: str
    nombre: str
    archivo: str
    linea: str
    palabras: frozenset[str]

    @property
    def fuente(self) -> str:
        return f"{self.archivo} {self.linea}".strip()


@dataclass
class Grafo:
    ruta: Path
    nodos: list[dict]
    aristas: list[dict]


@dataclass
class Resultado:
    deber_ser: list[Elemento]
    codigo: list[Elemento]
    identificadores: list[Elemento]
    nivel: str
    faltan_en_codigo: list[Elemento] = field(default_factory=list)
    debiles: list[tuple[Elemento, str]] = field(default_factory=list)
    cubiertos: int = 0
    faltan_en_diseno: list[Elemento] = field(default_factory=list)

    @property
    def hay_deriva(self) -> bool:
        return bool(self.faltan_en_codigo or self.faltan_en_diseno)


class ErrorDeGrafo(Exception):
    """El archivo existe pero no es un graph.json de Graphify."""


def leer_grafo(ruta: Path) -> Grafo:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ErrorDeGrafo(f"{ruta}: no se pudo leer como JSON ({error})") from error
    if not isinstance(datos, dict) or not isinstance(datos.get("nodes"), list):
        raise ErrorDeGrafo(f"{ruta}: no es un graph.json de Graphify (falta la lista 'nodes')")
    aristas = datos.get("links", datos.get("edges", []))
    if not isinstance(aristas, list):
        raise ErrorDeGrafo(f"{ruta}: la lista de aristas ('links') no es una lista")
    nodos = [n for n in datos["nodes"] if isinstance(n, dict)]
    return Grafo(ruta=ruta, nodos=nodos, aristas=[a for a in aristas if isinstance(a, dict)])


def partes_de(ruta: str) -> tuple[str, ...]:
    partes = PurePosixPath(ruta.replace("\\", "/")).parts
    if "codigo" in partes:
        partes = partes[partes.index("codigo") + 1 :]
    return partes


def es_ignorado(partes: Sequence[str]) -> bool:
    if not partes:
        return True
    nombre = partes[-1]
    return (
        any(p in PARTES_IGNORADAS for p in partes)
        or nombre.startswith("test_")
        or nombre.endswith("_test.py")
        or nombre == "conftest.py"
    )


def inventario_codigo(grafo: Grafo, ignorar_modulos: Iterable[str]) -> tuple[list[Elemento], list[Elemento]]:
    """(módulos, clases y funciones que se reportan) y (todos los identificadores que cubren el diseño)."""
    ignorados = {sin_acentos(m).lower() for m in ignorar_modulos}
    modulos: dict[str, Elemento] = {}
    identificadores: list[Elemento] = []
    for nodo in grafo.nodos:
        if nodo.get("file_type") != "code":
            continue
        archivo = str(nodo.get("source_file") or "")
        partes = partes_de(archivo)
        if es_ignorado(partes):
            continue
        etiqueta = str(nodo.get("label") or "")
        linea = str(nodo.get("source_location") or "")
        modulo = partes[0] if len(partes) >= 2 else ""
        de_infraestructura = sin_acentos(modulo).lower() in ignorados
        if modulo:
            if modulo not in modulos and not de_infraestructura:
                modulos[modulo] = Elemento("módulo", modulo, "/".join(("codigo", modulo)), "", palabras(modulo))
        if nodo.get("_callable_class"):
            tipo = "clase"
        elif etiqueta.startswith("."):
            tipo = "método"
        elif etiqueta.endswith("()"):
            tipo = "función"
        elif etiqueta.endswith(".py") or "." in etiqueta:
            tipo = "archivo"
        else:
            tipo = "otro"
        nombre = etiqueta.removesuffix("()").lstrip(".")
        if tipo == "archivo":
            nombre = PurePosixPath(nombre).stem
        clave = palabras(nombre)
        if not clave:
            continue
        if de_infraestructura:
            capa = "infraestructura"  # cubre el diseño, pero no se reporta como código sin diseño
        else:
            capa = "dominio" if "dominio" in partes else ("aplicacion" if "aplicacion" in partes else "otra")
        identificadores.append(Elemento(f"{tipo}:{capa}", nombre, archivo, linea, clave))
    identificadores.extend(modulos.values())
    return sorted(modulos.values(), key=lambda e: e.nombre), identificadores


def inventario_deber_ser(grafo: Grafo) -> tuple[list[Elemento], list[frozenset[str]], str]:
    """(elementos del diseño a buscar en el código), (vocabulario de todos los nodos) y el nivel del grafo."""
    por_id = {str(n.get("id")): n for n in grafo.nodos if n.get("file_type") != "code"}
    padre: dict[str, str] = {}
    for arista in grafo.aristas:
        origen, destino = str(arista.get("source")), str(arista.get("target"))
        if arista.get("relation") == "contains" and origen in por_id and destino in por_id:
            padre.setdefault(destino, origen)

    elementos: list[Elemento] = []
    vocabulario: list[frozenset[str]] = []
    semanticos = 0
    for identificador, nodo in por_id.items():
        etiqueta = str(nodo.get("label") or "")
        tipo_nodo = nodo.get("node_kind")
        if tipo_nodo == "heading":
            clave = palabras(PATRON_PREFIJO.sub("", normalizar_encabezado(etiqueta)))
        else:
            clave = palabras(etiqueta)
        if clave:
            vocabulario.append(clave)
        if tipo_nodo == "page" or not clave:
            continue
        if nodo.get("_origin") != "ast" and tipo_nodo != "heading":
            semanticos += 1
            elegido = True
        else:
            propio = normalizar_encabezado(etiqueta)
            superior = normalizar_encabezado(str(por_id.get(padre.get(identificador, ""), {}).get("label") or ""))
            elegido = bool(PATRON_ELEMENTO.search(propio)) or (
                superior.startswith(SECCIONES_DE_ELEMENTOS) and not propio.startswith(ENCABEZADOS_GENERICOS)
            )
        if elegido:
            nombre = re.sub(r"\s+", " ", PATRON_COMENTARIO.sub("", etiqueta)).strip()
            elementos.append(
                Elemento(
                    "concepto" if tipo_nodo != "heading" else "encabezado",
                    nombre,
                    str(nodo.get("source_file") or ""),
                    str(nodo.get("source_location") or ""),
                    clave,
                )
            )
    nivel = "semántico (con LLM)" if semanticos else "estructural (encabezados, sin LLM)"
    return sorted(elementos, key=lambda e: (e.archivo, e.nombre)), vocabulario, nivel


def correspondencia(concepto: frozenset[str], identificadores: Sequence[Elemento]) -> Elemento | None:
    """Un identificador que nombra el concepto completo, o que el concepto contiene sin ser una palabra suelta."""
    for ident in identificadores:
        if concepto <= ident.palabras:
            return ident
        if ident.palabras <= concepto and (len(ident.palabras) >= 2 or len(concepto) <= 2):
            return ident
    return None


def comparar(codigo: Grafo, deber_ser: Grafo, *, todas_las_clases: bool, con_funciones: bool,
             ignorar_modulos: Iterable[str]) -> Resultado:
    modulos, identificadores = inventario_codigo(codigo, ignorar_modulos)
    elementos, vocabulario_doc, nivel = inventario_deber_ser(deber_ser)
    vocabulario_codigo = frozenset().union(*(i.palabras for i in identificadores)) if identificadores else frozenset()

    reportables = list(modulos)
    for ident in identificadores:
        tipo, _, capa = ident.tipo.partition(":")
        if capa == "infraestructura":
            continue
        if tipo == "clase" and (todas_las_clases or capa == "dominio"):
            reportables.append(ident)
        elif tipo == "función" and con_funciones:
            reportables.append(ident)

    resultado = Resultado(deber_ser=elementos, codigo=reportables, identificadores=identificadores, nivel=nivel)
    for elemento in elementos:
        if correspondencia(elemento.palabras, identificadores):
            resultado.cubiertos += 1
            continue
        comunes = elemento.palabras & vocabulario_codigo
        if len(elemento.palabras) >= 2 and len(comunes) / len(elemento.palabras) >= PROPORCION_DEBIL:
            resultado.debiles.append((elemento, ", ".join(sorted(comunes))))
            continue
        resultado.faltan_en_codigo.append(elemento)

    vistos: set[tuple[str, str]] = set()
    for ident in reportables:
        tipo = ident.tipo.partition(":")[0]
        if (tipo, ident.nombre) in vistos:
            continue
        vistos.add((tipo, ident.nombre))
        nombrado = any(
            ident.palabras <= clave or (clave <= ident.palabras and len(clave) >= 2) for clave in vocabulario_doc
        )
        if not nombrado:
            resultado.faltan_en_diseno.append(Elemento(tipo, ident.nombre, ident.archivo, ident.linea, ident.palabras))
    resultado.faltan_en_diseno.sort(key=lambda e: (e.tipo != "módulo", e.archivo, e.nombre))
    return resultado


def celda(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ") or "—"


def reporte(resultado: Resultado, ruta_codigo: Path, ruta_deber_ser: Path) -> str:
    lineas = [
        "# Deriva entre el deber ser y lo que es",
        "",
        f"- **Lo que es** (grafo del código): `{ruta_codigo.as_posix()}`.",
        f"- **Deber ser** (grafo de la documentación): `{ruta_deber_ser.as_posix()}`, nivel {resultado.nivel}.",
        "- **Método:** comparación heurística por nombres normalizados (sin acentos, snake_case y CamelCase en"
        " palabras, plurales simples). Cada fila es un **candidato**: QA la confirma con `graphify explain`,"
        " `graphify path` o leyendo el archivo citado antes de reportarla como hallazgo del cierre.",
    ]
    if resultado.nivel.startswith("estructural"):
        lineas.append(
            "- **Alcance del nivel estructural:** solo se leen los encabezados de los documentos; lo que el DISEÑO"
            " declara en tablas (por ejemplo, D.1.2 y D.2.3) no se ve aquí. La pasada semántica, si el Product"
            " Owner la autoriza, cubre también el texto."
        )
    lineas += [
        "",
        "## Resumen",
        "",
        "| Medida | Cantidad |",
        "|--------|---------:|",
        f"| Elementos del deber ser analizados | {len(resultado.deber_ser)} |",
        f"| Con correspondencia en el código | {resultado.cubiertos} |",
        f"| Correspondencia débil (revisar) | {len(resultado.debiles)} |",
        f"| **El diseño lo dice y el código no lo tiene** | **{len(resultado.faltan_en_codigo)}** |",
        f"| Módulos, clases y funciones del código analizados | {len(resultado.codigo)} |",
        f"| **El código lo tiene y el diseño no lo dice** | **{len(resultado.faltan_en_diseno)}** |",
        "",
    ]
    if not resultado.hay_deriva:
        lineas += ["**Sin deriva detectada.**", ""]

    lineas += ["## El diseño lo dice y el código no lo tiene", ""]
    if resultado.faltan_en_codigo:
        lineas += ["| ID | Elemento del deber ser | Fuente |", "|----|------------------------|--------|"]
        for numero, elemento in enumerate(resultado.faltan_en_codigo, 1):
            lineas.append(f"| D-{numero} | {celda(elemento.nombre)} | {celda(elemento.fuente)} |")
    else:
        lineas.append("Ninguno.")
    lineas += ["", "## El código lo tiene y el diseño no lo dice", ""]
    if resultado.faltan_en_diseno:
        lineas += ["| ID | Tipo | Elemento del código | Archivo |", "|----|------|---------------------|---------|"]
        for numero, elemento in enumerate(resultado.faltan_en_diseno, 1):
            lineas.append(f"| C-{numero} | {elemento.tipo} | {celda(elemento.nombre)} | {celda(elemento.fuente)} |")
    else:
        lineas.append("Ninguno.")
    lineas += ["", "## Correspondencias débiles (revisar)", ""]
    if resultado.debiles:
        lineas += ["| Elemento del deber ser | Palabras que sí aparecen en el código | Fuente |", "|---|---|---|"]
        for elemento, comunes in resultado.debiles:
            lineas.append(f"| {celda(elemento.nombre)} | {celda(comunes)} | {celda(elemento.fuente)} |")
    else:
        lineas.append("Ninguna.")
    lineas += [
        "",
        "## Cómo se usa en el cierre del sprint",
        "",
        "1. QA confirma cada fila `D-n` y `C-n` (por ejemplo, `graphify explain \"<elemento>\"` sobre el grafo"
        " del código, o `graphify path` en el grafo combinado de `graphify merge-graphs`).",
        "2. Lo confirmado entra a la lista congelada del cierre como `OBS-SNN-n`: o falta código (lo corrige el"
        " desarrollador dueño), o falta diseño (lo resuelve el analista-arquitecto en una pasada documental),"
        " o es una decisión del Product Owner.",
        "3. Los falsos positivos se descartan con su motivo en el reporte del cierre.",
        "",
    ]
    return "\n".join(lineas)


COMO_GENERAR = {
    "codigo": "graphify update codigo   (análisis AST: sin LLM y sin costo)",
    "deber_ser": (
        "graphify update documentacion   (encabezados: sin LLM y sin costo); la pasada semántica\n"
        "    (graphify extract documentacion --backend <ollama|claude-cli|claude>) solo con permiso del Product Owner"
    ),
}


def main(argv: Sequence[str] | None = None) -> int:
    for flujo in (sys.stdout, sys.stderr):  # acentos legibles también en la consola de Windows
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Compara el grafo de la documentación (deber ser) con el del código (lo que es)."
    )
    parser.add_argument("--codigo", type=Path, default=GRAFO_CODIGO, help=f"graph.json del código ({GRAFO_CODIGO})")
    parser.add_argument(
        "--deber-ser", type=Path, default=GRAFO_DEBER_SER, help=f"graph.json de la documentación ({GRAFO_DEBER_SER})"
    )
    parser.add_argument("--salida", type=Path, help="archivo Markdown del reporte (sin él, se imprime)")
    parser.add_argument(
        "--todas-las-clases", action="store_true", help="reporta todas las clases, no solo las de dominio/"
    )
    parser.add_argument("--con-funciones", action="store_true", help="reporta también las funciones sueltas")
    parser.add_argument(
        "--ignorar-modulo",
        action="append",
        default=[],
        metavar="NOMBRE",
        help=f"módulo del código que no se reporta (se suma a {', '.join(MODULOS_IGNORADOS)})",
    )
    parser.add_argument("--estricto", action="store_true", help="sale con 1 si hay deriva")
    args = parser.parse_args(argv)

    faltantes = [
        (clave, ruta) for clave, ruta in (("codigo", args.codigo), ("deber_ser", args.deber_ser)) if not ruta.is_file()
    ]
    if faltantes:
        print("No se midió la deriva: falta el grafo de", file=sys.stderr)
        for clave, ruta in faltantes:
            nombre = "lo que es (código)" if clave == "codigo" else "el deber ser (documentación)"
            print(f"  - {nombre}: {ruta.as_posix()}", file=sys.stderr)
            print(f"    Genéralo desde la raíz del proyecto con: {COMO_GENERAR[clave]}", file=sys.stderr)
        print(
            "Si graphify no está instalado: uv tool install graphifyy (lo instala la persona, no un agente).\n"
            "Sin grafos el método sigue igual: QA anota la deriva como verificación omitida en el cierre.",
            file=sys.stderr,
        )
        return SALIDA_SIN_GRAFOS

    try:
        codigo = leer_grafo(args.codigo)
        deber_ser = leer_grafo(args.deber_ser)
    except ErrorDeGrafo as error:
        print(f"Error: {error}", file=sys.stderr)
        return SALIDA_USO

    resultado = comparar(
        codigo,
        deber_ser,
        todas_las_clases=args.todas_las_clases,
        con_funciones=args.con_funciones,
        ignorar_modulos=[*MODULOS_IGNORADOS, *args.ignorar_modulo],
    )
    texto = reporte(resultado, args.codigo, args.deber_ser)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(texto, encoding="utf-8", newline="\n")
        print(
            f"Reporte de deriva en {args.salida.as_posix()}: {len(resultado.faltan_en_codigo)} del diseño sin código,"
            f" {len(resultado.faltan_en_diseno)} del código sin diseño, {len(resultado.debiles)} débiles."
        )
    else:
        print(texto)
    if args.estricto and resultado.hay_deriva:
        return SALIDA_DERIVA
    return SALIDA_OK


if __name__ == "__main__":
    raise SystemExit(main())
