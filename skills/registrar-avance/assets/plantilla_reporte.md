# {ID} · {Título}

| Campo | Valor |
|-------|-------|
| Sprint | S{NN} ({fecha inicio} a {fecha fin}) |
| Entrega | {número}: {nombre} |
| Responsable | Dev A / Dev B |
| Puntos | {puntos} (si el esfuerzo real fue distinto, dilo y explícalo en la sección 5) |
| Trazabilidad | {CU} · {RF / RNF} · {ADR o sección del DISEÑO} |
| Commit o rama | {hash del squash en main o rama} |
| Estado final | ✅ Listo · 🔄 En proceso · ⛔ Bloqueado |
| Fecha | {AAAA-MM-DD} |

## 1. Qué se implementó
- {Resumen en 3 a 6 puntos, en lenguaje de negocio}
- **Módulos y archivos principales:** {lista}

## 2. Validación de QA
{Bloque de salida de la skill validar-historia, tal cual}

## 3. Evaluación del Angel Fixer
{Bloque de salida del Angel Fixer: cumplimiento de la historia, buenas prácticas y seguridad, con hallazgos y fixes aplicados}

## 4. Rondas de corrección
| Ronda | Origen | Hallazgos | Resultado |
|-------|--------|-----------|-----------|
| 0 | Dev | {si se detuvo antes de escribir código: motivo y cómo se resolvió} | {…} |
| 1 | QA / Angel Fixer | {IDs} | {corregido / pendiente} |
| Verificación final | Verificador | {IDs} | {Aprobado / pendientes} |

## 5. Decisiones y trabajo derivado (sin deuda técnica)
**Decisiones del Product Owner:**
- {…}

**Decisiones del orquestador (validadas por el Product Owner cuando aplica):**
- {…}

**Decisiones del desarrollador (aceptadas por la verificación):**
- {…}

**Lecciones e incidentes de proceso:** {qué pasó y qué regla nueva se agregó, si aplica}

**Hallazgos técnicos no obvios:** {…}

**Esfuerzo real:** {si difiere de lo estimado, para la retrospectiva y la recalibración de la velocidad}

**Trabajo que pertenece a otros elementos del plan (no es deuda):**
- **{ID}:** {…}

**Tareas de personas (no del código):** {…}

**CI:** {ejecutado (enlace o número de corrida) / **CI no ejecutado (sin remoto)**}

**Verificación pendiente (solo la cubre el CI o Docker):** {Ninguna / semgrep, hadolint, trivy, imagen, pruebas de despliegue}

## 6. Preguntas abiertas para el Product Owner
- {Ninguna / lista}
