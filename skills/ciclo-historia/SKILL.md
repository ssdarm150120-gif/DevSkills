---
name: ciclo-historia
description: >
  Orquesta el ciclo completo de un elemento del backlog (HU o EN) o de todo un sprint: rama y puntos de control,
  desarrollo (Dev A o Dev B), validación de QA, evaluación del Angel Fixer, rondas (máximo 3), pregunta al
  Product Owner, ronda extra con lista congelada, verificación final, reporte, regeneración del plan, Word y
  Anexo C, gitleaks y cierre con squash a main. Es la única fuente de las reglas del ciclo (`devskills:ciclo` es solo un atajo que la invoca).
  Trigger: "/devskills:ciclo-historia HU-xx", "implementa la historia", "ciclo de la HU", "cerrar el sprint".
license: MIT
metadata:
  author: devskills
  version: "1.0"
arguments: [id]
argument-hint: "HU-35 | EN-04 | S05 (todo un sprint)"
---

## When to Use

- El usuario pide implementar un elemento del backlog (`HU-xx`, `EN-xx`) o todo un sprint (`SNN`). Elemento solicitado: **$id**.

## Critical Patterns

La sesión principal es el **orquestador** (skill `devskills:orquestador`): no escribe código, delega y sintetiza.

### 1. Preparar
1. Cargar `devskills:proyecto-contexto` y leer `documentacion/CONTEXTO.md`.
2. Si el argumento es un sprint (`SNN`), tomar sus elementos de `documentacion/PLAN.md` **en orden de prioridad** y repetir el ciclo para cada uno. Si es un ID, verificar que exista en el plan, que cumpla la Definición de Listo y que sus dependencias anteriores estén Listas.
3. Asignar el desarrollador según el módulo del elemento (tabla "Asignación de módulos" de `documentacion/CONTEXTO.md`): `devskills:dev-a` o `devskills:dev-b`. Los habilitadores de cimientos van a `devskills:dev-a` salvo que `CONTEXTO.md` diga otra cosa.
4. Crear la rama del elemento y el primer punto de control (sección "Puntos de control").
5. Si algún agente va a usar Docker (es opcional: ver `devskills:proyecto-contexto`), asignarle un **prefijo `<slug>-<agente>`** (por ejemplo `miapp-dev-a`; el `<slug>` es el de `CONTEXTO.md`) y un **subrango de puertos** propios dentro del rango del proyecto, sin puertos reservados del host. El prefijo del stack principal es solo `<slug>`: los agentes **no** lo usan, y sobre ese stack nunca corren `docker compose down -v`, `docker volume prune` ni `docker system prune`.

### 2. Ciclo por elemento (máximo 3 rondas)
```
Desarrollo ──► punto de control ──► QA ──► Angel Fixer ──► ¿Listo? ──sí──► Verificación final ──► Cerrar
     ▲                                                        │
     └──────── no (defectos, observaciones o cualquier hallazgo) ◄┘
```
1. **Desarrollo:** lanzar el desarrollador con el ID y la instrucción de seguir `devskills:implementar-historia`. Si se detiene por un hueco del SRS o del DISEÑO, o porque el elemento excede claramente su estimación, **no se sigue**: se resuelve con el `analista-arquitecto` (pasada documental) y, si es de negocio, con el Product Owner; un elemento de más de 13 puntos se parte.
2. **Punto de control** antes de revisar (ver abajo).
3. **QA:** lanzar `devskills:qa` con el ID (skill `devskills:validar-historia`).
4. **Evaluación:** lanzar `devskills:angel-fixer` en **modo evaluación** con el ID y los archivos tocados. Puede aplicar **fixes quirúrgicos** solo de lo que él mismo confirmó; si aplica fixes, **QA re-valida** antes de cerrar. QA y Angel Fixer pueden lanzarse en paralelo sobre el mismo punto de control.
5. Si QA rechaza, deja observaciones, o el Angel Fixer reporta hallazgos de **cualquier severidad** (política de cero deuda): volver al desarrollador con la **lista exacta** (ronda 2 y 3), junto con las decisiones del orquestador y del Product Owner que apliquen.
6. Después de **3 rondas sin aprobar**: **preguntar al Product Owner** (skill `devskills:preguntar-al-po`). Por defecto se marca `Bloqueado`, se registra el avance con el motivo y no se sigue girando.
7. **Ronda extra con lista congelada** (solo si el Product Owner la autoriza): el desarrollador resuelve exactamente la lista pendiente. QA y el Angel Fixer (o el `devskills:verificador`) verifican **solo esa lista y las regresiones**, sin abrir búsquedas nuevas. Un hallazgo nuevo que no sea regresión se registra en el reporte con el ID del elemento del plan que lo absorbe (el que toque ese código después), y no reabre el elemento actual.
8. **Verificación final:** cuando la última ronda corrigió lo pendiente, lanzar `devskills:verificador` (una sola pasada con criterio de QA y de Angel Fixer, o solo la lista congelada). Si corrige algo, nuevo punto de control.
9. Si el Product Owner decide cerrar con pendientes menores (por ejemplo, "cerrar sin ronda extra"), los pendientes se registran con el ID del elemento que los absorbe y la decisión queda como "decisión del Product Owner" en el reporte.

