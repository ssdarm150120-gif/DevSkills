---
name: gga
description: >
  Gentleman Guardian Angel: revisión adversarial de seguridad. Lanza en paralelo dos subagentes auditores
  ciegos e independientes, sintetiza sus hallazgos en un reporte único con triage por severidad y entrega
  los confirmados a `devskills:angel-fixer` para su remediación quirúrgica. Trigger: "gga", "gentleman guardian
  angel", "security scan", "revisar seguridad", "escanear vulnerabilidades", "buscar inyecciones",
  "auditoría de seguridad".
license: Apache-2.0
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- El usuario dice "gga" o cualquier frase de arriba.
- Antes de desplegar a producción.
- Cuando el código toca consultas a la base, entrada del usuario, autenticación o archivos.
- Después de agregar endpoints, webhooks o flujos de autenticación.
- Cuando se construyen dinámicamente consultas SQL, comandos o rutas.

## Critical Patterns

### Patrón 0: alcance (ANTES de lanzar auditores)
1. Si el usuario indica un objetivo (archivo, módulo, endpoint), se usa ese.
2. Si no, se escanea **todo el proyecto**: `codigo/` (`.py`, `.html`, `.js`, `.sql`) y `despliegue/`.
3. Leer `devskills:proyecto-contexto` y `documentacion/CONTEXTO.md` para conocer el stack (bases, autenticación, frameworks, integraciones).
4. Armar la descripción del objetivo: lista de archivos + resumen del stack → va en LOS DOS prompts.

**Nunca lanzar auditores sin alcance definido.** Si es ambiguo, se pregunta una vez.

### Patrón 1: auditoría ciega en paralelo
- Lanzar **DOS** subagentes con la herramienta Agent, **en el mismo mensaje** (paralelo, nunca en secuencia).
- Cada auditor recibe **el mismo objetivo** y trabaja **de forma independiente**; ninguno sabe del otro.
- Ambos reciben los mismos criterios de seguridad.
- **El orquestador NUNCA audita código él mismo**: solo coordina.
- Los auditores son de solo lectura: no editan, no ejecutan en el repositorio nada que escriba archivos.

### Patrón 2: clasificación
```
CRÍTICO → explotable con poco esfuerzo, impacto directo (fuga de datos, RCE, saltarse la autenticación)
ALTO    → explotable en condiciones realistas (inyección SQL, XSS almacenado, path traversal)
MEDIO   → requiere condiciones específicas pero realistas (XSS reflejado, sesión débil, CSRF)
BAJO    → defensa en profundidad, endurecimiento, malas prácticas
INFO    → teórico: requiere condiciones artificiales o imposibles en este código
```
Regla: "¿Un atacante puede explotarlo contra un usuario real de esta aplicación?" Sí, fácil → CRÍTICO; sí, con esfuerzo → ALTO; sí, en condiciones específicas → MEDIO; solo con acceso interno o físico → BAJO; solo en laboratorio → INFO. Los INFO se reportan pero NO se corrigen ni disparan re-auditoría.

### Patrón 3: síntesis del veredicto (la hace el orquestador cuando AMBOS terminaron)
```
Confirmado    → lo encontraron LOS DOS            → alta confianza, se corrige
Sospecha A    → solo el auditor A                 → triage, probablemente real
Sospecha B    → solo el auditor B                 → triage, probablemente real
Contradicción → los auditores NO coinciden         → decisión manual
```
En seguridad, una sospecha se trata **como real hasta demostrar lo contrario**.

### Patrón 4: corregir y re-auditar
1. Presentar la tabla del veredicto.
2. PREGUNTAR (skill `devskills:preguntar-al-po`): "¿Mando los hallazgos confirmados al Angel Fixer?"
3. Si sí → lanzar `devskills:angel-fixer` (modo remediación) con la lista confirmada, como delegación SEPARADA.
4. Al terminar → relanzar LOS DOS auditores en paralelo (ronda 2).
5. Tras 2 iteraciones de fixes, si quedan problemas → presentarlos y PREGUNTAR si se sigue.
6. Si los dos auditores regresan limpios → AUDITORÍA: APROBADA ✅

