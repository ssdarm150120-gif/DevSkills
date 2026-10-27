# Orquestador local · diseño

Versión 2 (fase 2), 2026-10-27. Servicio local OPCIONAL del motor de DevSkills para que el usuario (y, más adelante, un asistente de voz y Telegram)
mande instrucciones a la sesión de Claude Code de cada proyecto del registro `proyectos.json` (en el directorio de
datos, `~/.devskills` o `DEVSKILLS_DATOS`; su estado vive en `<datos>/orquestador`), con inventario,
contexto de engram y un modelo de permisos con confirmación.

## 1. Las tres fases

| Fase | Qué agrega | Estado |
|---|---|---|
| 1 | Servicio `orquestador` en 127.0.0.1:18952 con API y token, inventario de proyectos (sesiones y configuración de Claude), búsqueda en engram, cola de instrucciones, modo lectura, cambios con confirmación e historial. Comando `orquestador` y `cliente.py`. | Hecha |
| 2a | Contexto con grafo (Graphify) para ahorrar tokens, `GET /api/grafo`, grafo en el inventario, propuestas de agente/skill/comando por instrucciones repetidas, resolución de proyecto desde texto libre (`GET /api/resolver`). Secciones 12 a 16. | Hecha |
| 2c | Enrutamiento de modelo por instrucción (sonnet para lecturas de proyectos con enrutamiento activo, escalamiento único a opus, `modelo` en la petición, `GET /api/enrutamiento`). Sección 15. | Hecha |
| 2b | Un asistente de voz o texto como **cliente** de la API: lee `.token`, llama a `POST /api/instruccion` y lee el resultado; para cambios le muestra o lee al usuario la solicitud pendiente y solo confirma con un "sí" explícito. El panel (18950) agrega una vista de instrucciones con el botón **Confirmar** y **Cancelar**. | Pendiente |
| 3 | Telegram: **un solo bot**, desactivado por omisión, activable **por proyecto** desde el panel. El bot es otro cliente de la API (no un canal de Claude Code): solo acepta el chat id del usuario y, para cambios, pide la confirmación en el panel o con un código de un solo uso. | Pendiente |

Decisión de arquitectura: el orquestador es el **único** proceso que lanza sesiones; voz, panel y Telegram son
clientes delgados de la misma API, así las reglas de permisos, la cola y el historial viven en un solo lugar.

## 2. Componentes

```
orquestador\
  orquestador.py        CLI: iniciar | servir | apagar | estado (lanza 'servir' en segundo plano con pythonw)
  cliente.py            cliente de prueba por terminal
  config.json           puerto, límites, presupuestos, política de sesión abierta, alias de engram
  nucleo\
    ajustes.py          carga de config.json y rutas (inyectables en pruebas)
    registro.py         lee proyectos.json (solo lectura; recarga si cambia; tolera campos nuevos)
    validacion.py       validación estricta de entradas
    sesiones.py         sesiones por proyecto, "última principal", detección de sesión abierta
    inventario.py       configuración de Claude por proyecto, solo nombres
    engram.py           búsqueda en engram en solo lectura (SQLite mode=ro)
    grafo.py            Graphify en solo lectura y sin LLM: estado, resumen y consulta (fase 2)
    texto.py            normalización y enmascarado deterministas (fase 2)
    resolver.py         proyecto más probable desde texto libre (fase 2)
    propuestas.py       instrucciones repetidas → propuestas de agente, skill o comando (fase 2)
    enrutamiento.py     modelo por instrucción, criterios de fallo, escalamiento y resumen de costos (fase 2c)
    permisos.py         herramientas por modo, reglas negadas y hook guardián
    ejecutor.py         cola, trabajadores, Agent SDK, historial
    api.py              servidor HTTP (stdlib)
  pruebas\              pytest sin red
  historial\            un JSON por instrucción
  enrutamiento-fallos.jsonl  una línea por escalamiento (sin el texto de la instrucción)
  propuestas\           ag-<id>.json por propuesta, analisis.json, version.json, cache_mensajes.json
  sesiones_propias.json IDs de sesiones creadas por el orquestador
  .token                {token, puerto, pid}; existe solo mientras corre
  orquestador.log       log rotativo (sin textos de instrucciones ni respuestas)
```

Dependencias: Python 3.12 con su propio venv (`devskills orquestador instalar` lo crea en `<datos>/orquestador/.venv`); `claude-agent-sdk==0.2.174` (trae el CLI 2.1.310, la misma versión
instalada) y `pytest`. El servidor HTTP es de la biblioteca estándar.

