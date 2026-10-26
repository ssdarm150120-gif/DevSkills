# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado semántico.

## [Sin publicar]

### Ciclo de calidad híbrido (decisión del Product Owner del método)
- **Roles sin traslape:** el Angel Fixer revisa el código (seguridad, arquitectura y límites de módulos, buenas prácticas, deuda); QA revisa el comportamiento (Gherkin de punta a punta, regresiones entre historias, RNF del Anexo C, mutaciones dirigidas al riesgo y ataques).
- **Ciclo normal por elemento** (`ciclo-historia`): desarrollo con TDD → punto de control → **revisión por historia** del Angel Fixer (código más lista mínima: build sin advertencias, pruebas en verde, gitleaks limpio, cada escenario Gherkin con su prueba; sin mutaciones, ataques ni fixes) → lista congelada → correcciones (máximo 3 rondas) → **verificación ligera** del `verificador` → merge con el elemento **En validación**, no Listo.
- **Cierre del sprint** (`/devskills:ciclo cierre-SNN`, rama `cierre-sNN`, base en la etiqueta local `inicio-sNN`): QA completo sobre todo el diff del sprint (todos los Gherkin, regresiones entre historias, RNF, 10 a 15 mutaciones dirigidas y ataques cuando aplica) → lista congelada → correcciones → verificación final independiente → todos los elementos a **Listo**, reportes completos, `CIERRE-S{NN}.md` y plan regenerado. Lo que encuentra se corrige en el mismo sprint.
- **Excepción con ciclo completo por historia:** seguridad (riesgos `S-nn`, autenticación, autorización, archivos, secretos), plataforma o núcleo compartido (nueva sección de `CONTEXTO.md`) o críticos por decisión del orquestador: QA y Angel Fixer en paralelo, correcciones y verificación final antes del merge.
- `validar-historia` con modo cierre de sprint (el normal) y modo por historia (excepción); `angel-fixer` con modo revisión por historia, y su evaluación enfocada en el código; `verificador` con modos ligero y final; `registrar-avance` con reporte parcial En validación, plantilla `plantilla_cierre_sprint.md` y regla de Listo por ciclo.
- El desarrollador escribe las pruebas de aceptación (Gherkin del SRS copiado tal cual a pytest-bdd) para que la revisión por historia pueda exigir un escenario con su prueba; QA las revisa y refuerza (`implementar-historia`, `dev-a`, `dev-b`, `qa-bdd`).
- Actualizados el orquestador, `proyecto-contexto` (Definición de Terminado), `planear-entregas`, `guarda-todo`, `recuperar-corte`, las plantillas `AGENTS.md`, `CONTEXTO.md`, `SRS.md`, `PLAN.md` y del avance, la leyenda de `plan_sprints.py`, el README y `docs/`.

### Seguridad
- `docs/instalacion.md`: el uso no interactivo ya no recomienda `Bash(git *)`, `Bash(python *)` ni `Bash(docker *)`; trae patrones mínimos, `--disallowedTools` explícito (push, reset, clean, `branch -D`, `gh` de escritura, `docker push`/`prune`) y la recomendación de correr en una carpeta o máquina aislada.
- gitleaks va **antes** de cualquier commit de cierre y de cualquier push (`guarda-todo`, `ciclo-historia`); ninguna acción hacia afuera (push, `gh` de escritura, merges de Dependabot, issue de lecciones) sin la confirmación explícita del usuario. La nota de lecciones para DevSkills es un borrador local sin datos del proyecto.
- Hook de plugin `PreToolUse` (`hooks/vetar_acciones_externas.sh`) que bloquea a los subagentes `git push`, `git branch -D`, `gh` de escritura y `docker push`/`login`/`prune`; vetos explícitos también en el bloque "Cuidado del repositorio" de todos los agentes.
- `devskills update` muestra los commits y el `diff --stat` que traería y pide confirmación (`--si` sin terminal); `devskills init` rechaza nombres y autores que romperían TOML, JSON, YAML o `.env`.

### Corregido
- `install.sh`: la limpieza de obsoletos nunca corría (la carga útil, y con ella el manifiesto, se borraba antes de leerlo). Rutas con `&`, `#` y `'` se instalan literales; se rechazan saltos de línea, `$`, comillas dobles y acento grave. Solo se borran entradas del manifiesto con aspecto de DevSkills. Lo mismo en `install.ps1` y los desinstaladores.
- Punto de control unificado (`codigo`, `.github` y `documentacion/avance`) en `ciclo-historia`, `recuperar-corte` y `guarda-todo`.
- Prefijo de Docker `<slug>-<agente>`; `down -v` y `prune` prohibidos sobre el stack principal. `qa-no-funcional` limita la prueba de `INSERT` con usuario de solo lectura a la base de pruebas; la línea base con datos reales requiere autorización del usuario y nunca lee `.env`.
- El esqueleto ya no anuncia una bitácora que no existe (capacidad, rol `auditor` y textos marcados como ejemplo) y documenta paso a paso cómo reemplazar los roles de ejemplo.
- Una sola Definición de Terminado (`proyecto-contexto`); el SRS y el PLAN la referencian. Los comandos de Word usan el Python del entorno de la documentación (`$PYDOC`). El README ya no contradice el orden descubrimiento → `init`.

