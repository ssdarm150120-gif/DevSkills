# Contexto del proyecto: {{NOMBRE_PROYECTO}}

<!--
Lo carga la skill devskills:proyecto-contexto antes de cualquier tarea de desarrollo, QA o evaluación.
Las reglas generales (arquitectura hexagonal, cero deuda, git, Docker, DoR y DoD) viven en la skill;
aquí va SOLO lo propio de este proyecto. Lo llena el analista-arquitecto al terminar el SRS y el
DISEÑO, y lo actualiza en cada pasada documental. Nada de secretos ni datos personales aquí.
-->

| Campo | Valor |
|-------|-------|
| Proyecto | {{NOMBRE_PROYECTO}} |
| Slug (carpetas, Docker, engram) | `{{SLUG}}` |
| Proyecto de engram (`mem_save` / `mem_search`) | `{{SLUG}}` |
| Prefijo de Docker del stack principal (solo si usas Docker, que es opcional) | `{{SLUG}}` (los agentes usan `{{SLUG}}-<agente>`) |
| Rango de puertos del host | `{{PUERTO_BASE}}` a `{{PUERTO_BASE}} + 49` |
| Puertos reservados del host (nunca usarlos ni apuntar a ellos por defecto) | {{PUERTOS_RESERVADOS}} |
| Idioma | {{IDIOMA_DESCRIPCION}} (código `{{IDIOMA}}`; documentos, código, reportes y respuestas; prevalece sobre el estilo personal del usuario) |
| Canal de avisos | <!-- Telegram (claude --channels plugin:telegram@claude-plugins-official) o "ninguno" --> |
| Product Owner | <!-- nombre o rol --> |

## Fuentes de verdad (en este orden)

| Qué | Dónde | Regla |
|-----|-------|-------|
| Requisitos, casos de uso, historias, trazabilidad | `documentacion/SRS.md` (secciones 3 y 4, Anexos A, B y C) | Es el **QUÉ**. Nunca se contradice desde el código |
| Diseño técnico | `documentacion/DISENO.md` (D.1 a D.6, ADR) | Es el **CÓMO**. Un cambio de diseño que afecte requisitos va primero al SRS |
| Plan y backlog | `documentacion/PLAN.md` (P.2.2, generado), `documentacion/analisis/plan_entregas.json` y `documentacion/avance/estado_backlog.json` | El backlog **no se edita a mano**: se regenera con `documentacion/analisis/plan_sprints.py` |
| Avances y reportes | `documentacion/avance/S{NN}/{ID}.md` | Lo escribe la skill `devskills:registrar-avance` |
| Código | `codigo/` (monolito Django) | Las herramientas se ejecutan desde `codigo/`. Ningún archivo nuevo va en la raíz del repositorio |

Si algo no está en el SRS, **no se implementa**: se reporta como pregunta al Product Owner.

## Módulos y desarrollador asignado

<!-- Según DISENO D.1.2. Cada módulo tiene un dueño; los habilitadores (EN) van a quien sea dueño del
módulo que tocan. Dev A suele llevar dominio y datos (identidad, núcleo, integraciones de datos);
Dev B, canales, experiencia e interfaz. Ajusta según el proyecto. -->

| Desarrollador | Módulos (DISENO D.1.2) |
|---------------|------------------------|
| `devskills:dev-a` | `nucleo`, `identidad`, <!-- módulos --> |
| `devskills:dev-b` | <!-- módulos --> |

Habilitadores con dueño fijo: <!-- p. ej. EN-01 y EN-02 van a dev-a -->

## Ciclo de calidad: plataforma y elementos críticos

El orquestador usa esta lista para decidir qué elementos llevan el **ciclo completo por historia** (QA y Angel Fixer en paralelo antes del merge) en lugar del ciclo normal (revisión por historia y QA en el cierre del sprint). Reglas en `devskills:ciclo-historia`, sección "Clasificación".

| Criterio | Valor en este proyecto |
|----------|------------------------|
| Módulos de plataforma o núcleo compartido | `nucleo`, `identidad`, `configuracion`, `herramientas`, `despliegue/`, `.github/` <!-- agrega los módulos compartidos del proyecto --> |
| Riesgos de seguridad del SRS (`S-nn`) que fuerzan la excepción | <!-- p. ej. S-03, S-07 --> |
| Otros elementos críticos (decisión del orquestador o del Product Owner) | <!-- ID y motivo, p. ej. "HU-12: cobros" --> |

