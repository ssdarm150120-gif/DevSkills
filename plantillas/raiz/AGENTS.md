# Equipo de agentes de {{NOMBRE_PROYECTO}}

Proyecto construido con **DevSkills**. El equipo implementa el plan de `documentacion/PLAN.md`: **1 analista-arquitecto, 2 desarrolladores, 1 QA, el Angel Fixer** como evaluador y un **verificador** final, coordinados por la sesión principal (el orquestador) con la skill `devskills:ciclo-historia`.

> Los agentes y las skills los aporta el plugin DevSkills: no hay carpeta `.claude/` en el repositorio. Abre Claude Code **desde la raíz de este repositorio** con el plugin instalado. Lo propio del proyecto está en `documentacion/CONTEXTO.md`.

## Estructura del repositorio

| Carpeta | Contenido |
|---------|-----------|
| `documentacion/` | SRS, diseño, plan, contexto, tablero de sprints, `analisis/` (generadores y mediciones), `avance/` (reportes), `presentacion/`, `sesiones/`, `ui/` y `word/` |
| `codigo/` | El monolito Django. Todas las herramientas (pytest, ruff, mypy, lint-imports, bandit) se ejecutan desde aquí |
| Raíz | Solo `.github/`, `AGENTS.md`, `.gitignore`, `.gitattributes`, `.venv/`, `.pgdata/` (dev) y `.pgdata_pruebas/` (pytest), que **tienen** que estar en la raíz para funcionar |

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
├── qa ...................... QA: veredicto por historia
│   ├── qa-bdd .................... Gherkin del SRS → pytest-bdd
│   └── qa-no-funcional ........... RNF con la verificación técnica del Anexo C
├── angel-fixer ............. Evaluación: cumplimiento de la historia, buenas prácticas y seguridad
└── verificador ............. Verificación final de una sola pasada o de una lista congelada
```

La profundidad máxima es de 2 niveles debajo de la sesión principal, dentro del límite de Claude Code (3 por defecto).

## Ciclo de calidad por elemento del backlog

```
Desarrollo ──► punto de control ──► QA ──► Angel Fixer ──► ¿Listo? ──sí──► Verificación final (solo si hubo correcciones) ──► Reporte + tachado en el plan
     ▲                                                        │
     └──────────────── no (máximo 3 rondas) ◄─────────────────┘ ──► después de 3 rondas: pregunta al Product Owner
```

**Listo** = QA APROBADA sin observaciones abiertas **y** Angel Fixer sin hallazgos abiertos de ninguna severidad (**política de cero deuda**). El Angel Fixer corrige solo CRÍTICOS y ALTOS; los MEDIOS y BAJOS vuelven al desarrollador.

## Reglas del repositorio

- **Idioma:** español de México con tuteo. Commits en inglés, Conventional Commits, sin atribución de IA.
- **Git:** cada elemento en su rama `hu-xx` o `en-xx`; commit de punto de control antes de cada revisión; solo el orquestador ejecuta comandos de git que cambian el árbol o la historia; nadie reconstruye archivos de memoria (`git restore`); cierre con `merge --squash` a `main`.
- **Docker (opcional):** se desarrolla y se prueba sin él. Si se usa: prefijo `{{SLUG}}` para el stack principal y `{{SLUG}}-<agente>` para cada agente; puertos del host solo entre `{{PUERTO_BASE}}` y el `{{PUERTO_BASE}}` + 49; nunca los puertos reservados (`{{PUERTOS_RESERVADOS}}`); nunca `down -v` ni `prune` sobre el stack principal.
- **Herramientas locales = CI:** semgrep (misma versión que el CI) y las demás herramientas de revisión se corren igual que en `.github/workflows/ci.yml`; con código 0 y sin hallazgos. **Un CI en rojo es deuda:** después de cada push autorizado se revisa con `gh run list` y se corrige antes de seguir.
- **Lista congelada:** tras 3 rondas sin aprobar y con la autorización del Product Owner, la ronda extra resuelve y verifica solo la lista pendiente y las regresiones, sin búsquedas nuevas; un hallazgo nuevo se anota con el ID del elemento que lo absorbe.
- **Preguntar al Product Owner:** lo de negocio (alcance, reglas, prioridades, cerrar con pendientes) lo decide el Product Owner, con decisiones numeradas y una recomendada; nadie lo asume. Después de 3 rondas sin aprobar, también se le pregunta.
- **Hacia afuera:** nada de `git push`, `gh` de escritura, `docker push` ni borrar ramas con `-D` sin la confirmación explícita del usuario; los subagentes no los ejecutan nunca.
- **Secretos:** nadie lee ni escribe `.env` ni `.env.*`.
- **Memoria:** engram con `project` = `{{SLUG}}`.

## Dónde queda el avance

- `documentacion/avance/estado_backlog.json`: estado oficial de cada ID (lo escribe `devskills:registrar-avance`).
- `documentacion/avance/S{NN}/{ID}.md`: reporte de cada elemento (QA + Angel Fixer + decisiones).
- `documentacion/avance/README.md`: índice de reportes.
- `documentacion/PLAN.md` y `documentacion/plan_sprints.html`: se regeneran con `python documentacion/analisis/plan_sprints.py` y **tachan** lo terminado.
