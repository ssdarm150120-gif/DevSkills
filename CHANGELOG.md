# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado semántico.

## [Sin publicar]

### Lanzador: reiniciar un servicio ya no deja una ventana muerta
- **Defecto:** en Windows, `apagar` mataba lo que escucha en los puertos pero el envoltorio `servicios.py _ejecutar` de la consola sobrevivía esperando el Enter, así que cada reinicio (Apagar + Levantar y el paso `reiniciar-servicio` de Aplicar cambios) dejaba una terminal con logs viejos.
- **Arreglo:** `lanzar` registra el pid del envoltorio en `servicios/pids/<id>.pid` (ahora también en Windows) y `apagar` lo cierra con su árbol (`taskkill /T /F`; `killpg` en macOS y Linux) tras verificar su línea de comandos (`servicios.py` + `_ejecutar`), para no matar un pid reciclado ni un proceso ajeno.
- **Apagado intencional:** `apagar` deja un marcador `<id>.apagado`; si el envoltorio sobrevive, cierra la ventana sin esperar Enter. Una caída real conserva la pausa para leer el error. El envoltorio se lanza con `python.exe` aunque el panel use `pythonw.exe`, y la pausa tolera la falta de consola. Sin cambios para `docker-compose` ni para el resto de los tipos.
- Pruebas en `motor/servicios/pruebas/test_servicios.py` (clase `Envoltorio`, con fakes); documentación en `docs/motor.md`.

### Panel: Aplicar cambios (recompilar el front y reiniciar los servicios con un clic)
- Nuevo apartado **Aplicar cambios** en cada proyecto: instala lo que cambió, recompila el front y reinicia los servicios, sin abrir terminales. El panel **propone la receta** a partir de lo que ve (carpetas con `package.json` y script `build`, `requirements.txt` junto al venv de un servicio `python-modulo`, servicios a reiniciar) y el usuario la aprueba una vez; queda en `proyectos.json` bajo `aplicar` y se edita o se quita después.
- **Pasos tipados de lista blanca**, nunca comandos libres ni shell: `npm-install` (`npm ci` con lock, si no `npm install`), `npm-script` (el script debe existir en `package.json`), `pip-requisitos` y `reiniciar-servicio` (con el lanzador: apagar, levantar y esperar la salud). Carpetas relativas validadas con `ruta_segura`, tiempo límite por paso (en Windows un tiempo agotado mata el árbol de procesos) y `npm`/`npm.cmd` resuelto sin shell.
- **Solo lo necesario:** una huella por paso de la última aplicación correcta en `~/.devskills/panel/estado/aplicar.json` (lock y `package.json`, requisitos y una firma barata del árbol de fuentes con `git ls-files` o un recorrido podado). Más **Forzar todo** y el aviso «Hay cambios sin aplicar: frontend, backend» para cuando una sesión termina de editar.
- **Segundo plano con progreso paso a paso** (pendiente, en curso, ✅, ❌, omitido con su razón, salida limpia y recortada); se detiene en el primer fallo, candado por proyecto, botón **Abrir** al final y respeta `--simular`. La confirmación es un modal de la página, nunca `confirm()`.
- **Chat del panel:** «aplica los cambios del <proyecto>», «actualiza el <proyecto>» o «recompila <proyecto>» las resuelve el panel (sin orquestador ni tokens) con una tarjeta con la receta y el botón Ejecutar; el resto de las frases sigue al orquestador.
- Endpoints: `GET /api/proyecto/aplicar`, `POST /api/proyecto/aplicar/receta`, `POST /api/proyecto/aplicar/ejecutar` y `GET /api/chat/intencion`. Pruebas en `motor/panel/pruebas/test_panel_aplicar.py`; documentación en `docs/motor.md`. Limitación: el panel no puede reiniciar la terminal de Claude Code (el `PATH` se hereda al arrancar).

### Panel: Aplicar y git en una sola sección
- **Aplicar cambios** y **Pendientes de git** ya no son dos secciones separadas: forman **Aplicar y subir cambios**, con un resumen común arriba («Hay cambios sin aplicar: backend · 3 archivos sin commit · rama X») y los dos pasos lado a lado (1 · Aplicar, 2 · Commit y push); en marcos angostos se apilan, sin scroll horizontal.
- Se refrescan entre sí: tras un commit o un push exitoso se recarga Aplicar y, al terminar de aplicar, se recarga git. Solo cambia la interfaz (`motor/panel/index.html`, `crearCambios`); los endpoints y las pruebas no cambian.