### Ronda de correcciones 4
- Idioma: la plantilla raíz trae `CLAUDE.md` (Claude Code no lee `AGENTS.md`) con `@AGENTS.md` y la regla de que el idioma de `CONTEXTO.md`, que sale de `--idioma`, prevalece sobre el `CLAUDE.md` global del usuario. Los agentes y el orquestador lo dicen.
- El borrador de lecciones ya no está en `documentacion/avance`: vive en `.devskills/` (ignorada por git), igual que `engram_pendiente.md`.
- Los subagentes no llaman `mem_save` (sus herramientas MCP no llegan): terminan con la sección **Para engram** y el orquestador la guarda, o la deja en `.devskills/engram_pendiente.md`.
- Ningún agente instala software; el hook veta a los subagentes `curl | sh`, `get-pip`, `winget`/`brew`/`apt install`, `npm -g` y pip fuera del venv; `devskills doctor` explica cómo instalar semgrep por sistema.
- Sin remoto, el reporte marca "CI no ejecutado (sin remoto)" y al cerrar cada entrega se exigen localmente con Docker imagen, hadolint, trivy y despliegue.
- `plan_sprints.py` y el tablero muestran el porcentaje con un decimal por debajo de 10 % (`0.9 %`, no `0 %`).
- Nuevo `devskills sync-scripts [ruta]` para llevar a un proyecto ya creado los scripts corregidos de `documentacion/analisis/`.
- `docs/instalacion.md` explica que la duración que muestra Claude Code incluye el tiempo con el equipo suspendido.

### Ronda de correcciones 2
- `scripts/gitleaks_archivos.py` distingue "herramienta no disponible" (código 2, con instrucciones) de "hay hallazgos" (código 1); busca el binario también en las rutas de winget y detecta un demonio de Docker apagado.
- `prod.py` rechaza `SECURE_SSL_REDIRECT` apagado y HSTS menor a un año en un servidor real (solo advierte en `localhost`); `APP_EXIGIR_TLS_DATOS` exige `sslmode` y `rediss://`; `roles_bd` valida la clave de Redis; tope de 128 caracteres de contraseña antes de Argon2.
- Idioma y zona horaria por defecto neutrales (`es`, `UTC`) en `configuracion/localizacion.py`, sobrescribibles con `APP_IDIOMA` y `APP_ZONA_HORARIA`; `devskills init --idioma --zona` los fija.
- `bin/devskills` sin `eval`; `uninstall.sh` e `install.sh` limpian carpetas vacías solo hasta la raíz de cada skill; imágenes de gitleaks y semgrep fijadas por digest; `.gitignore` de la plantilla excluye llaves y credenciales; `exportar_sesion.py` enmascara secretos obvios.
- Método: los agentes de `gga` y `judgment-day` no hacen commit (lo hace el orquestador), orden de cierre explícito, verificación final condicionada a que hubo correcciones, regla "herramientas locales = CI" entre los puntos de control, `main` sin commits `wip:`; Dev A y Dev B sin sesgo de dominio.

### Docker es opcional
- Se desarrolla y se prueba sin Docker: PostgreSQL embebido, Celery en modo local sin Redis en desarrollo y pruebas, gitleaks nativo, semgrep nativo (macOS/Linux) o por WSL/Docker (Windows) y siempre obligatorio en el CI. `devskills doctor` lo trata como opcional y dice qué se pierde. Las pruebas de Compose y del certificado se omiten sin Docker y no se pueden omitir en el CI (`REQUIERE_DOCKER=1`).
- El CI del plugin genera un proyecto con `devskills init` y corre ruff, mypy, lint-imports y el pytest completo sin Docker (`SIN_DOCKER=1`).

### Cadena de suministro
- `actions/checkout` y `actions/setup-python` fijados por SHA y `@anthropic-ai/claude-code` con versión en el CI del plugin; `package-lock.json` de la presentación versionado (`npm ci`, `sharp` y `pptxgenjs` actualizados, 0 vulnerabilidades); mermaid-cli, python-docx y pillow con versión exacta; `pip-tools` y lock con hashes documentados en la plantilla.

### Plantillas
- SRS: atributos por requisito (fuente, justificación, verificación, estado), modos y estados del sistema y cumplimiento normativo. DISEÑO: introducción con propósito, alcance, glosario, referencias, partes interesadas y preocupaciones, vista de contexto y algoritmos.

### Lecciones nuevas
- `gitleaks:allow` en la misma línea y nunca excluir carpetas; semgrep con montaje `:ro` y "corregir o suprimir con motivo, nunca excluir"; marca de visto por ID con doble comprobación; enmascarar solo valores largos; lentitud de `sh.exe` en equipos Windows de dominio.

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
