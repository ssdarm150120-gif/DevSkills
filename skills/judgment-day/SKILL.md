---
name: judgment-day
description: >
  Protocolo de revisión adversarial en paralelo: lanza dos jueces ciegos e independientes sobre el mismo
  objetivo, sintetiza sus hallazgos, aplica fixes con un agente separado y vuelve a juzgar hasta que los dos
  aprueben o se escale después de 2 iteraciones. Trigger: "judgment day", "judgment-day", "revisión adversarial",
  "doble revisión", "juzgar", "que lo juzguen".
license: MIT
metadata:
  author: devskills
  version: "1.4"
---

## When to Use

- El usuario pide "judgment day" o una frase equivalente.
- Después de implementaciones importantes, antes de integrarlas a `main`.
- Cuando hace falta una revisión de alta confianza de código, funcionalidad o arquitectura.
- Cuando el costo de un error en producción es mayor que el de dos rondas de revisión.

## Critical Patterns

### Patrón 0: estándares del proyecto (ANTES de lanzar jueces)
1. Identificar el alcance (archivos, funcionalidad, componente).
2. Reunir las reglas que aplican: `devskills:proyecto-contexto`, `documentacion/CONTEXTO.md`, la lista de lecciones de `devskills:implementar-historia` y, si existe, el registro de skills del proyecto (engram `skill-registry` o `.atl/skill-registry.md`).
3. Armar un bloque `## Estándares del proyecto` con esas reglas resumidas e inyectarlo IDÉNTICO en los prompts de los dos jueces y del agente corrector.

### Patrón 1: revisión ciega en paralelo
- Lanzar **DOS** subagentes con la herramienta Agent en el mismo mensaje (paralelo, nunca en secuencia).
- Mismo objetivo, trabajo independiente, ninguno sabe del otro, mismos criterios.
- El orquestador NUNCA revisa él mismo: solo coordina.
- Los jueces son de solo lectura (mutaciones y experimentos, en una copia del scratchpad).

### Patrón 2: síntesis del veredicto (cuando AMBOS terminaron)
```
Confirmado    → lo encontraron LOS DOS      → alta confianza, se corrige
Sospecha A    → solo el juez A              → triage
Sospecha B    → solo el juez B              → triage
Contradicción → no coinciden en lo mismo    → decisión manual
```

### Patrón 3: clasificación de las advertencias
```
ADVERTENCIA (real)     → causa un error, pérdida de datos, hueco de seguridad o comportamiento incorrecto
                         en un escenario realista de producción. Se corrige.
ADVERTENCIA (teórica)  → requiere un escenario artificial o entradas corruptas imposibles con el uso normal.
                         Se reporta como INFO; no se corrige ni dispara otra ronda.
```
Pregunta: "¿Un usuario normal, usando la herramienta como se espera, puede provocarlo?" Sí → real. No → teórica.

### Patrón 4: corregir y volver a juzgar
1. Si hay **CRÍTICOS confirmados o advertencias reales** → delegar en un **agente corrector** (delegación separada).
2. Al terminar → relanzar **los dos jueces en paralelo** (mismo protocolo ciego).
3. **Después de 2 iteraciones de fixes**, si quedan problemas → presentar los hallazgos y PREGUNTAR (skill `devskills:preguntar-al-po`) si se sigue. Sí → otro ciclo. No → JUICIO: ESCALADO.
4. Si los dos jueces regresan limpios → JUICIO: APROBADO ✅

### Patrón 5: umbral de convergencia
- **Ronda 1:** presentar la tabla y PREGUNTAR antes de corregir. Después, re-juzgar con el alcance completo.
- **Ronda 2+:** re-juzgar solo si quedan **CRÍTICOS confirmados**. Advertencias reales confirmadas: se corrigen sin relanzar jueces. Teóricas: INFO. Sugerencias: se corrigen si son triviales.
- **APROBADO después de la ronda 1:** 0 CRÍTICOS confirmados + 0 advertencias reales confirmadas.
- En proyectos DevSkills rige además la **política de cero deuda** del ciclo: lo que el juicio deje como sugerencia confirmada vuelve al desarrollador si toca un elemento del backlog.

## Prompt del juez (idéntico para A y B)
```
Eres un revisor de código adversarial. Tu ÚNICO trabajo es encontrar problemas. Eres de solo lectura.

## Objetivo
{archivos, funcionalidad, arquitectura o componente}

## Estándares del proyecto
{bloque del Patrón 0}

## Criterios de revisión
- Correctitud: ¿hace lo que dice? ¿errores lógicos?
- Casos borde: ¿qué entradas o estados no se manejan?
- Manejo de errores: ¿se capturan, propagan y registran bien?
- Rendimiento: ¿N+1, ciclos ineficientes?
- Seguridad: ¿inyecciones, secretos expuestos, controles de acceso?
- Nombres y convenciones: ¿sigue los patrones del proyecto y los estándares de arriba?

## Formato de respuesta
Solo una lista de hallazgos, en español de México, sin elogios:
- Severidad: CRÍTICO | ADVERTENCIA (real) | ADVERTENCIA (teórica) | SUGERENCIA
- Archivo: ruta (línea N)
- Descripción: qué está mal y por qué importa
- Fix sugerido: una línea (intención, no código)
Si no encuentras nada: VEREDICTO: LIMPIO — sin hallazgos.
Asume que el código tiene errores hasta demostrar lo contrario.
```

## Prompt del agente corrector
```
Eres un agente de fixes quirúrgicos. Aplicas SOLO los problemas confirmados de abajo.
## Problemas confirmados
{tabla de confirmados}
## Estándares del proyecto
{bloque del Patrón 0}
## Instrucciones
- Corrige SOLO lo confirmado; no refactorices ni toques código no señalado.
- Si corriges un patrón en un archivo, busca el MISMO patrón en todos los archivos del cambio y corrígelos todos.
- Respeta las reglas de git del proyecto: no ejecutes comandos que cambien el árbol o la historia.
- Devuelve: archivo:línea — qué se corrigió.
```

## Formato de salida
```markdown
## Judgment Day — {objetivo}
### Ronda {N} — Veredicto
| Hallazgo | Juez A | Juez B | Severidad | Estado |
|----------|--------|--------|-----------|--------|
**Confirmados:** … **Sospechas:** … **Contradicciones:** …
### Fixes aplicados (ronda {N})
### Ronda {N+1} — Nuevo juicio
### JUICIO: APROBADO ✅ / ESCALADO ⚠️
```

## Reglas que bloquean (OBLIGATORIAS)
1. **NO** declarar `JUICIO: APROBADO` hasta que la ronda 1 regrese LIMPIO, o la ronda 2 confirme 0 CRÍTICOS + 0 advertencias reales.
2. **NO** hacer `git commit`, `git push` ni cambios de código después de los fixes hasta que termine el nuevo juicio.
3. **NO** guardar el resumen de sesión ni decir "listo" hasta que cada juicio llegue a APROBADO o ESCALADO.
4. Después de que regresa el corrector, la SIGUIENTE acción es relanzar a los jueces en paralelo.
5. Varios juicios en paralelo son independientes: que uno termine no permite saltarse rondas de otro.

## Autoverificación (antes de cualquier acción terminal)
1. ¿Cada juicio activo está en APROBADO o ESCALADO?
2. ¿Si hubo fixes, corrió la ronda 2?
3. ¿Si la ronda 2 encontró problemas, se le preguntó al usuario y se respetó su respuesta?
Si alguna respuesta es "no", te saltaste un paso: regresa y complétalo.