### Panel: pendientes de git por proyecto (Commit y Push)
- Nuevo apartado **Pendientes de git** en cada proyecto: rama, upstream y adelante/atrás, archivos sin commit, stashes y ramas locales con commits fuera de `origin/<rama por omisión>` (se compara contra el remoto, no contra el `main` local). `GET /api/proyecto/git?id=…[&actualizar=1]`; el `git fetch` solo corre bajo petición y con tiempo límite.
- **Commit** (`POST /api/proyecto/git/commit`): mensaje propuesto por plantilla (sin IA, editable) y validado como conventional commits; archivos elegidos con casillas y aceptados solo si están en la salida actual de `git status --porcelain` (sin `..` ni rutas absolutas, tras `--`, sin shell); gitleaks siempre antes, y si no está disponible o hay hallazgos no se commitea.
- **Push** (`POST /api/proyecto/git/push`), con confirmación en un modal de la página: solo la rama actual, `-u origin` si no tiene upstream, jamás `--force`; bloqueado en `main`/`master` y en la rama por omisión del remoto (409). Verifica la cuenta contra `repositorio.cuenta` según el helper de credenciales (con Git Credential Manager no manda la cuenta activa de `gh`; sin usuario determinable solo advierte; con el helper de gh exige login) y nunca cambia de cuenta en silencio. Respeta `--simular`.
- Pruebas en `motor/panel/pruebas/test_panel_git.py`; documentación en `docs/motor.md`.

### Motor portable: enganche a Claude Code y hooks de Graphify por plugin
- **Hooks de Graphify en el plugin** (`hooks/hooks.json`): `SessionStart` → `sesion_inicio.py` y `PreToolUse` `Bash|Grep` → `hook_guard.py search`, `Read|Glob` → `hook_guard.py read`. Ya no se pegan en `settings.json` con rutas absolutas. El `command` es un fragmento POSIX con comandos internos del shell que prueba `python3`/`python` (en Windows `python`/`py`), hace `exec` y sale con 0 si no hay Python; sin `graphify-out/` ni siquiera lanza Python, y `GRAPHIFY_SESION=0` / `GRAPHIFY_GUARDIA=0` los desactivan. Decisión documentada en `docs/motor.md`.
- **`devskills motor enganchar [--quitar] [--si] [--envolver "<cmd>"] [--hooks] [--limpiar-hooks]`** (`motor/comun/enganchar.py`): escribe la `statusLine` de límites en el `settings.json` de usuario (`CLAUDE_CONFIG_DIR` o `~/.claude`) con la ruta de la copia instalada y el Python de ESE equipo; mezcla sin perder claves, muestra el diff, pide confirmación (`--si` sin terminal), respalda en `settings.json.bak-<fecha>`, es idempotente, no pisa una status line ajena (`--envolver` la conserva) y `--quitar` solo quita lo suyo. Detecta los hooks viejos de Graphify pegados a mano y los quita cuando el plugin está habilitado (`--limpiar-hooks` fuerza); sin plugin, `--hooks` los escribe en forma sin shell (`command` + `args`).
- **Portabilidad del motor:** el panel y el orquestador respetan `CLAUDE_CONFIG_DIR` (transcripts, `.claude.json`, agentes y skills); las carpetas de detección de proyectos se configuran en el registro (`raices_deteccion` se suma siempre; `"usar_raices_defecto": false` apaga `~/Documents/Proyectos` y `~/Desktop`) y la plantilla lo documenta.
- Documentación: `docs/motor.md` (secuencia de punta a punta, enganche, migración desde la configuración vieja, portabilidad), `docs/instalacion.md`, `motor/graphify/README.md`. Pruebas: `motor/comun/pruebas/test_enganchar.py` (incluye los comandos de `hooks.json` ejecutados con bash) y `spec/integration/motor_spec.sh`.

