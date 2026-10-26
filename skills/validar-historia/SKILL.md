---
name: validar-historia
description: >
  Validación de QA del comportamiento. Modo normal, cierre de sprint: QA completo sobre todo el diff del sprint
  (todos los Gherkin de sus historias de punta a punta, regresiones entre historias, RNF del Anexo C, 10 a 15
  mutaciones dirigidas al riesgo y ataques cuando aplica). Modo por historia: solo para los elementos de la
  excepción (seguridad, plataforma o críticos). Veredicto APROBADA / APROBADA CON OBSERVACIONES / RECHAZADA.
  Trigger: cuando QA valida el cierre de un sprint, un elemento de la excepción o re-valida tras correcciones.
license: MIT
metadata:
  author: devskills
  version: "2.0"
---

## When to Use

- **Cierre de sprint (modo normal):** todos los elementos del sprint están integrados en `main` (`En validación` o `Listo`) y el orquestador lanza el QA completo sobre el diff del sprint (sección 5 de `devskills:ciclo-historia`).
- **Por historia (solo la excepción):** un elemento de seguridad, de plataforma o núcleo compartido, o marcado como crítico por el orquestador, pasa por el ciclo completo antes de su merge.
- Una re-validación después de correcciones (del desarrollador o fixes del Angel Fixer) en el modo por historia.
- Una ronda con **lista congelada**: se verifica solo esa lista y las regresiones.

## Critical Patterns

### 0. Modos
QA revisa el **comportamiento**; el código (estilo, arquitectura, límites de módulos, deuda) es del Angel Fixer. No repitas su revisión.

| | Cierre de sprint (normal) | Por historia (excepción) |
|---|---|---|
| Alcance | `git diff inicio-sNN..main` del sprint (la base la da el orquestador) y todas sus historias | Un elemento y su punto de control |
| Gherkin | **Todos** los escenarios de las historias del sprint, de punta a punta | Los escenarios del elemento |
| Regresiones | Batería completa y escenarios que **cruzan historias** (datos, estados, permisos y eventos compartidos); los elementos de la excepción del sprint entran aquí | Batería completa |
| RNF | Los que citan las historias del sprint, con su verificación técnica del Anexo C | Los del elemento |
| Mutaciones | **10 a 15**, dirigidas a lo más riesgoso del diff (reglas de negocio, permisos, transiciones de estado, dinero, concurrencia) | Las reglas importantes del elemento |
| Ataques | Cuando aplica: los RNF de seguridad y los riesgos `S-nn` que toca el sprint | Siempre que el elemento sea de seguridad |
| Entradas extra | Las notas que dejaron las verificaciones ligeras de cada elemento | El veredicto anterior, si es re-validación |
| Deriva (deber ser frente a lo que es) | Confirma cada candidato de `documentacion/avance/S{NN}/DERIVA-S{NN}.md`, si el orquestador lo generó | No aplica |

Los defectos del cierre de sprint llevan el ID `DEF-SNN-n` (y `OBS-SNN-n` las observaciones), el elemento al que pertenecen y su desarrollador dueño; el orquestador los congela como lista.

### 0b. Grafo primero (ahorra tokens)
Si el proyecto tiene grafos de Graphify (`codigo/graphify-out/graph.json`, `documentacion/graphify-out/graph.json`), antes de explorar el código para ubicar una regla, un permiso o una transición: `graphify query "<pregunta>" --graph codigo/graphify-out/graph.json --budget 1500`, `graphify explain "<Nombre>"`, `graphify path "<A>" "<B>"` o `graphify affected "<Nombre>"` (con el mismo `--graph`), y `codigo/graphify-out/GRAPH_REPORT.md` para los módulos centrales. Para elegir las **mutaciones dirigidas** y los **escenarios que cruzan historias**, `graphify affected` sobre lo que tocó el sprint señala qué más depende de ello. Después se leen **solo** los archivos y líneas citados. El grafo refleja `main` al último merge; lo que no esté ahí se lee con `git diff`. Sin grafo o sin `graphify`, se trabaja igual con lecturas normales (no es un hallazgo y no se instala nada). Los comandos de consulta son de solo lectura.

### 1. Independencia
QA **no corrige código de producción**. Escribe y mantiene las **pruebas de aceptación** y reporta defectos. Si una prueba falla, el defecto vuelve al desarrollador. QA trabaja sobre el commit de punto de control que le indica el orquestador y nunca ejecuta en el repositorio nada que escriba archivos de `codigo/` (las mutaciones van en una copia del scratchpad).

