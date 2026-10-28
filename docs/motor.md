# Motor gráfico

El motor es el panel de control local de DevSkills: muestra tus proyectos, levanta y apaga sus servicios y lista las sesiones de Claude Code. Vive en `motor/` y no necesita nada fuera de Python 3.12 (el orquestador es opcional).

## Qué incluye

- **Panel** (`devskills panel`): web local en `http://127.0.0.1:18950`, solo biblioteca estándar.
- **Lanzador de servicios** (`devskills servicios`): levanta y apaga los servicios del registro. Tipos permitidos (lista blanca): `dotnet`, `npm`, `django-devskills`, `python-modulo`, `docker-compose`.
- **Orquestador** (opcional, `devskills orquestador`): API local para mandar instrucciones a las sesiones de Claude Code. Usa `claude-agent-sdk` en un venv propio.
- **Graphify** (`motor/graphify/`): hooks en Python, plantilla `.graphifyignore` y revisión del grafo antes de versionarlo.

## Instalación de punta a punta en un equipo nuevo

Nada del motor lleva rutas ni nombres de una persona: lo que depende del equipo (la ruta de la copia instalada, el intérprete de Python, la carpeta de configuración de Claude Code) se calcula ahí mismo.

1. **Instala DevSkills.** Plugin (`/plugin marketplace add ssdarm150120-gif/DevSkills` y `/plugin install devskills@devskills-local`) y, para tener el CLI `devskills` en el PATH, también `bash install.sh` (o `install.ps1` en Windows); ver [instalación](instalacion.md). El plugin trae los hooks de Graphify; el instalador trae el CLI y la copia estable de `motor/`.
2. **Crea tu registro:** `devskills motor iniciar` (crea `~/.devskills/proyectos.json` desde la plantilla si no existe).
3. **Engancha el motor a Claude Code:** `devskills motor enganchar` (status line de límites; muestra el diff, pide confirmación y respalda `settings.json`). Ver la sección siguiente.
4. **Abre el panel:** `devskills panel`; en la vista Registro, "Detectar" propone tus proyectos.
5. **Opcional, orquestador:** `devskills orquestador instalar` y luego `devskills orquestador iniciar`.

```bash
devskills motor iniciar
devskills motor enganchar
devskills panel
devskills servicios listar
devskills servicios levantar <proyecto|servicio> --simular   # muestra qué haría, sin ejecutar
```

Requisito: Python 3.12 en el PATH (`python3`, `python` o `py`). El motor no instala nada más.

## Enganchar el motor a Claude Code

`devskills motor enganchar [--quitar] [--si] [--envolver "<cmd>"] [--hooks] [--limpiar-hooks]` escribe en el `settings.json` de usuario de Claude Code (`$CLAUDE_CONFIG_DIR/settings.json` o `~/.claude/settings.json`):

- **Status line de límites:** `statusLine` con la ruta de la copia de DevSkills desde la que corres el comando y el intérprete de Python de ese equipo (`python3`/`python` si resuelven al mismo, si no la ruta absoluta). No puede ir en el plugin: Claude Code no la lee de ahí.
- **Garantías:** mezcla sin perder otras claves; si el JSON no se puede leer, no toca nada; muestra el diff y pide confirmación (`--si` sin terminal); respalda en `settings.json.bak-<fecha>` antes de escribir; si ya está como corresponde, no escribe ni respalda (idempotente).
- **No pisa una status line ajena.** Con `--envolver "<tu comando>"` la conserva: sus datos se muestran antes de los límites. En una terminal, si hay una ajena, pregunta si envolverla o reemplazarla. `--quitar` solo quita la propia (y te devuelve la tuya original si estaba envuelta).
- **Hooks viejos de Graphify** (pegados a mano apuntando a `sesion_inicio.py` o `hook_guard.py`): los detecta por nombre de script. Si el plugin `devskills` está habilitado, los quita (ahora los trae el plugin y quedarían duplicados); si no lo detecta, solo avisa. `--limpiar-hooks` fuerza la limpieza.
- **Sin plugin** (solo `install.sh`): `--hooks` escribe los tres hooks de Graphify en forma sin shell (`command` + `args`, con el Python de ese equipo) y reemplaza los viejos. Con el plugin habilitado, `--hooks` se rechaza para no duplicarlos.

Si corres el comando desde la carpeta de plugins de Claude Code, la ruta cambia con cada actualización del plugin; por eso conviene correrlo desde la copia instalada con `install.sh` (o repetirlo tras actualizar). Después de enganchar, reinicia Claude Code.

### Migrar desde la configuración vieja (rutas pegadas a mano)

```bash
devskills motor enganchar --quitar --limpiar-hooks   # quita statusLine y hooks viejos; muestra el diff y respalda
devskills motor enganchar                            # status line con la ruta de ESTE equipo (el plugin trae los hooks)
```

Si ya usabas otra status line, usa `--envolver "<tu comando>"` en el segundo paso. Para solo corregir la ruta basta el segundo comando: reemplaza la ruta vieja de `statusline_limites.py` y quita los hooks viejos si el plugin está habilitado.

## Estado fuera del repositorio