### 3. Cerrar
1. Lanzar o ejecutar `devskills:registrar-avance`: reporte `documentacion/avance/S{NN}/{ID}.md`, estado oficial `Listo`, índice y **regeneración del plan y del tablero** (`python documentacion/analisis/plan_sprints.py`; el elemento queda **tachado**).
2. **Squash a main** (ver regla 4 de "Puntos de control").
3. **Documentación en commit aparte:** si el ciclo cambió SRS o DISEÑO (preguntas cerradas, ADR, versiones), el `analista-arquitecto` hace la pasada (skill `devskills:pasada-documental`): regenera el Anexo C (`python documentacion/analisis/trazabilidad.py _tmp.md --escribir`), el plan y los Word (`python documentacion/analisis/md_a_word.py --mermaid <carpeta de mermaid-cli>`). Los commits de documentación (`docs: ...`) van **separados** del commit del código (`feat(...)` / `fix(...)`); los Word regenerados en su propio `docs: regenerate Word documents after <ID>`.
4. **gitleaks antes de cualquier commit de cierre y antes de cualquier push**, sobre los archivos de `git ls-files -co --exclude-standard` (script `${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py`: gitleaks nativo, con Docker como alternativa; ver Commands). Sin hallazgos no hay commit ni push. Un falso positivo se suprime con `gitleaks:allow` en esa misma línea y su motivo; nunca se excluye una carpeta.
5. Guardar en engram (`mem_save`, project de `CONTEXTO.md`, topic_key `<project>/<id>/cierre`) el resultado, commits y hallazgos no obvios, y revisar la regla de **mantenimiento de DevSkills** (lección general para el plugin, solo como borrador local).
6. Responder al usuario (y por Telegram si el canal está activo) con: veredicto, rondas, enlace al reporte, commits y avance de la entrega en puntos.

### Reglas
- Nunca marcar Listo sin el veredicto de QA **y** la evaluación del Angel Fixer (y la verificación final cuando hubo correcciones).
- Nunca editar `documentacion/PLAN.md` a mano.
- Si un agente encuentra una contradicción con el SRS: **detener el ciclo y preguntar al usuario**.
- Commits en inglés con Conventional Commits y **sin atribución de IA ni `Co-Authored-By`**.
- Si un agente se corta por límite de uso: skill `devskills:recuperar-corte` (no se rehace su trabajo).
- **Herramientas de revisión iguales al CI:** QA, Angel Fixer y verificador corren semgrep con la imagen oficial `semgrep/semgrep:<versión>` y la **misma versión** que fija `.github/workflows/ci.yml` (comando exacto en `devskills:validar-historia`; en Windows con `MSYS_NO_PATHCONV=1` y `pwd -W`) y exigen código 0 y "Findings: 0". Una herramienta distinta a la del CI no prueba nada.
- **Nada hacia afuera sin confirmación explícita del usuario:** `git push`, `gh` que escriba (crear repositorio, issues, PR, comentarios), merges de Dependabot y cualquier publicación se **proponen** con el comando exacto y se ejecutan solo con un "sí" del usuario en esta conversación (y con gitleaks limpio). En una corrida sin humano no se ejecutan: se dejan listados en el reporte para la persona.
- **El CI también es parte del Listo:** si el repositorio tiene remoto, después de cada push (autorizado) se revisa con `gh run list` y, si falla, `gh run view <id> --log-failed` (ambos son de lectura). Un CI en rojo es deuda: se corrige antes de seguir.
- **Mantenimiento de DevSkills (permanente):** al cerrar cada elemento, el orquestador revisa si dejó una **lección general del método o del stack** (no del dominio del proyecto). Si la hay, la redacta como **borrador local** (`documentacion/avance/lecciones_devskills.md`, sin nombres, datos, rutas ni código del proyecto: solo el tropiezo, la causa y la regla) y se la **enseña al usuario**. Solo si él lo aprueba se publica como issue en el repositorio del plugin (`gh issue create`, con el texto exacto que aprobó); sin aprobación se queda en el borrador. Así el siguiente proyecto no repite el tropiezo y ningún dato del proyecto sale sin permiso.

