# Skills

DevSkills, metodología y stack para construir cualquier sistema, trae 22 skills; ninguna asume un dominio. Con el plugin se invocan como `/devskills:<nombre>`; con el instalador, como `/devskills-<nombre>`. Las que tienen "atajo" son comandos pensados para que los escribas tú; las demás también las carga Claude cuando la tarea coincide con su descripción.

## Arranque y documentación

| Skill | Quién la usa | Qué hace |
|-------|--------------|----------|
| `nuevo-proyecto` (atajo) | Tú | `/devskills:nuevo-proyecto "<Nombre>"` → ejecuta `iniciar-proyecto` |
| `iniciar-proyecto` | Orquestador + analista | Descubrimiento con el Product Owner (problema, línea base medible, metas, actores, alcance, restricciones, integraciones, puertos de la máquina), crea la carpeta con `crear_proyecto.py`, llena `CONTEXTO.md` y el SRS 0.1 |
| `redactar-srs` | analista-arquitecto | SRS ISO/IEC/IEEE 29148 en orden estricto: problema y línea base, RF/RNF, preguntas `P-nn`, Anexo A, Anexo B con Gherkin, Anexo C generado |
| `redactar-diseno` | analista-arquitecto | DISEÑO IEEE 1016, D.1 a D.6, con ADR. Un cambio que afecte requisitos va primero al SRS |
| `planear-entregas` | analista-arquitecto | Entregas, sprints, puntos (Fibonacci, partir más de 13), velocidad y recalibración; carga `plan_entregas.json` y regenera `PLAN.md` y el tablero |
| `pasada-documental` | analista-arquitecto | Sube versión de SRS/DISEÑO con historial, registra preguntas y quién decidió, regenera Anexo C, plan, tablero y Word, y deja un commit `docs:` aparte |
| `evaluacion-alternativas` | analista-arquitecto | Comprar o construir: manifiesto de evaluación con opciones, criterios ponderados y su ADR |
| `prompts-figma` | analista-arquitecto | Prompts de Figma Make derivados del SRS y el PLAN: sistema de diseño, pantallas, actualización y correcciones |
| `generar-presentacion` | analista-arquitecto | Presentación `.pptx` para la dirección a partir de `datos_presentacion.json` |

## Ciclo de cada historia

| Skill | Quién la usa | Qué hace |
|-------|--------------|----------|
| `ciclo` (atajo) | Tú | `/devskills:ciclo HU-35` o `/devskills:ciclo S05` → invoca `ciclo-historia` (sin reglas propias; es la única fuente) |
| `ciclo-historia` | Orquestador | Rama y puntos de control, desarrollo, QA, Angel Fixer, rondas (máximo 3), pregunta al Product Owner, lista congelada, verificación final, reporte, plan, gitleaks y squash a `main` |
| `implementar-historia` | dev-a, dev-b | TDD, ubicación en la arquitectura, checklist de reglas y de lecciones aprendidas, entrega sin commit |
| `validar-historia` | qa, verificador | Gherkin del SRS a pytest-bdd, RNF, batería y mutaciones, veredicto |
| `angel-fixer` | angel-fixer, verificador | Modo evaluación (historia, buenas prácticas, seguridad) y modo remediación (hallazgos de GGA) |
| `registrar-avance` | Orquestador | Reporte con la plantilla, `estado_backlog.json`, índice, y regeneración del plan y el tablero |

## Calidad adicional

| Skill | Qué hace |
|-------|----------|
| `gga` | Auditoría de seguridad con dos auditores ciegos en paralelo; los hallazgos confirmados van al Angel Fixer |
| `judgment-day` | Revisión adversarial con dos jueces ciegos, corrector separado y nuevo juicio hasta aprobar o escalar |

## Sesión y coordinación

| Skill | Qué hace |
|-------|----------|
| `orquestador` | Reglas de la sesión principal: delegar, decidir lo técnico, preguntar lo de negocio, puntos de control, estado, engram, Telegram |
| `proyecto-contexto` | Reglas comunes (arquitectura fija, convenciones, DoR, DoD, cero deuda, entorno) y la orden de leer `documentacion/CONTEXTO.md` |
| `preguntar-al-po` | Decisiones numeradas con opción recomendada; terminal (`AskUserQuestion`) o Telegram; esperar; registrar quién decidió |
| `guarda-todo` | Commit, transcripción con `exportar_sesion.py`, gitleaks, commit y resumen en engram |
| `recuperar-corte` | Diagnóstico, commit de respaldo, reanudar al mismo agente con `SendMessage` sin rehacer, y limpieza |

## Equivalencias con el proyecto modelo

| Proyecto modelo | DevSkills |
|-----------------|-----------|
| `ciclo-historia` | `ciclo-historia` (más verificación final, cierre con squash, commits de documentación aparte, Word, Anexo C y gitleaks) |
| `<proyecto>-contexto` | `proyecto-contexto` + `documentacion/CONTEXTO.md` por proyecto |
| `<proyecto>-implementar-historia` | `implementar-historia` (más el checklist de lecciones aprendidas) |
| `<proyecto>-validar-historia` | `validar-historia` |
| `<proyecto>-registrar-avance` | `registrar-avance` (misma plantilla, con quién decidió) |
| Skills personales `angel-fixer`, `gga`, `judgment-day` | Las mismas, en español de México y autocontenidas |
| Trabajo manual del orquestador | `iniciar-proyecto`, `redactar-srs`, `redactar-diseno`, `planear-entregas`, `pasada-documental`, `preguntar-al-po`, `guarda-todo`, `recuperar-corte`, `orquestador`, `evaluacion-alternativas`, `prompts-figma`, `generar-presentacion` |