### 2. Del Gherkin del SRS a pruebas ejecutables
- El desarrollador deja el `.feature` con los escenarios de la historia (Anexo B) copiados **tal cual** y sus pasos con pytest-bdd (`devskills:implementar-historia`); el Angel Fixer solo comprueba que cada escenario tenga su prueba. **QA comprueba que la copia sea literal** (no se reescriben ni se suavizan) y que la prueba ejercite el comportamiento de punta a punta (de la vista o el caso de uso hasta la base de pruebas y el evento), no un atajo.
- Si falta un escenario, un paso es débil o el `.feature` no coincide con el SRS, QA completa o corrige **la prueba de aceptación** (es suya; nunca el código de producción) con datos ficticios y los adaptadores falsos de los sistemas externos. El reloj se controla en la prueba.
- En el cierre de sprint QA agrega los **escenarios de regresión entre historias** que hagan falta (por ejemplo, que la historia B no rompa la regla de la historia A sobre el mismo dato).
- **Cada escenario del SRS debe tener su prueba.** Un escenario sin prueba = historia no validada.
- Si un escenario depende de un módulo que todavía no existe, se prueba hasta el límite de los módulos que sí existen y se reporta qué parte cierra otro elemento (con su ID). Cerrar así requiere la aceptación del Product Owner.

### 3. Requisitos no funcionales
Revisar los RNF que cita la historia y su "verificación técnica" del Anexo C (subagente `devskills:qa-no-funcional`): seguridad (permisos por rol, tokens, firmas de webhooks, datos sensibles, sesiones), rendimiento (umbrales del SRS), accesibilidad y formatos.

### 4. Batería y mutaciones
- Desde `codigo/`: `python -m pytest`, `ruff check .`, `ruff format --check .`, `mypy .`, `lint-imports`, `bandit`, `pip-audit`, `python manage.py makemigrations --check --dry-run` y semgrep (siguiente punto).
- **semgrep igual que el CI:** la **misma versión** que fija `.github/workflows/ci.yml` del proyecto (`semgrep==<versión>`; hoy `1.178.0`). Una versión distinta no vale: sus reglas cambian. Solo se usa una vía que **ya esté instalada**: ningún agente instala semgrep, pipx, WSL ni Docker; si falta, se detiene y lo reporta (el orquestador lo pregunta al usuario; en Windows, la instalación en WSL va en un venv: `python3 -m venv ~/semgrep && ~/semgrep/bin/pip install semgrep==<versión del CI>`, ver `devskills doctor`). Vías, de la preferida a la alternativa: (1) **nativo** en macOS y Linux: `pipx run --spec "semgrep==1.178.0" semgrep scan --config p/python --config p/django --error --metrics=off --exclude pruebas --exclude conftest.py .`; (2) en Windows, el mismo comando dentro de **WSL**; (3) **Docker** (opcional), con el montaje en **solo lectura** (`:ro`): `MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/src:ro" -w /src semgrep/semgrep:1.178.0@sha256:32e459968daabe7ab86968184a29109b9564aa00392401156f9788452b42786b semgrep scan --config p/python --config p/django --error --metrics=off --exclude pruebas --exclude conftest.py .` (en Linux o macOS, `-v "$PWD:/src:ro"` y sin `MSYS_NO_PATHCONV`). Desde `codigo/`. Se exige **código de salida 0 y "Findings: 0"**; un hallazgo es un defecto aunque el código local pase. En el CI de GitHub semgrep es **siempre obligatorio**; si la máquina no tiene ninguna de las tres vías, se reporta "semgrep pendiente del CI" y el orquestador lo trata como verificación pendiente (ver `devskills:ciclo-historia`).
- **Un hallazgo de semgrep se corrige o se suprime con motivo; nunca se excluye.** Corregir el código es lo normal. Si de verdad es un falso positivo, se suprime **en esa línea** con `# nosemgrep: <regla>` y una explicación; **no se agregan `--exclude` ni se ignoran carpetas** para que "pase": la lista de exclusiones del CI (`pruebas`, `conftest.py`) no crece. Lo mismo vale para gitleaks: un falso positivo se suprime con `gitleaks:allow` en esa misma línea y el motivo, y nunca se excluye una carpeta o un archivo del escaneo.
- **Lección de `django-no-csrf-token`:** la regla es genérica y solo reconoce `{% csrf_token %}` si el `</form>` está a **10 líneas o menos**. Un formulario largo con el token lejos del cierre da un falso positivo que pone el CI en rojo: se parte el formulario en parciales (`{% include %}`) para que el token quede junto a su `</form>`; no se silencia la regla.
- Pruebas destructivas o de permisos de base de datos (por ejemplo, el `INSERT` con un usuario de solo lectura) **solo contra la base de pruebas**, nunca contra la de desarrollo ni contra datos reales.
- Mutaciones dirigidas **en una copia del scratchpad**: cada regla importante debe tener una prueba que falle si se rompe. En el cierre de sprint son **10 a 15**, elegidas por riesgo sobre el diff del sprint (no al azar ni repartidas por igual). Una mutación que sobrevive es una observación.
- Ataques (cuando aplica, delegados en `devskills:qa-no-funcional`): fuerza bruta sobre el ingreso, acceso a lo de otro usuario (IDOR) y escalamiento de rol, CSRF, firmas de webhooks inválidas o repetidas, archivos maliciosos o con rutas manipuladas. **Solo contra la base de pruebas** y el servidor de pruebas, nunca contra desarrollo ni datos reales.