Todo el estado vive en el directorio de datos: la variable `DEVSKILLS_DATOS` o, si no existe, `~/.devskills/`. (No se usa `DEVSKILLS_HOME` porque el CLI ya la usa para la carga útil.)

| Ruta | Contenido |
| --- | --- |
| `proyectos.json` | Registro central de proyectos |
| `preferencias.json` | Preferencias del panel |
| `panel/estado/`, `panel/.token`, `panel/panel.log` | Avisos, acciones, token y log del panel |
| `orquestador/` | Token, historial, propuestas, fallos de enrutamiento, log, `config.json` y `.venv` |
| `servicios/logs`, `servicios/pids` | Logs y pids de los servicios (macOS y Linux) |

Una instancia en otro puerto (`--puerto`) usa archivos con el puerto en el nombre y nunca pisa la principal.

## Orquestador opcional

`devskills orquestador instalar` crea el venv en `~/.devskills/orquestador/.venv` e instala `claude-agent-sdk` con versión fijada. Después: `iniciar`, `estado`, `apagar`. Sin instalarlo, el panel y los servicios funcionan igual. Se configura con `~/.devskills/orquestador/config.json` (valores por omisión en `motor/orquestador/config.defecto.json`).

## Status line de límites

`motor/panel/statusline_limites.py` guarda los límites del plan que Claude Code entrega a la status line y el panel los muestra. Se activa con `devskills motor enganchar` (ver arriba); ya no hace falta editar `settings.json` a mano.

## Hooks de Graphify

Los trae el plugin (`hooks/hooks.json`): `SessionStart` → `sesion_inicio.py`, y `PreToolUse` con `Bash|Grep` → `hook_guard.py search` y `Read|Glob` → `hook_guard.py read`. Son inocuos sin grafo (si el proyecto no tiene `graphify-out/`, salen en el acto sin lanzar Python), nunca bloquean (salen con 0) y se desactivan con `GRAPHIFY_SESION=0` / `GRAPHIFY_GUARDIA=0` o con un archivo `DESACTIVADO` junto al script.

**Cómo se elige el intérprete.** Claude Code ejecuta un `command` sin `args` con `sh -c` en macOS y Linux y con Git Bash en Windows (PowerShell si no hay Git Bash), y no existe un filtro por sistema operativo ni un `cmd`. El `command` del plugin es un fragmento POSIX que prueba `python3` y `python` (en Windows, `python` y `py`; la variable `OS=Windows_NT` evita lanzar `uname`), hace `exec` del primero que exista y, si no hay ninguno, sale con 0. Solo usa comandos internos del shell: no lanza procesos auxiliares ni scripts de bash. La forma sin shell (`command` + `args`) evitaría por completo el bash de Windows, pero exige conocer el nombre del intérprete de cada equipo y un solo `hooks.json` no puede declararlo para tres sistemas; por eso esa forma la escribe `devskills motor enganchar --hooks` (con el Python detectado) para quien no usa el plugin o quiere evitar Git Bash. Ver `motor/graphify/README.md`.

## Portabilidad y valores por omisión

- **Carpeta de Claude Code:** `CLAUDE_CONFIG_DIR` si existe; si no, `~/.claude` (transcripts que lee el panel, `.claude.json` y agentes/skills del orquestador).
- **Detección de proyectos del panel:** por omisión mira `~/Documents/Proyectos` y `~/Desktop`. Para tu equipo, en `~/.devskills/proyectos.json` agrega `"raices_deteccion": ["~/src", "D:/repos"]` (se suman siempre) y, si no quieres las dos de por omisión, `"usar_raices_defecto": false`.
- **Datos personales:** siempre en `DEVSKILLS_DATOS` o `~/.devskills`; nunca en el repositorio.
- **Python:** el CLI busca `python3.12`, `python3`, `python` y `py -3.12`.

## Migrar desde una instalación previa

```bash
devskills motor migrar --desde <carpeta-de-la-instalacion-previa> [--forzar]
```

Copia `proyectos.json`, preferencias, estado del panel, historial y propuestas del orquestador a `~/.devskills`. No sobrescribe lo existente (salvo `--forzar`), no copia tokens ni logs ni venvs, y no toca ni borra el origen.

## Pendientes de git (Commit y Push desde el panel)

Cada proyecto del registro (`carpeta` y `repositorio.cuenta` de `proyectos.json`) tiene un apartado **Pendientes de git** con dos botones separados: **Commit** (local) y **Push** (con confirmación). La carpeta debe ser la RAÍZ de un repositorio git; si no lo es, el panel lo dice y no muestra botones.

**Vista (solo lectura):** rama actual, upstream y adelante/atrás, archivos sin commit (`git status --porcelain=v1 -z`, estados M/A/D/??/R), commits sin push, stashes y las ramas locales con commits que NO están en `origin/<rama por omisión>` (se compara contra el REMOTO, no contra el `main` local: si el `main` local va atrás, compararlo daría falsos pendientes), con fecha, hash corto, asunto y si tienen remoto. El panel no hace `git fetch` por su cuenta: el botón **Actualizar remoto** (o `GET /api/proyecto/git?id=…&actualizar=1`) lo corre con tiempo límite de 20 s; mientras tanto se muestra la hora de la última consulta.

