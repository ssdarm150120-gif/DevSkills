---
name: redactar-srs
description: >
  Construye el SRS del proyecto (ISO/IEC/IEEE 29148) paso a paso y en orden estricto: problema de negocio
  con línea base medible, alcance, requisitos RF/RNF, pendientes P-nn, casos de uso (Anexo A), historias
  con Gherkin en español (Anexo B) y matriz de trazabilidad (Anexo C).
  Trigger: "redacta el SRS", "escribe los requisitos", "siguiente paso del SRS", "agrega historias al SRS",
  "casos de uso", "línea base de requisitos".
license: MIT
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- Después del descubrimiento (`devskills:iniciar-proyecto`), para llenar `documentacion/SRS.md` con el Product Owner.
- Cuando hay que agregar un módulo, un requisito, un caso de uso o una historia al SRS.
- Lo ejecuta el agente `devskills:analista-arquitecto`. Para subir de versión un SRS que ya tiene línea base, usa además `devskills:pasada-documental`.

## Critical Patterns

### 1. Orden estricto (regla del Product Owner)
**No se empieza el paso N+1 sin cerrar el paso N. No se salta nada.** Todo se lleva dentro del propio SRS: los artefactos nuevos son secciones del mismo documento y lo que falta definir es un `P-nn` de la sección 6.

| Paso | Sección del SRS | Se cierra cuando |
|------|-----------------|------------------|
| 1 | 1. Introducción: propósito, **1.1.1 problema de negocio**, metas medibles, línea base, alcance, definiciones | El Product Owner reconoce el problema con sus palabras y cada meta tiene indicador, línea base y valor meta |
| 2 | 2. Descripción general: perspectiva, funciones, clases de usuarios, entorno, **R-nn**, **S-nn**, stack (fijo) | Cada rol tiene responsabilidades, cada restricción o supuesto tiene su ID y los **modos y estados del sistema** (2.8) están descritos o dicen "un solo modo" |
| 3 | 3. Requisitos funcionales por módulo (`RF-XXX-nn`, prioridad A/M/B) | Cada función de 2.2 tiene requisitos verificables y cada requisito (RF y RNF) tiene sus **atributos** (3.0: fuente, justificación, método de verificación y estado) |
| 4 | 4. RNF (`RNF-nn` con categoría) y 5. Interfaces externas | Cada RNF es medible y tiene su verificación técnica en `documentacion/analisis/trazabilidad.json`, y el **cumplimiento normativo** (4.1) dice qué normas aplican, cuáles no y por qué |
| 5 | 6. Pendientes: cerrar todos los `P-nn` que bloquean | **Línea base de requisitos** declarada (sube la versión mayor) |
| 6 | Anexo A: A.1 actores → A.2 diagrama → A.3 catálogo de casos de uso | Cada RF del MVP está en la columna "Requisitos" de algún CU |
| 7 | Anexo B: B.0 convenciones y las historias, **un módulo a la vez** en el orden del Anexo A | El Product Owner valida cada módulo antes de pasar al siguiente |
| 8 | Anexo C: `trazabilidad.py --escribir` | 100 % de los RF del MVP con CU **y** HU; 0 huérfanas; 0 referencias inválidas |

Antes de pasar de fase, cierra cada pendiente abierto que la afecte. Si validar un módulo cambia requisitos, se sube la versión y se corrigen RF, CU y HU en la misma pasada.

### 2. Problema de negocio y línea base medible (paso 1)
- Escribe **la necesidad real**, no la solución: qué pasa hoy, cuándo duele, a quién. Marca qué confirmó el negocio y en qué versión.
- Cada meta va en la tabla "Metas medibles del sistema": indicador, línea base, meta. Si un indicador no se registra hoy, la línea base dice "No se registra" y la meta, cómo se medirá desde el primer día.
- **Línea base medida:** se mide con datos reales en **solo lectura** y **solo con la autorización expresa del usuario** (sistema, consultas y periodo); nunca se lee `.env` ni `.env.*` para obtener credenciales: las da el usuario por una variable de entorno o un archivo que él indique. Sin autorización queda un `P-nn`. Los scripts y consultas quedan en `documentacion/analisis/` y se citan en 1.4. Anota fuente, población y periodo, y escribe las **limitaciones de la medición** (qué dato falta, qué no se pudo calcular, qué no confirman los datos). Si los datos contradicen lo que dice el negocio, se registra un `P-nn`: no se acomoda la medición.
- Nunca copies datos personales ni datos reales del negocio a los ejemplos, a las pruebas ni a los prototipos.

