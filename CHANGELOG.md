# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado semántico.

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
