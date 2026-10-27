# Instalación

DevSkills es una metodología y un stack para construir cualquier sistema, nacida de un proyecto real. Hay dos formas de instalarlo. Las dos traen lo mismo; cambia cómo se llaman los agentes y las skills.

| Forma | Nombres | Cuándo conviene |
|-------|---------|-----------------|
| **Plugin de Claude Code** | `devskills:<nombre>` (por ejemplo `/devskills:ciclo`) | La recomendada: se actualiza y se desactiva desde `/plugin` |
| **Instalador** (`install.sh` o `install.ps1`) | `devskills-<nombre>` (por ejemplo `/devskills-ciclo`) | Si no usas el sistema de plugins o quieres el CLI `devskills` en tu PATH |

Puedes usar las dos a la vez (el plugin para Claude Code y el instalador solo por el CLI); no chocan porque usan nombres distintos.

## Como plugin de Claude Code

Dentro de una sesión de Claude Code:

```text
/plugin marketplace add ssdarm150120-gif/DevSkills
/plugin install devskills@devskills-local
```

O desde un clon local:

```text
/plugin marketplace add C:\ruta\a\DevSkills
/plugin install devskills@devskills-local
```

Lo mismo desde la terminal:

```bash
claude plugin marketplace add ssdarm150120-gif/DevSkills
claude plugin install devskills@devskills-local
claude plugin details devskills        # inventario de agentes y skills
```

Para probarlo sin instalar: `claude --plugin-dir /ruta/a/DevSkills`.

## Manual (macOS, Linux)

```bash
git clone https://github.com/ssdarm150120-gif/DevSkills.git
cd DevSkills
./install.sh
```

## Windows con Git Bash

```bash
git clone https://github.com/ssdarm150120-gif/DevSkills.git
cd DevSkills
bash install.sh
```

Si `devskills` no se encuentra después, agrega a tu `~/.bashrc`:

```bash
export PATH="$HOME/bin:$PATH"
```

## Windows con PowerShell

```powershell
git clone https://github.com/ssdarm150120-gif/DevSkills.git
cd DevSkills
powershell -ExecutionPolicy Bypass -File install.ps1
```

`install.ps1` instala además un lanzador `devskills.cmd`. El CLI está escrito en Bash, así que necesita **Git Bash** en el PATH (viene con Git para Windows).

## Qué hace el instalador

| Qué | Dónde |
|-----|-------|
| Agentes | `~/.claude/agents/devskills-<nombre>.md` |
| Skills | `~/.claude/skills/devskills-<nombre>/` |
| CLI | Windows: `~/bin/devskills` · Unix: `/usr/local/bin/devskills` si se puede escribir ahí; si no, `~/.local/bin/devskills` |
| Carga útil (plantillas, scripts) | Windows: `~/bin/lib/devskills/` · Unix: `~/.local/share/devskills/` |
| Manifiesto | `manifiesto.txt` dentro de la carga útil: la lista exacta de archivos instalados |

Al copiar, el instalador adapta el contenido: `devskills:<nombre>` pasa a `devskills-<nombre>` y las variables del plugin (`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_SKILL_DIR}`) se resuelven a la carpeta instalada.

**No pisa nada tuyo:**

- Si un archivo de destino existe y no lo instaló DevSkills, pregunta antes de sobrescribirlo; sin terminal, aborta sin instalar nada. `--forzar` (`-Forzar`) lo sobrescribe a propósito.
- Si la carpeta de la carga útil existe y no es una instalación de DevSkills, no la toca.
- Es idempotente: reinstalar deja exactamente los mismos archivos. El manifiesto anterior se lee **antes** de reemplazar la carga útil, así que lo que la versión nueva ya no trae (un agente o una skill quitados) se borra, junto con las carpetas que queden vacías.
- Solo quita o borra entradas del manifiesto con aspecto de DevSkills (`devskills-*` o el CLI): un manifiesto alterado no puede hacer borrar archivos ajenos.
- **Rutas con caracteres especiales:** `&`, `#`, `\` y la comilla simple (por ejemplo, una carpeta de usuario `O'Brien`) se instalan literales. Se **rechaza** (código 2, sin instalar nada) una ruta con saltos de línea o caracteres de control, `$`, comillas dobles o acento grave, porque las skills instaladas las incrustan en comandos de shell.

