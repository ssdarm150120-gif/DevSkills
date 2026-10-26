---
name: pasada-documental
description: >
  Pasada de versión de la documentación del proyecto: sube la versión del SRS y del DISEÑO con su historial,
  registra preguntas P-nn y decisiones (quién decidió), regenera el Anexo C, el plan, el tablero y los Word,
  y deja un commit docs separado del código. Trigger: "/devskills:pasada-documental", "pasada documental",
  "sube la versión del SRS", "actualiza el diseño", "registra la decisión en el SRS", "cambio de alcance",
  "retrospectiva del Product Owner", "regenera los Word".
license: MIT
metadata:
  author: devskills
  version: "1.0"
argument-hint: "[motivo de la pasada: decisión, hueco encontrado, cambio de alcance, cierre de elemento]"
---

## When to Use

- El Product Owner tomó decisiones o pidió cambios (una retrospectiva, un cambio de alcance, una respuesta a un `P-nn`).
- Un agente encontró un hueco o una contradicción en el SRS o en el DISEÑO y el ciclo se detuvo.
- Una revisión (QA, Angel Fixer, verificador) dejó precisiones que deben quedar escritas.
- Al cerrar un elemento del backlog, para que los documentos y los Word no queden desfasados.

Motivo de esta pasada: $ARGUMENTS

La ejecuta el agente `devskills:analista-arquitecto`; el commit lo hace el orquestador.

## Critical Patterns

### 1. Antes de escribir: análisis de impacto
Para cada punto que cambia, lee lo que existe (solo lectura) y clasifícalo:

| Clasificación | Qué significa |
|---------------|---------------|
| YA CUBIERTO | Un requisito o historia vigente ya lo dice. Se cita el ID; no cambia nada |
| CAMBIO A ALGO EXISTENTE | Modifica un RF, CU o HU vigente |
| NUEVO | No existe: IDs nuevos (se marcan "propuesto" hasta que el Product Owner los aprueba) |
| CONFLICTO | Contradice una restricción, una decisión aprobada o el plan |
| SOLO PRESENTACIÓN | No genera requisitos (va a 1.1.2 del SRS o a la presentación) |
| AMBIGUO | No se puede clasificar sin preguntar |

Por cada punto: **qué existe hoy** (con IDs), **impacto** en SRS, DISEÑO y PLAN (incluidos los efectos laterales sobre otros requisitos) y **preguntas para el Product Owner que bloquean**. Lo de negocio se pregunta con `devskills:preguntar-al-po` y se espera la respuesta; lo técnico lo decide el orquestador y queda registrado como tal.

### 2. Orden de la pasada (no se salta ningún paso)
1. **SRS primero.** Si cambia un requisito, el SRS sube de versión antes que cualquier otro documento.
   - Encabezado: Versión, Fecha y Estado (qué línea base es y qué pendientes siguen abiertos).
   - Historial: una fila nueva arriba, con el título del cambio en negritas, los IDs tocados y las decisiones separadas en **Decisiones del Product Owner** y **Decisiones del orquestador**. Si no hay IDs nuevos, dilo ("Sin IDs nuevos").
   - Sección 6: cada pregunta es un `P-nn`; al resolverla, la respuesta queda en su Estado y se propaga a RF, CU y HU **en la misma versión**.
   - Lo que sale se marca **Retirado en X.Y** (no se borra). Lo agregado a un módulo validado se marca **para validar**.
2. **Anexo C.** Regenera con `trazabilidad.py --escribir` y corrige hasta tener 0 faltantes, 0 huérfanas, 0 referencias inválidas y 0 referencias a retirados. Si hay un RNF nuevo, agrega su verificación técnica a `trazabilidad.json`.
3. **DISEÑO.** Sube su versión, alineado con la versión nueva del SRS ("alineado con el SRS X.Y"); di si hay módulos o flechas nuevas ("Sin módulos ni flechas nuevos"). Una flecha nueva va primero al diagrama de D.1.3.
4. **PLAN.** Si cambiaron historias, habilitadores o puntos: actualiza `plan_entregas.json`, sube la versión de `PLAN.md` con su fila de historial (total de puntos y sprints antes y después) y regenera.
5. **CONTEXTO y prototipos.** Actualiza `documentacion/CONTEXTO.md` si cambian módulos, reglas o integraciones; si cambian pantallas, agrega un prompt de actualización o de correcciones con `devskills:prompts-figma`.
6. **Word.** Regenera con `md_a_word.py`. Los `.md` son la fuente de verdad: nunca se edita un Word.
7. **Grafo del deber ser (si `graphify` está instalado).** Con los documentos ya en su versión nueva, desde la raíz: `GRAPHIFY_BACKEND=none graphify update documentacion` (encabezados de SRS, DISEÑO, PLAN, CONTEXTO y evaluación de alternativas; **sin LLM y sin costo**). La pasada **semántica** (`graphify extract documentacion --backend <backend>`) solo si la decisión "Pasada semántica del deber ser" de `CONTEXTO.md` la autoriza, con **ese** backend y nunca sin `--backend`; si está vacía, no se corre y se avisa al orquestador para que la pregunte al Product Owner. Revisa que `documentacion/graphify-out/graph.json` no contenga datos ni secretos (las exclusiones están en `.graphifyignore`). Sin `graphify`, este paso se omite y se dice en el reporte.
8. **Commit `docs:`**, separado del código.

