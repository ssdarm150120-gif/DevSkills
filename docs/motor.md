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

## Aplicar cambios (recompilar y reiniciar con un clic)

Después de que una sesión de Claude Code edita un proyecto, para ver los cambios hay que recompilar el front y reiniciar el back. El apartado **Aplicar cambios** de cada proyecto lo hace con un clic, sin abrir terminales. **Limitación:** el panel no puede reiniciar la terminal de Claude Code (el `PATH` se hereda al arrancar); sí recompila el proyecto y reinicia sus servicios.

**Receta detectada y aprobada.** La primera vez, el botón lleva a aprobar la receta que el panel propone a partir de lo que ve: cada subcarpeta (hasta 2 niveles, sin `node_modules`) con `package.json` y script `build` → `npm-install` + `npm-script build`; cada servicio `python-modulo` con `venv` y un `requirements.txt` (en su carpeta o en la raíz) → `pip-requisitos`; y al final el reinicio de los servicios `dotnet`, `django-devskills`, `python-modulo` y los `npm` que no sean de desarrollo (`dev`, `watch`, `serve`…). Los `docker-compose` no se reinician solos. El usuario marca o desmarca pasos y aprueba una vez; queda guardada en `proyectos.json` (clave `aplicar`) y se edita o se quita después. La escritura reusa la del resto del registro: validación completa con las reglas de lectura, escritura atómica y formato con sangría de 2 (el panel no hace respaldo de `proyectos.json` en ninguna de sus escrituras).

```json
"aplicar": {
  "version": 1,
  "aprobada": "2026-10-28T10:15:00-06:00",
  "pasos": [
    { "id": "npm-install-frontend", "tipo": "npm-install", "carpeta": "frontend" },
    { "id": "npm-build-frontend", "tipo": "npm-script", "carpeta": "frontend", "script": "build" },
    { "id": "pip-backend", "tipo": "pip-requisitos", "venv": ".venv", "requisitos": "backend/requirements.txt" },
    { "id": "reiniciar-dashboard-web", "tipo": "reiniciar-servicio", "servicio": "dashboard-web" }
  ]
}
```

**Pasos tipados de lista blanca, nunca comandos libres ni shell.** `npm-install` (`npm ci` si hay `package-lock.json`, si no `npm install`; siempre con `--no-audit --no-fund`), `npm-script` (`npm run <script>`; el nombre cumple `[A-Za-z0-9:._-]{1,60}` y debe existir en el `package.json`), `pip-requisitos` (`<venv>/python -m pip install -r <archivo .txt>`) y `reiniciar-servicio` (un servicio del MISMO proyecto, con el lanzador: `servicios.py apagar` y después `levantar`, y se espera a que su ruta de salud responda hasta 45 s; si no responde, el paso falla). Las carpetas son relativas al proyecto, validadas con `ruta_segura` del lanzador (sin `..`, rutas absolutas, unidades ni UNC) y con comprobación en disco al aprobar. `npm` se resuelve con `shutil.which` (en Windows, `npm.cmd`) y se ejecuta sin shell; si el `PATH` del panel no lo tiene, el paso falla explicando que hay que reiniciar el panel. Cada paso tiene su tiempo límite (900 s para npm y pip, 120 s para el reinicio; `timeout` opcional por paso, de 10 a 3600) y, en Windows, un tiempo agotado mata también a los procesos hijos. Una receta dañada a mano no tumba el registro: se avisa y no se ejecuta.

**Solo lo necesario (huellas).** Se guarda en `<estado>/aplicar.json` (por omisión `~/.devskills/panel/estado/`, nunca en el repo) la huella de cada paso de la última aplicación correcta. La huella es un sha256 de la definición del paso (si editas la receta, el paso vuelve a correr) y de sus entradas:
- `npm-install`: contenido de `package.json` y `package-lock.json` y si existe `node_modules`. Corre solo si cambió alguno.
- `npm-script` (el build): una firma barata del árbol de la carpeta, sin leer contenido: sha256 de (ruta, tamaño, mtime en ns) de cada archivo relevante. Dentro de un repo se listan con `git ls-files -co --exclude-standard` (rastreados más no rastreados no ignorados, así `node_modules`, `dist` y lo que ignore el `.gitignore` nunca cuentan); sin git, un recorrido que poda `node_modules`, `.venv`, `__pycache__`, `dist`, `build`, etc. Es barata y robusta: ediciones, altas y bajas cambian la firma; un `touch` o un checkout sin cambios solo puede causar una recompilación de más, nunca una de menos.
- `pip-requisitos`: contenido del archivo de requisitos y si existe el Python del venv.
- `reiniciar-servicio`: la misma firma del árbol de la carpeta de arranque del servicio. Además se reinicia siempre que haya corrido cualquier paso anterior (build o dependencias nuevas). Cuando un paso corre bien se invalidan las huellas de los reinicios: si el reinicio falla, la próxima vez se reintenta aunque el código del servicio no haya cambiado.