### 4b. Deriva entre el deber ser y lo que es (cierre de sprint)
Si existe `DERIVA-S{NN}.md` (lo genera el orquestador con `deriva_grafos.py` al abrir el cierre), cada fila es un **candidato**, no un hallazgo:
- `D-n` (el diseño lo dice y el código no lo tiene): confirma con `graphify query`/`explain` sobre el grafo del código y, si hace falta, leyendo la sección citada del SRS o del DISEÑO. Si el elemento del diseño pertenece a una historia **de este sprint**, es una observación; si es de otro elemento del plan, se anota con su ID (no es deuda).
- `C-n` (el código lo tiene y el diseño no lo dice): confirma leyendo el archivo citado y buscando el nombre en el DISEÑO (el nivel estructural solo ve encabezados: lo que el DISEÑO declara en tablas no aparece en el grafo).
- Lo confirmado va como `OBS-SNN-n` con su causa probable (falta código, falta diseño o decisión de negocio); el orquestador asigna el dueño. Los falsos positivos se listan con su motivo.
- Si el reporte dice "No se midió la deriva" o no existe, se anota **"deriva no medida (sin grafos)"** como verificación omitida; no cambia el veredicto.

### 5. Criterio de veredicto
| Veredicto | Condición |
|-----------|-----------|
| **APROBADA** | Todos los escenarios en verde, sin regresiones, los RNF aplicables verificados y todas las mutaciones detectadas |
| **APROBADA CON OBSERVACIONES** | Todo en verde; observaciones menores que no violan el SRS. **No cierra la historia ni el sprint** (política de cero deuda): las observaciones vuelven al desarrollador |
| **RECHAZADA** | Un escenario falla, falta su prueba, hay una regresión, o se viola un RNF o una regla de negocio |

En el cierre de sprint el veredicto es del sprint y además se da **por elemento** (con eso se completa el reporte de cada uno).

### 6. Defectos y observaciones
- Defecto: ID (`DEF-<ID>-n` por historia, `DEF-SNN-n` en el cierre de sprint), elemento y escenario o RNF afectado, pasos, resultado esperado (del SRS) frente al obtenido, severidad (Crítica, Alta, Media, Baja).
- Observación: ID (`OBS-n`, `OBS-SNN-n` en el cierre de sprint), archivo:línea, qué falta y la corrección esperada.

## Formato de salida (lo consume `devskills:registrar-avance`)

```markdown
## QA — <ID> <título>   (o: QA de cierre — S<NN>, alcance inicio-sNN..<commit>)
**Veredicto:** APROBADA | APROBADA CON OBSERVACIONES | RECHAZADA
| Escenario Gherkin | Prueba | Resultado |
|-------------------|--------|-----------|
| <escenario> | <ruta>.feature:3 | ✅ |
**RNF verificados:** RNF-04 ✅, RNF-19 ✅
**Regresiones entre historias:** escenarios agregados y resultado (cierre de sprint)
**Mutaciones:** N probadas, N detectadas (qué regla atacó cada una)
**Ataques:** cuáles y resultado (o "no aplica")
**Deriva:** D-n y C-n confirmados (como OBS-SNN-n) y descartados con motivo, o "deriva no medida (sin grafos)" (cierre de sprint)
**Veredicto por elemento:** HU-xx APROBADA · HU-yy RECHAZADA (DEF-SNN-1) (cierre de sprint)
**Defectos:** DEF-<ID>-1 (Alta) …
**Observaciones:** OBS-1 …
**Evidencia:** salida de pytest y de la batería, resumida
```

## Commands

```bash
# desde codigo/
python -m pytest -k HU_35 --gherkin-terminal-reporter
git diff --stat inicio-s05..main                       # alcance del cierre de sprint (solo lectura)
# desde la raíz, si hay grafos (solo lectura, sin LLM)
graphify affected "Pedido" --graph codigo/graphify-out/graph.json        # qué depende de lo que tocó el sprint
graphify explain "Factura" --graph codigo/graphify-out/graph.json        # confirmar un candidato D-n de la deriva
python -m pytest --cucumberjson=../documentacion/avance/_resultados.json
```
