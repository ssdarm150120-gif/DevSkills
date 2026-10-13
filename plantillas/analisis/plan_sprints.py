"""Genera el backlog priorizado y la asignación a sprints de documentacion/PLAN.md y el tablero plan_sprints.html.

Uso:  python documentacion/analisis/plan_sprints.py

De dónde sale cada dato (nada se escribe a mano en el plan):
- Títulos de las historias: del SRS (`#### HU-nn Título` del Anexo B). Las historias retiradas
  ("Retirada en X.Y" en el título) siguen en el SRS para conservar el rastro, pero no se planifican.
- Entregas, elementos (HU y EN) con sus puntos, habilitadores, velocidad, duración del sprint y
  fecha de inicio: de `plan_entregas.json`, junto a este script. Lo llena el analista con la skill
  `planear-entregas`. Para repriorizar o reestimar se edita ese archivo y se vuelve a ejecutar.
- Estado oficial de cada elemento: de `documentacion/avance/estado_backlog.json` (lo escribe la
  skill `registrar-avance`). Lo que está en "Listo" aparece tachado.
- Nombre del proyecto: del segundo encabezado de PLAN.md (`## <Nombre del proyecto>`).

El script reemplaza solo lo que está entre los marcadores
`<!-- INICIO BACKLOG GENERADO -->` y `<!-- FIN BACKLOG GENERADO -->` de PLAN.md.
"""
import datetime as _dt
import json
import pathlib
import re
import sys
import unicodedata

DOC = pathlib.Path(__file__).resolve().parent.parent  # carpeta documentacion/
ANALISIS = DOC / "analisis"
DATOS = ANALISIS / "plan_entregas.json"
ESTADO_ARCHIVO = DOC / "avance" / "estado_backlog.json"
PLAN = DOC / "PLAN.md"
INI, FIN = "<!-- INICIO BACKLOG GENERADO -->", "<!-- FIN BACKLOG GENERADO -->"


def salir(mensaje: str) -> None:
    sys.exit(f"plan_sprints.py: {mensaje}")


for requerido in (DOC / "SRS.md", PLAN, DATOS):
    if not requerido.exists():
        salir(f"no existe {requerido.relative_to(DOC.parent)}")

srs = (DOC / "SRS.md").read_text(encoding="utf-8")
srs = re.sub(r"<!--.*?-->", "", srs, flags=re.S)  # las instrucciones y ejemplos de la plantilla no cuentan
titulos = {m.group(1): m.group(2).replace("⭐", "").strip()
           for m in re.finditer(r"^#### (HU-\d+) (.+)$", srs, re.M)
           if "retirada en" not in m.group(2).lower()}

datos = json.loads(DATOS.read_text(encoding="utf-8"))
VELOCIDAD = int(datos.get("velocidad", 0))
DIAS_SPRINT = int(datos.get("dias_sprint", 14))
habilitadores = {k: v for k, v in datos.get("habilitadores", {}).items() if not k.startswith("_")}
entregas = [(str(e["num"]), e["nombre"], e.get("objetivo", ""), [(i, int(p)) for i, p in e.get("items", [])])
            for e in datos.get("entregas", [])]

txt_plan = PLAN.read_text(encoding="utf-8")
if INI not in txt_plan or FIN not in txt_plan:
    salir(f"PLAN.md no tiene los marcadores {INI} y {FIN}")
m_nombre = re.search(r"^## (.+)$", txt_plan, re.M)
PROYECTO = m_nombre.group(1).strip() if m_nombre else "Proyecto"


def escribir_bloque(cuerpo: str) -> None:
    t = PLAN.read_text(encoding="utf-8")
    a, b = t.index(INI) + len(INI), t.index(FIN)
    PLAN.write_text(t[:a] + "\n" + cuerpo + "\n" + t[b:], encoding="utf-8", newline="\n")


if not any(items for *_, items in entregas):
    escribir_bloque("> Todavía no hay entregas planificadas. El analista las carga en "
                    "`documentacion/analisis/plan_entregas.json` (skill `planear-entregas`) y vuelve a ejecutar este script.\n")
    print("Plan vacío: no hay elementos en plan_entregas.json. Se dejó el aviso en PLAN.md; el tablero no se generó.")
    if titulos:
        print(f"Historias del SRS por planificar: {len(titulos)}")
    sys.exit(0)

