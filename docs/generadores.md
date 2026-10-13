# Generadores de contenido

Cada proyecto creado con DevSkills trae sus generadores en `documentacion/analisis/` y `documentacion/presentacion/`. Todos leen los datos del propio proyecto (SRS, PLAN, archivos JSON que llena el analista): nada del contenido está escrito en el código. Los comandos se corren **desde la raíz del proyecto**.

| Genera | Comando | Skill | Dependencias |
|--------|---------|-------|--------------|
| `PLAN.md` (sección generada) y tablero `plan_sprints.html` | `python documentacion/analisis/plan_sprints.py` | `planear-entregas`, `registrar-avance`, `pasada-documental` | Python 3.12 |
| Anexo C de trazabilidad del SRS | `python documentacion/analisis/trazabilidad.py _tmp.md --escribir` | `redactar-srs`, `pasada-documental` | Python 3.12 |
| Documentos Word con diagramas | `python documentacion/analisis/md_a_word.py --mermaid ~/.devskills/doc` | `pasada-documental` | `python-docx`, `pillow`, mermaid-cli |
| Presentación `.pptx` | `cd documentacion/presentacion && npm install && node generar_presentacion.js` | `generar-presentacion` | Node.js |
| Transcripción de la sesión | `python documentacion/analisis/exportar_sesion.py --ultima documentacion/sesiones/<archivo>.md "<título>"` | `guarda-todo` | Python 3.12 |
| Prompts de Figma Make | (plantilla) `documentacion/ui/prompts_figma_make.md` | `prompts-figma` | — |
| Evaluación de alternativas | (plantilla) `documentacion/EVALUACION_ALTERNATIVAS.md` | `evaluacion-alternativas` | — |

## Plan y tablero de sprints

- **Datos:** `documentacion/analisis/plan_entregas.json` (entregas en orden de prioridad con los puntos de cada elemento, habilitadores, velocidad, días por sprint y fecha de inicio), los títulos de las historias del SRS y el estado oficial de `documentacion/avance/estado_backlog.json`.
- **Salida:** reemplaza solo lo que está entre `<!-- INICIO BACKLOG GENERADO -->` y `<!-- FIN BACKLOG GENERADO -->` en `PLAN.md`, y genera `documentacion/plan_sprints.html`: indicadores, avance por entrega, sprints con su capacidad, tarjetas arrastrables, Gantt y exportación a CSV. Lo `Listo` sale **tachado** con su fecha y el enlace a su reporte.
- **Cuándo:** al cerrar cada elemento, en cada pasada documental y al repriorizar o recalibrar. Nunca se edita a mano.
- **Errores claros:** una historia vigente sin planificar, un elemento duplicado, un habilitador sin definir, una historia inexistente o retirada, o un ID del estado que no está en el plan.

## Anexo C de trazabilidad

- Lee los RF de la sección 3, los RNF de la sección 4, la columna "Requisitos" del catálogo de casos de uso y la línea "Trazabilidad" de cada historia; las verificaciones técnicas de los RNF y la lista de requisitos de fase 2 salen de `documentacion/analisis/trazabilidad.json`.
- Sin argumentos solo diagnostica; con `--escribir` reemplaza el Anexo C del SRS. El primer argumento es un archivo temporal de salida que puedes borrar después.

## Documentos Word

- Convierte SRS, DISEÑO, PLAN, prompts de Figma y la evaluación de alternativas a `documentacion/word/<Documento>_<Proyecto>.docx`. El nombre del proyecto se lee del SRS (o se pasa con `--proyecto`).
- Los bloques ```mermaid se convierten en imágenes con mermaid-cli y se guardan en caché en `documentacion/word/_diagramas/`. Sin mermaid-cli, avisa y deja el diagrama como bloque de código.
- `--solo DISENO` genera solo los documentos cuyo nombre contiene el filtro.

### Instalar las dependencias sin tocar nada global

```bash
mkdir -p ~/.devskills/doc && cd ~/.devskills/doc
python -m venv venv
venv/Scripts/python -m pip install python-docx pillow      # en macOS/Linux: venv/bin/python
npm install @mermaid-js/mermaid-cli
```

Para usar el Chrome que ya tienes en lugar de que puppeteer descargue otro: define `PUPPETEER_SKIP_DOWNLOAD=1` antes del `npm install` y crea `~/.devskills/doc/puppeteer.json`:

```json
{ "executablePath": "<ruta a chrome o chromium>" }
```

Después:

```bash
~/.devskills/doc/venv/Scripts/python documentacion/analisis/md_a_word.py --mermaid ~/.devskills/doc
```

## Presentación

- **Datos:** `documentacion/presentacion/datos_presentacion.json` (título, problema, línea base, solución, metas, plan, riesgos, lo que se necesita). La diapositiva del plan toma las fechas de `PLAN.md`.
- **Dependencia:** Node.js; `npm install` dentro de `documentacion/presentacion/` instala `pptxgenjs` en su `node_modules/` local (ignorado por git).
- **Salida:** `<Proyecto>_Propuesta_v<versión>.pptx` junto al generador, o la ruta que pases como segundo argumento. No se edita el `.pptx` a mano: se cambia el JSON, se sube la versión y se regenera.

## Transcripción de la sesión

- Convierte la transcripción de Claude Code (`~/.claude/projects/<carpeta codificada>/<sesión>.jsonl`) a Markdown legible.
- `--ultima` toma la sesión más reciente de la carpeta de trabajo actual; también puedes pasar la ruta de un `.jsonl`.
- `guarda-todo` corre gitleaks sobre el resultado antes de hacer commit.