### 3. Convenciones de IDs (no se renumeran, no se reutilizan)
| Elemento | Formato | Dónde |
|----------|---------|-------|
| Restricción | `R-nn` | 2.5 |
| Supuesto, dependencia o riesgo aceptado | `S-nn` (el riesgo lleva su mitigación y la versión) | 2.6 |
| Requisito funcional | `RF-XXX-nn`, con prefijo por módulo | 3.x |
| Requisito no funcional | `RNF-nn` + categoría | 4 |
| Pendiente o pregunta | `P-nn` + tema, pregunta, estado | 6 |
| Actor | `AC-nn` + tipo | A.1 |
| Caso de uso | `CU-nn` + actor principal, secundarios, «include»/«extend», requisitos | A.3 |
| Historia | `HU-nn` | Anexo B |

- Lo nuevo toma el siguiente número libre, aunque quede fuera de orden en la tabla.
- **Nada se borra.** Lo que sale del alcance se marca `**Retirado en X.Y**` (prioridad "Retirado en X.Y" en un RF; "(Retirada en X.Y)" en el título de una HU) y conserva su texto anterior. Ningún elemento vigente puede referenciar uno retirado: `trazabilidad.py` lo reporta.
- Un requisito fuera del MVP a propósito lleva prioridad "Fase 2" o se lista en `fase2` de `trazabilidad.json`.
- Un cambio dentro de un requisito se anota en su texto: `**Versión X.Y:** ...`.

### 4. Preguntas y decisiones
- Lo que no está claro **no se inventa**: se registra como `P-nn` y se pregunta con `devskills:preguntar-al-po` (decisiones numeradas con opción recomendada). Se espera la respuesta.
- Al resolver un `P-nn`, la respuesta queda en su columna Estado y se propaga a RF, CU y HU en la misma versión.
- En el historial se distingue siempre quién decidió: **Decisiones del Product Owner** (negocio) y **Decisiones del orquestador** (técnicas o derivadas de una revisión; quedan a validar por el Product Owner). Nunca presentes una decisión tuya como del Product Owner.

### 5. Historias (Anexo B)
- Formato: `#### HU-nn Título`, la frase **Como** [rol] **quiero** [acción] **para** [beneficio], y la línea
  `- **Prioridad:** A · **Trazabilidad:** CU-nn · RF-XXX-nn, RNF-nn` (los scripts leen esa línea tal cual).
- Criterios en **Gherkin en español** dentro de un bloque `gherkin`: `Característica`, `Escenario`, `Dado`, `Cuando`, `Entonces`, `Y`. Cada escenario se convierte en una prueba automatizada y QA lo copia **tal cual**: escríbelo concreto, con datos ficticios, y sin ambigüedad.
- Un escenario por regla y por camino de error: permiso denegado, dato inválido, sistema externo caído, concurrencia (dos personas a la vez) cuando aplique.
- **Definición de Listo:** la historia tiene trazabilidad a un RF, criterios verificables y ningún pendiente abierto que la afecte.
- Lo agregado a un módulo ya validado se marca **para validar** en la tabla de B.0 hasta que el Product Owner lo valide.
- Si al estimar una historia supera 13 puntos, se parte en dos historias con su propia trazabilidad (`devskills:planear-entregas`).

### 6. Cierre de cada paso
1. Actualiza el encabezado (Versión, Fecha, Estado) y agrega la fila al historial, la más reciente arriba.
2. Regenera el Anexo C cuando existan los Anexos A y B, y corrige hasta que no haya faltantes.
3. Regenera el plan si cambiaron historias, y los Word.
4. Commit `docs:` separado del código (ver `devskills:pasada-documental`).

## Commands

```bash
python documentacion/analisis/trazabilidad.py                       # solo diagnóstico
python documentacion/analisis/trazabilidad.py _tmp.md --escribir    # regenera el Anexo C del SRS
python documentacion/analisis/plan_sprints.py                       # regenera PLAN.md y el tablero
"$PYDOC" documentacion/analisis/md_a_word.py --solo SRS               # regenera el Word del SRS
```

## Resources

- **Plantilla**: `${CLAUDE_PLUGIN_ROOT}/plantillas/documentacion/SRS.md` (ya copiada al proyecto como `documentacion/SRS.md`).
- **Verificación de RNF y fase 2**: `documentacion/analisis/trazabilidad.json`.
