---
name: validar-historia
description: >
  Validación de QA de una historia (HU) o habilitador (EN) contra sus escenarios Gherkin y los requisitos
  no funcionales del SRS, con veredicto APROBADA / APROBADA CON OBSERVACIONES / RECHAZADA.
  Trigger: cuando QA valida un elemento en estado "En validación" o re-valida tras correcciones.
license: MIT
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
- Desde `codigo/`: `python -m pytest`, `ruff check .`, `ruff format --check .`, `mypy .`, `lint-imports`, `bandit`, `pip-audit`, `python manage.py makemigrations --check --dry-run` y semgrep (siguiente punto).
- **semgrep igual que el CI:** la **misma versión** que fija `.github/workflows/ci.yml` del proyecto (`semgrep==<versión>`; hoy `1.178.0`). Una versión distinta no vale: sus reglas cambian. Vías, de la preferida a la alternativa: (1) **nativo** en macOS y Linux: `pipx run --spec "semgrep==1.178.0" semgrep scan --config p/python --config p/django --error --metrics=off --exclude pruebas --exclude conftest.py .`; (2) en Windows, el mismo comando dentro de **WSL**; (3) **Docker** (opcional), con el montaje en **solo lectura** (`:ro`): `MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/src:ro" -w /src semgrep/semgrep:1.178.0@sha256:32e459968daabe7ab86968184a29109b9564aa00392401156f9788452b42786b semgrep scan --config p/python --config p/django --error --metrics=off --exclude pruebas --exclude conftest.py .` (en Linux o macOS, `-v "$PWD:/src:ro"` y sin `MSYS_NO_PATHCONV`). Desde `codigo/`. Se exige **código de salida 0 y "Findings: 0"**; un hallazgo es un defecto aunque el código local pase. En el CI de GitHub semgrep es **siempre obligatorio**; si la máquina no tiene ninguna de las tres vías, se reporta "semgrep pendiente del CI" y el orquestador lo trata como verificación pendiente (ver `devskills:ciclo-historia`).
- **Un hallazgo de semgrep se corrige o se suprime con motivo; nunca se excluye.** Corregir el código es lo normal. Si de verdad es un falso positivo, se suprime **en esa línea** con `# nosemgrep: <regla>` y una explicación; **no se agregan `--exclude` ni se ignoran carpetas** para que "pase": la lista de exclusiones del CI (`pruebas`, `conftest.py`) no crece. Lo mismo vale para gitleaks: un falso positivo se suprime con `gitleaks:allow` en esa misma línea y el motivo, y nunca se excluye una carpeta o un archivo del escaneo.
- **Lección de `django-no-csrf-token`:** la regla es genérica y solo reconoce `{% csrf_token %}` si el `</form>` está a **10 líneas o menos**. Un formulario largo con el token lejos del cierre da un falso positivo que pone el CI en rojo: se parte el formulario en parciales (`{% include %}`) para que el token quede junto a su `</form>`; no se silencia la regla.
- Pruebas destructivas o de permisos de base de datos (por ejemplo, el `INSERT` con un usuario de solo lectura) **solo contra la base de pruebas**, nunca contra la de desarrollo ni contra datos reales.
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