if VELOCIDAD <= 0:
    salir("'velocidad' debe ser un entero positivo en plan_entregas.json")
try:
    INICIO = _dt.date.fromisoformat(datos["inicio"])
except (KeyError, ValueError):
    salir("'inicio' debe ser una fecha AAAA-MM-DD en plan_entregas.json")


def fechas(n):
    a = INICIO + _dt.timedelta(days=DIAS_SPRINT * (n - 1))
    return a, a + _dt.timedelta(days=DIAS_SPRINT - 1)


def fmt(d):
    return d.strftime("%d/%m/%Y")


# Validación: todas las historias del SRS están planificadas una sola vez, y todo lo planificado existe
planificadas = [i for _, _, _, items in entregas for i, _ in items if i.startswith("HU-")]
todos = [i for _, _, _, items in entregas for i, _ in items]
faltan = sorted(set(titulos) - set(planificadas), key=lambda x: int(x[3:]))
dup = sorted({x for x in todos if todos.count(x) > 1})
hu_inexistentes = sorted({i for i in planificadas if i not in titulos})
en_sin_definir = sorted({i for i in todos if i.startswith("EN-") and i not in habilitadores})
otros = sorted({i for i in todos if not i.startswith(("HU-", "EN-"))})
for lista, msg in ((faltan, "Historias del SRS sin planificar"), (dup, "Elementos duplicados"),
                   (hu_inexistentes, "Historias planificadas que no existen (o están retiradas) en el SRS"),
                   (en_sin_definir, "Habilitadores sin definir en 'habilitadores'"),
                   (otros, "IDs que no son HU-nn ni EN-nn")):
    if lista:
        salir(f"{msg}: {lista}")


def titulo(i):
    return titulos[i] if i.startswith("HU-") else habilitadores[i]["titulo"]


# Avance oficial: {"HU-59": {"estado": "Listo", "fecha": "AAAA-MM-DD", "reporte": "avance/S01/HU-59.md"}, ...}
avance = json.loads(ESTADO_ARCHIVO.read_text(encoding="utf-8")) if ESTADO_ARCHIVO.exists() else {}
ICONO = {"Listo": "✅ Listo", "En validación": "🔍 En validación", "En proceso": "🔄 En proceso", "Bloqueado": "⛔ Bloqueado"}
desconocidos = sorted(set(avance) - set(todos))
if desconocidos:
    salir(f"IDs en estado_backlog.json que no están en el plan: {desconocidos}")

out, resumen, sprint, carga = [], [], 1, 0
filas_sprint = []
for num, nombre, objetivo, items in entregas:
    if not items:
        continue
    pts = sum(p for _, p in items)
    hechos = sum(p for i, p in items if avance.get(i, {}).get("estado") == "Listo")
    s_ini = sprint
    out.append(f"\n#### Entrega {num}: {nombre}\n**Objetivo medible:** {objetivo}. **Total:** {pts} puntos · **Terminados:** {hechos} ({hechos * 100 // pts if pts else 0} %).\n")
    out.append("| Prioridad | ID | Elemento | Puntos | Sprint | Estado |\n|-----------|----|----------|--------|--------|--------|")
    for k, (i, p) in enumerate(items, 1):
        if carga + p > VELOCIDAD and carga > 0:
            sprint, carga = sprint + 1, 0
        carga += p
        ref = f" ({habilitadores[i]['ref']})" if i.startswith("EN-") and habilitadores[i].get("ref") else ""
        a_ = avance.get(i, {})
        est = a_.get("estado", "Pendiente")
        celda = ICONO.get(est, "Pendiente")
        if est == "Listo":
            celda += f" {a_.get('fecha', '')}" + (f" · [reporte]({a_['reporte']})" if a_.get("reporte") else "")
            out.append(f"| ~~{num}.{k}~~ | ~~{i}~~ | ~~{titulo(i)}{ref}~~ | ~~{p}~~ | S{sprint} | {celda} |")
        else:
            out.append(f"| {num}.{k} | {i} | {titulo(i)}{ref} | {p} | S{sprint} | {celda} |")
        filas_sprint.append((sprint, num, i, p))
    resumen.append((num, nombre, pts, s_ini, sprint, hechos, objetivo))
    sprint, carga = sprint + 1, 0   # cada entrega cierra su propio sprint

