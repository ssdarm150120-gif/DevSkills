# Grafo de conocimiento con Graphify

DevSkills usa [Graphify](https://github.com/Graphify-Labs/graphify) (CLI `graphify`, paquete de PyPI `graphifyy`) para que el grafo del proyecto se mantenga al día con **el deber ser** (lo que dicen el SRS, el DISEÑO, el PLAN y el CONTEXTO) y con **lo que es** (el código), y para medir la distancia entre los dos.

Es **opcional**. Sin Graphify el método funciona igual: los agentes leen archivos como siempre y el cierre del sprint anota la deriva como verificación omitida. `devskills doctor` avisa si falta y cómo instalarlo; ningún agente lo instala.

```bash
uv tool install graphifyy      # o: pipx install graphifyy   (el paquete lleva doble y)
```

Versión probada: 0.9.96.

## Dos grafos por proyecto

| Grafo | Fuente | Comando (desde la raíz del proyecto) | LLM | Salida |
|-------|--------|--------------------------------------|-----|--------|
| **Lo que es** | `codigo/` | `GRAPHIFY_BACKEND=none graphify update codigo` | No (AST con tree-sitter, 0 tokens) | `codigo/graphify-out/` |
| **Deber ser**, estructural | Encabezados de `SRS.md`, `DISENO.md`, `PLAN.md`, `CONTEXTO.md` y `EVALUACION_ALTERNATIVAS.md` | `GRAPHIFY_BACKEND=none graphify update documentacion` | No (0 tokens) | `documentacion/graphify-out/` |
| **Deber ser**, semántico | Conceptos y relaciones del texto de esos documentos | `graphify extract documentacion --backend <backend>` | **Sí** | `documentacion/graphify-out/` |

`graphify update` no llama a ningún LLM: también nombra las comunidades del grafo por su nodo central. `GRAPHIFY_BACKEND=none` es un seguro extra para que ningún comando caiga en un LLM por accidente.

### Pasada semántica del deber ser: solo con permiso

El grafo estructural solo ve encabezados: lo que el DISEÑO declara en tablas (por ejemplo, el mapa de módulos o el catálogo de entidades) no aparece. La pasada semántica lee el texto, pero gasta un LLM, así que **por omisión no se genera**. La primera vez el orquestador le pregunta al Product Owner y el analista-arquitecto registra la decisión en `CONTEXTO.md` ("Pasada semántica del deber ser"):

| Opción | Comando | Costo | Privacidad |
|--------|---------|-------|------------|
| No autorizarla (por omisión) | — | 0 | — |
| **Ollama local** | `graphify extract documentacion --backend ollama` (modelo con `OLLAMA_MODEL`; servidor en `OLLAMA_BASE_URL`, por defecto `localhost:11434`) | Gratis | Nada sale del equipo |
| **claude-cli** | `graphify extract documentacion --backend claude-cli` | Consume la cuota de la suscripción de Claude Code (`claude -p`), sin API key | Los documentos van a Anthropic |
| **API key** | `ANTHROPIC_API_KEY` y `--backend claude` (u otro proveedor: Gemini, OpenAI, DeepSeek...) | Cobro por tokens | Los documentos van al proveedor |

Siempre con `--backend` explícito: sin él, `graphify extract` toma la primera API key que encuentre en el entorno. `graphify label` y `graphify cluster-only` sin `--no-label` también llaman a un LLM (y, sin API key, recurren solos a `claude -p`): necesitan la misma autorización.

## Dónde se actualizan en el ciclo

| Momento | Quién | Qué |
|---------|-------|-----|
| Primera sesión con `graphify` instalado | Orquestador | Genera los dos grafos sin LLM y su commit; pregunta al Product Owner por la pasada semántica |
| Tras el squash a `main` de cada elemento (y del cierre del sprint, si corrigió código) | Orquestador | `graphify update codigo`; commit aparte `chore(graph): refresh code graph after <ID>`, tras gitleaks |
| Pasada documental | Analista-arquitecto | `graphify update documentacion` (y la semántica, si está autorizada); commit `docs(graph): ...` |
| Apertura del cierre del sprint | Orquestador | `python documentacion/analisis/deriva_grafos.py --salida documentacion/avance/S{NN}/DERIVA-S{NN}.md` |
| QA de cierre | QA | Confirma cada candidato de la deriva; lo confirmado entra a la lista congelada como `OBS-S{NN}-n` |

## Consultar antes de leer (ahorro de tokens)

Dev, QA, Angel Fixer, verificador, analista y orquestador consultan el grafo **antes** de explorar en masa y después leen solo los archivos y líneas que el grafo cita:

```bash
graphify query "¿qué casos de uso cambian el estado del pedido?" --graph codigo/graphify-out/graph.json --budget 1500
graphify explain "Pedido" --graph codigo/graphify-out/graph.json        # un nodo, sus vecinos y dónde está
graphify path "Pedido" "Factura" --graph codigo/graphify-out/graph.json # camino más corto entre dos nodos
graphify affected "Pedido" --graph codigo/graphify-out/graph.json       # qué depende de él (alcance de un cambio)
```

Más `codigo/graphify-out/GRAPH_REPORT.md`: nodos centrales, comunidades, ciclos de importación y preguntas sugeridas. Son consultas de solo lectura y sin LLM; salen con 3 si el nombre es ambiguo (listan los candidatos) y con 4 si no hay nodo. El grafo refleja `main` al último merge: lo que cambió en la rama del elemento se ve con `git diff`.

Para cruzar código y diseño en una sola consulta: `graphify merge-graphs codigo/graphify-out/graph.json documentacion/graphify-out/graph.json --out graphify-out/merged-graph.json` (local, ignorado por git) y `--graph graphify-out/merged-graph.json`.

## Deriva entre el deber ser y lo que es

`documentacion/analisis/deriva_grafos.py` (biblioteca estándar; se copia a cada proyecto y se actualiza con `devskills sync-scripts`) lee los dos `graph.json` y escribe un reporte Markdown:

- **El diseño lo dice y el código no lo tiene (`D-n`):** encabezados que nombran un elemento del diseño (`Entidad X`, `Módulo n: X`, `HU-nn ...`, hijos de "Requisitos funcionales", "Máquinas de estado", "Flujos de integración", "Interfaces externas", "Algoritmos" y del catálogo de casos de uso) y, si hay pasada semántica, los conceptos del LLM, sin un identificador del código que los nombre.
- **El código lo tiene y el diseño no lo dice (`C-n`):** módulos y clases de `dominio/` (con `--todas-las-clases`, todas; con `--con-funciones`, también funciones) que ningún nodo del deber ser nombra. No cuentan pruebas, migraciones, `despliegue/` ni los módulos de infraestructura del esqueleto (`configuracion`, `herramientas`; `--ignorar-modulo` agrega otros).
- **Correspondencias débiles:** elementos con dos tercios o más de sus palabras en el vocabulario del código, para revisar.

La comparación normaliza nombres (sin acentos ni mayúsculas, `snake_case` y `CamelCase` partidos en palabras, plurales simples). Es una heurística: cada fila es un **candidato** que QA confirma antes de reportarlo. Códigos de salida: 0 reporte generado, 1 hay deriva con `--estricto`, 2 un grafo inválido, 3 falta un grafo (el mensaje dice cómo generarlo; la deriva no se midió).

## Versionado, merge y secretos

- Se versionan `graph.json` y `GRAPH_REPORT.md` de `codigo/graphify-out/` y `documentacion/graphify-out/`. Cachés, estado, memoria de consultas y `graph.html` (crece con el grafo y se regenera) quedan fuera por el `.gitignore` de la plantilla.
- **Merge driver:** el `.gitattributes` de la plantilla asigna `merge=graphify` a los `graph.json`, y `devskills init` deja en el clon `merge.graphify.name` y `merge.graphify.driver = graphify merge-driver %O %A %B` (unión de los dos grafos en vez de un conflicto). Quien clone el repositorio repite esos dos `git config`; `devskills doctor`, dentro del proyecto, avisa si faltan. **No** se usa `graphify hook install`: instala hooks que regeneran el grafo tras cada commit y dejan el árbol sucio después de cada punto de control.
- **Exclusiones en `.graphifyignore`** (raíz del proyecto, sintaxis de `.gitignore`; Graphify lo lee desde la raíz del repositorio git): `.env*`, llaves y archivos de credenciales, `.venv`, `node_modules`, cachés, datos de PostgreSQL, migraciones, `despliegue/`, y de `documentacion/` todo lo que no es el deber ser (`analisis/`, `sesiones/`, `presentacion/`, `word/`, `avance/`, `ui/`). En Graphify 0.9, `.graphifyrc` no sirve para excluir: solo admite `language.<ext>` y `viz_node_limit`.
- **gitleaks** (`scripts/gitleaks_archivos.py`) escanea lo versionado y lo nuevo no ignorado, así que cubre los grafos antes de cada commit que los incluya. Si encuentra algo en un grafo, no hay commit: se agrega la exclusión, se regenera el grafo y se rota el secreto.
- `codigo/.dockerignore` deja `graphify-out/` fuera de la imagen.
