---
name: ciclo-historia
description: >
  Orquesta el ciclo de calidad híbrido de un elemento del backlog (HU o EN) o de todo un sprint: rama y puntos
  de control, desarrollo con TDD (Dev A o Dev B), revisión por historia del Angel Fixer con lista congelada y
  verificación ligera, merge con el elemento "En validación", y al cerrar el sprint el QA completo sobre todo el
  diff del sprint con su verificación final, que pasa los elementos a Listo. Los elementos de seguridad, de
  plataforma o críticos llevan el ciclo completo por historia (QA y Angel Fixer en paralelo). Incluye rondas
  (máximo 3), pregunta al Product Owner, reporte, regeneración del plan, Word y Anexo C, gitleaks y squash a main.
  Es la única fuente de las reglas del ciclo (`devskills:ciclo` es solo un atajo que la invoca).
  Trigger: "/devskills:ciclo-historia HU-xx", "implementa la historia", "ciclo de la HU", "cerrar el sprint".
license: MIT
metadata:
  author: devskills
  version: "2.0"
arguments: [id]
argument-hint: "HU-35 | EN-04 | S05 (todo un sprint) | cierre-S05 (solo el cierre del sprint)"
---

## When to Use

- El usuario pide implementar un elemento del backlog (`HU-xx`, `EN-xx`), todo un sprint (`SNN`) o solo el cierre de un sprint (`cierre-SNN`). Elemento solicitado: **$id**.

## Critical Patterns

La sesión principal es el **orquestador** (skill `devskills:orquestador`): no escribe código, delega y sintetiza.

### Separación de roles (sin traslape)
| Rol | Revisa | No hace |
|-----|--------|---------|
| **Angel Fixer** (`devskills:angel-fixer`) | El **código**: seguridad, arquitectura y límites de módulos, buenas prácticas, deuda; y que cada escenario Gherkin tenga su prueba | No valida comportamiento de punta a punta, no corre mutaciones ni ataques |
| **QA** (`devskills:qa`) | El **comportamiento**: escenarios Gherkin del SRS de punta a punta, regresiones entre historias, RNF verificables (Anexo C), mutaciones dirigidas al riesgo y ataques cuando aplica | No revisa estilo ni arquitectura; no corrige código de producción |
| **Verificador** (`devskills:verificador`) | Que una lista congelada quedó resuelta sin regresiones (ligera por historia, final en el cierre del sprint y en la excepción) | No abre búsquedas nuevas |

Cada pasada la hace un agente **distinto** del que corrigió: el desarrollador corrige, el verificador confirma.

### 1. Preparar
1. Cargar `devskills:proyecto-contexto` y leer `documentacion/CONTEXTO.md`.
2. Si el argumento es un sprint (`SNN`), tomar sus elementos de `documentacion/PLAN.md` **en orden de prioridad**, repetir el ciclo por elemento para cada uno y terminar con el **cierre del sprint** (sección 5). Si es `cierre-SNN`, ir directo a la sección 5. Si es un ID, verificar que exista en el plan, que cumpla la Definición de Listo y que sus dependencias anteriores estén Listas o `En validación` (ya integradas en `main`).
3. **Inicio del sprint:** antes del primer elemento de un sprint, el orquestador marca en `main` el punto de partida con una etiqueta local: `git tag inicio-sNN` (por ejemplo `inicio-s05`). Es la base del diff que revisa el QA de cierre. La etiqueta no se publica sin la confirmación del usuario.
4. **Clasificar el elemento** (sección "Clasificación: ciclo normal o excepción") y anotar la clase y su motivo; va al reporte.
5. Asignar el desarrollador según el módulo del elemento (tabla "Asignación de módulos" de `documentacion/CONTEXTO.md`): `devskills:dev-a` o `devskills:dev-b`. Los habilitadores de cimientos van a `devskills:dev-a` salvo que `CONTEXTO.md` diga otra cosa.
6. Crear la rama del elemento y el primer punto de control (sección "Puntos de control").
7. Si algún agente va a usar Docker (es opcional: ver `devskills:proyecto-contexto`), asignarle un **prefijo `<slug>-<agente>`** (por ejemplo `miapp-dev-a`; el `<slug>` es el de `CONTEXTO.md`) y un **subrango de puertos** propios dentro del rango del proyecto, sin puertos reservados del host. El prefijo del stack principal es solo `<slug>`: los agentes **no** lo usan, y sobre ese stack nunca corren `docker compose down -v`, `docker volume prune` ni `docker system prune`.