### Puntos de control (ningún trabajo sin respaldo en git)
Regla nacida de un incidente real: un verificador vació por accidente un archivo de pruebas que no tenía commit y hubo que reconstruirlo de memoria.
1. Cada elemento se trabaja en su **rama** `hu-xx` o `en-xx` (`git switch -c hu-60`), nunca directo en `main`.
2. **Antes de lanzar a QA, al Angel Fixer o a una verificación**, el orquestador hace un commit de punto de control con **todo lo que el desarrollador puede tocar**: el código, el CI y el avance, no solo `codigo/`. Comando único (el mismo en `devskills:recuperar-corte` y `devskills:guarda-todo`): `git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-xx): ronda N del desarrollador"`. Después, `git status --short` debe quedar vacío; si muestra algo fuera de esas rutas (`AGENTS.md`, `documentacion/` fuera de `avance/`, la raíz), se revisa con el usuario antes de agregarlo, porque ningún desarrollador debe tocarlo. Lo mismo al terminar cada ronda, antes de un corte previsible y después de cada verificación que haya corregido algo.
3. Con el punto de control hecho, lo que cambie un verificador se ve con `git diff` y cualquier accidente se deshace con `git restore <archivo>`. **Nadie reconstruye un archivo de memoria:** se restaura de git.
4. Al cerrar, la rama entra a `main` como **un solo commit** (`git switch main && git merge --squash hu-xx && git commit -m "feat(hu-xx): ..."`) y la rama se borra (`git branch -D hu-xx`, solo la del elemento y solo el orquestador; en una corrida sin humano se deja y se avisa). Los `wip` no llegan a `main`.
5. QA, el Angel Fixer y el verificador **no ejecutan en el repositorio** scripts, `sed`, redirecciones ni herramientas que escriban archivos de `codigo/`, `.github/` o `documentacion/avance/`; las mutaciones y experimentos van en una **copia** en el scratchpad. Si corrigen algo, usan solo la herramienta de edición, archivo por archivo, y reportan el `git diff --stat` de lo que tocaron.
6. Si un agente daña o pierde un archivo: **se detiene, lo restaura de git y lo reporta**. No sigue trabajando encima.
7. Ningún agente ejecuta comandos de git que cambien el árbol o la historia (`stash`, `checkout`, `switch`, `reset`, `rebase`, `merge`, `commit`, `clean`); eso es exclusivo del orquestador. Regla nacida de un incidente real: un desarrollador corrió `git stash` a media ronda y además aplicó mutaciones en el árbol de trabajo.

## Commands

```bash
git switch -c hu-60                                        # rama del elemento
git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-60): ronda 1 del desarrollador"
git status --short                                         # debe quedar vacío
python documentacion/analisis/plan_sprints.py              # regenera PLAN.md y el tablero (tacha lo Listo)
python documentacion/analisis/trazabilidad.py _tmp.md --escribir
python documentacion/analisis/md_a_word.py --mermaid ~/.devskills/doc   # regenera los Word (ver devskills:pasada-documental)
# gitleaks (nativo; Docker como alternativa) sobre `git ls-files -co --exclude-standard`, ANTES de cualquier commit de cierre o push
python "${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py"
git switch main && git merge --squash hu-60 && git commit -m "feat(hu-60): manage users and roles"
git branch -D hu-60                                        # solo el orquestador; en corridas sin humano la rama se deja
# Solo con la aprobación explícita del usuario: git push; después, lectura del CI
gh run list --limit 3                                      # tras el push autorizado, si hay remoto
gh run view <id> --log-failed                              # si el CI falló
# semgrep igual que el CI (desde codigo/; versión = la de semgrep== en .github/workflows/ci.yml)
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/src" -w /src semgrep/semgrep:1.178.0   semgrep scan --config p/python --config p/django --error --metrics=off --exclude pruebas --exclude conftest.py .
```
