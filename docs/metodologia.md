# Metodología

DevSkills es una metodología y un stack para construir **cualquier sistema**, nacida de un proyecto real: requisitos y diseño por escrito antes de programar, un equipo de agentes con roles separados, y un ciclo de calidad que no deja deuda. No presupone un dominio: los actores, los procesos, los roles y las integraciones (si las hay) salen del descubrimiento de cada proyecto, sea un sistema de inventarios, una plataforma escolar o una app interna de recursos humanos.

## Flujo completo de un proyecto

```
┌───────────────┐   ┌─────────┐   ┌─────────┐   ┌────────┐   ┌──────────────┐   ┌──────────────────┐
│ Descubrimiento│──▶│   SRS   │──▶│ DISEÑO  │──▶│  PLAN  │──▶│  Entrega 0   │──▶│ Ciclo por historia│
│ con el PO     │   │ 29148   │   │ IEEE1016│   │ sprints│   │  (cimientos) │   │ hasta cerrar      │
└───────────────┘   └─────────┘   └─────────┘   └────────┘   └──────────────┘   └──────────────────┘
        │                │             │             │                                   │
   línea base      RF, RNF, CU,   módulos, ADR,   entregas,                    reporte, plan tachado,
   y metas         HU + Gherkin   datos, eventos  puntos                       guarda-todo por sesión
```

| Paso | Quién | Skill | Resultado |
|------|-------|-------|-----------|
| 1. Descubrimiento | Orquestador + analista-arquitecto + Product Owner | `iniciar-proyecto`, `preguntar-al-po` | Problema, línea base medible, metas, actores, restricciones, integraciones |
| 2. Carpeta del proyecto | Orquestador (o `devskills init`) | `iniciar-proyecto` | Estructura, esqueleto del stack fijo, primer commit |
| 3. SRS | analista-arquitecto | `redactar-srs` | Requisitos, casos de uso, historias con Gherkin, Anexo C |
| 4. DISEÑO | analista-arquitecto | `redactar-diseno` | D.1 a D.6 y ADR |
| 5. PLAN | analista-arquitecto | `planear-entregas` | Entregas, sprints, tablero |
| 6. Cimientos | dev-a + QA + Angel Fixer | `ciclo-historia` | El esqueleto adaptado al proyecto (plataforma: ciclo completo por historia) |
| 7. Historias | Todo el equipo | `ciclo-historia` | Cada elemento integrado y En validación; Listo al cerrar su sprint |
| 8. Cierre de sesión | Orquestador | `guarda-todo` | Commit, transcripción, gitleaks, memoria |

**Orden estricto:** no se empieza un paso sin cerrar el anterior y sus pendientes. Todo queda registrado dentro del propio documento.

## El ciclo de calidad híbrido

Dos revisores con terrenos separados, sin traslape: el **Angel Fixer** revisa el **código** (seguridad, arquitectura y límites de módulos, buenas prácticas, deuda) y **QA** revisa el **comportamiento** (escenarios Gherkin del SRS de punta a punta, regresiones entre historias, RNF verificables del Anexo C, mutaciones dirigidas al riesgo y ataques). Quien verifica una corrección es siempre un agente distinto del que la hizo. La única fuente de las reglas es la skill `ciclo-historia`.

### Por elemento (ciclo normal)
```
Desarrollo (TDD) ──► punto de control ──► Revisión por historia (Angel Fixer) ──► ¿hallazgos? ──no──► Merge: En validación
                                                     │ sí
                                                     ▼
                                     lista congelada ──► corrección ──► verificación ligera ──► Merge: En validación
                                                         ▲   (máximo 3 rondas)   │ pendientes
                                                         └───────────────────────┘
```

1. **Desarrollo con TDD.** El desarrollador lee la historia, sus escenarios Gherkin y el diseño; copia el Gherkin tal cual a su `.feature` con sus pasos pytest-bdd y escribe las pruebas antes del código. Si algo falta o el elemento excede su estimación, **se detiene** antes de escribir código.
2. **Punto de control.** El orquestador hace un commit `wip` en la rama del elemento antes de cualquier revisión.
3. **Revisión por historia del Angel Fixer.** Código más la **lista mínima**: build sin advertencias, pruebas en verde, gitleaks limpio y cada escenario Gherkin con su prueba. Sin mutaciones, sin ataques y sin fixes: solo reporta.
4. **Lista congelada y rondas.** Los hallazgos, de cualquier severidad, se congelan; el desarrollador los corrige (máximo 3 rondas) y el **verificador** confirma esa lista en modo ligero, sin abrir búsquedas nuevas.
5. **Merge.** Reporte parcial, estado **En validación**, plan regenerado y squash a `main`. El elemento ya está integrado, pero no es Listo.

