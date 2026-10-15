# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado semántico.

## [Sin publicar]

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