## 3. Flujo de una instrucción

1. `POST /api/instruccion {proyecto, texto, modo, nueva_sesion?, contexto?, modelo?}` con cabecera
   `X-Orquestador-Token` (`contexto`: `auto` por omisión, `sesion` o `grafo`, sección 12; `modelo`: `haiku`, `sonnet`
   u `opus`, sección 15).
2. Validación: proyecto en la lista blanca del registro, texto de 1 a 4000 caracteres sin caracteres de control,
   modo `lectura` o `cambios`, campos desconocidos rechazados. Ningún parámetro es una ruta: la carpeta sale del
   registro.
3. Modo **lectura**: queda `en_cola` (HTTP 202). Modo **cambios**: queda `pendiente_confirmacion` (HTTP 200) y **no
   se ejecuta**; expira a las 24 h.
4. Confirmación: `POST /api/instruccion/<id>/confirmar {"confirmacion": "<id>"}`. Repetir el id evita que un POST
   vacío o reenviado confirme por error. `POST .../cancelar` la descarta.
5. Un trabajador toma la instrucción (una a la vez por proyecto; `trabajadores: 1` por omisión por la memoria). En
   ese momento, no al recibirla, decide la sesión (sección 5).
6. Ejecuta con el Agent SDK de Python: `query(prompt, ClaudeAgentOptions(cwd=<carpeta>, resume=<id o None>, ...))`
   con tiempo límite (600 s), `max_turns` 25 y `max_budget_usd` por modo.
7. Guarda en `historial\<id>.json`: estado, sesión usada y motivo, respuesta, costo, tokens, turnos, duración,
   herramientas pedidas con su decisión, denegaciones y errores. `GET /api/instruccion/<id>` lo devuelve.

Estados: `pendiente_confirmacion`, `en_cola`, `ejecutando`, `completada`, `error`, `tiempo_agotado`,
`aviso_sesion_abierta`, `cancelada`, `expirada`, `interrumpida` (el servicio se reinició a media ejecución).

## 4. Permisos y confirmación

Modo lectura: solo Read, Grep y Glob dentro de la carpeta del proyecto. Modo cambios (solo tras confirmar): además
Edit, Write y NotebookEdit dentro de la carpeta. **Nunca** Bash/PowerShell, Agent, Skill, WebSearch ni MCP en esta
fase; WebFetch está apagado (`lectura_permite_webfetch: false`) porque una página o un archivo malicioso podría
inducir a mandar contenido del proyecto en una URL.

Capas (verificadas en la documentación oficial de permisos y hooks del Agent SDK; cualquiera basta para bloquear):

1. `tools=[...]`: el modelo solo ve las herramientas del modo.
2. `disallowed_tools`: nombres desnudos (Bash, Edit, Write, Agent, `mcp__*`, ...) que se quitan del contexto, más
   reglas `Read(**/.env)`, `Read(**/appsettings*.json)`, `Read(**/.git/**)`, etc. (Claude Code las aplica a Grep/Glob como mejor esfuerzo; no está garantizado).
3. `strict_mcp_config=True`, `mcp_servers={}`: ningún servidor MCP (ni `.mcp.json`, ni plugins como Telegram o
   engram, ni conectores de claude.ai). Así una sesión del orquestador nunca levanta otro lector del bot.
