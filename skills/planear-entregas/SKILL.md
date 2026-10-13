---
name: planear-entregas
description: >
  Arma y mantiene el plan ágil del proyecto: entregas incrementales, sprints de 2 semanas, estimación por
  puntos, dependencias y velocidad; carga los datos en plan_entregas.json y regenera PLAN.md y el tablero
  de sprints con plan_sprints.py. Trigger: "arma el plan", "plan de entregas", "planea los sprints",
  "reestima", "reprioriza el backlog", "regenera el plan", "recalibra la velocidad", "parte la historia".
license: Apache-2.0
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- Cuando el SRS tiene las historias (Anexo B) y el diseño tiene los habilitadores, para escribir `documentacion/PLAN.md`.
- Cuando se agrega, retira, parte o reestima una historia o un habilitador.
- Al cerrar cada elemento del backlog y en cada pasada documental: se **regenera** (no se edita).
- Después del sprint 3, para recalibrar la velocidad.

## Critical Patterns

### 1. Dónde vive cada dato (nada se escribe a mano en el backlog)
| Dato | Fuente | Quién lo cambia |
|------|--------|-----------------|
| Títulos de las historias | `documentacion/SRS.md`, líneas `#### HU-nn Título` | El analista, en el SRS |
| Entregas, orden de prioridad, puntos por elemento | `documentacion/analisis/plan_entregas.json` → `entregas` | El analista, con esta skill |
| Habilitadores (título y referencia al diseño) | `plan_entregas.json` → `habilitadores` | El analista |
| Capacidad por sprint, duración del sprint, fecha de inicio | `plan_entregas.json` → `velocidad`, `dias_sprint`, `inicio` | El analista, con el Product Owner |
| Estado de cada elemento | `documentacion/avance/estado_backlog.json` | `devskills:registrar-avance` |
| Nombre del proyecto en el tablero | Segundo encabezado de `PLAN.md` | — |
| Marco, roles, ceremonias, lógica de entregas, medición, riesgos, costos | El texto de `PLAN.md` fuera de los marcadores | El analista |

`plan_sprints.py` reemplaza **solo** lo que está entre `<!-- INICIO BACKLOG GENERADO -->` y `<!-- FIN BACKLOG GENERADO -->` y genera `documentacion/plan_sprints.html`. **Nunca edites esa sección de `PLAN.md` ni el HTML a mano.**

### 2. Cómo se cargan las entregas
```json
{
  "inicio": "AAAA-MM-DD",
  "velocidad": 24,
  "dias_sprint": 14,
  "habilitadores": {
    "EN-01": {"titulo": "Adaptar el esqueleto del monolito modular", "ref": "D.1.5, D.6.2"}
  },
  "entregas": [
    {"num": "0", "nombre": "Cimientos", "objetivo": "Que todo lo demás se pueda construir y desplegar con seguridad",
     "items": [["EN-01", 5], ["HU-01", 8]]}
  ]
}
```
- `items` va **en orden de prioridad** y respeta las dependencias: lo que otro elemento necesita va antes. El script llena los sprints en ese orden hasta la `velocidad`, y **cada entrega cierra en su propio sprint**.
- `num` admite letras para una entrega intercalada (`"2b"`).
- El script falla con un mensaje claro si una historia vigente del SRS no está planificada, si un elemento está duplicado, si un `EN-nn` no está en `habilitadores`, si se planifica una historia que no existe o está retirada, o si `estado_backlog.json` tiene un ID que no está en el plan.
- Un valor de `velocidad` de ejemplo no es una decisión: se fija con el Product Owner según el equipo y se anota en P.1.4.

### 3. Entregas
- **Entrega 0, Cimientos:** sin esto nada funciona. Aquí van la adaptación del esqueleto de DevSkills al proyecto (módulos, contratos, CI, Compose), los adaptadores falsos de las integraciones, la identidad y lo que el diseño pide como base.
- Cada entrega siguiente tiene un **objetivo medible** ligado a las metas del SRS 1.1.1 y busca **el camino más corto al valor**: si una entrega pasa muchos sprints sin valor para el negocio, se divide.
- Escribe en P.2.1 por qué van en ese orden, y en P.3 cómo se mide cada una.

### 4. Estimación
- Puntos de historia en escala de Fibonacci: 1, 2, 3, 5, 8, 13.
- **Una historia de más de 13 puntos se parte antes de entrar a un sprint.** Partirla es un cambio del SRS (dos historias con su trazabilidad y sus escenarios), así que va con `devskills:pasada-documental` y lo decide el Product Owner.
- **Si el desarrollador detecta que un elemento vale claramente más de lo estimado, se detiene antes de escribir código y lo reporta.** Entonces se recorta el alcance, se parte o se reestima, y se regenera el plan. No se sigue "porque ya empezamos".
- Los habilitadores se estiman y priorizan igual que las historias.
- Las estimaciones tentativas se marcan en P.2.1 y se reestiman en el refinamiento antes de entrar a un sprint.
- Cuando un elemento absorbe trabajo de otro (o se lo deja), se ajustan los puntos de ambos y se anota en el historial del plan.

### 5. Velocidad y recalibración
- La velocidad inicial es un **supuesto**. Hasta recalibrar, las fechas son una estimación, no un compromiso.
- **Se recalibra después del sprint 3** con la velocidad real y se regenera el plan.
- Si un elemento llevó mucho más esfuerzo que sus puntos, se anota en su reporte de avance ("Esfuerzo real") para la retrospectiva: si la velocidad se calcula solo con los puntos estimados, sale más baja de lo que el equipo trabajó.
- Las fechas no descuentan feriados ni vacaciones: se absorben en la velocidad.

### 6. Cuándo se regenera
| Momento | Quién |
|---------|-------|
| Al cerrar cada elemento (queda **tachado** y suben los porcentajes) | `devskills:registrar-avance`, dentro de `devskills:ciclo-historia` |
| En cada pasada documental que cambie historias, habilitadores o puntos | `devskills:pasada-documental` |
| Al repriorizar, reestimar o recalibrar | Esta skill |

Cada cambio del plan sube la versión de `PLAN.md` y agrega una fila a su historial con el motivo, el total de puntos y de sprints antes y después.

### 7. Verificación después de regenerar
- [ ] El script terminó sin error y reporta el total de puntos y de sprints.
- [ ] Lo marcado `Listo` aparece tachado (`~~ID~~`) con su fecha y su enlace al reporte.
- [ ] Ningún sprint supera la capacidad (en el tablero, la barra del sprint sale en rojo).
- [ ] `documentacion/plan_sprints.html` abre y muestra los indicadores, los sprints y el Gantt.

## Commands

```bash
python documentacion/analisis/plan_sprints.py      # regenera PLAN.md (P.2.2) y documentacion/plan_sprints.html
python documentacion/analisis/md_a_word.py --solo PLAN
```

## Resources

- **Plantillas**: `${CLAUDE_PLUGIN_ROOT}/plantillas/documentacion/PLAN.md` y `${CLAUDE_PLUGIN_ROOT}/plantillas/analisis/plan_entregas.json` (ya copiadas al proyecto).
