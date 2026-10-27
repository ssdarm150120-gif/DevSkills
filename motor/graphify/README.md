# Integración con Graphify

Graphify convierte el código de un proyecto en un grafo de conocimiento (`graphify-out/`) sin llamar a ningún LLM
(`graphify update .`). Esta carpeta trae lo que el motor de DevSkills agrega encima. Todo es opcional: sin Graphify,
los agentes exploran con lecturas normales (ver `docs/graphify.md`).

| Archivo | Para qué sirve |
| --- | --- |
| `plantilla.graphifyignore` | Reglas de exclusión (sintaxis de `.gitignore`) que refuerzan las de Graphify: secretos, dependencias, datos reales, respaldos y bitácoras. Cópiala como `.graphifyignore` en la raíz de tu proyecto y ajústala. |
| `revisar_grafo.py` | Revisa `graph.json`, `GRAPH_REPORT.md` y `graph.html` ANTES de versionarlos: busca correos, IPs, cadenas de conexión, contraseñas, tokens, hosts internos y rutas absolutas del usuario. Sale con código 1 si encuentra algo. |
| `sesion_inicio.py` | Hook `SessionStart` de Claude Code: inyecta un resumen corto del grafo (tamaño, comunidades, nodos centrales) y avisa si quedó atrás de git. Nunca bloquea. |
| `hook_guard.py` | Envoltura del `PreToolUse` de Graphify: solo llama a `graphify hook-guard` si el proyecto tiene grafo (localiza `graphify` con el PATH y luego `~/.local/bin`). Nunca bloquea. |

## Uso

Desde la raíz del repositorio de DevSkills (o su copia instalada), sustituye `<DEVSKILLS>` por esa ruta:

```bash
# Excluir lo que no debe indexarse
cp <DEVSKILLS>/motor/graphify/plantilla.graphifyignore .graphifyignore

# Regenerar el grafo sin LLM y revisarlo antes de versionarlo
graphify update .
python <DEVSKILLS>/motor/graphify/revisar_grafo.py graphify-out
```

`revisar_grafo.py` acepta `--permitir REGEX ...` para falsos positivos conocidos (por ejemplo, un dominio de ejemplo en
la documentación). Si encuentra algo real, corrige la fuente (o amplía el `.graphifyignore`) y regenera; no edites el
grafo a mano.

## Hooks de sesión (opcional)

Agrega a `.claude/settings.json` del proyecto (o a `~/.claude/settings.json`):

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "python <DEVSKILLS>/motor/graphify/sesion_inicio.py" } ] }
    ],
    "PreToolUse": [
      { "matcher": "Bash|Grep", "hooks": [ { "type": "command", "command": "python <DEVSKILLS>/motor/graphify/hook_guard.py search" } ] },
      { "matcher": "Read|Glob", "hooks": [ { "type": "command", "command": "python <DEVSKILLS>/motor/graphify/hook_guard.py read" } ] }
    ]
  }
}
```

**El hook del `PreToolUse` debe ser Python, no bash (en Windows).** Un hook de bash lanza un `bash.exe` extra en CADA
llamada a herramienta de cada sesión y subagente; con agentes en paralelo la capa MSYS de Git Bash falla con
`add_item ... failed, errno 1` y las herramientas de Bash dejan de responder. Por eso se entrega `hook_guard.py`.

Variables: `GRAPHIFY_SESION=0` desactiva el resumen; `GRAPHIFY_SESION_AUTOUPDATE=1` lanza `graphify update .` en segundo
plano cuando el grafo está desactualizado (modifica `graphify-out/`, que suele estar versionado); `GRAPHIFY_SESION_MAX`
limita los caracteres del resumen; `GRAPHIFY_GUARDIA=0` desactiva el `hook-guard`. Crear un archivo `DESACTIVADO` junto a
cada script también los apaga.
