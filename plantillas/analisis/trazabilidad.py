"""Matriz de trazabilidad del SRS (Anexo C): RF → CU → HU y RNF → HU.

Uso:  python documentacion/analisis/trazabilidad.py [salida_temporal.md] [--escribir]

- Sin argumentos: imprime el diagnóstico (RF sin CU, RF sin HU, historias huérfanas, referencias
  inválidas, CU sin HU, elementos retirados y referencias a ellos).
- `salida_temporal.md`: además escribe ahí las filas de C.2 y C.3 (para revisarlas antes).
- `--escribir`: reemplaza el Anexo C del SRS con la matriz regenerada. El Anexo C no se edita a mano.

Qué lee del SRS (documentacion/SRS.md):
- Requisitos funcionales: filas `| RF-XXX-nn | texto | prioridad |` de las secciones 1 a 6.
  Prioridad "Retirado..." = retirado; "Fase 2..." o "Excluido..." = fuera del MVP.
- Requisitos no funcionales: filas `| RNF-nn | categoría | texto |` de la sección 4.
- Casos de uso: filas `| CU-nn | ... | Requisitos |` del Anexo A (la última columna). "Retirado en" = retirado.
- Historias: `#### HU-nn Título` del Anexo B y su línea `**Trazabilidad:**`. "Retirada en" en el título = retirada.

Qué lee de `trazabilidad.json` (junto a este script, lo mantiene el analista):
- `fase2`: lista de RF que quedan fuera del MVP a propósito (además de los marcados por prioridad).
- `verificacion`: la verificación técnica de cada RNF (columna de C.3), parte de la Definición de Terminado.
- `nota_cu_sin_hu`: aclaración que acompaña a "Casos de uso sin historia" en C.1 (por ejemplo, "fase 2").
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# En Windows la consola y las tuberías usan la página de códigos local (cp1252): sin esto los acentos
# salen corruptos. La salida de DevSkills siempre es UTF-8.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8")

AQUI = Path(__file__).resolve().parent
SRS = AQUI.parent / "SRS.md"
CONFIG = AQUI / "trazabilidad.json"


def salir(mensaje: str) -> None:
    sys.exit(f"trazabilidad.py: {mensaje}")


args = [a for a in sys.argv[1:] if a != "--escribir"]
ESCRIBIR = "--escribir" in sys.argv[1:]
SALIDA = Path(args[0]) if args else None

if not SRS.exists():
    salir(f"no existe {SRS}")
txt = SRS.read_text(encoding="utf-8")
for marca in ("## Anexo A.", "## Anexo B."):
    if marca not in txt:
        salir(f"el SRS no tiene la sección '{marca}' (usa la plantilla de DevSkills)")
config = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}

idx_a = txt.index("## Anexo A.")
idx_b = txt.index("## Anexo B.")
idx_c = txt.index("## Anexo C.") if "## Anexo C." in txt else len(txt)
cuerpo, anexo_a, anexo_b = txt[:idx_a], txt[idx_a:idx_b], txt[idx_b:idx_c]
# Los comentarios HTML (instrucciones de la plantilla y ejemplos) no cuentan.
sin_comentarios = lambda s: re.sub(r"<!--.*?-->", "", s, flags=re.S)
cuerpo, anexo_a, anexo_b = map(sin_comentarios, (cuerpo, anexo_a, anexo_b))


def expandir(s):
    """Expande 'RF-ABC-02 a RF-ABC-06' y devuelve todos los IDs RF/RNF del texto."""
    ids = set()
    for a, b in re.findall(r"(RF-[A-Z]+-\d+) a (RF-[A-Z]+-\d+)", s):
        pa, na = a.rsplit("-", 1)
        pb, nb = b.rsplit("-", 1)
        if pa == pb:
            for n in range(int(na), int(nb) + 1):
                ids.add(f"{pa}-{n:02d}")
    ids |= set(re.findall(r"RF-[A-Z]+-\d+", s))
    ids |= set(re.findall(r"RNF-\d+", s))
    return ids


# Requisitos definidos (filas de tabla en el cuerpo)
rf_def = {}
for m in re.finditer(r"^\| (RF-[A-Z]+-\d+) \| (.*?) \| ([^|]*?) \|\s*$", cuerpo, re.M):
    rf_def[m.group(1)] = m.group(3).strip()
rnf_def = {}
for m in re.finditer(r"^\| (RNF-\d+) \| ([^|]+) \|", cuerpo, re.M):
    rnf_def[m.group(1)] = m.group(2).strip()

# Elementos retirados: no se borran del documento, pero no cuentan para la cobertura.
rf_retirados = {r for r, p in rf_def.items() if p.lower().startswith("retirado")}
cu_retirados, hu_retiradas = set(), set()

# Casos de uso
cu_req = {}
for m in re.finditer(r"^\| (CU-\d+) \| (.*)$", anexo_a, re.M):
    if "Retirado en" in m.group(2):
        cu_retirados.add(m.group(1))
        continue
    cols = [c.strip() for c in m.group(2).split("|")]
    cu_req[m.group(1)] = expandir(cols[-2] if cols[-1] == "" else cols[-1])

# Historias
hu_cu, hu_req = {}, {}
for m in re.finditer(r"^#### (HU-\d+)([^\n]*)\n(.*?)(?=^#### |^### |^## |\Z)", anexo_b, re.M | re.S):
    hu, titulo, bloque = m.group(1), m.group(2), m.group(3)
    if "Retirada en" in titulo:
        hu_retiradas.add(hu)
        continue
    t = re.search(r"Trazabilidad:\*\*(.*)", bloque)
    linea = t.group(1) if t else ""
    hu_cu[hu] = set(re.findall(r"CU-\d+", linea))
    hu_req[hu] = expandir(linea)

req_cu, req_hu = defaultdict(set), defaultdict(set)
for cu, rs in cu_req.items():
    for r in rs:
        req_cu[r].add(cu)
for hu, rs in hu_req.items():
    for r in rs:
        req_hu[r].add(hu)
# La trazabilidad se cuenta explícita: una HU no hereda los RF de sus CU.


def orden(x):
    p, n = x.rsplit("-", 1)
    return (p, int(n))


def lista(s):
    return ", ".join(sorted(s, key=orden)) if s else "—"


fase2 = {r for r, p in rf_def.items() if p.lower().startswith(("fase 2", "excluido"))}
fase2 |= set(config.get("fase2", [])) & set(rf_def)

filas, sin_cu, sin_hu = [], [], []
for r in sorted(rf_def, key=orden):
    cus, hus = req_cu.get(r, set()), req_hu.get(r, set())
    if r in rf_retirados:
        estado = "Retirado"
    elif r in fase2:
        estado = "Fase 2 / fuera del MVP"
    elif cus and hus:
        estado = "Cubierto"
    else:
        estado = "**FALTA " + ("CU" if not cus else "") + (" y " if not cus and not hus else "") + ("HU" if not hus else "") + "**"
        if not cus:
            sin_cu.append(r)
        if not hus:
            sin_hu.append(r)
    filas.append(f"| {r} | {rf_def[r]} | {lista(cus)} | {lista(hus)} | {estado} |")

VERIF = config.get("verificacion", {})
rnf_filas = [f"| {r} | {rnf_def[r]} | {lista(req_hu.get(r, set()))} | {VERIF.get(r, '<!-- por definir: verificación técnica -->')} |"
             for r in sorted(rnf_def, key=orden)]
rnf_sin_verif = [r for r in rnf_def if r not in VERIF]

huerfanas = [h for h, rs in hu_req.items() if not any(x in rf_def or x in rnf_def for x in rs)]
refs_invalidas = sorted({x for rs in list(cu_req.values()) + list(hu_req.values()) for x in rs
                         if (x.startswith("RF-") and x not in rf_def) or (x.startswith("RNF-") and x not in rnf_def)}, key=orden)
cu_sin_hu = sorted(set(cu_req) - {c for s in hu_cu.values() for c in s}, key=orden)
# Un CU o una HU vigente no debe apoyarse en un requisito retirado ni en un CU retirado.
refs_retiradas = sorted({x for rs in list(cu_req.values()) + list(hu_req.values()) for x in rs
                         if x in rf_retirados} | {c for s in hu_cu.values() for c in s if c in cu_retirados}, key=orden)

print(f"RF definidos: {len(rf_def)} | RNF: {len(rnf_def)} | CU: {len(cu_req)} | HU: {len(hu_req)}")
print("RF sin CU:", sin_cu)
print("RF sin HU:", sin_hu)
print("HU huérfanas:", huerfanas)
print("Referencias a RF o RNF inexistentes:", refs_invalidas)
print("CU sin HU:", cu_sin_hu)
print("RNF sin verificación técnica en trazabilidad.json:", sorted(rnf_sin_verif, key=orden))
print("Retirados (RF, CU, HU):", sorted(rf_retirados, key=orden), sorted(cu_retirados, key=orden), sorted(hu_retiradas, key=orden))
print("Referencias vigentes a elementos retirados:", refs_retiradas)
if SALIDA:
    SALIDA.write_text("\n".join(filas) + "\n@@RNF@@\n" + "\n".join(rnf_filas), encoding="utf-8")

if ESCRIBIR:
    n_mvp = sum(1 for r in rf_def if r not in fase2 and r not in rf_retirados)
    n_cub = sum(1 for r in rf_def if r not in fase2 and r not in rf_retirados and req_cu.get(r) and req_hu.get(r))
    porcentaje = f"{n_cub / n_mvp:.0%}" if n_mvp else "—"
    nota = config.get("nota_cu_sin_hu", "")
    nota = f" ({nota})" if nota and cu_sin_hu else ""
    filas_c2 = "\n".join(filas) if filas else "| — | — | — | — | Sin requisitos todavía |"
    filas_c3 = "\n".join(rnf_filas) if rnf_filas else "| — | — | — | Sin requisitos no funcionales todavía |"
    anexo = f"""## Anexo C. Matriz de trazabilidad

