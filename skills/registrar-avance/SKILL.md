---
name: registrar-avance
description: >
  Escribe el reporte de avance (MD) de un elemento del backlog y del cierre de cada sprint, actualiza el estado
  oficial y el índice, y regenera el PLAN y el tablero de sprints (tacha lo Listo). En el ciclo híbrido, el
  merge de un elemento normal deja el reporte parcial y el estado "En validación"; el cierre del sprint completa
  los reportes y pasa los elementos a Listo. Trigger: al hacer merge de una HU o un EN, al cerrar un sprint, o al
  bloquear un elemento.
license: MIT
metadata:
  author: devskills
  version: "2.1"
---

## When to Use

- **Merge de un elemento del ciclo normal:** la revisión por historia del Angel Fixer quedó sin hallazgos abiertos (y la verificación ligera aprobó, si hubo correcciones). Reporte **parcial** y estado `En validación`.
- **Merge de un elemento de la excepción:** QA dio su veredicto, el Angel Fixer terminó su evaluación y la verificación final aprobó (o el Product Owner decidió cerrar). Reporte completo y estado `Listo`.
- **Cierre del sprint:** el QA de cierre aprobó (y la verificación final, si hubo correcciones). Reporte del cierre, reportes de los elementos completados y estado `Listo`.
- También cuando un elemento queda `Bloqueado`, para dejar constancia.
- Para marcar `En proceso` o `En validación` durante el ciclo (solo el estado, sin reporte).

## Critical Patterns

### 1. Regla de "Listo" (no se negocia)
Un elemento se marca **Listo** (y se tacha en el plan) **solo si**:
- **Ciclo normal:** la revisión por historia del Angel Fixer quedó sin hallazgos abiertos de ninguna severidad (con la verificación ligera aprobada si hubo correcciones), **y** el QA de cierre de su sprint lo dio por **APROBADO** sin observaciones abiertas, **y** la verificación final del cierre aprobó cuando hubo correcciones. Antes del cierre del sprint queda **`En validación`**, aunque ya esté en `main`.
- **Excepción:** QA **APROBADA** sin observaciones abiertas, **y** Angel Fixer **sin hallazgos abiertos de ninguna severidad** (política de cero deuda), **y** la verificación final, cuando hubo correcciones, aprobó.

La única excepción es una **decisión explícita del Product Owner** de cerrar con pendientes menores; entonces cada pendiente queda en el reporte con el ID del elemento que lo absorbe, y la decisión queda registrada como del Product Owner. En cualquier otro caso queda `En proceso` (vuelve al desarrollador) o `Bloqueado` (con el motivo).

### 2. Reporte
- Ruta: `documentacion/avance/S{NN}/{ID}.md`, con `NN` = sprint del plan con dos dígitos (por ejemplo, `documentacion/avance/S05/HU-42.md`).
- Usar la plantilla de [assets/plantilla_reporte.md](assets/plantilla_reporte.md), completa, sin dejar secciones vacías. El campo **Ciclo** dice si fue normal o excepción, y por qué.
- **Ciclo normal, en el merge:** reporte **parcial**: la sección de QA dice "Pendiente del QA de cierre del sprint S{NN}" y el estado es `En validación`; todo lo demás (revisión por historia, rondas, verificación ligera, decisiones) va completo. **En el cierre del sprint** se completa: la parte del QA de cierre que le toca al elemento (su veredicto, escenarios, defectos `DEF-SNN-n`), las correcciones y la verificación final, y el estado `Listo`.
- **Cierre del sprint:** además, `documentacion/avance/S{NN}/CIERRE-S{NN}.md` con la plantilla de [assets/plantilla_cierre_sprint.md](assets/plantilla_cierre_sprint.md): alcance del diff, QA de cierre completo, **deriva entre el deber ser y lo que es** (enlace a `DERIVA-S{NN}.md`, candidatos confirmados y descartados, o "deriva no medida (sin grafos)"), lista congelada, rondas, verificación final y estado de cada elemento.
- Incluir los resúmenes de QA, del Angel Fixer y del verificador **tal como los entregaron**, más el commit o la rama.
- Separar siempre quién decidió: Product Owner, orquestador o desarrollador.

### 3. Estado oficial, índice y plan
1. Actualizar `documentacion/avance/estado_backlog.json` (UTF-8, JSON válido, sin editar los demás IDs):
   ```json
   {"HU-42": {"estado": "Listo", "fecha": "2026-12-14", "reporte": "avance/S05/HU-42.md"}}
   ```
   En el merge de un elemento del ciclo normal el estado es `"En validación"` (con su reporte parcial); el cierre del sprint lo cambia a `"Listo"` con la fecha del cierre.
   Estados válidos: `En proceso`, `En validación`, `Listo`, `Bloqueado`.
2. **Regenerar el plan y el tablero:** `python documentacion/analisis/plan_sprints.py` desde la raíz del proyecto. El script **tacha** los elementos Listo en `documentacion/PLAN.md`, actualiza los porcentajes por entrega y regenera el tablero `documentacion/plan_sprints.html`. **Nunca editar `documentacion/PLAN.md` a mano.** Comprueba que quedó tachado.
3. Agregar una línea al índice `documentacion/avance/README.md` (fecha, ID, sprint, veredicto de QA con rondas, resultado del Angel Fixer, estado, enlace al reporte). En el merge de un elemento normal, el veredicto de QA dice "Pendiente (cierre S{NN})"; en el cierre del sprint se actualiza esa misma línea (veredicto y estado) y se agrega una línea `CIERRE-S{NN}` con el enlace a su reporte.
4. **Grafo (si hay `graphify`):** el grafo del código se actualiza **después** del squash (commit aparte `chore(graph): ...`), así que el reporte del elemento no lo cita; el reporte del cierre del sprint dice con qué grafos se midió la deriva o "deriva no medida (sin grafos)". Los grafos no son requisito del Listo.
5. Guardar en engram (el orquestador, con `mem_save`; project de `CONTEXTO.md`, topic_key `<project>/avance/<ID>`) el resultado y los hallazgos no obvios.
6. **CI sin remoto:** si `git remote` no lista ninguno, el reporte marca **"CI no ejecutado (sin remoto)"** y enumera como **verificación pendiente** lo que solo cubre el CI (semgrep sin vía local, hadolint, trivy, construcción de la imagen, pruebas de despliegue). Al cerrar una entrega, esa lista exige correr las pruebas localmente con Docker (ver "Cierre de entrega" en `devskills:ciclo-historia`).

## Commands

```bash
python documentacion/analisis/plan_sprints.py
rg -n "~~<ID>" documentacion/PLAN.md     # comprobar que quedó tachado (o la herramienta Grep)
```

## Resources

- **Plantilla del elemento**: [assets/plantilla_reporte.md](assets/plantilla_reporte.md)
- **Plantilla del cierre de sprint**: [assets/plantilla_cierre_sprint.md](assets/plantilla_cierre_sprint.md)
