# Enrutamiento de modelo y esfuerzo

DevSkills puede elegir el **modelo** y el **esfuerzo** de cada subagente según su rol y el riesgo del trabajo, en lugar de que todos usen el modelo de su frontmatter. Es **opcional, por proyecto y local**: sin el archivo de configuración, o con `"activo": false`, el método funciona exactamente como siempre.

## De dónde sale

Del *Model Routing Playbook* (@donimas, 2026-10-05), en cinco reglas:

1. **Ajustar el esfuerzo antes que el modelo.** Más esfuerzo en el mismo modelo suele bastar y no cambia de familia.
2. **Por omisión, un escalón abajo del modelo más caro;** el caro se reserva para escalar y para lo de más riesgo.
3. **Reglas simples por tipo de tarea y riesgo:** una tabla rol → modelo/esfuerzo, no un clasificador.
4. **Verificar con código** (pruebas, tipos, lint) y, ante una **falla**, escalar **una vez**: primero más esfuerzo, luego un modelo mayor.
5. **Registrar cada fallo y volverlo regla:** los fallos ajustan la tabla.

## Cómo funciona en Claude Code

- **Quién enruta:** la sesión principal, que en DevSkills es el **orquestador**. Al lanzar cada subagente con la herramienta Agent le pasa los parámetros `model` y `effort` que tocan a su rol. Un hook no puede cambiar el modelo por mensaje, así que no hay otra vía.
- **El orquestador no se enruta:** cambiar el modelo de la sesión principal a media sesión rompe la caché de su contexto (se paga todo el contexto otra vez). Se queda con el modelo con que se abrió.
- **Precedencia (documentación oficial de Claude Code, subagentes):** para el modelo, primero el parámetro `model` de la invocación, luego el `model` del frontmatter del agente (`inherit` = el de la sesión principal), luego la variable `CLAUDE_CODE_SUBAGENT_MODEL` y al final el modelo de la sesión principal. Para el esfuerzo, el parámetro `effort` de la invocación gana sobre el campo `effort` del frontmatter. Los valores que usa DevSkills son los alias `haiku`, `sonnet` y `opus`, y los esfuerzos `low`, `medium` y `high`.
- **Lo que lo anula:** `CLAUDE_CODE_EFFORT_LEVEL` gana sobre cualquier esfuerzo; `CLAUDE_CODE_SUBAGENT_MODEL` junto con `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` fuerzan un solo modelo en todos los subagentes, y un mod con un hook `agent.spawn` que fije modelo también reemplaza el parámetro. Antes de Claude Code 2.1.251, `CLAUDE_CODE_SUBAGENT_MODEL` ganaba sobre el parámetro y el frontmatter. Si usas cualquiera de estos, el enrutamiento no tiene efecto.
- **Subagentes de segundo nivel:** `dev-a`, `dev-b` y `qa` lanzan a los suyos (`dev-dominio`, `dev-integraciones`, `dev-interfaz`, `dev-servicios`, `qa-bdd`, `qa-no-funcional`) con el mismo `model` y `effort` que les llegaron: el orquestador los escribe en el prompt ("Enrutamiento: modelo X, esfuerzo Y").

## El archivo `.devskills/enrutamiento.json`

Vive en la raíz del proyecto, dentro de `.devskills/`, que ya está en el `.gitignore` de la plantilla: **nunca entra a un commit** (es una preferencia de costo de cada persona o equipo, no parte del proyecto). Formato exacto, versión 1:

```json
{
  "activo": true,
  "version": 1,
  "tabla": {
    "desarrollo": {"modelo": "sonnet", "esfuerzo": "medium"},
    "desarrollo-excepcion": {"modelo": "sonnet", "esfuerzo": "high"},
    "angel-fixer-revision": {"modelo": "sonnet", "esfuerzo": "medium"},
    "angel-fixer-excepcion": {"modelo": "opus", "esfuerzo": "high"},
    "qa-excepcion": {"modelo": "opus", "esfuerzo": "high"},
    "qa-cierre-sprint": {"modelo": "opus", "esfuerzo": "high"},
    "verificador-ligero": {"modelo": "sonnet", "esfuerzo": "medium"},
    "verificador-final": {"modelo": "sonnet", "esfuerzo": "high"},
    "analista-arquitecto": {"modelo": "opus", "esfuerzo": "medium"},
    "pasada-documental": {"modelo": "haiku", "esfuerzo": "low"},
    "registrar-avance": {"modelo": "haiku", "esfuerzo": "low"},
    "mecanico": {"modelo": "haiku", "esfuerzo": "low"}
  },
  "escalamiento": {"max_reintentos": 1, "orden": ["esfuerzo", "modelo"]},
  "actualizado": "2026-10-27T15:51:48Z"
}
```

| Campo | Tipo | Significado |
|-------|------|-------------|
| `activo` | booleano | `true`: el orquestador pasa `model` y `effort`. `false` (o el archivo no existe o no se puede leer): nadie los pasa y cada agente usa su frontmatter |
| `version` | entero | Versión del formato; hoy `1` |
| `tabla` | objeto | Clave de rol → `{"modelo": "haiku" \| "sonnet" \| "opus", "esfuerzo": "low" \| "medium" \| "high"}`. Una clave que falte = ese rol se lanza sin `model` ni `effort` |
| `escalamiento.max_reintentos` | entero | Reintentos escalados ante una falla; por omisión `1` |
| `escalamiento.orden` | arreglo | Qué se sube primero; por omisión `["esfuerzo", "modelo"]` |
| `actualizado` | texto ISO 8601 UTC | Última vez que se creó, activó, desactivó o ajustó la tabla |

