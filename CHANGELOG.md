# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado semántico.

## [Sin publicar]

### Agregado
- `docs/instalacion.md`: "Uso no interactivo" (`claude -p`, `stream-json`, permisos acotados, presupuesto, respuestas del Product Owner en el prompt, `--resume` tras un corte, costo observado, `jq` para engram) y "GitHub CLI (`gh`) y el CI".
- Lecciones del CRM en las skills y agentes: semgrep local con la imagen y la versión del CI, CI revisado con `gh` tras cada push, orden con Dependabot, y regla permanente de anotar lecciones para DevSkills al cerrar cada elemento.
- Prueba ShellSpec de `devskills doctor` con mermaid-cli en `~/.devskills/doc` y prueba estática del `!reset` de Compose.

### Cambiado
- `ciclo` es solo un atajo de `ciclo-historia`, que queda como única fuente de las reglas.
- Flujos de CI con `ubuntu-24.04` en lugar de `ubuntu-latest` (plantilla y CI del plugin).
- `docker-compose.pruebas.yml`: `build: !reset null` en cada servicio y no en el ancla (Compose 2.38 pierde el `!reset` por la fusión `<<:`).
- `docs/generadores.md`: `puppeteer.json` con barras invertidas escapadas para Windows.

## [1.0.0] - 2026-10-13

Primera versión: la metodología, el equipo de agentes y el stack fijo con que se construyó un sistema real, generalizados para cualquier proyecto nuevo.

### Agregado
- **Plugin de Claude Code** (`.claude-plugin/plugin.json` y `marketplace.json`) instalable con `/plugin marketplace add` y `/plugin install devskills@devskills-local`.
- **13 agentes:** `orquestador`, `analista-arquitecto`, `dev-a`, `dev-b`, `dev-dominio`, `dev-integraciones`, `dev-interfaz`, `dev-servicios`, `qa`, `qa-bdd`, `qa-no-funcional`, `angel-fixer` y `verificador`, con las reglas comunes de idioma, git, Docker, secretos, memoria y cero deuda.
- **22 skills:** arranque (`nuevo-proyecto`, `iniciar-proyecto`), documentación (`redactar-srs`, `redactar-diseno`, `planear-entregas`, `pasada-documental`, `evaluacion-alternativas`, `prompts-figma`, `generar-presentacion`), ciclo (`ciclo`, `ciclo-historia`, `implementar-historia`, `validar-historia`, `registrar-avance`, `angel-fixer`), calidad (`gga`, `judgment-day`) y sesión (`orquestador`, `proyecto-contexto`, `preguntar-al-po`, `guarda-todo`, `recuperar-corte`).
- **Plantillas de documentación:** SRS (ISO/IEC/IEEE 29148), DISEÑO (IEEE 1016), PLAN, CONTEXTO, evaluación de alternativas, avance, prompts de Figma Make y datos de la presentación.
- **Generadores:** plan y tablero de sprints, Anexo C de trazabilidad, documentos Word con Mermaid, presentación `.pptx` y transcripción de la sesión.
- **Esqueleto del stack fijo** en `plantillas/codigo`: Django modular hexagonal con configuración por entorno, núcleo (actor, puertos, reloj, outbox, permisos), identidad, herramientas, despliegue con Docker Compose y nginx TLS, y CI.
- **CLI `devskills`** (`init`, `doctor`, `version`, `update`, `help`) en Bash portable.
- **Instaladores** `install.sh` / `install.ps1` y desinstaladores con manifiesto, idempotentes y sin pisar archivos ajenos.
- **Pruebas** del instalador y del CLI con ShellSpec; CI en GitHub Actions para macOS, Linux y Windows.
- Utilidades `scripts/gitleaks_archivos.py` y `scripts/validar_plugin.py`.
- Documentación en `docs/` y plantillas de issues y pull requests.
