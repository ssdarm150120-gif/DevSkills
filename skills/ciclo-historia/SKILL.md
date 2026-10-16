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
     ▲                                                        │            (solo si hubo correcciones)
     └──────── no (defectos, observaciones o cualquier hallazgo) ◄┘
```
1. **Desarrollo:** lanzar el desarrollador con el ID y la instrucción de seguir `devskills:implementar-historia`. Si se detiene por un hueco del SRS o del DISEÑO, o porque el elemento excede claramente su estimación, **no se sigue**: se resuelve con el `analista-arquitecto` (pasada documental) y, si es de negocio, con el Product Owner; un elemento de más de 13 puntos se parte.
2. **Punto de control** antes de revisar (ver abajo).
3. **QA:** lanzar `devskills:qa` con el ID (skill `devskills:validar-historia`).
4. **Evaluación:** lanzar `devskills:angel-fixer` en **modo evaluación** con el ID y los archivos tocados. Puede aplicar **fixes quirúrgicos** solo de lo que él mismo confirmó; si aplica fixes, **QA re-valida** antes de cerrar. QA y Angel Fixer pueden lanzarse en paralelo sobre el mismo punto de control.
5. Si QA rechaza, deja observaciones, o el Angel Fixer reporta hallazgos de **cualquier severidad** (política de cero deuda): volver al desarrollador con la **lista exacta** (ronda 2 y 3), junto con las decisiones del orquestador y del Product Owner que apliquen.
6. Después de **3 rondas sin aprobar**: **preguntar al Product Owner** (skill `devskills:preguntar-al-po`). Por defecto se marca `Bloqueado`, se registra el avance con el motivo y no se sigue girando.
7. **Ronda extra con lista congelada** (solo si el Product Owner la autoriza): el desarrollador resuelve exactamente la lista pendiente. QA y el Angel Fixer (o el `devskills:verificador`) verifican **solo esa lista y las regresiones**, sin abrir búsquedas nuevas. Un hallazgo nuevo que no sea regresión se registra en el reporte con el ID del elemento del plan que lo absorbe (el que toque ese código después), y no reabre el elemento actual.
8. **Verificación final, solo si hubo correcciones** (ronda 2 o 3, ronda extra, o fixes que aplicó el Angel Fixer): lanzar `devskills:verificador` (una sola pasada con criterio de QA y de Angel Fixer, o solo la lista congelada). Si corrige algo, nuevo punto de control y se repite la pasada. Si QA aprobó y el Angel Fixer cerró sin hallazgos ni fixes en la primera ronda, **no hay verificación final**: no hay nada corregido que confirmar, y el diagrama la dibuja condicionada por eso.
9. Si el Product Owner decide cerrar con pendientes menores (por ejemplo, "cerrar sin ronda extra"), los pendientes se registran con el ID del elemento que los absorbe y la decisión queda como "decisión del Product Owner" en el reporte.

### 3. Cerrar
Este orden es obligatorio; cada paso se hace solo cuando el anterior terminó:
1. **Avance, en la rama del elemento** (`devskills:registrar-avance`): reporte `documentacion/avance/S{NN}/{ID}.md`, estado oficial `Listo` en `estado_backlog.json`, línea del índice `documentacion/avance/README.md` y **regeneración del plan y del tablero** (`python documentacion/analisis/plan_sprints.py`; el elemento queda **tachado** en `PLAN.md`). Los cuatro quedan en **un** punto de control: `git add -A -- documentacion/avance documentacion/PLAN.md documentacion/plan_sprints.html && git commit -m "wip(hu-xx): reporte, estado y plan"`.
2. **gitleaks antes de cualquier commit de cierre y antes de cualquier push**, sobre los archivos de `git ls-files -co --exclude-standard` (script `${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py`: gitleaks nativo, con Docker como alternativa; ver Commands). Códigos de salida: 0 limpio, 1 hay hallazgos, 2 la herramienta no está disponible (instalarla; no es un hallazgo ni un visto bueno). Sin código 0 no hay commit ni push. Un falso positivo se suprime con `gitleaks:allow` en esa misma línea y su motivo; nunca se excluye una carpeta.
3. **Squash a `main`:** un **solo** commit `feat(hu-xx): ...` / `fix(...)` que lleva el código **y** el reporte, `estado_backlog.json`, el índice y el `PLAN.md` y tablero regenerados. Así `main` nunca muestra un elemento tachado sin su evidencia, ni código sin reporte, y revertir el elemento revierte también su estado. Los `wip` quedan en la rama y la rama se borra (regla 4 de "Puntos de control"); por eso `main` no contiene commits `wip`.
4. **Documentación regenerada, en commits aparte sobre `main` y solo si el ciclo cambió SRS o DISEÑO** (preguntas cerradas, ADR, versiones): el `analista-arquitecto` hace la pasada (skill `devskills:pasada-documental`): regenera el Anexo C (`python documentacion/analisis/trazabilidad.py _tmp.md --escribir`), el plan si hizo falta y los Word (`"$PYDOC" documentacion/analisis/md_a_word.py --mermaid <carpeta de mermaid-cli>`). Los commits de documentación (`docs: ...`) van **separados** del commit del código, y los Word regenerados en el suyo: `docs: regenerate Word documents after <ID>`. **Cada uno** pasa antes por gitleaks (paso 2). Si el ciclo no cambió SRS ni DISEÑO, este paso se omite; los pasos 1 a 3 nunca.
5. Guardar en engram (el orquestador, con `mem_save`; project de `CONTEXTO.md`, topic_key `<project>/<id>/cierre`) el resultado, commits y hallazgos no obvios, junto con las secciones **Para engram** que trajeron los agentes en sus reportes (los subagentes no tienen `mem_save`). Si `mem_save` no existe en la sesión, esas secciones se anexan a `.devskills/engram_pendiente.md` y se avisa al usuario. Revisar también la regla de **mantenimiento de DevSkills** (lección general para el plugin, solo como borrador local).
6. **Si el elemento cierra su entrega** (era el último pendiente de la entrega en el plan), seguir la sección "Cierre de entrega" antes de declararla cerrada.
7. Responder al usuario (y por Telegram si el canal está activo) con: veredicto, rondas, enlace al reporte, commits y avance de la entrega en puntos. Si el repositorio no tiene remoto, el reporte dice **"CI no ejecutado (sin remoto)"** y lista como **verificación pendiente** lo que solo cubre el CI (semgrep si no hay vía local, hadolint, trivy, construcción de la imagen y pruebas de despliegue). Un `git push`, si el usuario lo autoriza, va **después de todo lo anterior** y con gitleaks limpio.

### Reglas
- Nunca marcar Listo sin el veredicto de QA **y** la evaluación del Angel Fixer (y la verificación final cuando hubo correcciones, como dice el paso 8).
- Nunca editar `documentacion/PLAN.md` a mano.
- Si un agente encuentra una contradicción con el SRS: **detener el ciclo y preguntar al usuario**.
- Commits en inglés con Conventional Commits y **sin atribución de IA ni `Co-Authored-By`**.
- Si un agente se corta por límite de uso: skill `devskills:recuperar-corte` (no se rehace su trabajo).
- **Herramientas de revisión iguales al CI:** ver la regla 8 de "Puntos de control".
- **Nada hacia afuera sin confirmación explícita del usuario:** `git push`, `gh` que escriba (crear repositorio, issues, PR, comentarios), merges de Dependabot y cualquier publicación se **proponen** con el comando exacto y se ejecutan solo con un "sí" del usuario en esta conversación (y con gitleaks limpio). En una corrida sin humano no se ejecutan: se dejan listados en el reporte para la persona.
- **Ningún agente instala software** (pip fuera del venv del proyecto, `curl ... | sh`, `get-pip`, `winget`, `brew`, `apt`, `npm -g`, WSL): si falta una herramienta, el agente se detiene y la reporta, y el orquestador pregunta al usuario con el comando exacto y la versión. Un hook del plugin lo bloquea a los subagentes.
- **El CI también es parte del Listo:** ver la regla 8 de "Puntos de control".
- **Mantenimiento de DevSkills (permanente):** al cerrar cada elemento, el orquestador revisa si dejó una **lección general del método o del stack** (no del dominio del proyecto). Si la hay, la redacta como **borrador local** (`.devskills/lecciones.md`, sin nombres, datos, rutas ni código del proyecto: solo el tropiezo, la causa y la regla) y se la **enseña al usuario**. `.devskills/` está en el `.gitignore` del proyecto: el borrador nunca entra a un commit ni al punto de control. Solo si él lo aprueba se publica como issue en el repositorio del plugin (`gh issue create`, con el texto exacto que aprobó); sin aprobación se queda en el borrador. Así el siguiente proyecto no repite el tropiezo y ningún dato del proyecto sale sin permiso.

### Cierre de entrega (lo que solo cubre el CI se corre con Docker)
Una entrega se cierra cuando todos sus elementos están `Listo`. Sin remoto no hay CI, y sin Docker no corren las pruebas de despliegue, hadolint ni trivy: si nadie las corre, nunca se corren. Por eso, al cerrar **cada entrega**:
1. El orquestador exige correr **localmente con Docker** (delegado en `devskills:qa` o `devskills:verificador`, con su prefijo `<slug>-<agente>` y su subrango de puertos): la construcción de la imagen, hadolint y trivy con las mismas imágenes fijadas en `.github/workflows/ci.yml`, el Compose válido y las pruebas de despliegue y del certificado que se omiten solas sin Docker.
2. Si no hay Docker (`docker info` falla), el orquestador **se lo pide al usuario**: que lo arranque o lo instale (ningún agente instala nada), o que las corra en otra máquina o en el CI de un remoto. Sin esas pruebas la entrega queda como **verificación pendiente** y solo se declara cerrada si el usuario lo acepta de forma explícita; esa decisión va al reporte como "decisión del Product Owner".
3. Si además no hay remoto, el reporte de la entrega marca **"CI no ejecutado (sin remoto)"**.

### Puntos de control (ningún trabajo sin respaldo en git)
Regla nacida de un incidente real: un verificador vació por accidente un archivo de pruebas que no tenía commit y hubo que reconstruirlo de memoria.
1. Cada elemento se trabaja en su **rama** `hu-xx` o `en-xx` (`git switch -c hu-60`), nunca directo en `main`.
2. **Antes de lanzar a QA, al Angel Fixer o a una verificación**, el orquestador hace un commit de punto de control con **todo lo que el desarrollador puede tocar**: el código, el CI y el avance, no solo `codigo/`. Comando único (el mismo en `devskills:recuperar-corte` y `devskills:guarda-todo`): `git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-xx): ronda N del desarrollador"`. Después, `git status --short` debe quedar vacío; si muestra algo fuera de esas rutas (`AGENTS.md`, `documentacion/` fuera de `avance/`, la raíz), se revisa con el usuario antes de agregarlo, porque ningún desarrollador debe tocarlo. Lo mismo al terminar cada ronda, antes de un corte previsible y después de cada verificación que haya corregido algo.
3. Con el punto de control hecho, lo que cambie un verificador se ve con `git diff` y cualquier accidente se deshace con `git restore <archivo>`. **Nadie reconstruye un archivo de memoria:** se restaura de git.
4. Al cerrar, la rama entra a `main` como **un solo commit** (`git switch main && git merge --squash hu-xx && git commit -m "feat(hu-xx): ..."`) y la rama se borra (`git branch -D hu-xx`, solo la del elemento y solo el orquestador; en una corrida sin humano se deja y se avisa). Los `wip` no llegan a `main`.
5. QA, el Angel Fixer y el verificador **no ejecutan en el repositorio** scripts, `sed`, redirecciones ni herramientas que escriban archivos de `codigo/`, `.github/` o `documentacion/avance/`; las mutaciones y experimentos van en una **copia** en el scratchpad. Si corrigen algo, usan solo la herramienta de edición, archivo por archivo, y reportan el `git diff --stat` de lo que tocaron.
6. Si un agente daña o pierde un archivo: **se detiene, lo restaura de git y lo reporta**. No sigue trabajando encima.
7. Ningún agente ejecuta comandos de git que cambien el árbol o la historia (`add`, `stash`, `checkout`, `switch`, `reset`, `rebase`, `merge`, `commit`, `clean`, `push`); eso es exclusivo del orquestador, también en `devskills:gga` y `devskills:judgment-day`: los auditores, los jueces y los correctores solo editan archivos, y **el orquestador** deja el punto de control `wip` tras sus fixes y antes de relanzar la re-auditoría o el nuevo juicio. Regla nacida de un incidente real: un desarrollador corrió `git stash` a media ronda y además aplicó mutaciones en el árbol de trabajo.
8. **Herramientas locales = CI; un CI en rojo es deuda.** QA, Angel Fixer y verificador corren semgrep con la **misma versión** que fija `.github/workflows/ci.yml` (nativo en macOS y Linux; en Windows por WSL o Docker, opcionales; comando exacto en `devskills:validar-historia`) y exigen código 0 y "Findings: 0": una herramienta distinta a la del CI no prueba nada. Solo se usa una vía que **ya esté instalada**: ningún agente instala semgrep, pipx, WSL ni Docker (si falta, se detiene y lo reporta; el orquestador se lo pregunta al usuario). Si la máquina no tiene ninguna de las tres vías, el semgrep del CI de GitHub (siempre obligatorio) es el que cuenta: el orquestador lo deja listado como verificación pendiente y el elemento no se da por Listo hasta que ese job esté en verde (después de un push que el usuario autorice) o el usuario acepte explícitamente cerrar sin él. Si el repositorio tiene remoto, después de cada push (autorizado) se revisa con `gh run list` y, si falla, `gh run view <id> --log-failed` (ambos son de lectura): un CI en rojo se corrige antes de seguir.