### 3. Versionado
- Borradores: `0.x`. La **línea base** de requisitos sube la versión mayor (por ejemplo, `1.0`); cada pasada posterior sube la menor.
- Un cambio de alcance grande lo anuncia el historial en negritas ("**Cambio de alcance.**") y agrupa sus pendientes en una subsección propia de la sección 6.
- Cada documento lleva su propia numeración; el DISEÑO y el PLAN dicen con qué versión del SRS están alineados.

### 4. Quién decidió
- **Decisión del Product Owner:** negocio, alcance, prioridad, riesgo aceptado, costo. Solo se escribe así si el Product Owner lo dijo; se anota la fecha.
- **Decisión del orquestador:** técnica o derivada de una revisión. Se escribe como tal y queda "pendiente de validar por el Product Owner" hasta que la valide; entonces el historial dice "validada por el Product Owner".
- **Decisión del desarrollador aceptada por la verificación:** va en el reporte de avance del elemento, no en el SRS.

### 5. Commit de documentación
- Lo hace el **orquestador** (los agentes no ejecutan comandos de git que cambien el árbol ni la historia).
- Un commit solo de `documentacion/`, separado del commit de código del elemento: mensaje en inglés, Conventional Commits, **sin atribución de IA ni `Co-Authored-By`**. Ejemplos: `docs: SRS 5.3 absolute session cap`, `docs: design 1.13 event bus decisions`, `docs: regenerate Word documents after EN-03`. El grafo del deber ser va en su propio commit: `git add -- documentacion/graphify-out/graph.json documentacion/graphify-out/GRAPH_REPORT.md && git commit -m "docs(graph): refresh design graph for SRS 5.3"`.
- Antes del commit, el escaneo de secretos del cierre de sesión (`devskills:guarda-todo`) cubre también `documentacion/`, incluido `documentacion/graphify-out/` (gitleaks escanea lo versionado y lo nuevo no ignorado).

### 6. Verificación de la pasada
- [ ] Versión, fecha y estado del encabezado coinciden con la última fila del historial, en cada documento tocado.
- [ ] Ningún `P-nn` resuelto quedó sin propagar; ningún ID nuevo quedó sin trazabilidad.
- [ ] `trazabilidad.py` sin faltantes; `plan_sprints.py` sin errores.
- [ ] Los Word se generaron y ningún diagrama quedó como bloque de código (si hay mermaid-cli).
- [ ] No se dejó `_tmp.md` ni otros temporales en el repositorio.
- [ ] Si hay `graphify`: el grafo del deber ser se regeneró después de los documentos, sin LLM salvo autorización del Product Owner, y gitleaks quedó limpio.
- [ ] Todo en español de México con tuteo; sin datos personales ni datos reales del negocio.

## Commands

```bash
python documentacion/analisis/trazabilidad.py _tmp.md --escribir   # Anexo C (borra _tmp.md al terminar)
python documentacion/analisis/plan_sprints.py                      # PLAN.md (P.2.2) y plan_sprints.html
"$PYDOC" documentacion/analisis/md_a_word.py --mermaid <carpeta_mermaid_cli>   # todos los Word
"$PYDOC" documentacion/analisis/md_a_word.py --solo SRS              # solo un documento
GRAPHIFY_BACKEND=none graphify update documentacion                 # grafo del deber ser, encabezados (sin LLM)
graphify extract documentacion --backend ollama                     # semántico: SOLO si CONTEXTO.md lo autoriza (y con ese backend)
```

### Instalar las dependencias de los Word (una vez, sin tocar nada global)
Van en una carpeta del usuario, fuera del repositorio (ningún archivo nuevo va en la raíz del proyecto), y sirven para todos los proyectos:
```bash
mkdir -p ~/.devskills/doc && cd ~/.devskills/doc
# Python: un entorno propio de la documentación (no el entorno del código)
python -m venv venv
venv/Scripts/python -m pip install python-docx==1.2.0 pillow==12.3.0      # en Linux o macOS: venv/bin/python
# mermaid-cli: con su propio package.json (sin él, npm instala en la primera carpeta superior que tenga uno)
npm init -y
npm install --save-exact @mermaid-js/mermaid-cli@12.0.0      # versión fija a propósito: no uses un npm install sin versión
```
- Para usar el Chrome ya instalado en lugar de descargar otro, define `PUPPETEER_SKIP_DOWNLOAD=1` antes de `npm install` y crea `~/.devskills/doc/puppeteer.json` con `{"executablePath": "<ruta a chrome>"}`.
- `md_a_word.py` necesita `python-docx` y `pillow`, que viven en ese entorno y no en el del código ni en el del sistema. Por eso todos los comandos de los Word usan `"$PYDOC"`, el Python de ese entorno: `PYDOC=~/.devskills/doc/venv/Scripts/python` (en Linux o macOS, `~/.devskills/doc/venv/bin/python`). Pasa también la carpeta: `"$PYDOC" documentacion/analisis/md_a_word.py --mermaid ~/.devskills/doc`. Los demás generadores (`plan_sprints.py`, `trazabilidad.py`, `exportar_sesion.py`) usan solo la biblioteca estándar y corren con el Python del sistema.
- Sin mermaid-cli el script funciona igual: avisa y deja los diagramas como bloque de código.
- Los PNG de los diagramas se guardan en caché en `documentacion/word/_diagramas/`.

## Resources

- `devskills:redactar-srs`, `devskills:redactar-diseno`, `devskills:planear-entregas`: las convenciones de cada documento.
- `devskills:preguntar-al-po`: formato de las preguntas y registro de quién decidió.