**Commit (local, siempre con gitleaks):**
- Mensaje propuesto con plantilla, sin IA y editable: el tipo sale del prefijo de la rama (`fix/` → `fix`, `feat/` → `feat`, `docs/` → `docs`, `en-02`/`hu-07` → `wip(en-02)`, otra → `chore`) más un resumen de los archivos. Al enviar se valida conventional commits (`tipo(alcance opcional)!?: descripción` con los tipos estándar y `wip`), que no esté vacío, una primera línea de a lo más 100 caracteres y línea en blanco antes del cuerpo. Un `Co-Authored-By` o una atribución de IA se rechazan.
- Los archivos los elige el usuario con casillas (todas marcadas por omisión). El servidor SOLO acepta rutas que estén en la salida actual de `git status --porcelain` (lista blanca recalculada en el momento del commit); rechaza cualquier otra, `..` y rutas absolutas. Las rutas llegan a git después de `--`, con `--literal-pathspecs` y sin shell; los renombres viajan completos y los nombres con espacios o acentos funcionan (`-z`). No se commitean archivos con pinta de credencial (`.env`, claves `.pem`, `.netrc`…); `git commit --only` deja fuera lo que ya estuviera preparado en el índice y no se haya elegido.
- Antes de tocar el índice corre **gitleaks** sobre una copia temporal del contenido de esos archivos (`gitleaks dir`, con el `.gitleaks.toml` del repo si existe). Mismo criterio que `scripts/gitleaks_archivos.py`: busca el binario en el `PATH` y en las rutas de winget; código 0 = limpio, 1 = hallazgos, cualquier otra cosa o sin binario = "herramienta no disponible" (no cuenta como escaneo bueno). Con hallazgos (422) o sin herramienta (503) NO se hace el commit y se explica por qué. El panel solo usa el binario nativo (no Docker).

**Push (con confirmación en un modal de la página, nunca `confirm()`):**
- Sube solo la rama actual (`git push -u origin <rama>` si no tiene upstream, `git push origin <rama>` si lo tiene) y la rama del cuerpo debe coincidir con HEAD. Nunca `--force` (el constructor del comando lo impide); si el remoto cambió, git lo rechaza y no se pisa nada.
- **Bloqueado en `main`, `master` y en la rama por omisión del remoto** (`origin/HEAD`): el botón no aparece y el endpoint responde 409 (el flujo es rama de trabajo + PR).
- **Cuenta:** antes de subir se verifica con qué cuenta saldría el push contra `repositorio.cuenta`, según el helper de credenciales (`modo_helper`). Con **Git Credential Manager** (`manager`) la cuenta activa de `gh` NO decide: se compara el usuario de la URL del remoto (`https://usuario@github.com/…`) o el `credential.https://github.com.username` del repo; si no hay ninguno, no se bloquea y el modal muestra una advertencia. Con el **helper de gh** manda el usuario del repo o, si falta, la cuenta activa de `gh`, y se exige que la cuenta del proyecto esté autenticada en `gh` (`requiere_login`). Si no coincide, el push NO se hace y la respuesta lleva qué hacer (`accion`: `POST /api/proyecto/credencial` o `POST /api/github/cuenta`, los mismos endpoints del bloque GitHub); el panel nunca cambia de cuenta en silencio. Un remoto que no es `https://github.com/…` no se puede verificar: se advierte.

**Endpoints** (token, `Host` y `Origin` como el resto): `GET /api/proyecto/git?id=<proyecto>[&actualizar=1]`, `POST /api/proyecto/git/commit` `{id, archivos[], mensaje}` y `POST /api/proyecto/git/push` `{id, rama}`. Con `--simular` las lecturas se hacen, pero no hay `git fetch`, gitleaks, `add`, `commit` ni `push`: se devuelven los comandos. Todos los subprocesos de git tienen tiempo límite y sin preguntas interactivas; el log del panel (`panel.log`) solo guarda proyecto, rama, código y hash, sin mensajes, tokens ni URLs con credenciales. Pruebas: `motor/panel/pruebas/test_panel_git.py` (repos temporales y un remoto bare local).

## Seguridad

- Todo escucha solo en `127.0.0.1`; el panel valida `Host` y `Origin` y exige un token por sesión (en un archivo con permisos restringidos, nunca enviado al navegador en el caso del orquestador).
- El orquestador solo escribe en su carpeta de datos; los cambios piden confirmación explícita.
- El lanzador no usa shell ni texto libre: tipos en lista blanca, patrones estrictos para script de npm, módulo, argumentos y variables de entorno, y carpetas relativas sin `..` ni rutas absolutas.
- Los datos personales (registro, historial, tokens) nunca se versionan: viven en `~/.devskills`.

## Limitaciones

El apagado por grupo de procesos y `taskkill /T` se probaron solo en Windows; en macOS y Linux se probaron las rutas de código con pruebas unitarias. `docker-compose` corre en primer plano porque `docker compose up -d` termina enseguida.