**Qué no trae el instalador:** el hook de vetos para subagentes (`hooks/vetar_acciones_externas.sh`) pertenece al sistema de plugins de Claude Code y solo funciona instalado como plugin. Con el instalador, los vetos dependen de las reglas escritas en cada agente y de `--disallowedTools` en las corridas sin humano.

Opciones: `--si` (`-Si`) no pregunta al reinstalar. Variables: `CLAUDE_CONFIG_DIR`, `DEVSKILLS_BIN_DIR`, `DEVSKILLS_SHARE_DIR`.

## Actualizar

```bash
devskills update        # muestra los commits y los archivos que cambiarían y pide confirmación
devskills update --si   # confirma sin preguntar (obligatorio sin terminal)
```

`devskills update` consulta el remoto del clon de origen (`git fetch`), **te enseña qué traería** (commits y `diff --stat`) y no cambia nada hasta que confirmas. Después avanza el clon solo si es un avance limpio (`--ff-only`) y corre el `install.sh` del código nuevo: por eso conviene revisar el diff antes, sobre todo si no confías en el remoto. Sin terminal y sin `--si` no aplica nada.

Como plugin: `/plugin marketplace update devskills-local`.

### Actualizar los scripts de un proyecto ya creado

Un proyecto conserva una copia de los generadores de `documentacion/analisis/` del momento en que se creó. Si DevSkills corrige un script después (por ejemplo, la salida en UTF-8 o el formato del porcentaje del plan), tu proyecto sigue con el viejo. Se actualiza con:

```bash
devskills sync-scripts [ruta]        # lista los .py que difieren de la plantilla, muestra el diff --stat y pide confirmación
devskills sync-scripts [ruta] --si   # confirma sin preguntar (obligatorio sin terminal)
```

Sin `ruta` usa la carpeta actual, que debe ser un proyecto DevSkills (tiene `documentacion/CONTEXTO.md` y `documentacion/analisis/`). Copia **solo** los `.py` de `documentacion/analisis/` que cambiaron o que el proyecto no tiene; no toca `codigo/`, ni `documentacion/*.md`, ni los JSON de datos (`plan_entregas.json`, `trazabilidad.json`). La plantilla HTML del tablero (`plan_sprints_plantilla.html`) nunca se copia: si difiere de la de DevSkills (porque la personalizaste o porque quedó vieja), el comando la compara, te da el `git diff --no-index` para revisarla y lo decides tú. Si un script de la plantilla trae marcadores `{{...}}`, se comparan ya sustituidos con los datos de `CONTEXTO.md`; uno con un marcador que no se puede resolver se omite y se avisa. Después revisa `git diff` y haz el commit.

## Desinstalar

```bash
./uninstall.sh                                             # macOS, Linux, Git Bash
powershell -ExecutionPolicy Bypass -File uninstall.ps1     # PowerShell
```

Quita exactamente lo que está en el manifiesto y la carpeta de la carga útil. No toca tus otros agentes y skills ni los proyectos creados con `devskills init`.

Como plugin: `/plugin uninstall devskills@devskills-local`.

## Uso no interactivo

Sirve para correr un ciclo sin una persona frente a la terminal (un servidor, una prueba, un trabajo programado). Lo que sigue es lo que se comprobó en una prueba real con una historia pequeña.