### Al cerrar el sprint
6. **QA completo sobre todo el diff del sprint** (desde la etiqueta `inicio-sNN`): todos los escenarios de las historias del sprint, regresiones entre historias, RNF, 10 a 15 mutaciones dirigidas a lo más riesgoso y ataques cuando aplica.
7. **Lista congelada → correcciones → verificación final independiente**, en la rama `cierre-sNN`. Lo que QA encuentra se corrige en el mismo sprint (cero deuda).
8. **Listo.** Todos los elementos aprobados pasan a Listo, se completan sus reportes, se escribe `CIERRE-S{NN}.md` y se regenera el plan (quedan tachados).

Si el proyecto usa Graphify, al abrir el cierre el orquestador genera el **reporte de deriva** entre el grafo del deber ser (documentación) y el de lo que es (código) y QA confirma cada candidato: lo confirmado entra a la lista congelada como observación (falta código, falta diseño o decisión de negocio). Ver [graphify](graphify.md).

### La excepción: ciclo completo por historia
Los elementos de **seguridad** (riesgos `S-nn`, autenticación, autorización, archivos, secretos), de **plataforma o núcleo compartido** (los módulos que lista `CONTEXTO.md`) o que el orquestador marque como **críticos** no esperan al cierre del sprint: QA (por historia) y el Angel Fixer (evaluación, con fixes quirúrgicos de CRÍTICOS y ALTOS) corren en paralelo, se corrige, y la verificación final confirma **antes** del merge, que los deja en Listo. En la duda, excepción.

### Cierre, en este orden (cada merge y cada cierre de sprint)
(1) En la rama: reporte, `estado_backlog.json`, índice y plan y tablero regenerados, en un punto de control. (2) gitleaks (código 0; el 2 significa que la herramienta no está disponible). (3) Squash a `main` en **un solo commit** que lleva el código **y** el reporte, el estado, el índice y el `PLAN.md`: `main` nunca muestra un elemento sin su evidencia. (3b) Si hay Graphify: grafo del código actualizado sin LLM en un commit aparte `chore(graph): ...`, tras gitleaks. (4) Solo si cambió SRS o DISEÑO: Anexo C, plan, Word y grafo del deber ser en commits `docs:` aparte sobre `main`, cada uno tras gitleaks. (5) Engram y respuesta; un `push`, solo con la confirmación del usuario y después de todo lo anterior.

## Reglas que no se negocian

### Cero deuda
No se registra deuda técnica. Todo hallazgo (CRÍTICO, ALTO, MEDIO o BAJO) y toda observación de QA se corrige antes de tachar el elemento; lo que encuentra el QA de cierre se corrige en el mismo sprint. Lo que pertenece a otro elemento del plan **no es deuda**: se anota con el ID que lo cubre.

### Rondas y lista congelada
En el ciclo normal la lista del Angel Fixer y la del QA de cierre se congelan desde la primera ronda. Después de 3 rondas sin aprobar se le pregunta al Product Owner. Si autoriza una ronda extra, es con **lista congelada**: el desarrollador resuelve exactamente lo pendiente, y los revisores verifican solo esa lista y las regresiones. Un hallazgo nuevo que no sea regresión se anota con el ID del elemento que lo absorbe.

### Puntos de control
Ningún trabajo sin respaldo en git:

1. Cada elemento en su rama `hu-xx` o `en-xx`, y el cierre de cada sprint en `cierre-sNN`.
2. Commit `wip` antes de lanzar a QA, al Angel Fixer o a una verificación, y al terminar cada ronda.
3. Lo que cambie un revisor se ve con `git diff` y se deshace con `git restore`. Nadie reconstruye un archivo de memoria.
4. Al cerrar, la rama entra a `main` como un solo commit (`merge --squash`).
5. Los revisores no ejecutan en el repositorio nada que escriba archivos de código; las mutaciones (de QA) van en una copia.
6. Quien dañe un archivo se detiene, lo restaura y lo reporta.
7. Solo el orquestador ejecuta comandos de git que cambian el árbol o la historia, también en `gga` y `judgment-day`: sus auditores, jueces y correctores no hacen `add`, `commit` ni `push`; el orquestador deja el punto de control después de los fixes y antes de relanzar la revisión.
8. **Herramientas locales = CI; un CI en rojo es deuda.** QA, Angel Fixer y verificador corren semgrep con la misma versión que fija el CI y exigen código 0 y "Findings: 0"; si la máquina no puede, el job del CI de GitHub es el que cuenta y el elemento no es Listo hasta que esté en verde. Tras cada push autorizado se revisa con `gh run list`; un CI en rojo se corrige antes de seguir.

Las reglas 1 a 6 nacieron de un verificador que vació por accidente un archivo de pruebas sin commit; la 7, de un desarrollador que corrió `git stash` a media ronda.

**`main` no lleva commits `wip:`.** Viven en la rama del elemento y el `merge --squash` los elimina: en `main` solo entra el commit del elemento (más los `docs:` aparte). Si un `wip:` llegó a `main` en un historial ya publicado, se documenta y se deja: no se reescribe el historial publicado.

### Quién decide qué
- **Negocio** (alcance, reglas, riesgos, prioridades): el Product Owner. Se le pregunta con decisiones numeradas y una opción recomendada, y se espera su respuesta.
- **Técnica** (cómo implementar dentro del SRS y el DISEÑO): el orquestador. Se registra como "decisión del orquestador" y el Product Owner puede revertirla.

Cada decisión queda escrita con quién la tomó: en el SRS, en el reporte de avance y en la memoria.

### Idioma, secretos y entorno
- El idioma del proyecto es el de `documentacion/CONTEXTO.md` (por defecto español de México con tuteo) y prevalece sobre el estilo personal del usuario; el `CLAUDE.md` de la raíz del proyecto importa `AGENTS.md` y lo declara. Commits en inglés, Conventional Commits, sin atribución de IA.
- Los borradores locales del orquestador (lecciones para DevSkills, engram pendiente) viven en `.devskills/`, ignorada por git: nunca entran a un commit.
- Sin remoto no hay CI: el reporte marca "CI no ejecutado (sin remoto)" con la verificación pendiente, y al cerrar cada entrega se exigen localmente con Docker las pruebas que solo cubre el CI (imagen, hadolint, trivy, despliegue); sin Docker se le pide al usuario.
- Nadie lee ni escribe `.env` ni `.env.*`.
- Docker es **opcional**: se desarrolla y se prueba sin él (PostgreSQL embebido y Celery local); Compose solo hace falta para desplegar. Si lo usas, el prefijo es `<slug>-<agente>` y la limpieza es solo de lo tuyo. Nunca en puertos reservados del host.
- Nada sale del equipo sin la confirmación explícita del usuario: `git push`, `gh` de escritura, merges de Dependabot, publicar una lección en el repositorio de DevSkills.
- Nada de la organización escrito en el código: va en configuración.

## Documentos de un proyecto

| Documento | Estándar | Qué contiene |
|-----------|----------|--------------|
| `documentacion/SRS.md` | ISO/IEC/IEEE 29148 | Problema, línea base, metas, RF, RNF, restricciones `R-nn`, supuestos y riesgos `S-nn`, preguntas `P-nn`, Anexo A (casos de uso), Anexo B (historias con Gherkin), Anexo C (trazabilidad, generado) |
| `documentacion/DISENO.md` | IEEE 1016 | D.1 a D.6 y decisiones `ADR-nnn` |
| `documentacion/PLAN.md` | — | Entregas, sprints y backlog (generado, nunca a mano) |
| `documentacion/CONTEXTO.md` | — | Lo propio del proyecto: módulos, asignación, reglas de negocio, puertos, memoria |
| `documentacion/avance/` | — | Estado oficial, índice, un reporte por elemento y uno por cierre de sprint |

Sigue en: [agentes](agentes.md) · [skills](skills.md) · [generadores](generadores.md) · [stack](stack.md).