### Roles de la tabla

| Clave | A quién se aplica | Por omisión |
|-------|-------------------|-------------|
| `desarrollo` | `dev-a` / `dev-b` y sus subagentes en el ciclo normal (desarrollo y rondas) | sonnet / medium |
| `desarrollo-excepcion` | Los mismos en un elemento de la excepción (seguridad, plataforma, crítico) | sonnet / high |
| `angel-fixer-revision` | Angel Fixer, revisión por historia | sonnet / medium |
| `angel-fixer-excepcion` | Angel Fixer, evaluación de la excepción y remediación de `gga` | opus / high |
| `qa-excepcion` | QA por historia en la excepción | opus / high |
| `qa-cierre-sprint` | QA de cierre de sprint | opus / high |
| `verificador-ligero` | Verificador, modo ligero | sonnet / medium |
| `verificador-final` | Verificador, modo final | sonnet / high |
| `analista-arquitecto` | Redactar SRS, DISEÑO y PLAN | opus / medium |
| `pasada-documental` | Pasada documental (versiones, Anexo C, Word) | haiku / low |
| `registrar-avance` | Reporte de avance, estado y plan, cuando se delega | haiku / low |
| `mecanico` | Otras tareas mecánicas delegadas | haiku / low |
| — | El orquestador | No se enruta |

`desarrollo-excepcion` no estaba en la lista original del Playbook aplicada a DevSkills: se agregó para que un elemento de la excepción no comparta esfuerzo con el ciclo normal (más riesgo, más esfuerzo, mismo modelo).

## Falla, reintento y registro

Las reglas completas están en la skill `devskills:ciclo-historia`, sección 6. En corto:

- **Qué es una falla** (siempre la detecta el código): un desarrollador entrega con la lista mínima en rojo (build, pruebas, tipos, lint, gitleaks) o no resuelve la lista congelada; un revisor entrega un reporte incompleto (sin lista mínima, sin veredicto o sin evidencia); una tarea mecánica deja un script fallido o un estado que no cuadra. Los hallazgos normales de una revisión **no** son fallas de enrutamiento; un corte por límite de uso tampoco.
- **Reintento:** uno solo, del mismo rol, con la evidencia de la falla y un escalón más: esfuerzo (`low` → `medium` → `high`) y, si ya estaba en `high`, modelo (`haiku` → `sonnet` → `opus`). En el desarrollador el reintento es la ronda siguiente ya escalada (no suma rondas). Después, el rol se queda escalado hasta cerrar el elemento y rigen las rondas de siempre (máximo 3 y la pregunta al Product Owner).
- **Registro:** `.devskills/enrutamiento-fallos.md` (local) y la sección "Para engram":

  ```markdown
  | Fecha | Elemento | Rol | Modelo/esfuerzo | Motivo | Escalado a | Resultado |
  |-------|----------|-----|-----------------|--------|------------|-----------|
  | 2026-10-27T16:02:11Z | HU-12 | desarrollo | sonnet/medium | pruebas en rojo tras la ronda 1 | sonnet/high | resuelto |
  ```

- **Volverlo regla:** en la pasada documental y en el cierre del sprint el orquestador revisa los fallos y propone ajustar la tabla como **decisión del orquestador** (subir un rol que falló dos veces por la misma causa o una vez en la excepción; bajar uno que lleva dos sprints sin fallos y con verificación completa). El ajuste va al `CIERRE-S{NN}.md` y a engram.

## Comandos

```bash
devskills enrutamiento evaluar     # ¿encaja este proyecto? Veredicto: recomendado / parcial / no recomendado
devskills enrutamiento activar     # crea .devskills/enrutamiento.json con la tabla por omisión (o reactiva el existente sin tocarlo)
devskills enrutamiento activar --forzar   # reescribe la tabla por omisión
devskills enrutamiento desactivar  # "activo": false, conserva la tabla
devskills enrutamiento estado      # (por omisión) muestra si está activo y la tabla; también sale en devskills doctor
```

Todos aceptan una ruta al final (`devskills enrutamiento evaluar ../mi-proyecto`); por omisión, la carpeta actual. `activar` exige un proyecto DevSkills (`documentacion/CONTEXTO.md`) y avisa si git no ignora `.devskills/`.

### `evaluar`: cuándo conviene

La cascada solo es segura si el código detecta que el modelo menor falló. `evaluar` revisa:

| Revisión | Cómo la detecta |
|----------|-----------------|
| Pruebas automatizadas | Algún `test_*.py`, `*_test.py`, `*.feature`, `*_spec.sh`, `*.test.ts/js`, `*.spec.ts/js` o `*_test.go` |
| Comando de pruebas | `pytest` (configuración en `pytest.ini`, `pyproject.toml` o `setup.cfg`, en `codigo/` o la raíz), `npm test`, `shellspec`, `make test` o `go test ./...` |
| CI | `.github/workflows/*.yml` o `.gitlab-ci.yml` |
| Tipos y lint | mypy, ruff, import-linter, TypeScript, ESLint o ShellCheck en el CI |
| SRS con Gherkin | Escenarios en `documentacion/SRS.md` |

- **No recomendado:** no hay pruebas. Sin pruebas no hay cascada segura: nada detecta la falla y no hay cuándo escalar.
- **Parcial:** hay pruebas pero falta alguna de las demás; algunos fallos se detectarían tarde (en el QA de cierre).
- **Recomendado:** están todas.

Activarlo cambia costo y calidad, así que es una **decisión del Product Owner**; el orquestador se la presenta con el veredicto y la registra en la sección "Enrutamiento de modelos" de `documentacion/CONTEXTO.md`.
