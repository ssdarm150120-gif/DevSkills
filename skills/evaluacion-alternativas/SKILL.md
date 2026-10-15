---
name: evaluacion-alternativas
description: >
  Evalúa comprar o adoptar un producto existente frente a construir con el stack del esqueleto: manifiesto
  de evaluación con opciones, hechos a verificar, propiedad de los datos, cobertura del SRS, impacto, spike
  y criterios ponderados, cerrado con un ADR aceptado o rechazado. Trigger: "¿por qué no usamos X?",
  "comprar o construir", "evalúa el producto", "evaluación de alternativas", "manifiesto de evaluación",
  "montar el sistema sobre".
license: MIT
metadata:
  author: devskills
  version: "1.0"
arguments: [producto]
argument-hint: "<producto o plataforma existente a evaluar>"
---

## When to Use

- Alguien propone montar el proyecto sobre un producto existente (un ERP, una plataforma, un servicio) en lugar de construirlo.
- Antes de un ADR de "comprar o construir", para decidir con evidencia y no con opinión.

Producto a evaluar: $producto

## Critical Patterns

### 1. Principios
- **La evaluación no cambia requisitos.** El SRS sirve igual para cualquier opción: dice qué hace el sistema, no con qué se construye. Si la evaluación descubre un requisito que falta, primero va al SRS.
- **Los hechos del producto se verifican.** Lo que se sabe "de memoria" (módulos, ediciones, licencias) se marca como "hechos a verificar" contra la versión vigente y su documentación oficial antes de decidir.
- **Decide el Product Owner**, con el equipo. El analista recomienda; no decide.
- El stack del esqueleto es fijo para lo que se construye: la pregunta es si el producto reemplaza una parte, no qué framework usar.

### 2. Pasos
1. Copia la plantilla a `documentacion/EVALUACION_<PRODUCTO>.md` (o llena `documentacion/EVALUACION_ALTERNATIVAS.md` si es la única) y reserva el siguiente `ADR-nnn` del DISEÑO.
2. **La pregunta** (sección 1), tal como la hicieron.
3. **Opciones** (sección 2): el producto completo, solo una parte del producto, construir según el diseño actual y, si tiene sentido, un híbrido.
4. **Hechos a verificar** (sección 3): qué es, sobre qué framework, ediciones y licencias, qué trae y qué no, política de actualizaciones.
5. **Quién es dueño de los datos** (sección 4): contrasta cada opción con las fuentes de verdad y las restricciones del SRS (por ejemplo, un sistema externo en solo lectura). Dos sistemas que creen ser dueños de lo mismo son un **riesgo estructural**, no de implementación.
6. **Cobertura del SRS** (sección 5): módulo por módulo, ✅ de fábrica, ⚠️ a medias o ❌ a medida; estima cuántas historias del Anexo B se resuelven de fábrica. Pregunta clave: ¿el producto ahorra lo fácil (lo que el esqueleto ya trae: usuarios, roles, segundo factor) o lo difícil (las historias de mayor valor)?
7. **Impacto** (sección 6) en SRS, DISEÑO, equipo, mantenimiento, licencias y PLAN.
8. **Cuándo sí convendría** (sección 7): las condiciones del negocio que cambiarían la respuesta.
9. **Spike** (sección 8): tiempo acotado, **una sola historia difícil** implementada en las dos opciones, la prueba del punto crítico de la sección 4, la cotización y las horas reales. Si se levanta el producto en Docker, usa el prefijo y el rango de puertos de `documentacion/CONTEXTO.md` y nunca un puerto reservado del host; al terminar, se retira.
10. **Criterios ponderados** (sección 9), en escala de 1 a 5, completados con los datos del spike.
11. **Recomendación y decisión** (sección 10). Pregunta con `devskills:preguntar-al-po`. El Product Owner puede decidir sin ejecutar el spike: se registra así, con sus motivos.

### 3. Cierre
- Estado del manifiesto: **Cerrado: Aceptado** o **Cerrado: Rechazado**, con fecha, y fila en su historial.
- ADR en `DISENO.md` D.1.6. Si se rechaza, la fila se conserva: `**Rechazado (AAAA-MM-DD):** ... Ver documentacion/EVALUACION_<PRODUCTO>.md`, con el motivo y "Decisión del Product Owner".
- Si se acepta: el DISEÑO y el PLAN se rehacen con `devskills:pasada-documental`; el SRS no cambia.
- Anota qué reabriría la decisión (por ejemplo, un requisito nuevo que el producto sí resuelve).
- Regenera el Word y deja el commit `docs:`.

## Commands

```bash
"$PYDOC" documentacion/analisis/md_a_word.py --solo EVALUACION   # Word del manifiesto (una plantilla sin llenar se omite)
```

## Resources

- **Plantilla**: `${CLAUDE_PLUGIN_ROOT}/plantillas/documentacion/EVALUACION_ALTERNATIVAS.md` (ya copiada al proyecto en `documentacion/`).
