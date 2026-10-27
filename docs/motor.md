# Motor gráfico

El motor es el panel de control local de DevSkills: muestra tus proyectos, levanta y apaga sus servicios y lista las sesiones de Claude Code. Vive en `motor/` y no necesita nada fuera de Python 3.12 (el orquestador es opcional).

## Qué incluye

- **Panel** (`devskills panel`): web local en `http://127.0.0.1:18950`, solo biblioteca estándar.
- **Lanzador de servicios** (`devskills servicios`): levanta y apaga los servicios del registro. Tipos permitidos (lista blanca): `dotnet`, `npm`, `django-devskills`, `python-modulo`, `docker-compose`.
- **Orquestador** (opcional, `devskills orquestador`): API local para mandar instrucciones a las sesiones de Claude Code. Usa `claude-agent-sdk` en un venv propio.
- **Graphify** (`motor/graphify/`): hooks en Python, plantilla `.graphifyignore` y revisión del grafo antes de versionarlo.

## Instalación y primer uso

El motor viaja con DevSkills (`install.sh` / `install.ps1` copian `motor/`).

```bash
devskills motor iniciar        # crea ~/.devskills/proyectos.json desde la plantilla si no existe
devskills panel                # abre el panel; en él, "Detectar" propone tus proyectos
devskills servicios listar
devskills servicios levantar <proyecto|servicio> --simular   # muestra qué haría, sin ejecutar
```

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

`motor/panel/statusline_limites.py` guarda los límites del plan que Claude Code entrega a la status line y el panel los muestra. No se activa solo: agrega a `~/.claude/settings.json`

```json
"statusLine": { "type": "command", "command": "python <ruta-de-DevSkills>/motor/panel/statusline_limites.py", "refreshInterval": 60 }
```

`devskills panel estado` imprime la ruta exacta. Si ya tienes otra status line, usa `--envolver "<tu comando>"`.

## Hooks de Graphify

El hook `PreToolUse` debe ser Python (`motor/graphify/hook_guard.py`), no bash: en Windows un hook de bash lanza un `bash.exe` por cada llamada a herramienta y, con agentes en paralelo, Git Bash falla con `add_item ... errno 1`. Ver `motor/graphify/README.md`.

## Migrar desde una instalación previa

```bash
devskills motor migrar --desde <carpeta-de-la-instalacion-previa> [--forzar]
```

Copia `proyectos.json`, preferencias, estado del panel, historial y propuestas del orquestador a `~/.devskills`. No sobrescribe lo existente (salvo `--forzar`), no copia tokens ni logs ni venvs, y no toca ni borra el origen.

## Seguridad

- Todo escucha solo en `127.0.0.1`; el panel valida `Host` y `Origin` y exige un token por sesión (en un archivo con permisos restringidos, nunca enviado al navegador en el caso del orquestador).
- El orquestador solo escribe en su carpeta de datos; los cambios piden confirmación explícita.
- El lanzador no usa shell ni texto libre: tipos en lista blanca, patrones estrictos para script de npm, módulo, argumentos y variables de entorno, y carpetas relativas sin `..` ni rutas absolutas.
- Los datos personales (registro, historial, tokens) nunca se versionan: viven en `~/.devskills`.

## Limitaciones

El apagado por grupo de procesos y `taskkill /T` se probaron solo en Windows; en macOS y Linux se probaron las rutas de código con pruebas unitarias. `docker-compose` corre en primer plano porque `docker compose up -d` termina enseguida.