## Commands

```bash
git switch -c hu-60                                        # rama del elemento
git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-60): ronda 1 del desarrollador"
git status --short                                         # debe quedar vacío
# Cierre, en este orden:
python documentacion/analisis/plan_sprints.py              # 1. regenera PLAN.md y el tablero (tacha lo Listo), tras el reporte y el estado
git add -A -- documentacion/avance documentacion/PLAN.md documentacion/plan_sprints.html && git commit -m "wip(hu-60): reporte, estado y plan"
# 2. gitleaks (nativo; Docker como alternativa) sobre `git ls-files -co --exclude-standard`: 0 limpio, 1 hallazgos, 2 herramienta no disponible
python "${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py"
git switch main && git merge --squash hu-60 && git commit -m "feat(hu-60): manage users and roles"   # 3. un commit: código + reporte + estado + índice + plan
git branch -D hu-60                                        # solo el orquestador; en corridas sin humano la rama se deja
# 4. solo si cambió SRS o DISEÑO, en commits docs: aparte sobre main (cada uno tras gitleaks):
python documentacion/analisis/trazabilidad.py _tmp.md --escribir
"$PYDOC" documentacion/analisis/md_a_word.py --mermaid ~/.devskills/doc   # regenera los Word (ver devskills:pasada-documental)
# Solo con la aprobación explícita del usuario: git push; después, lectura del CI
gh run list --limit 3                                      # tras el push autorizado, si hay remoto
gh run view <id> --log-failed                              # si el CI falló
# semgrep igual que el CI (desde codigo/; versión = la de semgrep== en .github/workflows/ci.yml), con montaje de solo lectura
pipx run --spec "semgrep==1.178.0" semgrep scan --config p/python --config p/django --error --metrics=off --exclude pruebas --exclude conftest.py .   # macOS/Linux/WSL
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/src:ro" -w /src semgrep/semgrep:1.178.0@sha256:32e459968daabe7ab86968184a29109b9564aa00392401156f9788452b42786b semgrep scan --config p/python --config p/django --error --metrics=off --exclude pruebas --exclude conftest.py .   # alternativa con Docker
```