### Clasificación: ciclo normal o excepción
El orquestador decide la clase **antes del desarrollo** y la confirma con el `git diff --stat` del primer punto de control (si el diff toca algo de la excepción, el elemento se reclasifica antes de cualquier revisión). Es una **decisión del orquestador**: se registra con su motivo y el Product Owner puede revertirla.

Un elemento va por la **excepción (ciclo completo por historia)** si cumple **cualquiera** de estas condiciones:
1. **Seguridad:** traza a un riesgo `S-nn` del SRS o a un RNF de seguridad, o toca autenticación, autorización (permisos, roles, filtros de propiedad), archivos (subida, descarga, rutas), secretos, llaves, tokens o cifrado.
2. **Plataforma o núcleo compartido:** toca los módulos que `documentacion/CONTEXTO.md` lista en "Ciclo de calidad: plataforma y elementos críticos" (por defecto `nucleo`, `identidad`, `configuracion`, `herramientas`, `despliegue/` y `.github/`), contratos entre módulos (`api_publica.py`, catálogo de eventos, puertos de `nucleo`) o la configuración de import-linter.
3. **Crítico por decisión del orquestador:** por ejemplo migraciones destructivas, dinero, concurrencia delicada, integraciones de escritura con sistemas externos, o un elemento que en un sprint anterior escapó defectos. El motivo va escrito.

Todo lo demás es **ciclo normal**. En la duda, excepción.

### 2. Ciclo normal por elemento (revisión por historia; máximo 3 rondas)
```
Desarrollo (TDD) ──► punto de control ──► Revisión por historia del Angel Fixer ──► ¿hallazgos? ──no──► Merge (En validación)
                                                  │ sí
                                                  ▼
                                          lista congelada ──► Corrección (dev) ──► punto de control ──► Verificación ligera ──► ¿resuelta? ──sí──► Merge (En validación)
                                                                    ▲                                        (verificador)           │ no
                                                                    └──────────────────── ronda 2 y 3 ◄──────────────────────────────┘
```
1. **Desarrollo:** lanzar el desarrollador con el ID y la instrucción de seguir `devskills:implementar-historia` (TDD; incluye copiar el Gherkin del SRS tal cual a su `.feature` con sus pasos de pytest-bdd). Si se detiene por un hueco del SRS o del DISEÑO, o porque el elemento excede claramente su estimación, **no se sigue**: se resuelve con el `analista-arquitecto` (pasada documental) y, si es de negocio, con el Product Owner; un elemento de más de 13 puntos se parte.
2. **Punto de control** antes de revisar (ver abajo) y confirmación de la clase con el `git diff --stat`.
3. **Revisión por historia:** lanzar `devskills:angel-fixer` en **modo revisión por historia** con el ID y los archivos tocados. Revisa el código (seguridad, arquitectura y límites de módulos, buenas prácticas, deuda) y la **lista mínima**: build sin advertencias, pruebas en verde, gitleaks limpio y cada escenario Gherkin con su prueba. **Sin mutaciones, sin ataques y sin fixes:** solo reporta.
4. **Lista congelada:** si el Angel Fixer reporta hallazgos de **cualquier severidad** (cero deuda), el orquestador congela esa lista con sus IDs (`AF-n`). Las rondas siguientes no abren búsquedas nuevas.
5. **Ronda de corrección:** el desarrollador resuelve exactamente la lista (junto con las decisiones del orquestador y del Product Owner que apliquen). Nuevo punto de control.
6. **Verificación ligera:** lanzar `devskills:verificador` en **modo ligero**: comprueba punto por punto la lista congelada, las regresiones y la lista mínima. No corrige ni abre búsquedas. Un hallazgo nuevo que no sea regresión **no reabre** el elemento: se anota en el reporte como entrada del QA de cierre del sprint, que lo resuelve en el mismo sprint.
7. Si quedan pendientes, ronda 2 y 3 (pasos 5 y 6). **Después de 3 rondas sin resolver la lista: preguntar al Product Owner** (skill `devskills:preguntar-al-po`). Por defecto se marca `Bloqueado`, se registra el avance con el motivo y no se sigue girando. Una ronda extra solo con su autorización y sobre la misma lista congelada.
8. Si el Angel Fixer no reportó hallazgos, no hay correcciones ni verificación ligera: se pasa directo al merge.
9. **Merge:** sección 4 con el estado **`En validación`** (no Listo). El elemento queda integrado en `main` y espera el QA de cierre del sprint.