total = sum(r[2] for r in resumen)
total_hechos = sum(r[5] for r in resumen)
n_sprints = sprint - 1
tabla_res = ["| Entrega | Nombre | Puntos | Terminados | Sprints | Fechas estimadas |", "|---------|--------|--------|------------|---------|------------------|"]
for num, nombre, pts, a, b, h, _ in resumen:
    tabla_res.append(f"| {num} | {nombre} | {pts} | {h} ({h * 100 // pts} %) | S{a} a S{b} | {fmt(fechas(a)[0])} a {fmt(fechas(b)[1])} |")
tabla_res.append(f"| **Total** | | **{total}** | **{total_hechos} ({total_hechos * 100 // total} %)** | **{n_sprints} sprints** | **{fmt(INICIO)} a {fmt(fechas(n_sprints)[1])} ({n_sprints * DIAS_SPRINT // 7} semanas)** |")

cuerpo = (f"> Velocidad supuesta: **{VELOCIDAD} puntos por sprint** de {DIAS_SPRINT // 7} semanas. Cada entrega cierra en su propio sprint. "
          f"Los elementos ~~tachados~~ pasaron el ciclo de calidad (desarrollo → QA → Angel Fixer) y tienen su reporte en `documentacion/avance/`.\n\n"
          + "\n".join(tabla_res) + "\n" + "\n".join(out))
escribir_bloque(cuerpo)
print(f"Terminados: {total_hechos} de {total} puntos | Historias: {len(planificadas)} | Habilitadores: {sum(1 for f in filas_sprint if f[2].startswith('EN-'))} | Puntos: {total} | Sprints: {n_sprints}")
for r in resumen:
    print(r[:5])

# ==================== Tablero HTML con sprints y diagrama de Gantt ====================
prioridad = {i: f"{num}.{k}" for num, _, _, items in entregas for k, (i, _) in enumerate(items, 1)}
tablero = {
    "inicio": INICIO.isoformat(),
    "velocidad": VELOCIDAD,
    "entregas": [{"num": num, "nombre": nombre, "objetivo": obj, "puntos": pts, "sprint_inicio": a, "sprint_fin": b}
                 for num, nombre, pts, a, b, _h, obj in resumen],
    "sprints": [{"num": n, "inicio": fechas(n)[0].isoformat(), "fin": fechas(n)[1].isoformat(),
                 "entregas": sorted({e for s, e, _, _ in filas_sprint if s == n})}
                for n in range(1, n_sprints + 1)],
    "items": [{"id": i, "titulo": titulo(i), "puntos": p, "sprint": s, "entrega": e, "prioridad": prioridad[i], "estado": avance.get(i, {}).get("estado", "Pendiente")}
              for s, e, i, p in filas_sprint],
}
sin_acentos = unicodedata.normalize("NFKD", PROYECTO).encode("ascii", "ignore").decode()
slug = re.sub(r"[^a-z0-9]+", "_", sin_acentos.lower()).strip("_") or "proyecto"
plantilla = (ANALISIS / "plan_sprints_plantilla.html").read_text(encoding="utf-8")
# Los datos van dentro de <script>: se escapa "</" para que un título no pueda cerrar la etiqueta.
html = (plantilla.replace("__DATA__", json.dumps(tablero, ensure_ascii=False).replace("</", "<\\/"))
        .replace("__TITULO__", PROYECTO.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        .replace("__CLAVE__", json.dumps(f"{slug}_sprints_v1"))
        .replace("__ARCHIVO_CSV__", json.dumps(f"plan_sprints_{slug}.csv")))
(DOC / "plan_sprints.html").write_text(html, encoding="utf-8", newline="\n")
print("Tablero generado: documentacion/plan_sprints.html")