## Reglas de negocio que no se negocian

<!-- Las reglas del SRS que todo agente debe respetar aunque la historia no las repita. Cita el ID. -->
- <!-- regla (RF-..., R-...) -->

## Integraciones externas

| Sistema | Puerto (DISENO D.1.4) | Modo | Adaptador falso |
|---------|-----------------------|------|-----------------|
| <!-- sistema --> | <!-- `PuertoAlgo` --> | <!-- solo lectura / lectura y escritura --> | <!-- sí / no --> |

## Convenciones propias del proyecto

- Nombres de dominio **en español**, iguales a los del SRS: <!-- entidades principales -->.
- <!-- formatos (moneda, identificadores, teléfonos), zonas horarias, países -->
- **Nada propio de la empresa escrito en el código:** nombres, dominios, identificadores, horarios o cualquier dato del negocio van en configuración, no en constantes.

## Grafo de conocimiento (Graphify)

Dos grafos del proyecto con [Graphify](https://github.com/Graphify-Labs/graphify), para consultar antes de leer archivos en masa y para medir la **deriva** entre lo que el diseño dice y lo que el código hace. Son **opcionales**: sin `graphify` (lo instala la persona: `uv tool install graphifyy`) el método funciona igual, con lecturas normales, y el cierre del sprint anota la deriva como verificación omitida. Reglas completas en `devskills:proyecto-contexto`.

| Grafo | Fuente | Comando (desde la raíz) | Costo | Se actualiza |
|-------|--------|-------------------------|-------|--------------|
| **Lo que es** | `codigo/` | `GRAPHIFY_BACKEND=none graphify update codigo` | Sin LLM (AST), 0 tokens | Tras el squash a `main` de cada elemento y del cierre del sprint (orquestador) |
| **Deber ser** (estructural) | Encabezados de SRS, DISEÑO, PLAN, CONTEXTO y evaluación de alternativas | `GRAPHIFY_BACKEND=none graphify update documentacion` | Sin LLM, 0 tokens | En cada pasada documental (analista-arquitecto) |
| **Deber ser** (semántico) | Conceptos y relaciones del texto de esos documentos | `graphify extract documentacion --backend <backend>` | **Usa un LLM** | Solo si el Product Owner lo autorizó (abajo) |

| Decisión | Valor en este proyecto |
|----------|------------------------|
| Pasada semántica del deber ser | <!-- "no autorizada" (por omisión) / "ollama" / "claude-cli" / "API: <proveedor>"; quién decidió y fecha --> |

- **Pasada semántica:** por omisión **no se genera**, para no gastar sin permiso. La primera vez el orquestador se la pregunta al Product Owner con las opciones: **Ollama local** (gratis, nada sale del equipo; `--backend ollama`, modelo con `OLLAMA_MODEL`), **claude-cli** (usa la suscripción de Claude Code, sin API key; consume cuota del plan; `--backend claude-cli`) o **API key** (`ANTHROPIC_API_KEY` con `--backend claude`, u otro proveedor; cobro por tokens y los documentos salen al proveedor). Siempre con `--backend` explícito: sin él, Graphify toma cualquier API key del entorno. `graphify label` y `graphify cluster-only` sin `--no-label` también llaman a un LLM: solo con la misma autorización.
- **Versionado:** se versionan `graph.json` y `GRAPH_REPORT.md` de `codigo/graphify-out/` y `documentacion/graphify-out/`; `graph.html`, cachés y estado son locales (`.gitignore`). Commit aparte: `chore(graph): refresh code graph after <ID>` o `docs(graph): refresh design graph`.
- **Merge driver:** `.gitattributes` une los `graph.json` de dos ramas con `graphify merge-driver`. `devskills init` deja la configuración local; en un clon nuevo: `git config merge.graphify.name "graphify graph.json union merge"` y `git config merge.graphify.driver "graphify merge-driver %O %A %B"`. **No** uses `graphify hook install`: regenera el grafo tras cada commit y ensucia el árbol después de cada punto de control.
- **Nada sensible en el grafo:** `.graphifyignore` (raíz) deja fuera `.env*`, llaves, datos, migraciones, sesiones, Word y avance (`.graphifyrc` no sirve para excluir: solo admite `language.<ext>` y `viz_node_limit`). gitleaks (`gitleaks_archivos.py`) escanea los grafos versionados antes de cada commit que los incluya; si encuentra algo, no hay commit: se agrega la exclusión, se regenera el grafo y se rota el secreto.
- **Consultar antes de leer:** `graphify query "<pregunta>" --graph codigo/graphify-out/graph.json --budget 1500`, `graphify explain "<Nombre>" --graph ...`, `graphify path "<A>" "<B>" --graph ...`, `graphify affected "<Nombre>" --graph ...` y `codigo/graphify-out/GRAPH_REPORT.md`; después, solo los archivos y líneas que citan. El grafo refleja `main` al último merge: lo que cambió en la rama del elemento se lee con `git diff`.
- **Deriva (cierre del sprint):** `python documentacion/analisis/deriva_grafos.py --salida documentacion/avance/S{NN}/DERIVA-S{NN}.md`.

## Enrutamiento de modelos

**Opcional y local.** El orquestador (la sesión principal) puede elegir el modelo y el esfuerzo de cada subagente según su rol, en lugar de que todos usen el de su frontmatter: un escalón abajo del modelo más caro por omisión, el caro para lo de más riesgo y un solo reintento escalado cuando la verificación con código detecta una falla. Reglas completas en `devskills:ciclo-historia`, sección 6.

- **Archivo:** `.devskills/enrutamiento.json`, **local** (`.devskills/` está en el `.gitignore`; nunca entra a un commit). Si no existe o tiene `"activo": false`, todo funciona como siempre. El orquestador nunca cambia su propio modelo (rompe la caché).
- **Comandos:** `devskills enrutamiento evaluar` (¿encaja? recomendado / parcial / no recomendado; sin pruebas no hay cascada segura), `devskills enrutamiento activar` (crea la tabla por omisión; `--forzar` la reescribe), `devskills enrutamiento desactivar`, `devskills enrutamiento estado` (también en `devskills doctor`).
- **Fallos:** cada falla de un subagente enrutado y su reintento se anotan en `.devskills/enrutamiento-fallos.md` (local) y en engram; en la pasada documental y en el cierre del sprint el orquestador propone ajustar la tabla como decisión suya.

| Rol (clave de `tabla`) | Modelo | Esfuerzo por omisión |
|------------------------|--------|----------------------|
| `desarrollo` (dev-a, dev-b y sus subagentes, ciclo normal) | sonnet | medium |
| `desarrollo-excepcion` (los mismos, en la excepción) | sonnet | high |
| `angel-fixer-revision` (revisión por historia) | sonnet | medium |
| `angel-fixer-excepcion` y `qa-excepcion` (seguridad, plataforma, crítico) | opus | high |
| `qa-cierre-sprint` | opus | high |
| `verificador-ligero` / `verificador-final` | sonnet | medium / high |
| `analista-arquitecto` (SRS, DISEÑO, PLAN) | opus | medium |
| `pasada-documental`, `registrar-avance`, `mecanico` | haiku | low |
| Orquestador | no se enruta | — |

| Decisión | Valor en este proyecto |
|----------|------------------------|
| Enrutamiento de modelos | <!-- "inactivo" (por omisión) / "activo desde <fecha>"; quién decidió y veredicto de `devskills enrutamiento evaluar` --> |

## Entorno local

- El proyecto **nunca** apunta por defecto a un puerto reservado del host ({{PUERTOS_RESERVADOS}}).
- Docker es **opcional** (desarrollo y pruebas con PostgreSQL embebido y Celery local). Si se usa: el stack principal lleva el prefijo `{{SLUG}}`, cada agente `{{SLUG}}-<agente>`, y los puertos publicados van solo dentro del rango `{{PUERTO_BASE}}` a `{{PUERTO_BASE}} + 49`. Sobre el stack principal nadie corre `down -v` ni `prune`.
- <!-- cómo se levanta la base de desarrollo y la de pruebas (ver codigo/README.md) -->

## Decisiones vigentes del Product Owner que afectan el trabajo diario

<!-- Resumen corto con referencia al SRS o al DISEÑO (p. ej. "Python 3.12 en local y CI (SRS 2.7)"). -->
- <!-- decisión (versión) -->