### 3. Ciclo de la excepción (ciclo completo por historia; máximo 3 rondas)
```
Desarrollo ──► punto de control ──► QA ∥ Angel Fixer ──► ¿Listo? ──sí──► Verificación final ──► Merge (Listo)
     ▲                                                     │            (solo si hubo correcciones)
     └──────── no (defectos, observaciones o cualquier hallazgo) ◄┘
```
1. **Desarrollo** y **punto de control**, igual que en el ciclo normal.
2. **QA:** lanzar `devskills:qa` en **modo por historia** con el ID (skill `devskills:validar-historia`): Gherkin de punta a punta, RNF, mutaciones dirigidas y ataques cuando aplica.
3. **Evaluación:** lanzar `devskills:angel-fixer` en **modo evaluación** con el ID y los archivos tocados (código: seguridad a fondo, arquitectura, buenas prácticas). Puede aplicar **fixes quirúrgicos** solo de CRÍTICOS y ALTOS que él mismo confirmó; si aplica fixes, **QA re-valida** antes de cerrar. QA y Angel Fixer se lanzan **en paralelo** sobre el mismo punto de control.
4. Si QA rechaza, deja observaciones, o el Angel Fixer reporta hallazgos de **cualquier severidad** (política de cero deuda): volver al desarrollador con la **lista exacta** (ronda 2 y 3), junto con las decisiones del orquestador y del Product Owner que apliquen.
5. Después de **3 rondas sin aprobar**: **preguntar al Product Owner** (skill `devskills:preguntar-al-po`). Por defecto se marca `Bloqueado`, se registra el avance con el motivo y no se sigue girando.
6. **Ronda extra con lista congelada** (solo si el Product Owner la autoriza): el desarrollador resuelve exactamente la lista pendiente. QA y el Angel Fixer (o el `devskills:verificador`) verifican **solo esa lista y las regresiones**, sin abrir búsquedas nuevas. Un hallazgo nuevo que no sea regresión se registra en el reporte con el ID del elemento del plan que lo absorbe, y no reabre el elemento actual.
7. **Verificación final, solo si hubo correcciones** (ronda 2 o 3, ronda extra, o fixes que aplicó el Angel Fixer): lanzar `devskills:verificador` en **modo final** (una sola pasada con criterio de QA y de Angel Fixer, o solo la lista congelada). Si corrige algo, nuevo punto de control y se repite la pasada. Si QA aprobó y el Angel Fixer cerró sin hallazgos ni fixes en la primera ronda, **no hay verificación final**.
8. Si el Product Owner decide cerrar con pendientes menores, los pendientes se registran con el ID del elemento que los absorbe y la decisión queda como "decisión del Product Owner" en el reporte.
9. **Merge:** sección 4 con el estado **`Listo`**. En el QA de cierre del sprint el elemento entra solo como **alcance de regresión**: no se re-valida historia por historia, pero una regresión que toque su código se corrige en el cierre y se anota en su reporte.

