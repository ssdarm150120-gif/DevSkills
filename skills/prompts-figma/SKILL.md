---
name: prompts-figma
description: >
  Deriva del SRS y del PLAN los prompts para Figma Make del proyecto: Prompt 0 (sistema de diseño,
  navegación por rol y datos ficticios), un prompt por grupo de sprints, la maqueta de venta, y los
  prompts de actualización y de correcciones. Trigger: "prompts de Figma", "Figma Make", "maqueta del
  proyecto", "prototipo navegable", "corrige la maqueta", "actualiza los prompts de la maqueta".
license: Apache-2.0
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- Cuando el SRS tiene las historias y el PLAN las entregas, para escribir `documentacion/ui/prompts_figma_make.md`.
- Cuando una pasada documental cambia pantallas o reglas visibles (prompt de **actualización**).
- Cuando la maqueta generada contradice los requisitos (prompt de **correcciones**).

## Critical Patterns

### 1. Qué es y qué no es
Es **solo la parte visual**: un prototipo navegable con datos ficticios, sin backend. No define requisitos: si al maquetar aparece una regla que no está en el SRS, se registra como `P-nn` y se pregunta; no se resuelve en el prompt.

### 2. Estructura del documento
| Sección | Contenido | Fuente |
|---------|-----------|--------|
| Encabezado | Versión, fecha, versiones de SRS, DISEÑO y PLAN de origen, alcance | — |
| Cómo usarlos | Un solo archivo de Figma Make; Prompt 0 primero; después en orden; la frase para corregir desvíos | — |
| Tabla de prompts | Prompt → sprints → entrega → pantallas | PLAN P.2.2 |
| **Prompt 0** | Qué es el producto, objetivo, roles con selector, sistema de diseño (tipografía, tokens de color, semánticos, contraste AA, estados vacío, de carga y de error), navegación lateral por rol y **datos ficticios** | SRS 1.1.1, 2.2 y 2.3 |
| **Prompt 1..N** | Uno por grupo de sprints de una entrega, con la línea `*Historias: HU-nn, ...*` y las pantallas numeradas | PLAN (entregas y sprints) y Anexo B |
| **Prompt M** (opcional) | Maqueta de venta: todas las pestañas funcionales en memoria, modo claro y oscuro con tokens, roles y recorrido de demo | SRS 1.1.1 (la historia que se cuenta) |
| **Prompt R** (actualización) | Se pega **sobre la maqueta existente** cuando cambia el alcance: cambio de enfoque, datos nuevos, pantallas nuevas, lo que se quita, y las HU que cubre | La versión nueva del SRS |
| **Prompt R2** (correcciones) | Se pega sobre la maqueta actual: lista numerada de lo que contradice el SRS y cómo debe quedar; **no agrega pantallas**; termina con una lista de verificación | Revisión de la maqueta contra el SRS |

### 3. Datos ficticios (Prompt 0)
- [ ] **Nunca datos reales**: ni clientes, ni personas, ni montos, ni identificadores. Los prototipos se comparten y se suben a la nube.
- [ ] Un usuario ficticio por rol del SRS 2.3.
- [ ] Las entidades principales con IDs con prefijo, y **al menos un ejemplo en cada estado** de las máquinas de estado del DISEÑO D.3 (incluidos los estados de error y de excepción).
- [ ] Montos, fechas y cantidades coherentes entre sí (lo que suma debe sumar).
- [ ] Todo prompt posterior repite: "usa SOLO los DATOS FICTICIOS del Prompt 0". Un prompt de actualización declara sus "DATOS NUEVOS" y los suma.
- [ ] Son los mismos datos que usan las pruebas de aceptación (`devskills:qa-bdd`): una sola fuente de datos de prueba.

### 4. Cómo se escribe cada pantalla
- Nombre de la pantalla en mayúsculas y su ruta de navegación; qué muestra, qué acciones tiene y qué cambia en pantalla.
- Cada regla visible sale de una historia: lo que un rol **no** puede hacer también se escribe (botón ausente o deshabilitado con su texto).
- Estados vacío, de carga y de error; responsivo (escritorio, tablet, celular); contraste AA; navegación por teclado.
- Interfaz en español de México; fechas, números y monedas con el formato local.
- Modo claro y oscuro definidos con **tokens** (variables), no con colores sueltos.

### 5. Correcciones: revisar la maqueta contra el SRS
Compara pantalla por pantalla con las historias. Lo típico que se cuela y hay que quitar:
- Datos que no están en los datos ficticios (productos, clientes o montos inventados por la herramienta).
- Acciones que el rol no tiene según el SRS, o funciones fuera del alcance.
- Reglas con el valor equivocado (plazos, horarios, límites).
- Pantallas que mezclan pasos que el SRS separa.

Cada punto del prompt de correcciones cita qué está mal y cómo queda. Al final: "Al final revisa: ..." con lo que no debe aparecer.

### 6. Versionado
- Cada cambio sube la versión del documento y actualiza las versiones de origen del encabezado.
- Los prompts de actualización y de correcciones **se agregan**, no reemplazan a los anteriores: la ruta rápida dice en qué orden pegarlos.
- Regenera el Word con la pasada documental; el commit es `docs:`.
- El diseño de las pantallas reales (`devskills:dev-interfaz`) sigue este documento y la maqueta de Figma.

## Commands

```bash
python documentacion/analisis/md_a_word.py --solo prompts_figma   # Word de los prompts
```

## Resources

- **Plantilla**: `${CLAUDE_PLUGIN_ROOT}/plantillas/documentacion/ui/prompts_figma_make.md` (ya copiada al proyecto en `documentacion/ui/`), con el formato de cada tipo de prompt.
