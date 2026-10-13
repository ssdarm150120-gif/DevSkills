# Plan de entregas ágil
## {{NOMBRE_PROYECTO}}

| Campo | Valor |
|-------|-------|
| Versión | 0.1 (borrador) |
| Fecha | {{FECHA}} |
| Autor | {{AUTOR}} |
| Marco de trabajo | Scrum (sprints de 2 semanas) con entregas incrementales |
| Insumos | `documentacion/SRS.md` <!-- X.Y --> (historias del Anexo B), `documentacion/DISENO.md` <!-- X.Y --> (habilitadores técnicos) |
| Estado | Borrador |

> **Regla del documento:** el backlog (sección P.2.2) **se genera** con `documentacion/analisis/plan_sprints.py`, que lee las historias del SRS y los datos de `documentacion/analisis/plan_entregas.json`, y verifica que todas las historias estén planificadas una sola vez. Para repriorizar o reestimar, se edita `plan_entregas.json` y se vuelve a ejecutar; el backlog no se edita a mano.

### Historial de cambios
| Versión | Fecha | Cambios |
|---------|-------|---------|
| 0.1 | {{FECHA}} | Marco Scrum, roadmap de entregas y backlog estimado |

---

## P.1 Marco de trabajo

### P.1.1 Por qué Scrum (y no Kanban puro)
<!-- Por qué conviene demostrar avance cada dos semanas (objetivo medible del SRS 1.1.1), qué dependencias ordena la planificación por sprint, y qué parte se lleva en Kanban (incidentes y soporte, con un porcentaje de capacidad reservado desde la primera salida a producción). -->

### P.1.2 Roles
| Rol Scrum | Quién | Responsabilidad |
|-----------|-------|-----------------|
| Product Owner | <!-- nombre --> | Prioriza el backlog, acepta las historias según sus escenarios Gherkin, mantiene el SRS |
| Scrum Master | **<!-- A definir; no debería ser el Product Owner -->** | Facilita las ceremonias, remueve impedimentos (accesos, infraestructura) |
| Equipo de desarrollo | <!-- p. ej. 2 desarrolladores full-stack (Python/Django) y 1 QA --> | Construye, prueba y despliega |
| Interesados clave | <!-- áreas --> | Participan en las revisiones de sprint de las entregas que los afectan |

### P.1.3 Ceremonias
| Ceremonia | Frecuencia y duración | Resultado |
|-----------|-----------------------|-----------|
| Planificación del sprint | Día de inicio, 2 h | Objetivo del sprint y compromiso del sprint backlog |
| Daily | Diaria, 15 min | Impedimentos visibles el mismo día |
| Refinamiento | Semanal, 1 h | Historias del próximo sprint con la **Definición de Listo** (SRS B.0) y estimadas |
| Revisión (demo) | Día de cierre, 1 h | Demo **con usuarios reales** sobre el entorno de pruebas |
| Retrospectiva | Día de cierre, 45 min | Una o dos mejoras concretas para el próximo sprint |

> **Calendario operativo:** <!-- qué día empieza y termina cada sprint, y qué días nunca se despliega por el negocio. --> Las fechas **no descuentan feriados ni vacaciones**: esos días se absorben en la velocidad y se ajustan al recalibrar.

### P.1.4 Estimación y capacidad
- **Unidad:** puntos de historia (escala de Fibonacci: 1, 2, 3, 5, 8, 13), estimados con planning poker. Una historia de 13 puntos se divide antes de entrar a un sprint.
- **Supuesto de velocidad inicial: <!-- 24 --> puntos por sprint**, con el equipo de <!-- composición -->. Se mantiene conservador porque los primeros sprints incluyen aprender las integraciones.
- **El supuesto se recalibra después del sprint 3** con la velocidad real, y el plan se regenera. Hasta entonces, las fechas son una **estimación**, no un compromiso.
- **Habilitadores técnicos (EN-xx):** trabajo que pide el diseño y que no es una historia de usuario. Se estiman y priorizan igual que las historias.

### P.1.5 Definiciones de Listo y de Terminado
- **Definición de Listo:** la del SRS B.0, más: dependencias del backlog ya terminadas, accesos externos disponibles y datos de prueba preparados.
- **Definición de Terminado:** la del SRS B.0, más: el pipeline en verde (límites de módulos, pruebas, análisis de seguridad), desplegado en el entorno de pruebas, y la matriz de trazabilidad (Anexo C) regenerada si cambió algún requisito.
- **Ciclo de calidad:** cada elemento pasa por **desarrollo → QA → Angel Fixer** (agentes del plugin DevSkills, comando `/devskills:ciclo`). Solo se marca Listo con QA aprobada sin observaciones abiertas y el Angel Fixer sin hallazgos abiertos de ninguna severidad (política de cero deuda); entonces se escribe su reporte en `avance/S{NN}/{ID}.md` y el elemento aparece **tachado** en P.2.2.

### P.1.6 Herramientas
- **Backlog y tablero:** <!-- herramienta --> y el tablero generado `documentacion/plan_sprints.html`.
- **Código y CI/CD:** GitHub y GitHub Actions (DISENO D.6.2).
- **Agentes de IA del equipo:** desarrolladores, QA, Angel Fixer y verificador del plugin DevSkills, con sus subagentes y skills (`AGENTS.md`). Las personas dirigen y aprueban; los agentes ejecutan el ciclo y dejan evidencia en `avance/`.

---

## P.2 Roadmap y backlog

### P.2.1 Lógica de las entregas
<!-- Por qué las entregas van en este orden: cada entrega entrega valor medible y respeta dependencias.
1. **Entrega 0, Cimientos:** sin esto nada funciona (adaptar el esqueleto de DevSkills, integraciones base, adaptadores falsos, identidad).
2. **Entrega 1, ...:** el camino más corto a la meta principal del SRS 1.1.1.
Anota las estimaciones tentativas que se re-estiman en el refinamiento y el piloto de cada entrega. -->

### P.2.2 Backlog priorizado y asignación a sprints

> **Vista interactiva:** `documentacion/plan_sprints.html` (tablero de sprints con scroll horizontal, cada sprint con su scroll vertical, y el diagrama de Gantt por entrega y sprint). Se regenera junto con esta sección con `documentacion/analisis/plan_sprints.py`. El estado que se cambie en el tablero se guarda solo en el navegador de quien lo usa; el oficial es `avance/estado_backlog.json`.
<!-- INICIO BACKLOG GENERADO -->
> Todavía no hay entregas planificadas. El analista las carga en `documentacion/analisis/plan_entregas.json` (skill `planear-entregas`) y vuelve a ejecutar este script.
<!-- FIN BACKLOG GENERADO -->

## P.3 Medición por entrega

| Entrega | Indicador (SRS 1.1.1) | Cómo se mide |
|---------|-----------------------|--------------|
| <!-- n --> | <!-- indicador --> | <!-- HU o consulta que lo mide --> |

Además, por sprint: **velocidad** (puntos terminados), **burndown** y **defectos escapados** a producción.

## P.4 Riesgos del plan

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| La velocidad real es menor a la supuesta | Las fechas se corren | Recalibrar después del sprint 3 y regenerar el plan |
| Un elemento resulta más grande que su estimación | El sprint no cierra | El desarrollador se detiene y lo reporta; se re-estima o se parte (más de 13 puntos) antes de seguir |
| <!-- riesgo --> | <!-- impacto --> | <!-- mitigación --> |

## P.5 Costos operativos estimados
<!-- Opcional. Valores de referencia, no una cotización: concepto, cómo se calcula y costo mensual, con las fuentes y la fecha de consulta. Borra la sección si no aplica. -->