4. `permission_mode="dontAsk"`: lo no aprobado se niega; nunca se queda esperando una pregunta.
5. `allowed_tools=[]`: a propósito. Un `Read` desnudo en allowed_tools aprobaría lecturas en cualquier ruta.
6. Hook `PreToolUse` sin matcher (`guardian`): aprueba solo herramientas del modo, con rutas resueltas (siguiendo
   enlaces) dentro de la carpeta del proyecto y fuera de la lista de sensibles (`.env*`, `appsettings*.json`, llaves,
   `.git\`, `.ssh\`, `.token`, ...); niega patrones de Glob/Grep con `..`, rutas absolutas o nombres sensibles. Cada
   decisión queda en el historial.
7. `setting_sources=["project","local"]`: carga CLAUDE.md y settings del proyecto, no los del usuario (evita que los
   hooks de plugins del usuario escriban en engram o arranquen canales).

Prueba de que se cumple: `pruebas\test_permisos.py` (lectura nunca expone ni aprueba escritura/shell/MCP) y
`pruebas\test_ejecutor.py` (cambios sin confirmar no llega al ejecutor; confirmada, expirada o cancelada).

## 5. Sesión: reanudar o nueva (fase 1; en la fase 2 la decide además `contexto`, sección 12)

- **Última sesión principal**: la más reciente de las carpetas del proyecto (carpeta y campo `transcripts` del
  registro, con comodines) según `claude_agent_sdk.list_sessions`, excluyendo las creadas por un SDK (entrypoint
  `sdk-*`) y las de `sesiones_propias.json`.
- **¿Está abierta?** Sí si aparece en `claude agents --json` (lista sesiones interactivas y en segundo plano activas;
  existe en el CLI 2.1.310) **o** su transcript cambió hace menos de 120 s. Si `claude agents` falla, queda solo la
  heurística y el resultado lo dice (`deteccion`).
- **Sesiones protegidas** (`config.json`): nunca se reanudan (hoy, la conversación del orquestador db6a48ab).
- **Decisión (la más segura)**: si está abierta o protegida, **no se reanuda** y se crea una **sesión nueva** en la
  carpeta del proyecto, con un resumen de títulos recientes de engram como contexto, y la respuesta explica el
  motivo. Nunca se ejecuta `claude stop` sobre una sesión del usuario. Con `politica_sesion_abierta: "aviso"` no se
  ejecuta nada y queda `aviso_sesion_abierta`.
  - Descartado: reanudar igual (los mensajes se mezclan con la terminal abierta) y `fork_session` de la sesión
    abierta (copia un transcript que se está escribiendo, posiblemente con un tool_use sin resultado, y carga todo su
    contexto, lo que cuesta mucho).
- Al reanudar, el intercambio queda dentro de la sesión del usuario: lo verá al abrirla con `claude --resume`.
- `nueva_sesion: true` en la petición fuerza una sesión nueva.

## 6. Inventario (sin secretos)

`GET /api/inventario` y `/api/inventario/<proyecto>`: sesiones (total, última principal con estado de apertura,
5 recientes con título, fecha, tamaño y entrypoint), y de la configuración de Claude solo **nombres y conteos**:
CLAUDE.md/AGENTS.md (existe, tamaño, fecha; nunca el contenido), servidores de `.mcp.json`, agentes de
`.claude\agents`, skills de `.claude\skills`, settings (claves, plugins habilitados, número de reglas allow/deny/ask,
eventos de hooks) y de `~/.claude.json` solo los nombres de servidores MCP por proyecto y del usuario. Nunca valores
de `env`, `args`, URLs, comandos de hooks ni prompts guardados (`lastSessionFirstPrompt`). Probado en
`pruebas\test_inventario.py` con secretos sembrados.

## 7. Engram (solo lectura)

Opciones evaluadas: `engram search` (CLI de texto, sin JSON, y consulta actualizaciones por red), `engram serve`
(HTTP 7437, otro proceso residente), `engram mcp` (stdio, pensado para agentes) y la base SQLite. Se eligió abrir
`~/.engram/engram.db` con URI `mode=ro`: garantiza que el proceso no puede escribir y usa la misma tabla FTS5 que
`engram search`. Cada término se cita (sin sintaxis FTS del usuario), se filtra por proyecto (alias en `config.json`,
p. ej. `calculadora` → `calculadora-envio`; el alias se escribe en el `config.json` del orquestador), `scope='project'` y no borradas, y se ocultan valores con forma de
secreto. Riesgo: depende del esquema de engram 1.12; si cambia, la API responde 503 "engram no disponible".

## 8. API

Todas exigen `X-Orquestador-Token` salvo `GET /api/ping`. Host debe ser `127.0.0.1:<puerto>` o `localhost:<puerto>`
(anti DNS rebinding) y, si llega `Origin`, el mismo origen. Cuerpo JSON de máximo 16 KB.

| Método y ruta | Uso |
|---|---|
| GET /api/ping | `{"orquestador": true}` |
| GET /api/estado | puerto, cola, proyectos, engram |
| GET /api/inventario | todos los proyectos (resumen) |
| GET /api/inventario/<proyecto> | detalle con sesiones recientes |
| POST /api/instruccion | `{proyecto, texto, modo, nueva_sesion?}` → registro con `id` |
| GET /api/instruccion/<id> | estado, sesión, respuesta, costo, tokens |
| GET /api/instrucciones | últimas 50 (resumen) |
| POST /api/instruccion/<id>/confirmar | `{"confirmacion": "<id>"}` |
| POST /api/instruccion/<id>/cancelar | pendiente o en cola |
| GET /api/contexto/<proyecto>?q= | búsqueda en engram del proyecto (sin q: las más recientes) |
| GET /api/grafo/<proyecto>?q= | estado, resumen y consulta al grafo (sin LLM, recortada y enmascarada) |
| GET /api/enrutamiento | proyectos con enrutamiento activo, costos por modelo y tasa de escalamiento (del historial) |
| GET /api/resolver?texto= | proyecto más probable desde texto libre, con puntaje y candidatos |
| GET /api/propuestas-agentes?estado=&desde= | propuestas (filtro por estado y por versión) |
| GET /api/propuestas-agentes/version | `{version, actualizada, pendientes, total}` (consulta barata del panel) |
| GET /api/propuestas-agentes/<id> | una propuesta |
| POST /api/propuestas-agentes/analizar | `{}` → recalcula |
| POST /api/propuestas-agentes/<id>/crear | `{"confirmacion": "<id>", "destino": "general"\|"proyecto", "proyecto"?, "tipo"?}` |
| POST /api/propuestas-agentes/<id>/descartar | `{}` o `{"motivo": "..."}` |
| POST /api/apagar | apaga el servicio |

Puerto 18952 (rango de herramientas 18950-18999); si está ocupado usa el siguiente libre y `orquestador` lo
reporta. El socket usa `SO_EXCLUSIVEADDRUSE` (en Windows `SO_REUSEADDR` permitiría que otro proceso compartiera el
puerto). El token se genera en cada arranque y solo vive en `.token` (no se imprime).

## 9. Costos y tokens

- Cada instrucción es un proceso del CLI y una llamada al modelo; el SDK devuelve `total_cost_usd`, `usage` y
  `model_usage` (estimaciones del cliente, no factura) y se guardan en el historial.
- Prueba real (sesión nueva, sca-maestria-unir): 0.13 USD, 4 turnos, 8.5 s, ~39 mil tokens de entrada (14 mil de
  caché nueva). Casi todo es el prompt de sistema y las herramientas.
- **Reanudar una sesión larga cuesta mucho más**: se vuelve a mandar todo su contexto, y si la caché expiró se paga
  como caché nueva. Por eso hay `max_budget_usd` (2 USD lectura, 4 USD cambios; el SDK puede pasarse un poco),
  `max_turns` 25 y tiempo límite de 600 s. Si el costo preocupa, `nueva_sesion: true` es la opción barata.
- `modelo: null` usa el modelo por omisión de la cuenta; se puede fijar uno más barato en `config.json`.

## 10. Riesgos

| Riesgo | Mitigación |
|---|---|
| Mezclar mensajes con una terminal abierta | Detección doble (claude agents + actividad) y sesión nueva; protegidas nunca se reanudan. La detección por actividad puede fallar con una terminal abierta e inactiva más de 120 s si `claude agents` no está disponible. |
| Escritura en modo lectura | Siete capas (sección 4) y pruebas. |
| Leer secretos con Grep sin ruta | Reglas `Read(...)` negadas que el CLI aplica a Grep/Glob como mejor esfuerzo, y el guardián para rutas y patrones explícitos. Riesgo residual: un archivo sensible con nombre fuera de la lista. |
| Inyección de instrucciones desde archivos del repo o engram | Sin shell, sin red, sin MCP y sin escritura en lectura; engram se marca como datos. En cambios, el usuario confirmó el texto, pero el modelo podría editar algo inesperado dentro de la carpeta: el historial lista las herramientas y el repo tiene git. |
| Hooks de settings del proyecto | Se cargan `project` y `local` (son del usuario); si un proyecto tiene hooks con efectos, corren también aquí. |
| Otro proceso en el puerto o token robado | Solo 127.0.0.1, `SO_EXCLUSIVEADDRUSE`, token aleatorio por arranque en la carpeta del usuario, chequeo de Host/Origin. |
| Memoria | Un trabajador: un proceso pesado a la vez. |
| Cambios de esquema de engram o de la salida de `claude agents` | Degradan con un aviso (503 / `deteccion: solo actividad`), no tumban el servicio. |

## 11. Qué NO hace (fases 1 y 2)

- No modifica `proyectos.json`, `servicios.py`, el panel, los repos de proyecto ni a ningún asistente cliente.
- No escribe en engram ni en los transcripts (salvo que Claude agrega el turno a la sesión reanudada o crea la nueva).
- No ejecuta comandos (ni en modo cambios), no hace commits ni push, no usa MCP ni red.
- No hace `claude stop` ni se conecta a sesiones en segundo plano.
- No escucha fuera de 127.0.0.1 ni acepta órdenes de nadie sin token; no hay Telegram ni voz todavía.
- No transmite la respuesta en vivo (se consulta por id).
- No genera ni actualiza grafos (`graphify update` es del usuario o de los hooks); solo los lee. Nunca llama a un LLM
  desde graphify (`GRAPHIFY_BACKEND=none`).
- No crea agentes, skills ni comandos por su cuenta: solo cuando el usuario confirma una propuesta, y nunca hace commit
  del archivo creado en un repo de proyecto.

## 12. Contexto con grafo (fase 2)

Problema: reanudar una sesión larga reenvía todo su contexto (cientos de miles de tokens; si la caché expiró se paga
como caché nueva). Solución: una sesión NUEVA en la carpeta del proyecto, sembrada con un bloque compacto.

- `contexto: "sesion"`: comportamiento de la fase 1 (reanuda la última principal si está cerrada).
- `contexto: "grafo"`: siempre sesión nueva con el bloque.
- `contexto: "auto"` (por omisión): `grafo` si la última principal está abierta o protegida, o si es grande
  (`contexto_auto.umbral_mb` 2 MB del transcript o `umbral_tokens` 150 000 tokens de contexto, estimados con el
  `usage` del último mensaje del asistente: entrada + caché leída + caché creada, leyendo solo el final del archivo);
  si es chica y está cerrada, `sesion`. `nueva_sesion: true` equivale a `grafo`; con `contexto: "sesion"` se rechaza.
- Toda sesión nueva (también la que se abre porque la principal está abierta) se siembra con el bloque.
- Bloque (máximo `grafo.contexto_max_chars`, 10 000): resumen de GRAPH_REPORT.md (tamaño, nodos centrales y
  comunidades; `resumen_chars` 1 500), resultado de `graphify query "<instrucción>" --budget N` (`presupuesto_chars`
  6 000), la REGLA de consultar el grafo antes de leer archivos (con Grep sobre graph.json o leyendo el reporte, porque
  la sesión no tiene Bash) y hasta 8 entradas de engram (búsqueda con la instrucción + recientes). Sin grafo, el bloque
  pide usar Glob/Grep acotados. Todo marcado como DATOS, no instrucciones.
- El registro guarda `contexto` (pedido) y `contexto_usado` (`modo`, `solicitado`, `motivo`, `estimacion`, `grafo`,
  `consulta`, `engram`, `caracteres`), además del costo de siempre.
- Graphify: `graphify query/explain/path` con lista de argumentos (sin shell), `GRAPHIFY_BACKEND=none`, tiempo
  límite, salida recortada y enmascarada (rutas absolutas, IDs, secretos). La pregunta se limpia (sin acentos ni
  guiones iniciales, 300 caracteres).
- Vigencia del grafo: GRAPH_REPORT.md dice el commit con el que se construyó; se compara con `git rev-parse HEAD` y
  `git diff --name-only <commit> HEAD` sin contar graphify-out, .gitignore, .gitattributes ni .graphifyignore.
  Resultado en el inventario (`grafo`: `tiene_grafo`, `fecha`, `nodos`, `commit_grafo`, `commit_git`,
  `desactualizado` true/false/null, `motivo`, `archivos_cambiados`, `cambios_sin_commit`), con caché de 60 s.
- Costo medido (2026-10-27, modo lectura, contexto `grafo`, worktree Dashboard-wt-graphify-light, pregunta sobre el
  cálculo del cumplimiento de presupuesto): 0.20 USD, 3 turnos, 8.5 s, 2 lecturas, ~42 mil tokens de entrada (22.8 mil
  de caché nueva), bloque de 7 275 caracteres. La fase 1 costó 0.13 USD con una pregunta trivial y sin bloque. La
  comparación que importa es contra reanudar: una sesión principal larga puede tener ~136 mil o ~440 mil tokens de
  contexto; reanudarla reenvía todo eso en cada instrucción.

## 13. Instrucciones repetidas → propuestas de agente, skill o comando (fase 2)

- Fuentes: `~/.claude/projects/*/*.jsonl` (solo el hilo principal) y `historial\`. Del transcript se toman solo
  mensajes `type: user` escritos por el usuario: se excluyen tool_result, `isMeta`, `isSidechain`, resúmenes de
  compactación, notificaciones de tareas, comandos `/x` y sus salidas, recordatorios del sistema, prompts del
  orquestador, sesiones con entrypoint `sdk-*` y las de `sesiones_propias.json`. Se quita lo pegado
  (`<pasted_content>`, bloques de código, prompts de terminal) y se descartan los mensajes que siguen largos
  (`max_caracteres` 1 200), con muchos símbolos (salidas pegadas) o con menos de `min_palabras` (2) palabras de
  contenido. Los mensajes de Telegram (`<channel ...>`) sí cuentan. Caché por archivo (tamaño + fecha).
- Normalización: minúsculas, sin acentos, sin rutas/URLs/correos/IDs/números, sin palabras vacías ni relleno; raíz
  burda (sin plural, 6 letras). Proyecto de cada mensaje por su `cwd` contra las carpetas del registro.
- Agrupación determinista sin LLM: TF-IDF de raíces y bigramas, orden fijo por fecha, agrupamiento por líder con
  centroide y coseno ≥ `umbral_similitud` (0.4, calibrado con los transcripts reales: 0.5 separaba variantes obvias).
- Propuesta si `veces ≥ min_veces` (3) o `conversaciones ≥ min_conversaciones` (2). Alcance: `conversacion`,
  `proyecto` o `general` (varios proyectos).
- Tipo recomendado (`recomendar_tipo`, reglas en orden): **comando** si la petición es corta (≤ 6 palabras de
  contenido) y casi idéntica (≤ 50 % de variantes) o solo dispara una operación de terminal; **agente** si pide delegar
  una tarea completa (revisar, analizar, implementar, investigar...) o es larga y necesita editar o ejecutar;
  **skill** en otro caso (mismo procedimiento o reglas aplicados en la conversación principal). Cada propuesta lleva
  los tres borradores (formatos verificados en la documentación oficial de Claude Code: subagente con
  `name/description/tools`; skill `SKILL.md` con `name/description`; comando `.claude/commands/<n>.md` con
  `description`, `argument-hint`, `disable-model-invocation: true` y `$ARGUMENTS`), el recomendado, el porqué
  (`motivo_tipo`), herramientas mínimas sugeridas y un `mensaje` corto para la burbuja del chat del panel.
- Persistencia: `propuestas\ag-<id>.json` (id = hash de las firmas del grupo). Al recalcular, un grupo que comparte
  ≥ 50 % de firmas con una propuesta existente la actualiza si está pendiente; si ya fue aceptada o descartada no se
  reabre ni se duplica (solo se recuerdan las firmas nuevas). `version.json` sube con cada propuesta nueva, actualizada
  o decidida; cada propuesta guarda su `version` y `GET ...?desde=N` devuelve solo lo que cambió después de N.
- Recalcula sola cada `cada_h` (12) horas, empezando `retraso_inicial_min` (10) minutos después de arrancar, y nunca
  mientras corre o espera una instrucción (memoria escasa). Tarda menos de 1 s con caché.
- Crear (`POST .../crear`, repitiendo el id): escribe SOLO en `~/.claude/{agents/<n>.md, skills/<n>/SKILL.md,
  commands/<n>.md}` (general) o `<carpeta del proyecto>/.claude/...` (proyecto). Nombre `^[a-z0-9]+(-[a-z0-9]+)*$`
  (máx. 64), creación exclusiva (`open(..., "x")`; nunca sobrescribe), carpeta resuelta (enlaces) dentro del destino,
  y una skill y un comando con el mismo nombre se rechazan. En proyecto, el archivo queda sin commit (se avisa).

## 14. Resolución de proyecto desde texto libre (fase 2)

`GET /api/resolver?texto=` (máx. 500 caracteres). Nombres por proyecto: id, nombre del registro y
`alias_proyectos` de config.json. Puntaje: frase exacta 0.85-1.0; todas las palabras separadas 0.82-0.97; difuso
(difflib ≥ 0.75) × 0.8. Un alias contenido en el alias más largo de otro proyecto ("kpis" en "kpis acme") se
penaliza. Resuelve si el mejor ≥ 0.6 y le saca 0.1 al segundo; si no, `ambiguo: true` con candidatos.

## 15. Enrutamiento de modelo (fase 2c)

Según el Model Routing Playbook: por omisión un escalón abajo del más caro, escalar UNA vez si falla y registrar los
fallos.

- **Activación por proyecto**: `proyectos.json` → `enrutamiento: {"activo": bool, "evaluacion": {...},
  "actualizado": ISO}`. Lo escribe el panel; el orquestador solo lo lee (`Proyecto.enrutamiento_activo`, verdadero
  únicamente si `activo` es el booleano `true`).
- **Precedencia**: (1) `modelo` en la petición (lista blanca `haiku`/`sonnet`/`opus`; no se escala); (2) enrutamiento
  activo: lectura → `sonnet` con `effort="medium"`, cambios → `opus`; (3) si no, `config.json → modelo` (null = el de la
  cuenta), como en la fase 1. Configurable en `config.json → enrutamiento` (`lectura`, `cambios`,
  `esfuerzo_lectura`, `escalar_a`, `min_caracteres`).
- **SDK verificado** (claude-agent-sdk 0.2.174): `ClaudeAgentOptions.model` se pasa tal cual a `--model` (el CLI
  acepta los alias `haiku`, `sonnet`, `opus`) y `ClaudeAgentOptions.effort` es `Literal["low","medium","high","xhigh",
  "max"]` → `--effort`. Prueba sin red: `test_sdk_recibe_model_y_effort`.
- **Fallo** (determinista, en orden): estado distinto de `completada` (error, tiempo agotado, presupuesto o turnos
  agotados); respuesta vacía o de menos de 20 caracteres; respuesta corta (< 600 caracteres) que en sus primeros 300
  dice que no pudo ("no pude", "no fue posible", "no tengo acceso", "I was unable", "unable to"...). Una respuesta
  larga que menciona un "no pude" puntual no cuenta como fallo.
- **Escalamiento**: solo lecturas enrutadas; un único reintento con `opus` sin esfuerzo forzado, con la misma
  decisión de sesión (si era nueva, otra sesión nueva; la del intento fallido se registra como propia). Se registra
  en el historial (`intentos`, `escalado`, `motivo_escalamiento`) y en `enrutamiento-fallos.jsonl` (`fecha, id,
  proyecto, modo, modelo, esfuerzo, motivo, costo_usd, escalado_a, estado_final, fallo_tras_escalar`).
- **Respuesta de la instrucción**: `modelo` (pedido), `modelo_decision` (`modelo, esfuerzo, origen:
  parametro|enrutamiento|config, enrutamiento_activo, escalable`), `modelo_usado` (alias final, o el id real si no se
  forzó), `modelo_real` (id del modelo que más costó según `model_usage`), `escalado`, `motivo_escalamiento`,
  `intentos` (`modelo, esfuerzo, estado, costo_usd, num_turnos, duracion_ms, session_id, modelo_real, uso, fallo`) y
  `costo_usd` = suma de los intentos.
- **Costo medido** (2026-10-27, misma instrucción de lectura, contexto `grafo`, worktree Dashboard-wt-graphify-light):
  Opus 0.20 USD (3 turnos, 8.5 s) frente a Sonnet con esfuerzo medio 0.11 USD (4 turnos, 12.3 s, sin escalar), con una
  respuesta equivalente y algo más detallada: ~46 % menos.

## 16. Pendiente para fases 2b y 3

- Fase 2b: cliente de un asistente de voz (puede usar `/api/resolver` para elegir el proyecto y `contexto: "auto"`) (lectura del `.token`, tiempo de espera y lectura en voz de la respuesta);
  vista en el panel con Confirmar/Cancelar; opcional: al crear una solicitud de cambios, generar antes un plan en
  modo lectura para que el usuario confirme sabiendo qué se va a tocar; opcional: lista blanca de comandos de Bash
  (p. ej. pruebas) para modo cambios, con su propia confirmación.
- Fase 3: bot de Telegram único, apagado por omisión, con activación por proyecto guardada por el panel; solo el chat
  id del usuario; los cambios se confirman en el panel o con código de un solo uso.
- Panel: burbuja de propuestas (consulta `/api/propuestas-agentes/version` y luego `?desde=`), botones Crear
  (con tipo y destino) y Descartar.
- Ambas: eventos en vivo (SSE) del progreso, y reanudar con `fork_session` cuando la sesión principal esté cerrada
  pero el usuario no quiera ensuciarla.