### 4. Merge del elemento
Este orden es obligatorio; cada paso se hace solo cuando el anterior terminó:
1. **Avance, en la rama del elemento** (`devskills:registrar-avance`): reporte `documentacion/avance/S{NN}/{ID}.md` (en el ciclo normal, **parcial**: la sección de QA dice "pendiente del cierre del sprint S{NN}"), estado oficial en `estado_backlog.json` (**`En validación`** en el ciclo normal, **`Listo`** en la excepción), línea del índice `documentacion/avance/README.md` y **regeneración del plan y del tablero** (`python documentacion/analisis/plan_sprints.py`; solo lo `Listo` queda **tachado** en `PLAN.md`; lo `En validación` aparece con su icono). Los cuatro quedan en **un** punto de control: `git add -A -- documentacion/avance documentacion/PLAN.md documentacion/plan_sprints.html && git commit -m "wip(hu-xx): reporte, estado y plan"`.
2. **gitleaks antes de cualquier commit de cierre y antes de cualquier push**, sobre los archivos de `git ls-files -co --exclude-standard` (script `${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py`: gitleaks nativo, con Docker como alternativa; ver Commands). Códigos de salida: 0 limpio, 1 hay hallazgos, 2 la herramienta no está disponible (instalarla; no es un hallazgo ni un visto bueno). Sin código 0 no hay commit ni push. Un falso positivo se suprime con `gitleaks:allow` en esa misma línea y su motivo; nunca se excluye una carpeta.
3. **Squash a `main`:** un **solo** commit `feat(hu-xx): ...` / `fix(...)` que lleva el código **y** el reporte, `estado_backlog.json`, el índice y el `PLAN.md` y tablero regenerados. Así `main` nunca muestra un elemento sin su evidencia ni código sin reporte, y revertir el elemento revierte también su estado. Los `wip` quedan en la rama y la rama se borra (regla 4 de "Puntos de control"); por eso `main` no contiene commits `wip`. Un pull request es opcional y solo existe si el usuario autoriza el push y `gh` (regla "Nada hacia afuera").
4. **Documentación regenerada, en commits aparte sobre `main` y solo si el ciclo cambió SRS o DISEÑO** (preguntas cerradas, ADR, versiones): el `analista-arquitecto` hace la pasada (skill `devskills:pasada-documental`): regenera el Anexo C (`python documentacion/analisis/trazabilidad.py _tmp.md --escribir`), el plan si hizo falta y los Word (`"$PYDOC" documentacion/analisis/md_a_word.py --mermaid <carpeta de mermaid-cli>`). Los commits de documentación (`docs: ...`) van **separados** del commit del código, y los Word regenerados en el suyo: `docs: regenerate Word documents after <ID>`. **Cada uno** pasa antes por gitleaks (paso 2). Si el ciclo no cambió SRS ni DISEÑO, este paso se omite; los pasos 1 a 3 nunca.
5. Guardar en engram (el orquestador, con `mem_save`; project de `CONTEXTO.md`, topic_key `<project>/<id>/cierre`) el resultado, commits y hallazgos no obvios, junto con las secciones **Para engram** que trajeron los agentes en sus reportes (los subagentes no tienen `mem_save`). Si `mem_save` no existe en la sesión, esas secciones se anexan a `.devskills/engram_pendiente.md` y se avisa al usuario. Revisar también la regla de **mantenimiento de DevSkills** (lección general para el plugin, solo como borrador local).
6. Responder al usuario (y por Telegram si el canal está activo) con: clase del elemento, resultado de la revisión, rondas, enlace al reporte, commits y estado (`En validación` hasta el cierre del sprint, o `Listo`). Si el repositorio no tiene remoto, el reporte dice **"CI no ejecutado (sin remoto)"** y lista como **verificación pendiente** lo que solo cubre el CI (semgrep si no hay vía local, hadolint, trivy, construcción de la imagen y pruebas de despliegue). Un `git push`, si el usuario lo autoriza, va **después de todo lo anterior** y con gitleaks limpio.

