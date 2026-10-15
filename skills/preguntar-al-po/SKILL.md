---
name: preguntar-al-po
description: >
  Cómo hacerle preguntas de negocio al Product Owner: decisiones numeradas con opciones y una opción
  recomendada, por terminal con AskUserQuestion o por Telegram como texto numerado; esperar la respuesta
  sin suponer; registrar en el SRS (o en el reporte) quién decidió. Trigger: cuando una decisión es de
  negocio, cuando un agente encuentra un hueco o contradicción del SRS, al llegar a 3 rondas sin aprobar,
  o para autorizar una ronda extra o un cierre con pendientes.
license: MIT
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- La decisión es **de negocio**: alcance, reglas, prioridades, riesgos aceptados, datos, plazos, costos, partir una historia, cerrar con pendientes, autorizar una ronda extra con lista congelada.
- Un agente se detuvo por un hueco o una contradicción del SRS.
- Un elemento llegó a **3 rondas sin aprobar**.

**No se pregunta** lo técnico que el orquestador puede decidir con el SRS y el DISEÑO: eso se decide, se registra como **"decisión del orquestador"** y se informa (el Product Owner puede revertirlo).

## Critical Patterns

### 1. Formato de la pregunta
- Contexto en 2 a 4 líneas, en lenguaje de negocio (sin jerga técnica innecesaria).
- **Decisiones numeradas** (`D1`, `D2`, …), cada una con opciones con letra (`a`, `b`, `c`), su consecuencia en una línea, y **una opción recomendada** marcada con "(recomendada)" y el porqué.
- Un default explícito si no hay respuesta (por ejemplo, en el ciclo: "si no decides, el elemento queda Bloqueado").
- Máximo 4 decisiones por mensaje; si hay más, se priorizan.

```text
HU-60 · Gestionar usuarios — 3 decisiones (ronda 1 de QA y Angel Fixer)

D1. ¿El Administrador puede cambiar sus propios roles?
  a) Sí, y queda registrado (recomendada: no bloquea la operación y deja rastro)
  b) No, lo hace otro Administrador
D2. …

Responde, por ejemplo: "D1 a, D2 b". Mientras no respondas, el elemento sigue en la ronda 1.
```

### 2. Por dónde preguntar
- **Terminal:** herramienta `AskUserQuestion`, una pregunta por decisión, con las opciones (la recomendada primero y marcada como "(recomendada)"). Si la herramienta no está disponible, el mismo texto numerado en la respuesta.
- **Telegram** (si la sesión se abrió con el canal, por ejemplo `claude-tg` o `claude --channels plugin:telegram@claude-plugins-official`): el Product Owner no ve la terminal; manda el **texto numerado** con la herramienta `reply` del canal (las respuestas tipo "D1 a, D2 b" son fáciles de escribir en el celular). Si la pregunta es larga, adjunta el detalle como archivo `.md`.
- Nunca por los dos a la vez con textos distintos.

### 3. Esperar
- **Detente y espera la respuesta.** No continúes con la parte que depende de la decisión ni supongas la opción recomendada.
- Mientras esperas puedes avanzar trabajo que **no** depende de la decisión, y lo dices.
- Si la respuesta es ambigua, repregunta solo lo ambiguo.

### 4. Registrar quién decidió
- **En el SRS** (vía `analista-arquitecto` y `devskills:pasada-documental`): la pregunta `P-nn` pasa a "**Resuelto**: …" y la fila del historial dice "Decisión del Product Owner: …". Las decisiones técnicas quedan como "decisión del orquestador".
- **En el reporte de avance** (`devskills:registrar-avance`, sección 5): "Decisiones del Product Owner", "Decisiones del orquestador (validadas por el Product Owner)", "Decisiones del desarrollador (aceptadas por la verificación)".
- **En engram** (`mem_save`, type `decision`, project de `CONTEXTO.md`).
- Si la decisión cambia una regla de trabajo (por ejemplo, "todo en español de México" o "cero deuda"), se agrega a `documentacion/CONTEXTO.md` y, si es del método, se propone para la siguiente versión del plugin.