> Generada automáticamente desde este documento con `documentacion/analisis/trazabilidad.py`: lee los requisitos de la sección 3, la columna "Requisitos" del catálogo de casos de uso (Anexo A) y la línea "Trazabilidad" de cada historia (Anexo B). Si cambia un requisito, un caso de uso o una historia, **se vuelve a generar**; no se edita a mano.

### C.1 Resumen de cobertura

| Indicador | Valor |
|-----------|-------|
| Requisitos funcionales definidos | {len(rf_def)} |
| Requisitos funcionales del MVP | {n_mvp} |
| Requisitos del MVP con caso de uso **y** historia | **{n_cub} de {n_mvp} ({porcentaje})** |
| Requisitos de fase 2 o exclusiones (sin historia a propósito) | {len(fase2)} |
| Requisitos retirados (se conservan en el documento, no cuentan) | {len(rf_retirados)}: {lista(rf_retirados)} |
| Casos de uso vigentes | {len(cu_req)} (retirados: {lista(cu_retirados)}) |
| Historias de usuario vigentes | {len(hu_req)} (retiradas: {lista(hu_retiradas)}) |
| Referencias vigentes a elementos retirados | {len(refs_retiradas)} |
| Historias sin requisito (huérfanas) | {len(huerfanas)} |
| Referencias a requisitos inexistentes | {len(refs_invalidas)} |
| Casos de uso sin historia | {lista(set(cu_sin_hu))}{nota} |

