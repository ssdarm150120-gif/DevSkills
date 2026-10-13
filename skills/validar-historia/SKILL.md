---
name: validar-historia
description: >
  Validación de QA de una historia (HU) o habilitador (EN) contra sus escenarios Gherkin y los requisitos
  no funcionales del SRS, con veredicto APROBADA / APROBADA CON OBSERVACIONES / RECHAZADA.
  Trigger: cuando QA valida un elemento en estado "En validación" o re-valida tras correcciones.
license: Apache-2.0
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- Un elemento del backlog está en `En validación` en `documentacion/avance/estado_backlog.json`.
- Una re-validación después de correcciones (del desarrollador o fixes del Angel Fixer).
- Una ronda con **lista congelada**: se verifica solo esa lista y las regresiones.

## Critical Patterns

### 1. Independencia
QA **no corrige código de producción**. Escribe y mantiene las **pruebas de aceptación** y reporta defectos. Si una prueba falla, el defecto vuelve al desarrollador. QA trabaja sobre el commit de punto de control que le indica el orquestador y nunca ejecuta en el repositorio nada que escriba archivos de `codigo/` (las mutaciones van en una copia del scratchpad).

### 2. Del Gherkin del SRS a pruebas ejecutables
- Copiar los escenarios de la historia (Anexo B) **tal cual** a su `.feature` (convención del proyecto; por defecto en las pruebas del módulo). No se reescriben ni se suavizan.
- Implementar los pasos con **pytest-bdd**, usando datos ficticios y los adaptadores falsos de los sistemas externos. El reloj se controla en la prueba.
- **Cada escenario del SRS debe tener su prueba.** Un escenario sin prueba = historia no validada.
- Si un escenario depende de un módulo que todavía no existe, se prueba hasta el límite de los módulos que sí existen y se reporta qué parte cierra otro elemento (con su ID). Cerrar así requiere la aceptación del Product Owner.

### 3. Requisitos no funcionales
Revisar los RNF que cita la historia y su "verificación técnica" del Anexo C (subagente `devskills:qa-no-funcional`): seguridad (permisos por rol, tokens, firmas de webhooks, datos sensibles, sesiones), rendimiento (umbrales del SRS), accesibilidad y formatos.

### 4. Batería y mutaciones
- Desde `codigo/`: `python -m pytest`, `ruff check .`, `ruff format --check .`, `mypy .`, `lint-imports`, `bandit`, `pip-audit`, `python manage.py makemigrations --check --dry-run`.
- Mutaciones dirigidas **en una copia del scratchpad**: cada regla importante de la historia debe tener una prueba que falle si se rompe. Una mutación que sobrevive es una observación.

### 5. Criterio de veredicto
| Veredicto | Condición |
|-----------|-----------|
| **APROBADA** | Todos los escenarios en verde y los RNF aplicables verificados |
| **APROBADA CON OBSERVACIONES** | Todo en verde; observaciones menores que no violan el SRS. **No cierra la historia** (política de cero deuda): las observaciones vuelven al desarrollador |
| **RECHAZADA** | Un escenario falla, falta su prueba, o se viola un RNF o una regla de negocio |

### 6. Defectos y observaciones
- Defecto: ID (`DEF-<ID>-n`), escenario o RNF afectado, pasos, resultado esperado (del SRS) frente al obtenido, severidad (Crítica, Alta, Media, Baja).
- Observación: ID (`OBS-n`), archivo:línea, qué falta y la corrección esperada.

## Formato de salida (lo consume `devskills:registrar-avance`)

```markdown
## QA — <ID> <título>
**Veredicto:** APROBADA | APROBADA CON OBSERVACIONES | RECHAZADA
| Escenario Gherkin | Prueba | Resultado |
|-------------------|--------|-----------|
| <escenario> | <ruta>.feature:3 | ✅ |
**RNF verificados:** RNF-04 ✅, RNF-19 ✅
**Mutaciones:** N probadas, N detectadas
**Defectos:** DEF-<ID>-1 (Alta) …
**Observaciones:** OBS-1 …
**Evidencia:** salida de pytest y de la batería, resumida
```

## Commands

```bash
# desde codigo/
python -m pytest -k HU_35 --gherkin-terminal-reporter
python -m pytest --cucumberjson=../documentacion/avance/_resultados.json
```