### Motor gráfico: panel de control local, lanzador de servicios y orquestador opcional
- **Nueva carpeta `motor/`** con el panel de control local (solo biblioteca estándar de Python, escucha únicamente en `127.0.0.1`, token por sesión y verificación de Host/Origin), el lanzador de servicios multiplataforma, la integración con Graphify (`hook_guard.py`, `sesion_inicio.py`, `revisar_grafo.py`, plantilla `.graphifyignore`), la status line de límites del plan y el orquestador **opcional** (API local con `claude-agent-sdk` en su propio venv).
- **El estado vive fuera del repositorio**, en `DEVSKILLS_DATOS` o `~/.devskills`: registro `proyectos.json`, preferencias, estado y token del panel, historial, propuestas y token del orquestador, logs y pids. (No se llama `DEVSKILLS_HOME` porque el CLI ya usa esa variable para la carga útil.)
- **Lanzador `motor/servicios/servicios.py`** (equivale al `servicios.ps1` original): `listar`, `levantar`, `apagar` y `--simular`, con la misma lista blanca de tipos (`dotnet`, `npm`, `django-devskills`, `python-modulo`, `docker-compose`) y las mismas validaciones (patrones de script de npm, módulo, argumentos y variables de entorno; carpetas relativas sin `..` ni rutas absolutas). Windows: consola nueva por servicio; macOS y Linux: proceso en segundo plano con log y pid en el directorio de datos. Apagado por puerto (`netstat`, `lsof` o `ss`, sin `psutil`) y `docker compose stop`; el arranque de `django-devskills` ya no depende de `django.ps1`.
- **CLI:** `devskills panel [iniciar|apagar|estado] [--puerto N] [--no-abrir]`, `devskills servicios <levantar|apagar|listar> [objetivo] [--simular]`, `devskills orquestador [instalar|iniciar|apagar|estado]`, `devskills motor iniciar` y `devskills motor migrar --desde <carpeta> [--forzar]` (copia los datos de una instalación previa sin sobrescribir ni tocar el origen); `devskills doctor` y la ayuda actualizados. `install.sh` e `install.ps1` instalan `motor/`.
- **Graphify:** el hook de `PreToolUse` se entrega en Python (`hook_guard.py`) y no en bash: en Windows un hook de bash lanza un `bash.exe` por cada llamada a herramienta y, con agentes en paralelo, la capa MSYS de Git Bash falla con `add_item ... errno 1`.
- **CI:** nuevo job `Motor` en Ubuntu, macOS y Windows (pruebas de rutas, migración, lanzador, panel, Graphify y orquestador con pytest; las que requieren el SDK opcional se saltan solas) y pruebas ShellSpec de los subcomandos (`spec/integration/motor_spec.sh`). `.gitleaks.toml` permite solo los secretos falsos de las pruebas del orquestador.
- Documentación nueva en `docs/motor.md` y `motor/README.md`.