```bash
claude -p "<prompt con el ID y las respuestas del Product Owner>" \
  --plugin-dir /ruta/a/DevSkills \
  --output-format stream-json --verbose \
  --permission-mode acceptEdits \
  --allowedTools "Read,Edit,Write,Glob,Grep,Agent,Skill,Bash(git status*),Bash(git diff*),Bash(git log*),Bash(git show*),Bash(git add*),Bash(git commit*),Bash(git switch*),Bash(git merge --squash*),Bash(git restore*),Bash(python -m pytest*),Bash(python -m ruff*),Bash(python -m mypy*),Bash(lint-imports*),Bash(python manage.py*),Bash(python documentacion/analisis/*),Bash(gh run list*),Bash(gh run view*)" \
  --disallowedTools "Bash(git push*),Bash(git reset*),Bash(git clean*),Bash(git branch -D*),Bash(git remote*),Bash(git config*),Bash(gh issue*),Bash(gh pr*),Bash(gh repo*),Bash(gh release*),Bash(gh api*),Bash(gh workflow*),Bash(gh secret*),Bash(gh variable*),Bash(docker push*),Bash(docker login*),Bash(docker system prune*),Bash(docker volume prune*),Bash(docker compose down -v*),Bash(docker compose down --volumes*)" \
  --max-turns 200 --max-budget-usd 25
```

| Qué | Para qué |
|-----|----------|
| `--plugin-dir <ruta a DevSkills>` | Carga el plugin desde el clon sin instalarlo. Si ya está instalado como plugin, no hace falta |
| `--output-format stream-json --verbose` | Emite un evento JSON por línea: ves qué agentes (`devskills:dev-a`, `devskills:qa`…) y qué skills se invocan, y de ahí sacas el `session_id` |
| `--permission-mode acceptEdits` | Acepta las ediciones de archivos; el resto de herramientas solo corre si está permitida |
| `--allowedTools` | Lista **acotada con patrones mínimos**: solo los subcomandos que el ciclo necesita. **No uses `Bash(git *)`, `Bash(python *)` ni `Bash(docker *)`**: `git *` permite `push`, `reset --hard` y `clean -fd`; `python *` ejecuta cualquier código; `docker *` permite borrar volúmenes o publicar imágenes. Sin humano, una herramienta no permitida se rechaza y el agente se detiene; amplía la lista solo con lo que veas rechazado y siempre con el subcomando exacto |
| `--disallowedTools` | **Vetos explícitos**: las reglas de rechazo ganan a las de permiso, así que aunque un patrón permitido sea demasiado ancho, esto sigue bloqueado. El ciclo nunca necesita subir nada, tocar la configuración de git ni escribir en GitHub: eso lo decide una persona |
| `--max-turns` y `--max-budget-usd` | Tope de turnos y de gasto: sin ellos un ciclo que se atora gasta sin límite. Ajusta los números al tamaño del elemento |

Notas sobre la lista:

