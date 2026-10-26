# Equipo de agentes de {{NOMBRE_PROYECTO}}

Proyecto construido con **DevSkills**. El equipo implementa el plan de `documentacion/PLAN.md`: **1 analista-arquitecto, 2 desarrolladores, 1 QA** (comportamiento), **el Angel Fixer** (código) y un **verificador**, coordinados por la sesión principal (el orquestador) con la skill `devskills:ciclo-historia`.

> Los agentes y las skills los aporta el plugin DevSkills: no hay carpeta `.claude/` en el repositorio. Abre Claude Code **desde la raíz de este repositorio** con el plugin instalado. Lo propio del proyecto está en `documentacion/CONTEXTO.md`.

## Estructura del repositorio

| Carpeta | Contenido |
|---------|-----------|
| `documentacion/` | SRS, diseño, plan, contexto, tablero de sprints, `analisis/` (generadores y mediciones), `avance/` (reportes), `presentacion/`, `sesiones/`, `ui/` y `word/` |
| `codigo/` | El monolito Django. Todas las herramientas (pytest, ruff, mypy, lint-imports, bandit) se ejecutan desde aquí |
| Raíz | Solo `.github/`, `AGENTS.md`, `CLAUDE.md` (importa `AGENTS.md`; Claude Code lee `CLAUDE.md`), `.gitignore`, `.gitattributes`, `.venv/`, `.devskills/` (borradores locales, ignorada por git), `.pgdata/` (dev) y `.pgdata_pruebas/` (pytest), que **tienen** que estar en la raíz para funcionar |

Ningún archivo nuevo va en la raíz: lo que se lee va a `documentacion/` y lo que se ejecuta va a `codigo/`.

## Jerarquía

```
Sesión principal (orquestador) ── /devskills:ciclo <ID | SNN>
├── analista-arquitecto ..... SRS (ISO/IEC/IEEE 29148), DISEÑO (IEEE 1016), PLAN, Anexo C, pasadas documentales
├── dev-a ................... Dev A: dominio y datos (núcleo, identidad, módulos de datos, integraciones de entrada)
│   ├── dev-dominio ............... dominio, máquinas de estado, casos de uso (TDD)
│   ├── dev-integraciones ......... adaptadores, outbox, Celery, migraciones
│   └── dev-interfaz .............. pantallas de sus módulos
├── dev-b ................... Dev B: interfaz, experiencia y servicios
│   ├── dev-interfaz .............. Django + HTMX, accesibilidad, modo claro y oscuro
│   ├── dev-servicios ............. servicios internos separados
│   ├── dev-dominio
│   └── dev-integraciones
├── qa ...................... QA del comportamiento: cierre de sprint (o por historia en la excepción)
│   ├── qa-bdd .................... Gherkin del SRS → pytest-bdd
│   └── qa-no-funcional ........... RNF con la verificación técnica del Anexo C
├── angel-fixer ............. Revisión del código: seguridad, arquitectura, buenas prácticas y deuda
└── verificador ............. Verificación ligera (por historia) o final (cierre de sprint y excepción)
```

La profundidad máxima es de 2 niveles debajo de la sesión principal, dentro del límite de Claude Code (3 por defecto).

## Ciclo de calidad (híbrido)

El **Angel Fixer** revisa el **código** (seguridad, arquitectura y límites de módulos, buenas prácticas, deuda); **QA** revisa el **comportamiento** (Gherkin de punta a punta, regresiones entre historias, RNF del Anexo C, mutaciones y ataques). Sin traslape.

```
Por elemento (ciclo normal):
Desarrollo (TDD) ──► punto de control ──► Revisión por historia del Angel Fixer ──► lista congelada ──► correcciones (máx. 3 rondas) ──► verificación ligera ──► merge: En validación

Al cerrar el sprint:
QA completo sobre el diff del sprint ──► lista congelada ──► correcciones ──► verificación final ──► todos Listo + reportes + plan regenerado
```

