---
name: registrar-avance
description: >
  Escribe el reporte de avance (MD) de un elemento del backlog después de QA, del Angel Fixer y de la
  verificación final, actualiza el estado oficial, el índice, y regenera el PLAN y el tablero de sprints
  (tacha lo Listo). Trigger: al cerrar el ciclo de calidad de una HU o un EN, o al bloquearlo.
license: MIT
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- QA dio su veredicto, el Angel Fixer terminó su evaluación y la verificación final aprobó (o el Product Owner decidió cerrar).
- También cuando un elemento queda `Bloqueado`, para dejar constancia.
- Para marcar `En proceso` o `En validación` durante el ciclo (solo el estado, sin reporte).

## Critical Patterns

### 1. Regla de "Listo" (no se negocia)
Un elemento se marca **Listo** (y se tacha en el plan) **solo si**:
- QA: **APROBADA** sin observaciones abiertas, y
- Angel Fixer: **sin hallazgos abiertos de ninguna severidad** (política de cero deuda), y
- la verificación final, cuando hubo correcciones, aprobó.

La única excepción es una **decisión explícita del Product Owner** de cerrar con pendientes menores; entonces cada pendiente queda en el reporte con el ID del elemento que lo absorbe, y la decisión queda registrada como del Product Owner. En cualquier otro caso queda `En proceso` (vuelve al desarrollador) o `Bloqueado` (con el motivo).

### 2. Reporte
- Ruta: `documentacion/avance/S{NN}/{ID}.md`, con `NN` = sprint del plan con dos dígitos (por ejemplo, `documentacion/avance/S05/HU-42.md`).
- Usar la plantilla de [assets/plantilla_reporte.md](assets/plantilla_reporte.md), completa, sin dejar secciones vacías.
- Incluir los resúmenes de QA, del Angel Fixer y de la verificación final **tal como los entregaron**, más el commit o la rama.
- Separar siempre quién decidió: Product Owner, orquestador o desarrollador.

### 3. Estado oficial, índice y plan
1. Actualizar `documentacion/avance/estado_backlog.json` (UTF-8, JSON válido, sin editar los demás IDs):
   ```json
   {"HU-42": {"estado": "Listo", "fecha": "2026-12-14", "reporte": "avance/S05/HU-42.md"}}
   ```
   Estados válidos: `En proceso`, `En validación`, `Listo`, `Bloqueado`.
2. **Regenerar el plan y el tablero:** `python documentacion/analisis/plan_sprints.py` desde la raíz del proyecto. El script **tacha** los elementos Listo en `documentacion/PLAN.md`, actualiza los porcentajes por entrega y regenera el tablero `documentacion/plan_sprints.html`. **Nunca editar `documentacion/PLAN.md` a mano.** Comprueba que quedó tachado.
3. Agregar una línea al índice `documentacion/avance/README.md` (fecha, ID, sprint, veredicto de QA con rondas, resultado del Angel Fixer, estado, enlace al reporte).
4. Guardar en engram (`mem_save`, project de `CONTEXTO.md`, topic_key `<project>/avance/<ID>`) el resultado y los hallazgos no obvios.

## Commands

```bash
python documentacion/analisis/plan_sprints.py
rg -n "~~<ID>" documentacion/PLAN.md     # comprobar que quedó tachado (o la herramienta Grep)
```

## Resources

- **Plantilla**: [assets/plantilla_reporte.md](assets/plantilla_reporte.md)