### Patrón 5: convergencia
- **Ronda 1:** se presenta el veredicto y se pregunta antes de corregir.
- **Ronda 2+:** se re-audita solo si quedan CRÍTICOS o ALTOS confirmados. MEDIOS/BAJOS confirmados tras la ronda 1 se corrigen con el Angel Fixer sin re-auditar (en proyectos DevSkills, por la política de cero deuda, se corrigen siempre). INFO: nunca.

## Criterios de revisión (van en LOS DOS prompts)
```
PRIORIDAD 1 — Inyección SQL: consultas con concatenación o f-strings con entrada del usuario; raw() sin parámetros.
PRIORIDAD 2 — Inyección de comandos: subprocess, os.system, os.popen con entrada controlable; shell=True con contenido dinámico.
PRIORIDAD 3 — Credenciales en el código: contraseñas, llaves, tokens, cadenas de conexión; archivos .env versionados.
PRIORIDAD 4 — Autenticación y autorización: endpoints sin control; JWT sin verificar firma; hash débil; tokens de sesión con poca entropía; permisos solo en la vista.
PRIORIDAD 5 — XSS: entrada sin escapar en plantillas; innerHTML/document.write con datos dinámicos; |safe o mark_safe sin justificación.
PRIORIDAD 6 — Path traversal: rutas construidas con entrada del usuario sin normalizar y sin verificar prefijo.
PRIORIDAD 7 — CSRF: endpoints que cambian estado sin token; cookies sin SameSite.
PRIORIDAD 8 — IDOR: IDs del usuario sin verificar propiedad o rol.
PRIORIDAD 9 — Exposición de datos sensibles: datos personales o credenciales en logs o eventos; errores verbosos; HTTP sin TLS.
PRIORIDAD 10 — Dependencias vulnerables: requirements con CVE conocidos.
```

## Prompt del auditor (idéntico para A y B)
```
Eres un auditor de seguridad. Tu ÚNICO trabajo es encontrar vulnerabilidades. Eres de solo lectura:
no editas archivos ni ejecutas en el repositorio nada que escriba.

## Objetivo
{lista de archivos + descripción del stack}

## Criterios de revisión
{pega completos los criterios de arriba}

## Formato de respuesta
Solo una lista estructurada de hallazgos, en español de México. Sin elogios ni aprobaciones.
Cada hallazgo:
- Severidad: CRÍTICO | ALTO | MEDIO | BAJO | INFO
- Archivo: ruta (línea N)
- Vulnerabilidad: tipo
- Evidencia: el fragmento exacto vulnerable
- Escenario de ataque: una oración
- Corrección recomendada: una línea (intención, no código)
Si no encuentras nada: VEREDICTO: LIMPIO — sin vulnerabilidades.
Sé exhaustivo y adversarial. Asume que toda entrada del usuario llega a toda consulta.
```

## Formato de salida
```markdown
## Auditoría GGA — {objetivo}
### Ronda {N} — Veredicto
| Hallazgo | Auditor A | Auditor B | Severidad | Estado |
|----------|-----------|-----------|-----------|--------|
| Inyección SQL en <archivo>:95 | ✅ | ✅ | CRÍTICO | Confirmado |
**Confirmados:** … **Sospechas:** … **INFO:** …
### AUDITORÍA: ESCALADA ⚠️ / APROBADA ✅
```

## Reglas que bloquean (OBLIGATORIAS)
1. **NO** declarar `AUDITORÍA: APROBADA` hasta que los dos auditores regresen LIMPIO o la ronda 2 confirme 0 CRÍTICOS + 0 ALTOS.
2. **NO** hacer `git commit` ni `git push` después de los fixes hasta que termine la re-auditoría.
3. **NO** decir "listo" hasta que la auditoría llegue a APROBADA o ESCALADA.
4. **Esperar SIEMPRE** a los dos auditores antes de sintetizar.
5. Las sospechas de seguridad se tratan como reales.
6. El Angel Fixer es una delegación SEPARADA: nunca se usa un auditor como corrector.
7. Si aparece un CRÍTICO, se avisa al usuario de inmediato (y por Telegram si el canal está activo) con lenguaje claro sobre el riesgo.
