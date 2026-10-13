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
| 6. Cimientos | dev-a + QA + Angel Fixer | `ciclo-historia` | El esqueleto adaptado al proyecto |
| 7. Historias | Todo el equipo | `ciclo-historia` | Un elemento Listo por ciclo |
| 8. Cierre de sesión | Orquestador | `guarda-todo` | Commit, transcripción, gitleaks, memoria |

**Orden estricto:** no se empieza un paso sin cerrar el anterior y sus pendientes. Todo queda registrado dentro del propio documento.

## El ciclo por historia

```
Desarrollo ──► punto de control ──► QA ──► Angel Fixer ──► ¿Listo? ──sí──► Verificación final ──► Cierre
     ▲                                                        │
     └──────── no (defectos, observaciones o cualquier hallazgo) ◄┘
```

1. **Desarrollo.** El desarrollador lee la historia, sus escenarios Gherkin y el diseño. Si algo falta o el elemento excede su estimación, **se detiene** antes de escribir código.
2. **Punto de control.** El orquestador hace un commit `wip` en la rama del elemento antes de cualquier revisión.
3. **QA.** Convierte el Gherkin del SRS en pruebas de aceptación, verifica los RNF y emite un veredicto.
4. **Angel Fixer.** Evalúa cumplimiento, buenas prácticas y seguridad. Corrige solo lo CRÍTICO y ALTO que confirma.
5. **Rondas.** Cualquier hallazgo vuelve al desarrollador con la lista exacta. Máximo 3 rondas.
6. **Verificación final.** Una sola pasada confirma que todo quedó corregido y sin regresiones.
7. **Cierre.** Reporte, estado oficial, plan y tablero regenerados, squash a `main`, documentación en commits aparte, gitleaks.

## Reglas que no se negocian

### Cero deuda
No se registra deuda técnica. Todo hallazgo (CRÍTICO, ALTO, MEDIO o BAJO) y toda observación de QA se corrige antes de tachar el elemento. Lo que pertenece a otro elemento del plan **no es deuda**: se anota con el ID que lo cubre.

### Rondas y lista congelada
Después de 3 rondas sin aprobar se le pregunta al Product Owner. Si autoriza una ronda extra, es con **lista congelada**: el desarrollador resuelve exactamente lo pendiente, y los revisores verifican solo esa lista y las regresiones. Un hallazgo nuevo que no sea regresión se anota con el ID del elemento que lo absorbe.

### Puntos de control
Ningún trabajo sin respaldo en git:

1. Cada elemento en su rama `hu-xx` o `en-xx`.
2. Commit `wip` antes de lanzar a QA, al Angel Fixer o a una verificación, y al terminar cada ronda.
3. Lo que cambie un revisor se ve con `git diff` y se deshace con `git restore`. Nadie reconstruye un archivo de memoria.
4. Al cerrar, la rama entra a `main` como un solo commit (`merge --squash`).
5. Los revisores no ejecutan en el repositorio nada que escriba archivos de código; las mutaciones van en una copia.
6. Quien dañe un archivo se detiene, lo restaura y lo reporta.
7. Solo el orquestador ejecuta comandos de git que cambian el árbol o la historia.

Las reglas 1 a 6 nacieron de un verificador que vació por accidente un archivo de pruebas sin commit; la 7, de un desarrollador que corrió `git stash` a media ronda.

### Quién decide qué
- **Negocio** (alcance, reglas, riesgos, prioridades): el Product Owner. Se le pregunta con decisiones numeradas y una opción recomendada, y se espera su respuesta.
- **Técnica** (cómo implementar dentro del SRS y el DISEÑO): el orquestador. Se registra como "decisión del orquestador" y el Product Owner puede revertirla.

Cada decisión queda escrita con quién la tomó: en el SRS, en el reporte de avance y en la memoria.

### Idioma, secretos y entorno
- Todo en español de México con tuteo. Commits en inglés, Conventional Commits, sin atribución de IA.
- Nadie lee ni escribe `.env` ni `.env.*`.
- Docker con prefijo y rango de puertos propios por agente, nunca en puertos reservados del host, y limpieza al terminar.
- Nada de la organización escrito en el código: va en configuración.

## Documentos de un proyecto

| Documento | Estándar | Qué contiene |
|-----------|----------|--------------|
| `documentacion/SRS.md` | ISO/IEC/IEEE 29148 | Problema, línea base, metas, RF, RNF, restricciones `R-nn`, supuestos y riesgos `S-nn`, preguntas `P-nn`, Anexo A (casos de uso), Anexo B (historias con Gherkin), Anexo C (trazabilidad, generado) |
| `documentacion/DISENO.md` | IEEE 1016 | D.1 a D.6 y decisiones `ADR-nnn` |
| `documentacion/PLAN.md` | — | Entregas, sprints y backlog (generado, nunca a mano) |
| `documentacion/CONTEXTO.md` | — | Lo propio del proyecto: módulos, asignación, reglas de negocio, puertos, memoria |
| `documentacion/avance/` | — | Estado oficial, índice y un reporte por elemento |

Sigue en: [agentes](agentes.md) · [skills](skills.md) · [generadores](generadores.md) · [stack](stack.md).