### 5. Cierre del sprint (QA completo sobre todo el diff del sprint)
Se hace cuando todos los elementos del sprint están `En validación` o `Listo` (o con `cierre-SNN`). Si alguno sigue `En proceso` o `Bloqueado`, el orquestador pregunta al Product Owner si se espera o si pasa al sprint siguiente (`devskills:planear-entregas` lo replanifica); el cierre cubre solo lo integrado en `main`.
```
Rama cierre-sNN ──► QA de cierre (diff inicio-sNN..main) ──► ¿hallazgos? ──no──► Listo (todos) ──► Reportes + plan ──► Squash a main
                                 │ sí                                             ▲
                                 ▼                                                │ sí
                         lista congelada ──► Corrección (dev dueño) ──► punto de control ──► Verificación final ──► ¿resuelta?
                                                   ▲                                       (verificador)          │ no
                                                   └──────────────────── ronda 2 y 3 ◄────────────────────────────┘
```
1. **Rama y punto de control:** `git switch -c cierre-s05 main`. El alcance es `git diff inicio-s05..main` (si falta la etiqueta, la base es el padre del primer squash del sprint en `main`).
2. **QA de cierre:** lanzar `devskills:qa` en **modo cierre de sprint** (skill `devskills:validar-historia`) con el sprint, la base del diff, la lista de elementos y su clase, y las entradas que dejaron las verificaciones ligeras. Cubre: **todos** los escenarios Gherkin de las historias del sprint de punta a punta, **regresiones entre historias** (batería completa y escenarios que cruzan historias: datos, estados y permisos compartidos), los **RNF** que citan (verificación técnica del Anexo C), **10 a 15 mutaciones** dirigidas a lo más riesgoso del diff (en una copia del scratchpad) y **ataques** cuando aplica (solo contra la base de pruebas). Los elementos de la excepción entran como alcance de regresión.
3. **Lista congelada:** cada defecto u observación con su ID (`DEF-SNN-n`, `OBS-SNN-n`), el elemento al que pertenece y su desarrollador dueño. Si QA aprueba sin hallazgos, no hay correcciones ni verificación final: se pasa al paso 6.
4. **Ronda de corrección:** cada desarrollador dueño resuelve su parte de la lista (uno tras otro, o en paralelo solo si no tocan los mismos archivos). Nuevo punto de control.
5. **Verificación final:** lanzar `devskills:verificador` en **modo final con lista congelada** (agente distinto de QA y de los desarrolladores): la lista, las regresiones y la batería completa igual que el CI. Si quedan pendientes, ronda 2 y 3; después de 3 rondas, **preguntar al Product Owner** (por defecto, los elementos afectados quedan `Bloqueado` y los demás pasan a Listo). **Cero deuda:** lo que el QA de cierre encuentra se corrige en el mismo sprint; solo lo que pertenece a otro elemento del plan se anota con el ID que lo absorbe. Un hallazgo nuevo del verificador sobre código del sprint (no regresión) se suma a la ronda siguiente del cierre, no se deja para otro sprint.
6. **Avance, en la rama `cierre-sNN`** (`devskills:registrar-avance`): reporte del cierre `documentacion/avance/S{NN}/CIERRE-S{NN}.md`, **completar** el reporte de cada elemento (su parte del QA de cierre, correcciones y verificación final), estado **`Listo`** de todos los elementos aprobados en `estado_backlog.json`, índice actualizado y **regeneración del plan y del tablero** (quedan tachados). Un punto de control: `git add -A -- codigo .github documentacion/avance documentacion/PLAN.md documentacion/plan_sprints.html && git commit -m "wip(s05): cierre del sprint"`.
7. **gitleaks** (paso 2 de la sección 4) y **squash a `main`:** un solo commit `fix(s05): ...` si hubo correcciones de código, o `chore(s05): close sprint quality cycle` si solo cambia el avance. La rama `cierre-sNN` se borra como la de un elemento. Después, los pasos 4 y 5 de la sección 4 (documentación si cambió SRS o DISEÑO, engram con topic_key `<project>/s05/cierre`).
8. **Si el sprint cierra una entrega**, seguir la sección "Cierre de entrega" antes de declararla cerrada.
9. Responder al usuario (y por Telegram si el canal está activo) con: veredicto del QA de cierre, rondas, elementos que pasaron a Listo, enlace al reporte del cierre, commits y avance de la entrega en puntos.