- **Revisión por historia:** código más la lista mínima (build sin advertencias, pruebas en verde, gitleaks limpio, cada escenario Gherkin con su prueba); sin mutaciones ni ataques. La verificación ligera la hace un agente distinto (el verificador).
- **Excepción, ciclo completo por historia:** los elementos de **seguridad** (riesgos `S-nn`, autenticación, autorización, archivos, secretos), de **plataforma o núcleo compartido** (ver `documentacion/CONTEXTO.md`) o que el orquestador marque como **críticos** pasan por QA y Angel Fixer en paralelo, correcciones y verificación final **antes** del merge.
- **Listo** = Angel Fixer sin hallazgos abiertos de ninguna severidad **y** QA APROBADA sin observaciones abiertas (en el cierre del sprint, o por historia en la excepción) (**política de cero deuda**). Lo que encuentra el QA de cierre se corrige en el mismo sprint. Después de 3 rondas sin aprobar, se pregunta al Product Owner.

## Reglas del repositorio

- **Idioma:** el del campo Idioma de `documentacion/CONTEXTO.md` ({{IDIOMA_DESCRIPCION}}); prevalece sobre el estilo personal del usuario (su `CLAUDE.md` global). Commits en inglés, Conventional Commits, sin atribución de IA.
- **Git:** cada elemento en su rama `hu-xx` o `en-xx` (y el cierre de cada sprint en `cierre-sNN`, con base en la etiqueta local `inicio-sNN`); commit de punto de control antes de cada revisión; solo el orquestador ejecuta comandos de git que cambian el árbol o la historia; nadie reconstruye archivos de memoria (`git restore`); cierre con `merge --squash` a `main`.
- **Docker (opcional):** se desarrolla y se prueba sin él. Si se usa: prefijo `{{SLUG}}` para el stack principal y `{{SLUG}}-<agente>` para cada agente; puertos del host solo entre `{{PUERTO_BASE}}` y el `{{PUERTO_BASE}}` + 49; nunca los puertos reservados (`{{PUERTOS_RESERVADOS}}`); nunca `down -v` ni `prune` sobre el stack principal.
- **Herramientas locales = CI:** semgrep (misma versión que el CI) y las demás herramientas de revisión se corren igual que en `.github/workflows/ci.yml`; con código 0 y sin hallazgos. **Un CI en rojo es deuda:** después de cada push autorizado se revisa con `gh run list` y se corrige antes de seguir.
- **Lista congelada:** tras 3 rondas sin aprobar y con la autorización del Product Owner, la ronda extra resuelve y verifica solo la lista pendiente y las regresiones, sin búsquedas nuevas; un hallazgo nuevo se anota con el ID del elemento que lo absorbe.
- **Preguntar al Product Owner:** lo de negocio (alcance, reglas, prioridades, cerrar con pendientes) lo decide el Product Owner, con decisiones numeradas y una recomendada; nadie lo asume. Después de 3 rondas sin aprobar, también se le pregunta.
- **Hacia afuera:** nada de `git push`, `gh` de escritura, `docker push` ni borrar ramas con `-D` sin la confirmación explícita del usuario; los subagentes no los ejecutan nunca.
- **Secretos:** nadie lee ni escribe `.env` ni `.env.*`.
- **Memoria:** engram con `project` = `{{SLUG}}`. Los subagentes no tienen `mem_save`: terminan su reporte con la sección **Para engram** y el orquestador la guarda (o la deja en `.devskills/engram_pendiente.md`).
- **Instalaciones:** ningún agente instala software (pip fuera del venv, `curl ... | sh`, `winget`, `brew`, `apt`, `npm -g`, WSL); si falta una herramienta, se detiene y el orquestador se lo pregunta al usuario.

## Dónde queda el avance

- `documentacion/avance/estado_backlog.json`: estado oficial de cada ID (lo escribe `devskills:registrar-avance`).
- `documentacion/avance/S{NN}/{ID}.md`: reporte de cada elemento (Angel Fixer + QA + decisiones; parcial y `En validación` hasta el cierre del sprint en el ciclo normal).
- `documentacion/avance/S{NN}/CIERRE-S{NN}.md`: reporte del QA de cierre de cada sprint.
- `documentacion/avance/README.md`: índice de reportes.
- `documentacion/PLAN.md` y `documentacion/plan_sprints.html`: se regeneran con `python documentacion/analisis/plan_sprints.py` y **tachan** lo terminado.