- **La rama del elemento no se borra sola.** El cierre hace `git merge --squash` a `main`; borrar la rama requiere `git branch -D`, que está vetado. Bórrala tú después de revisar (`git branch -D hu-xx`).
- **Sin `push` ni `gh` de escritura.** Subir a GitHub, abrir issues o PR y mezclar los PR de Dependabot se hace a mano, con tu aprobación, después de la corrida.
- **Python:** los comandos se dan por módulo (`python -m pytest`, `python -m ruff`…) y por scripts conocidos; si usas un entorno virtual, permite también su ruta (`Bash(.venv/Scripts/python -m pytest*)` en Windows, `Bash(.venv/bin/python -m pytest*)` en Unix).
- **Docker no hace falta** para desarrollar y probar (ver [Docker es opcional](#docker-es-opcional)); si tu corrida lo usa, permite solo `Bash(docker compose -p <slug>-*)`. No uses `Bash(docker *)`.

### Corre en un entorno aislado

Una corrida sin humano ejecuta código que escribió un modelo. Aunque las listas de arriba reduzcan el riesgo, el aislamiento es la defensa de fondo:

- Trabaja en **una carpeta propia del proyecto** (un clon dedicado, sin otros repositorios ni secretos cerca), o mejor en una **máquina virtual o contenedor desechable**.
- No dejes en esa máquina credenciales de GitHub con permiso de escritura ni claves de nube; usa un token de solo lectura si el ciclo necesita consultar el CI.
- No montes tu carpeta de usuario ni tu `~/.ssh`. Revisa `git log` y `git diff` antes de subir nada.

### Las respuestas del Product Owner van en el prompt

Sin humano, `AskUserQuestion` y `devskills:preguntar-al-po` no tienen quién conteste. Incluye en el prompt las decisiones que normalmente darías en vivo y el default para lo que no esté previsto:

```text
Ejecuta /devskills:ciclo-historia HU-01.
Respuestas del Product Owner: (1) el límite de intentos es 5; (2) el aviso va por correo, no por SMS;
(3) si tras 3 rondas quedan pendientes, marca Bloqueado y registra el motivo; no pidas más rondas.
Si algo no está cubierto aquí, no inventes: deja la pregunta registrada en el reporte y detente.
```

### Retomar tras un corte por límite de uso

Si la corrida se corta (límite de uso o de presupuesto), el punto de control `wip` protege lo hecho: lo que alcanzó a commitearse sigue en la rama del elemento. Retoma la **misma sesión**, con su contexto:

```bash
claude -p "Continúa exactamente donde te quedaste; no rehagas lo que ya está en el commit wip." \
  --resume <id de sesión> --plugin-dir /ruta/a/DevSkills --permission-mode acceptEdits
```

El `<id de sesión>` sale del campo `session_id` de los eventos del `stream-json`. Antes de reanudar sigue el diagnóstico de la skill [`recuperar-corte`](../skills/recuperar-corte/SKILL.md): `git status`, contenedores huérfanos con tu prefijo y commit de respaldo.

### Costo observado y cómo abaratarlo

En la prueba real, una historia **pequeña** costó **unos 17 USD** con el modelo más potente en los subagentes (el ciclo lanza desarrollador, QA, Angel Fixer y verificador, cada uno con su propio contexto). Para abaratarlo:

- Pon un modelo más ligero en los subagentes: `export CLAUDE_CODE_SUBAGENT_MODEL=sonnet` (o el modelo que prefieras) antes de lanzar, o cambia `model:` en el encabezado de los agentes. Deja el modelo potente solo para el hilo del orquestador y el analista-arquitecto.
- Mejor aún, por rol y riesgo: activa el [enrutamiento de modelo y esfuerzo](enrutamiento.md) (`devskills enrutamiento evaluar` y luego `activar`); el orquestador pasa `model` y `effort` a cada subagente y escala solo cuando la verificación falla. No lo combines con `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` ni con `CLAUDE_CODE_EFFORT_LEVEL`, que lo anulan.
- Fija siempre `--max-budget-usd` y `--max-turns`.
- Parte los elementos grandes (más de 13 puntos) antes de correrlos.

### Tiempos: la suspensión del equipo cuenta como duración

Si el equipo se suspende (tapa cerrada, reposo) mientras un agente trabaja, el reloj sigue corriendo: la duración que Claude Code muestra para los agentes y para la sesión **incluye el tiempo dormido**. Un desarrollador que "tardó 9 horas" puede haber trabajado 40 minutos. No sirve para estimar esfuerzo ni para calibrar la velocidad del plan; para eso usa los puntos de cada reporte y su sección "Esfuerzo real". El costo en USD y los tokens no se ven afectados por la suspensión, así que son la medida confiable del gasto.

### Plugin engram en sesiones anidadas

El plugin engram puede fallar en las sesiones anidadas (la de `claude -p` lanzada desde otra sesión) si falta `jq`: sus hooks lo usan para leer el evento. Instálalo (`winget install jqlang.jq`, `brew install jq`, `apt install jq`) o deshabilita engram en esa corrida; el ciclo sigue funcionando sin memoria, pero no se guardará el avance en engram.

## Correo del autor en el primer commit

`devskills init` hace el primer commit con el `user.email` de tu git, que puede ser el corporativo. En un repositorio público ese correo queda en el historial. Para evitarlo:

```bash
devskills init ~/proyectos/mi-sistema --nombre "Mi sistema" --correo 12345+usuario@users.noreply.github.com
```

`--correo` fija `user.email` **solo en el repositorio nuevo** (no toca tu configuración global) antes del primer commit. Sin `--correo`, `init` imprime un aviso con el correo que usó. Tu noreply está en <https://github.com/settings/emails> (`<id>+<usuario>@users.noreply.github.com`). Si ya hiciste el commit con otro correo y aún no publicas: `git config user.email <noreply> && git commit --amend --reset-author --no-edit` (solo mientras el bootstrap sea el único commit).

## GitHub CLI (`gh`) y el CI

Un proyecto creado con DevSkills trae su CI en `.github/workflows/`, pero **solo corre cuando el repositorio tiene remoto** en GitHub. Crea el remoto privado desde el inicio y revisa el CI después de cada push, con `gh`. **Los agentes no suben nada por su cuenta:** proponen el comando y esperas tu "sí"; lo que sigue lo ejecutas tú (o lo apruebas cuando te lo propongan):

```bash
winget install GitHub.cli        # Windows · macOS: brew install gh · Linux: https://github.com/cli/cli#installation
gh auth login                    # GitHub.com → HTTPS → navegador (o con un token)
gh auth status                   # comprueba la sesión

gh repo create <organizacion>/<slug> --private --source . --remote origin --push
gh run list --limit 3            # estado de las últimas corridas del CI
gh run view <id> --log-failed    # solo el registro de lo que falló
```

Un CI en rojo es deuda: se corrige antes de seguir. Los PR de Dependabot fallarán mientras el CI de `main` esté en rojo: primero `main` en verde, luego `@dependabot rebase`, integra las menores y revisa aparte las versiones mayores. **Cada `@dependabot rebase` y cada merge es una acción hacia afuera:** el agente los lista y los propone, y solo ejecuta los que apruebas. Los flujos usan `ubuntu-24.04` (no `ubuntu-latest`): subir esa imagen es un cambio a mano.

## Windows en un equipo de dominio: Git Bash puede ir lento

En equipos Windows unidos a un dominio, cada arranque de `sh.exe` (Git Bash) puede consultar al controlador de dominio (Netlogon) y, fuera de la red corporativa o sin VPN, esperar su tiempo de espera. Un `sh -c true` que debería tardar milisegundos tarda segundos, y todo lo que lanza muchos procesos se vuelve lentísimo: la suite de ShellSpec de DevSkills (27 ejemplos) tarda **unos 5 minutos** en una máquina así, con más tiempo de sistema que de usuario, y el pytest de un proyecto con PostgreSQL embebido, varios minutos. No es un fallo del plugin:

- Mide con `time sh -c true`; más de unos 100 ms por arranque indica este problema.
- Conéctate a la red corporativa o a la VPN antes de correr suites largas, o córrelas en WSL o en el CI.
- Corre una sola prueba con `shellspec spec/integration/cli_spec.sh:LÍNEA` y deja la suite completa para el CI; en pytest, por módulos (`pytest -q nucleo`).
- No subas los tiempos de espera ni reintentes en bucle: empeora la lentitud.

## Requisitos

Corre `devskills doctor` para revisarlos todos.

| Requisito | Para qué | Cómo instalarlo |
|-----------|----------|-----------------|
| Git | Todo | <https://git-scm.com/downloads> |
| Claude Code | Agentes y skills | <https://code.claude.com> |
| Python 3.12 | Esqueleto y generadores | `winget install Python.Python.3.12` · `brew install python@3.12` |
| gitleaks | Búsqueda de secretos antes de cada commit | Nativo: `winget install Gitleaks.Gitleaks` · `brew install gitleaks` · release de <https://github.com/gitleaks/gitleaks/releases>. Alternativa: `docker pull zricethezav/gitleaks:v8.21.2@sha256:0e99e8821643ea5b235718642b93bb32486af9c8162c8b8731f7cbdc951a7f46` |

Las imágenes de Docker de gitleaks y semgrep se fijan por **digest** (`etiqueta@sha256:...`), no solo por etiqueta: una etiqueta puede reapuntarse a otra imagen, un digest no. Al subir de versión se recalcula el digest del índice multiarquitectura en el registro (por ejemplo, el encabezado `Docker-Content-Digest` de `GET /v2/<repositorio>/manifests/<etiqueta>`, o `docker buildx imagetools inspect <imagen>:<etiqueta>`) y se cambia en todos los archivos a la vez; la prueba `spec/integration/gitleaks_spec.sh` falla si queda una referencia solo con etiqueta.

**Opcionales** (`devskills doctor` los avisa sin bloquear y dice qué pierdes):

| Requisito | Para qué | Cómo instalarlo |
|-----------|----------|-----------------|
| Docker | Levantar el stack con Compose y construir la imagen en tu máquina | Docker Desktop o Docker Engine. Ver [Docker es opcional](#docker-es-opcional) |
| semgrep | Análisis estático igual que el CI, en tu máquina | macOS: `pipx install semgrep==1.178.0` (la versión de `semgrep==` en el `ci.yml` del proyecto); Linux y Windows con WSL, en un venv propio: `python3 -m venv ~/semgrep && ~/semgrep/bin/pip install semgrep==1.178.0` (en Windows se corre dentro de WSL, nunca en el Python de Windows); o Docker (`docker pull semgrep/semgrep:1.178.0@sha256:32e459968daabe7ab86968184a29109b9564aa00392401156f9788452b42786b`). En el CI de GitHub es obligatorio |
| Node.js LTS | Presentación y mermaid-cli | <https://nodejs.org> |
| mermaid-cli | Diagramas en los Word | En una carpeta local con versión fija, ver [generadores](generadores.md) |
| GitHub CLI (`gh`) | Remoto privado y revisión del CI | Ver "GitHub CLI (`gh`) y el CI" |
| Plugin engram | Memoria entre sesiones | Como plugin de Claude Code |
| Graphify | Grafos del deber ser y de lo que es, deriva en el cierre del sprint y consultas que ahorran tokens | `uv tool install graphifyy` (o `pipx install graphifyy`). Sin él, el método sigue con lecturas normales. Ver [graphify](graphify.md) |

### Docker es opcional

Docker **no es un requisito** para usar DevSkills ni para desarrollar o probar un proyecto. El stack sigue siendo el mismo (Django, PostgreSQL, Redis, Celery, nginx) y **Docker Compose es la forma de desplegarlo**, pero:

| Qué | Sin Docker | Con Docker |
|-----|-----------|------------|
| Base de datos de desarrollo y de pruebas | PostgreSQL 16 embebido (`pgserver`), ya soportado por el esqueleto | El `postgres` del Compose |
| Celery y Redis | Modo local (eager) y caché en memoria; sin worker ni beat | `worker`, `worker-outbox`, `beat` y `redis` reales |
| Batería de pruebas (`pytest`) | Completa; las pruebas de Compose y del certificado se omiten con el motivo a la vista | Completa, sin omisiones |
| Secretos (gitleaks) | Binario nativo | Imagen de Docker |
| semgrep | Nativo en macOS y Linux; en Windows, WSL o Docker | Imagen de Docker |
| Desplegar, construir la imagen, hadolint y trivy | No aplica en tu máquina | Sí |

Qué se pierde sin Docker: levantar el stack completo en tu máquina (nginx con TLS, worker y beat reales) y probar ahí los reintentos del outbox; todo eso se prueba en el CI de GitHub, donde Docker **siempre** está y las pruebas que lo necesitan no se pueden omitir (`REQUIERE_DOCKER=1`). `devskills doctor` trata Docker como opcional: lo avisa, no lo cuenta como error y explica qué pierdes.

Para correr sin humano, ver "Uso no interactivo".

Opcional: el plugin de Telegram, para trabajar desde el celular ([telegram](telegram.md)).