Las huellas se calculan DESPUÉS de cada paso correcto (un build que escribe dentro de la carpeta vigilada no se vuelve a disparar solo). Si la carpeta de un servicio es `.`, la firma abarca todo el proyecto (un cambio del front también marcaría cambios del back). **Forzar todo** ejecuta todos los pasos.

**Aviso de cambios sin aplicar.** El apartado muestra «Hay cambios sin aplicar: frontend, backend» con las áreas de los pasos que cambiaron por sí mismos (carpeta del front, del archivo de requisitos o del servicio). Se calcula en el servidor con caché de 5 s por proyecto y se refresca cada 4 s; cuando una sesión termina de editar, es el disparador para dar clic.

**Ejecución en segundo plano.** **Aplicar cambios** abre un modal de la página (nunca `confirm()`) con lo que se ejecutará, lo que se omite y por qué; el clic en «Sí, aplicar» lanza un hilo (no bloquea el servidor HTTP) y el apartado muestra el progreso paso a paso: pendiente, en curso, ✅, ❌, omitido (con su razón) o simulado, con la salida de cada paso limpia (sin colores ni barras de progreso, secretos enmascarados, recortada a sus últimos 1500 caracteres). Se detiene en el primer fallo y marca el resto como omitido. Al terminar bien aparece **Abrir** con la `url` y el `abrir` del servicio reiniciado. Un candado por proyecto: no dos aplicaciones a la vez ni junto con Levantar/Apagar del mismo proyecto (409). Con `--simular` se muestran los comandos y no se ejecuta ni se guarda nada (la receta sí se puede aprobar: es solo configuración).

**Chat del panel.** Frases como «aplica (los) cambios (de/del/en) <proyecto>», «actualiza el <proyecto>» y «recompila <proyecto>» las intercepta el panel ANTES de mandarlas al orquestador (sin gastar tokens y aunque esté apagado): coincide solo si lo que sigue al verbo es exactamente el id, el nombre o un alias (`alias_proyectos` de la configuración del orquestador) de UN proyecto, sin acentos ni mayúsculas y sin palabras de relleno («el», «proyecto», «por favor»…). Es un resolvedor mínimo propio en `panel.py` (no se importa nada del orquestador): igualdad exacta de palabras, sin puntajes difusos. Si el proyecto no se reconoce o es ambiguo, la frase sigue su camino normal al orquestador. La respuesta es una tarjeta con la receta (o la propuesta, si todavía no hay una aprobada) y el botón **Ejecutar**, que abre la misma confirmación que el botón del apartado; ejecutar siempre requiere un clic explícito.

**Endpoints** (token, `Host` y `Origin` como el resto; claves exactas, sin texto libre): `GET /api/proyecto/aplicar?id=<proyecto>[&propuesta=1]` (receta, plan, aviso, ejecución, última aplicación y propuesta), `POST /api/proyecto/aplicar/receta` `{id, pasos[]}` (aprueba o edita; `pasos: []` quita la receta), `POST /api/proyecto/aplicar/ejecutar` `{id, forzar?}` (202; el progreso se consulta con el GET) y `GET /api/chat/intencion?texto=…`. El log del panel solo guarda proyecto, paso y resultado. Pruebas: `motor/panel/pruebas/test_panel_aplicar.py` (proyecto temporal con front y back, fakes para npm, pip y el lanzador; no se instala ni se compila nada).

## Seguridad

- Todo escucha solo en `127.0.0.1`; el panel valida `Host` y `Origin` y exige un token por sesión (en un archivo con permisos restringidos, nunca enviado al navegador en el caso del orquestador).
- El orquestador solo escribe en su carpeta de datos; los cambios piden confirmación explícita.
- El lanzador no usa shell ni texto libre: tipos en lista blanca, patrones estrictos para script de npm, módulo, argumentos y variables de entorno, y carpetas relativas sin `..` ni rutas absolutas.
- Los datos personales (registro, historial, tokens) nunca se versionan: viven en `~/.devskills`.

## Limitaciones

El apagado por grupo de procesos y `taskkill /T` se probaron solo en Windows; en macOS y Linux se probaron las rutas de código con pruebas unitarias. `docker-compose` corre en primer plano porque `docker compose up -d` termina enseguida.