### Escalera del mínimo en `implementar-historia`
- Inspirada en [Ponytail](https://github.com/DietrichGebert/ponytail) (MIT): con la prueba en rojo, el desarrollador recorre seis peldaños (¿hace falta?, ¿ya existe en el proyecto?, ¿biblioteca estándar?, ¿framework?, ¿dependencia instalada?, ¿cabe en una línea?) y se detiene en el primero que resuelva; solo entonces escribe el mínimo. No recorta validación, errores, permisos, seguridad, accesibilidad ni la arquitectura.
- Renglón nuevo "Sin sobrediseño" en las lecciones aprendidas. Objetivo: menos código generado y menos rondas con el Angel Fixer, que es donde se va el gasto de caché en los ciclos multiagente.

### Enrutamiento de modelo y esfuerzo (opcional, local)
- Basado en el *Model Routing Playbook*: esfuerzo antes que modelo, por omisión un escalón abajo del modelo más caro, reglas simples por rol y riesgo, verificación con código y un solo reintento escalado, y cada fallo vuelto regla.
- **Archivo local por proyecto** `.devskills/enrutamiento.json` (`activo`, `version`, `tabla` rol → `modelo`/`esfuerzo`, `escalamiento` y `actualizado`); `.devskills/` ya está en el `.gitignore` de la plantilla. Sin el archivo o con `"activo": false`, nada cambia.
- **Orquestador y `ciclo-historia` (sección 6, fuente de las reglas):** al lanzar cada subagente con la herramienta Agent, el orquestador pasa `model` y `effort` según el rol y el tipo de ciclo; él no se enruta ni cambia de modelo (rompe la caché). Ante una falla detectada por el código (lista mínima en rojo, lista congelada sin resolver, reporte incompleto, script fallido), un reintento escalado (primero esfuerzo, luego modelo); registro en `.devskills/enrutamiento-fallos.md` y en "Para engram"; en la pasada documental y en el cierre del sprint, ajuste de la tabla como decisión del orquestador. `dev-a`, `dev-b` y `qa` pasan el mismo `model` y `effort` a sus subagentes.
- **CLI:** `devskills enrutamiento [estado|activar|desactivar|evaluar] [ruta] [--forzar]`; `evaluar` revisa pruebas y su comando, CI, tipos y lint y Gherkin, y da "recomendado", "parcial" o "no recomendado"; `devskills doctor` muestra el estado dentro de un proyecto. Pruebas en `spec/integration/enrutamiento_spec.sh`.
- Plantilla de `CONTEXTO.md` con la sección "Enrutamiento de modelos"; documentación nueva en `docs/enrutamiento.md`; README, `docs/metodologia.md` y `docs/agentes.md` actualizados.

### Grafo de conocimiento con Graphify (opcional)
- **Dos grafos versionados por proyecto** con [Graphify](https://github.com/Graphify-Labs/graphify) 0.9.x: **lo que es** (`graphify update codigo`, AST sin LLM, `codigo/graphify-out/`) y **el deber ser** (`graphify update documentacion`, encabezados de SRS, DISEÑO, PLAN, CONTEXTO y evaluación de alternativas, también sin LLM, `documentacion/graphify-out/`). La **pasada semántica** del deber ser (`graphify extract documentacion --backend ...`) usa un LLM y por omisión no se genera: el orquestador se la pregunta al Product Owner la primera vez (Ollama local gratis, claude-cli con la suscripción, o API key) y queda registrada en `CONTEXTO.md`.
- **En el ciclo** (`ciclo-historia`, `orquestador`, `pasada-documental`, `registrar-avance`): el grafo del código se actualiza tras cada squash a `main` en un commit aparte `chore(graph): ...`; el del deber ser en cada pasada documental; al abrir el cierre del sprint, el orquestador genera el reporte de **deriva** y QA confirma cada candidato (`validar-historia`): lo confirmado entra a la lista congelada como `OBS-SNN-n` (falta código, falta diseño o decisión de negocio). Plantilla del cierre con la sección de deriva.
- **Ahorro de tokens:** `proyecto-contexto`, `implementar-historia`, `validar-historia`, `angel-fixer`, el orquestador y los agentes dev-a, dev-b, qa, angel-fixer, verificador y analista-arquitecto consultan el grafo (`graphify query`, `explain`, `path`, `affected`, `GRAPH_REPORT.md`) antes de leer archivos en masa, y después solo los archivos citados.
- **Nuevo `documentacion/analisis/deriva_grafos.py`** (biblioteca estándar, pruebas en `spec/integration/deriva_grafos_spec.sh`): compara los dos `graph.json` y escribe un Markdown con lo que el diseño dice y el código no tiene, lo que el código tiene sin estar en el diseño y las correspondencias débiles; sale con 3 y un mensaje claro si falta un grafo.
- **Plantillas:** `.graphifyignore` en la raíz (secretos, entornos, datos, migraciones, `despliegue/` y lo que no es deber ser en `documentacion/`; en Graphify 0.9 `.graphifyrc` no excluye), `.gitignore` que versiona solo `graph.json` y `GRAPH_REPORT.md` de cada `graphify-out/`, `.gitattributes` con `merge=graphify` para los `graph.json`, `codigo/.dockerignore` sin `graphify-out/`, y la sección "Grafo de conocimiento (Graphify)" en `CONTEXTO.md` y en el `AGENTS.md` del proyecto.
- **CLI:** `devskills init` deja configurado el merge driver local (`merge.graphify.driver = graphify merge-driver %O %A %B`) para que dos ramas que regeneraron el grafo no choquen; `devskills doctor` avisa si falta Graphify (`uv tool install graphifyy`) sin hacerlo obligatorio y, dentro de un proyecto, si falta el merge driver. No se usa `graphify hook install` (regenera tras cada commit y ensucia los puntos de control).
- **Seguridad:** el grafo nunca contiene credenciales ni datos; gitleaks escanea los grafos versionados antes de cada commit que los incluya.
- Documentación nueva en `docs/graphify.md`; README, `docs/metodologia.md`, `docs/generadores.md`, `docs/instalacion.md` y `docs/skills.md` actualizados.

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
- **CI, gitleaks:** `.gitleaks.toml` usa `[allowlist]` (forma singular, válida desde gitleaks 8.21 hasta 8.30) en lugar de `[[allowlists]]` (8.25 o posterior), que la imagen fijada `v8.21.2` ignoraba y marcaba como secretos los valores falsos de las pruebas del orquestador.
- **Orquestador, guardián de permisos:** `decidir` trata la barra invertida como separador en cualquier sistema, niega todo componente `..` y, fuera de Windows, las letras de unidad, las rutas UNC y las raíces con barra invertida (en POSIX eran rutas relativas y pasaban la comprobación de contención). Pruebas de las variantes (`..\x`, `C:/x`, `\\server\share`, `a/..\b`) simulando POSIX y Windows, sin depender del sistema del host.
- **Plantilla de código:** `pytest` se limita a `<9.2` en `requirements-dev.txt`: pytest 9.2.0 quitó `FixtureManager._arg2fixturedefs` y rompe `pytest-bdd` 8.1.0 y 9.0.0 (verificado con ambos); se sube el tope cuando haya un `pytest-bdd` compatible.
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
