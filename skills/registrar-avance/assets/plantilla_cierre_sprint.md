# CIERRE-S{NN} · Cierre de calidad del sprint {NN}

| Campo | Valor |
|-------|-------|
| Sprint | S{NN} ({fecha inicio} a {fecha fin}) |
| Entrega | {número}: {nombre} (¿la cierra este sprint? sí / no) |
| Alcance del diff | `inicio-s{NN}..{commit de main}` ({N} archivos, {+N/-N} líneas) |
| Rama del cierre | `cierre-s{NN}` |
| Commit del cierre en main | {hash del squash} |
| Fecha | {AAAA-MM-DD} |

## 1. Elementos del sprint
| ID | Ciclo | Estado antes del cierre | Veredicto del QA de cierre | Estado final | Reporte |
|----|-------|-------------------------|----------------------------|--------------|---------|
| {HU-xx} | Normal | 🔍 En validación | APROBADA / RECHAZADA (DEF-S{NN}-n) | ✅ Listo / ⛔ Bloqueado | [HU-xx](HU-xx.md) |
| {EN-xx} | Excepción ({motivo}) | ✅ Listo | Solo regresión: sin hallazgos / DEF-S{NN}-n | ✅ Listo | [EN-xx](EN-xx.md) |

**Elementos que no entraron al cierre** (seguían En proceso o Bloqueado): {Ninguno / ID, motivo y decisión del Product Owner}

## 2. QA de cierre
{Bloque de salida de la skill validar-historia en modo cierre de sprint, tal cual: escenarios de todas las historias, regresiones entre historias, RNF, mutaciones (10 a 15, con la regla que atacó cada una), ataques y veredicto por elemento}

**Entradas recibidas de las verificaciones ligeras:** {Ninguna / lista con su resultado}

**Deriva entre el deber ser y lo que es:** {[DERIVA-S{NN}](DERIVA-S{NN}.md), nivel estructural o semántico: candidatos confirmados (OBS-S{NN}-n, con su causa: falta código, falta diseño o decisión de negocio) y descartados con su motivo / deriva no medida (sin grafos)}

## 3. Lista congelada y rondas
| ID | Elemento | Severidad | Dueño | Ronda en que se corrigió | Estado |
|----|----------|-----------|-------|--------------------------|--------|
| DEF-S{NN}-1 | {HU-xx} | Alta | Dev A | 1 | Corregido |

| Ronda | Origen | Hallazgos | Resultado |
|-------|--------|-----------|-----------|
| 1 | QA de cierre | {IDs} | {corregido / pendiente} |
| Verificación final | Verificador | {IDs} | {Aprobado / pendientes} |

## 4. Verificación final
{Bloque de salida del verificador (modo final con lista congelada), tal cual; "No aplica: el QA de cierre aprobó sin hallazgos" si no hubo correcciones}

## 5. Decisiones y trabajo derivado (sin deuda técnica)
**Decisiones del Product Owner:** {…}

**Decisiones del orquestador:** {…}

**Trabajo que pertenece a otros elementos del plan (no es deuda):**
- **{ID}:** {…}

**CI:** {ejecutado (enlace o número de corrida) / **CI no ejecutado (sin remoto)**}

**Verificación pendiente (solo la cubre el CI o Docker):** {Ninguna / semgrep, hadolint, trivy, imagen, pruebas de despliegue}

## 6. Preguntas abiertas para el Product Owner
- {Ninguna / lista}
