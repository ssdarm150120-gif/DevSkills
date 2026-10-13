---
name: generar-presentacion
description: >
  Genera la presentación .pptx del proyecto (propuesta para la dirección) a partir de los datos del SRS y
  del PLAN, con el generador de Node documentacion/presentacion/generar_presentacion.js y su archivo
  datos_presentacion.json. Trigger: "genera la presentación", "presentación del proyecto", "pptx de la
  propuesta", "actualiza la presentación", "deck para la dirección".
license: Apache-2.0
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- Cuando hay que presentar el proyecto a la dirección: el SRS tiene el problema, las metas y la línea base (1.1.1), y el PLAN tiene las entregas.
- Cuando cambia el alcance o el plan y la presentación quedó desfasada (se sube `version` y se regenera; no se edita el .pptx a mano).

## Critical Patterns

### 1. De dónde sale cada diapositiva
Todo el contenido vive en `documentacion/presentacion/datos_presentacion.json`. **Nada se inventa:** cada texto y cada cifra sale de los documentos, y lo que no esté ahí se pregunta (`devskills:preguntar-al-po`).

| Diapositiva (`tipo`) | Fuente |
|----------------------|--------|
| `portada`, `cierre` | SRS 1.1 (propósito) y la petición que se hace a la dirección |
| `tarjetas` (el problema), `flujo` (la causa) | SRS 1.1.1, problema de negocio |
| `cifras` (lo que dicen los datos) | SRS 1.1.1, **línea base medida**, con su fuente y periodo |
| `pilares` (la solución), `recorrido`, `beneficios`, `modulos` | SRS 1.2 y 2.2 |
| `grafica` + tarjetas | SRS 1.1.2, contexto para la dirección |
| `reglas` | SRS 2.5 y las reglas de negocio de `documentacion/CONTEXTO.md` |
| `demo` | El recorrido de `documentacion/ui/prompts_figma_make.md` y el enlace de la maqueta |
| `metas` | SRS 1.1.1, tabla "Metas medibles del sistema" (indicador, hoy, meta) |
| `bases` | SRS 2.1 y 2.7 (sobre qué se construye) |
| `plan` | `documentacion/PLAN.md`: el generador lee solo la tabla de entregas con fechas (regenera el plan antes) |
| `metodo` | PLAN P.1 (sprints, equipo, demos, piloto) |
| `necesitamos` | SRS 2.6 (dependencias S-nn) y PLAN P.5 (costos) |

### 2. Reglas del contenido
- Una idea por diapositiva; el título es la conclusión, no el tema.
- Las cifras de "hoy" son **medidas** y llevan su fuente; las metas son compromisos, no resultados. No mezcles poblaciones distintas sin aclararlo.
- Las fechas son estimadas hasta recalibrar la velocidad (después del sprint 3): dilo en la diapositiva del plan.
- `notas` lleva lo que dice quien presenta, en lenguaje de negocio.
- **Sin datos personales ni datos reales sensibles.** La firma usa el rol o el nombre que el Product Owner autorice.
- Español de México con tuteo.
- Los límites por tipo los marca el diseño: 3 tarjetas, 4 cifras, 4 pasos de flujo, 3 pilares, 5 pasos de recorrido, 5 beneficios, 12 módulos, 2 bloques, 4 reglas, 7 pasos de guion, 4 bases, 7 entregas, 4 cifras de método, 5 pendientes. Lo que excede no se dibuja: resume.
- Los íconos son nombres de `react-icons/fi` (por ejemplo `FiCalendar`, `FiUsers`, `FiDatabase`, `FiShield`); un nombre inexistente se dibuja como un círculo.
- Los colores del tema se pueden cambiar con `"colores": {"accent1": "RRGGBB", ...}` en el JSON; el diseño (maestros, tarjetas, tipografía) no se toca.
- Quita del arreglo `diapositivas` las que no apliquen; el orden del arreglo es el orden del deck, y `seccion` agrupa.

### 3. Dependencias (Node, sin instalar nada global)
`documentacion/presentacion/package.json` declara `pptxgenjs`, `react`, `react-dom`, `react-icons` y `sharp`. Se instalan **en esa carpeta**:
```bash
cd documentacion/presentacion
npm install
```
`node_modules/` y `package-lock.json` de esa carpeta no se versionan (deben estar en `.gitignore`). Si prefieres no instalar dentro del proyecto, instala las mismas dependencias en otra carpeta y ejecuta con `NODE_PATH` apuntando a su `node_modules`.

### 4. Generar y verificar
1. Regenera el plan (`python documentacion/analisis/plan_sprints.py`) para que la diapositiva `plan` tenga las fechas vigentes.
2. Llena o actualiza `datos_presentacion.json` (sube `version` si ya se presentó una versión anterior: la anterior queda intacta).
3. Genera. La salida queda junto al generador: `<Proyecto>_Propuesta_v<version>.pptx`.
4. Verifica: el comando termina con `Generado: ...`, el archivo abre, no queda ningún marcador `<...>` sin llenar y ninguna caja de texto se desborda.

## Commands

```bash
cd documentacion/presentacion
npm install                                   # una sola vez
node generar_presentacion.js                  # usa datos_presentacion.json
node generar_presentacion.js otros_datos.json Otra_Salida.pptx
```

## Resources

- **Generador y datos**: `${CLAUDE_PLUGIN_ROOT}/plantillas/documentacion/presentacion/` (`generar_presentacion.js`, `datos_presentacion.json`, `package.json`), ya copiados al proyecto en `documentacion/presentacion/`.