### Reglas
- **Nunca marcar Listo** un elemento del ciclo normal antes del QA de cierre de su sprint (y de su verificación final cuando hubo correcciones); ni uno de la excepción sin el veredicto de QA **y** la evaluación del Angel Fixer (y la verificación final cuando hubo correcciones).
- Nunca editar `documentacion/PLAN.md` a mano.
- Si un agente encuentra una contradicción con el SRS: **detener el ciclo y preguntar al usuario**.
- Commits en inglés con Conventional Commits y **sin atribución de IA ni `Co-Authored-By`**.
- Si un agente se corta por límite de uso: skill `devskills:recuperar-corte` (no se rehace su trabajo).
- **Herramientas de revisión iguales al CI:** ver la regla 8 de "Puntos de control".
- **Nada hacia afuera sin confirmación explícita del usuario:** `git push` (también de etiquetas), `gh` que escriba (crear repositorio, issues, PR, comentarios), merges de Dependabot y cualquier publicación se **proponen** con el comando exacto y se ejecutan solo con un "sí" del usuario en esta conversación (y con gitleaks limpio). En una corrida sin humano no se ejecutan: se dejan listados en el reporte para la persona.
- **Ningún agente instala software** (pip fuera del venv del proyecto, `curl ... | sh`, `get-pip`, `winget`, `brew`, `apt`, `npm -g`, WSL): si falta una herramienta, el agente se detiene y la reporta, y el orquestador pregunta al usuario con el comando exacto y la versión. Un hook del plugin lo bloquea a los subagentes.
- **El CI también es parte del Listo:** ver la regla 8 de "Puntos de control".
- **Mantenimiento de DevSkills (permanente):** al cerrar cada elemento y cada sprint, el orquestador revisa si dejó una **lección general del método o del stack** (no del dominio del proyecto). Si la hay, la redacta como **borrador local** (`.devskills/lecciones.md`, sin nombres, datos, rutas ni código del proyecto: solo el tropiezo, la causa y la regla) y se la **enseña al usuario**. `.devskills/` está en el `.gitignore` del proyecto: el borrador nunca entra a un commit ni al punto de control. Solo si él lo aprueba se publica como issue en el repositorio del plugin (`gh issue create`, con el texto exacto que aprobó); sin aprobación se queda en el borrador. Así el siguiente proyecto no repite el tropiezo y ningún dato del proyecto sale sin permiso.

### Cierre de entrega (lo que solo cubre el CI se corre con Docker)
Una entrega se cierra cuando todos sus elementos están `Listo`, es decir, después del cierre del último sprint que la contiene. Sin remoto no hay CI, y sin Docker no corren las pruebas de despliegue, hadolint ni trivy: si nadie las corre, nunca se corren. Por eso, al cerrar **cada entrega**:
1. El orquestador exige correr **localmente con Docker** (delegado en `devskills:qa` o `devskills:verificador`, con su prefijo `<slug>-<agente>` y su subrango de puertos): la construcción de la imagen, hadolint y trivy con las mismas imágenes fijadas en `.github/workflows/ci.yml`, el Compose válido y las pruebas de despliegue y del certificado que se omiten solas sin Docker.
2. Si no hay Docker (`docker info` falla), el orquestador **se lo pide al usuario**: que lo arranque o lo instale (ningún agente instala nada), o que las corra en otra máquina o en el CI de un remoto. Sin esas pruebas la entrega queda como **verificación pendiente** y solo se declara cerrada si el usuario lo acepta de forma explícita; esa decisión va al reporte como "decisión del Product Owner".
3. Si además no hay remoto, el reporte de la entrega marca **"CI no ejecutado (sin remoto)"**.

