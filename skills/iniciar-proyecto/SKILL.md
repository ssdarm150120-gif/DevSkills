---
name: iniciar-proyecto
description: >
  Arranca un sistema nuevo con DevSkills: descubrimiento con el Product Owner (problema, actores, línea base
  medible, metas, restricciones, integraciones), creación de la carpeta del proyecto con la estructura exacta
  del método (código con el esqueleto del stack fijo, documentación con SRS, DISEÑO, PLAN y CONTEXTO vacíos,
  avance, análisis con los scripts), git init y primer commit. Trigger: "/devskills:nuevo-proyecto",
  "nuevo proyecto", "iniciar un sistema", "arrancar un proyecto".
license: Apache-2.0
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- El usuario quiere construir un sistema nuevo desde cero con la metodología DevSkills.
- No aplica a un repositorio que ya tiene código: ahí se adapta a mano con el `analista-arquitecto`.

## Critical Patterns

### Fase 1. Descubrimiento con el Product Owner (antes de crear nada)
Lo conduce el orquestador con el `analista-arquitecto`, preguntando con `devskills:preguntar-al-po` y **esperando cada respuesta**. Orden estricto: no se pasa al siguiente bloque sin cerrar el anterior.
1. **Identidad:** nombre del sistema, organización (solo para la configuración, nunca en el código), Product Owner, idioma (por defecto español de México).
2. **Problema de negocio (la necesidad real):** qué duele hoy, a quién, cuándo y cuánto cuesta; cuál es el objetivo principal y qué funciones solo lo apoyan.
3. **Línea base medible:** qué indicadores muestran el problema y cómo medirlos hoy con datos reales. Si hay sistemas fuente, se escriben consultas **de solo lectura** y un script o notebook de medición en `documentacion/analisis/`, con sus limitaciones de la medición. Los datos con información personal o de la empresa **no se versionan**. Sin línea base no hay metas.
4. **Metas medibles:** indicador → línea base → meta (con la fecha o el sprint en que se mide).
5. **Actores y clases de usuarios:** roles internos y externos, sistemas externos, temporizadores; volumen de usuarios; quién es el usuario principal.
6. **Alcance:** qué entra en el MVP, qué va a fases siguientes y qué queda fuera.
7. **Restricciones (`R-nn`):** legales, de privacidad, de canales, de sistemas de solo lectura, de infraestructura.
8. **Integraciones:** cada sistema externo, el sentido (lectura o escritura), el mecanismo y quién da los accesos; si un producto existente podría resolverlo, se evalúa comprar o construir (skill `devskills:evaluacion-alternativas`).
9. **Supuestos y riesgos (`S-nn`):** dependencias externas (cuentas, servidores, permisos) y riesgos aceptados.
10. **Entorno de la máquina de desarrollo:** puertos del host ya ocupados por otros servicios (por ejemplo, otro PostgreSQL en `5432`) → `--puertos-reservados`; un rango libre de 50 puertos para el proyecto → `--puerto-base`; prefijo de Docker (el slug).
11. **Stack:** es **fijo** (Python 3.12, Django 5 + DRF, monolito modular hexagonal, PostgreSQL 16, Redis, Celery con worker, worker-outbox y beat, nginx con TLS, Docker Compose, HTMX). Solo se pregunta si hace falta un servicio interno separado (por ejemplo, FastAPI para cálculos o modelos).

Todo lo que no se pueda responder queda como pregunta `P-nn` abierta para el SRS.

### Fase 2. Crear la carpeta del proyecto
Ejecuta el script del plugin (Python 3.12, solo librería estándar):

```bash
python "${CLAUDE_SKILL_DIR}/scripts/crear_proyecto.py" --destino <ruta-del-proyecto> --nombre "<Nombre del sistema>" --slug <slug> --puerto-base <N> --puertos-reservados 5432 --autor "<Autor>"
```

- `--slug`: minúsculas, `[a-z][a-z0-9-]*`; es el prefijo de Docker, el nombre del proyecto de Compose y el project de engram.
- `--puerto-base`: inicio de un rango de 50 puertos libres del host (no privilegiados y sin puertos reservados).
- El script se niega si el destino existe y no está vacío; copia la estructura, sustituye los marcadores, hace `git init -b main` y el primer commit `chore: bootstrap project from devskills` (sin atribución de IA). Con `--sin-git` omite git.

Estructura resultante (la misma del proyecto modelo):
```
<proyecto>/
├── AGENTS.md                      equipo de agentes y reglas del repositorio
├── .gitignore  .gitattributes  .github/workflows/ci.yml  .github/dependabot.yml
├── codigo/                        esqueleto del stack fijo (configuracion, nucleo, identidad, herramientas, despliegue…)
└── documentacion/
    ├── SRS.md  DISENO.md  PLAN.md  CONTEXTO.md
    ├── analisis/                  plan_sprints.py (+ plantilla HTML), trazabilidad.py, md_a_word.py, exportar_sesion.py
    ├── avance/                    README.md (índice), estado_backlog.json
    ├── ui/prompts_figma_make.md
    ├── presentacion/  sesiones/  word/
```
No hace falta `.claude/`: el plugin aporta los agentes y las skills.

### Fase 3. Primeros documentos
1. El `analista-arquitecto` llena `documentacion/CONTEXTO.md` con lo del descubrimiento (módulos y asignación Dev A / Dev B quedan "por definir" hasta el DISEÑO).
2. Vuelca el descubrimiento al SRS versión 0.1 (skill `devskills:redactar-srs`): sección 1 (problema, línea base, metas), 2 (actores, restricciones, supuestos) y 6 (preguntas abiertas).
3. Commit `docs: discovery and SRS 0.1` y `mem_save` con el resumen del descubrimiento.

### Fase 4. Siguientes pasos (flujo completo)
1. SRS hasta la línea base de requisitos: RF, RNF, Anexo A, Anexo B con Gherkin, Anexo C (`devskills:redactar-srs`).
2. DISEÑO (`devskills:redactar-diseno`): módulos y su grafo de dependencias (que se vuelve `configuracion/modulos.py`), puertos, datos, estados, eventos, despliegue y ADR.
3. PLAN (`devskills:planear-entregas`): Entrega 0 de cimientos y entregas por valor; tablero con `plan_sprints.py`.
4. Entrega 0: los habilitadores de cimientos adaptan el esqueleto al proyecto (módulos del DISEÑO en `modulos.py` y contratos regenerados, catálogo de roles y matriz de permisos, puertos y falsos de las integraciones, Compose) y pasan el ciclo completo (`devskills:ciclo-historia`).
5. Ciclo por historia hasta cerrar cada entrega; `devskills:guarda-todo` al terminar cada sesión.

## Commands

```bash
python "${CLAUDE_SKILL_DIR}/scripts/crear_proyecto.py" --help
```