**Cómo se usa:**
- **QA:** cada requisito del MVP tiene al menos una historia, y cada historia tiene escenarios Gherkin que se convierten en pruebas. La matriz dice qué probar para dar un requisito por cumplido.
- **Gestión de cambios:** antes de cambiar un requisito, búscalo en la matriz para ver qué casos de uso e historias se afectan.
- **Desarrollo:** el backlog se arma con las historias; la matriz evita que quede un requisito sin implementar.

### C.2 Requisitos funcionales → casos de uso → historias

| Requisito | Prioridad | Casos de uso | Historias | Estado |
|-----------|-----------|--------------|-----------|--------|
""" + filas_c2 + """

### C.3 Requisitos no funcionales → historias

> Los requisitos no funcionales no siempre tienen una historia de usuario, porque muchos son atributos técnicos. Todos tienen una **verificación técnica** definida, que forma parte de la Definición de Terminado.

| Requisito | Categoría | Historias que lo verifican | Verificación técnica |
|-----------|-----------|----------------------------|----------------------|
""" + filas_c3 + "\n"
    t = SRS.read_text(encoding="utf-8")
    if "## Anexo C." in t:
        t = t[:t.index("## Anexo C.")].rstrip() + "\n\n"
    else:
        t = t.rstrip() + "\n\n---\n\n"
    SRS.write_text(t + anexo, encoding="utf-8", newline="\n")
    print("Anexo C escrito")