### Puntos de control (ningún trabajo sin respaldo en git)
Regla nacida de un incidente real: un verificador vació por accidente un archivo de pruebas que no tenía commit y hubo que reconstruirlo de memoria.
1. Cada elemento se trabaja en su **rama** `hu-xx` o `en-xx` (`git switch -c hu-60`), y el cierre de cada sprint en la rama `cierre-sNN`; nunca directo en `main`.
2. **Antes de lanzar a QA, al Angel Fixer o a una verificación**, el orquestador hace un commit de punto de control con **todo lo que el desarrollador puede tocar**: el código, el CI y el avance, no solo `codigo/`. Comando único (el mismo en `devskills:recuperar-corte` y `devskills:guarda-todo`): `git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-xx): ronda N del desarrollador"`. Después, `git status --short` debe quedar vacío; si muestra algo fuera de esas rutas (`AGENTS.md`, `documentacion/` fuera de `avance/`, la raíz), se revisa con el usuario antes de agregarlo, porque ningún desarrollador debe tocarlo. Lo mismo al terminar cada ronda, antes de un corte previsible y después de cada verificación que haya corregido algo.
3. Con el punto de control hecho, lo que cambie un verificador se ve con `git diff` y cualquier accidente se deshace con `git restore <archivo>`. **Nadie reconstruye un archivo de memoria:** se restaura de git.
4. Al cerrar, la rama entra a `main` como **un solo commit** (`git switch main && git merge --squash hu-xx && git commit -m "feat(hu-xx): ..."`) y la rama se borra (`git branch -D hu-xx`, solo la del elemento o la del cierre y solo el orquestador; en una corrida sin humano se deja y se avisa). Los `wip` no llegan a `main`.
5. QA, el Angel Fixer y el verificador **no ejecutan en el repositorio** scripts, `sed`, redirecciones ni herramientas que escriban archivos de `codigo/`, `.github/` o `documentacion/avance/`; las mutaciones y experimentos (de QA) van en una **copia** en el scratchpad. Si corrigen algo (solo donde su modo lo permite), usan solo la herramienta de edición, archivo por archivo, y reportan el `git diff --stat` de lo que tocaron.
6. Si un agente daña o pierde un archivo: **se detiene, lo restaura de git y lo reporta**. No sigue trabajando encima.
7. Ningún agente ejecuta comandos de git que cambien el árbol o la historia (`add`, `stash`, `checkout`, `switch`, `reset`, `rebase`, `merge`, `commit`, `clean`, `tag`, `push`); eso es exclusivo del orquestador, también en `devskills:gga` y `devskills:judgment-day`: los auditores, los jueces y los correctores solo editan archivos, y **el orquestador** deja el punto de control `wip` tras sus fixes y antes de relanzar la re-auditoría o el nuevo juicio. Regla nacida de un incidente real: un desarrollador corrió `git stash` a media ronda y además aplicó mutaciones en el árbol de trabajo.
8. **Herramientas locales = CI; un CI en rojo es deuda.** QA, Angel Fixer y verificador corren semgrep con la **misma versión** que fija `.github/workflows/ci.yml` (nativo en macOS y Linux; en Windows por WSL o Docker, opcionales; comando exacto en `devskills:validar-historia`) y exigen código 0 y "Findings: 0": una herramienta distinta a la del CI no prueba nada. Solo se usa una vía que **ya esté instalada**: ningún agente instala semgrep, pipx, WSL ni Docker (si falta, se detiene y lo reporta; el orquestador se lo pregunta al usuario). Si la máquina no tiene ninguna de las tres vías, el semgrep del CI de GitHub (siempre obligatorio) es el que cuenta: el orquestador lo deja listado como verificación pendiente y el elemento no se da por Listo hasta que ese job esté en verde (después de un push que el usuario autorice) o el usuario acepte explícitamente cerrar sin él. Si el repositorio tiene remoto, después de cada push (autorizado) se revisa con `gh run list` y, si falla, `gh run view <id> --log-failed` (ambos son de lectura): un CI en rojo se corrige antes de seguir.

## Commands

```bash
git tag inicio-s05                                         # al empezar el sprint, en main (local; no se publica sin confirmación)
git switch -c hu-60                                        # rama del elemento
git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-60): ronda 1 del desarrollador"
git status --short                                         # debe quedar vacío
git diff --stat main...hu-60                               # confirma la clase del elemento (normal o excepción)
# Merge del elemento, en este orden:
python documentacion/analisis/plan_sprints.py              # 1. regenera PLAN.md y el tablero, tras el reporte y el estado
git add -A -- documentacion/avance documentacion/PLAN.md documentacion/plan_sprints.html && git commit -m "wip(hu-60): reporte, estado y plan"
# 2. gitleaks (nativo; Docker como alternativa) sobre `git ls-files -co --exclude-standard`: 0 limpio, 1 hallazgos, 2 herramienta no disponible
python "${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py"
git switch main && git merge --squash hu-60 && git commit -m "feat(hu-60): manage users and roles"   # 3. un commit: código + reporte + estado + índice + plan
git branch -D hu-60                                        # solo el orquestador; en corridas sin humano la rama se deja
# Cierre del sprint:
git switch -c cierre-s05 main
git diff --stat inicio-s05..main                           # alcance del QA de cierre
git add -A -- codigo .github documentacion/avance documentacion/PLAN.md documentacion/plan_sprints.html && git commit -m "wip(s05): cierre del sprint"
git switch main && git merge --squash cierre-s05 && git commit -m "fix(s05): sprint quality findings"   # tras gitleaks
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
