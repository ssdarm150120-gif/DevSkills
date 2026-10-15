---
name: iniciar-proyecto
description: >
  Arranca un sistema nuevo con DevSkills: descubrimiento con el Product Owner (problema, actores, línea base
  medible, metas, restricciones, integraciones), creación de la carpeta del proyecto con la estructura exacta
  del método (código con el esqueleto del stack fijo, documentación con SRS, DISEÑO, PLAN y CONTEXTO vacíos,
  avance, análisis con los scripts), git init y primer commit. Trigger: "/devskills:nuevo-proyecto",
  "nuevo proyecto", "iniciar un sistema", "arrancar un proyecto".
license: MIT
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
3. **Línea base medible:** qué indicadores muestran el problema y cómo medirlos hoy con datos reales. Si hay sistemas fuente, se escriben consultas **de solo lectura** y un script o notebook de medición en `documentacion/analisis/`, con sus limitaciones de la medición. **Autorización antes de tocar datos reales:** medir contra un sistema fuente o cualquier dato real del negocio requiere la **autorización expresa del usuario** (qué sistema, qué consultas y qué periodo), siempre en solo lectura y con las credenciales que él te dé por una variable de entorno o un archivo que él indique. **Nunca leas `.env` ni `.env.*`** para conseguirlas; sin autorización, la línea base queda como pregunta `P-nn` abierta. Los datos con información personal o de la empresa **no se versionan**. Sin línea base no hay metas.
4. **Metas medibles:** indicador → línea base → meta (con la fecha o el sprint en que se mide).
5. **Actores y clases de usuarios:** roles internos y externos, sistemas externos, temporizadores; volumen de usuarios; quién es el usuario principal.
6. **Alcance:** qué entra en el MVP, qué va a fases siguientes y qué queda fuera.
7. **Restricciones (`R-nn`):** legales, de privacidad, de canales, de sistemas de solo lectura, de infraestructura.
8. **Integraciones:** cada sistema externo, el sentido (lectura o escritura), el mecanismo y quién da los accesos; si un producto existente podría resolverlo, se evalúa comprar o construir (skill `devskills:evaluacion-alternativas`).
9. **Supuestos y riesgos (`S-nn`):** dependencias externas (cuentas, servidores, permisos) y riesgos aceptados.
10. **Entorno de la máquina de desarrollo:** puertos del host ya ocupados por otros servicios (por ejemplo, otro PostgreSQL en `5432`) → `--puertos-reservados`; un rango libre de 50 puertos para el proyecto → `--puerto-base`; prefijo de Docker (el slug).
11. **Stack:** es **fijo** (Python 3.12, Django 5 + DRF, monolito modular hexagonal, PostgreSQL 16, Redis, Celery con worker, worker-outbox y beat, nginx con TLS, Docker Compose, HTMX). Solo se pregunta si hace falta un servicio interno separado (por ejemplo, FastAPI para cálculos o modelos).

Todo lo que no se pueda responder queda como pregunta `P-nn` abierta para el SRS.

**El método no presupone un dominio.** No des por hecho clientes, ventas, canales de mensajería ni sistemas externos: pregunta por los actores, los procesos y las integraciones **si las hay**. Sirve igual para un sistema de inventarios (almacenistas, entradas y salidas, conteos), una plataforma escolar (docentes, alumnos, calificaciones) o una app interna de recursos humanos (colaboradores, vacaciones, autorizaciones).

### Fase 2. Crear la carpeta del proyecto
**Si la carpeta ya existe** (el usuario corrió `devskills init` antes y la sesión está abierta en ella: hay `documentacion/CONTEXTO.md` y el commit `chore: bootstrap project from devskills`), **salta esta fase**: usa su nombre, slug y rango de puertos (están en `CONTEXTO.md`) y confirma con el Product Owner solo si el descubrimiento los cambia. El orden del método es descubrimiento primero; `devskills init` por su cuenta es el atajo de quien ya conoce esos datos.

En cualquier otro caso, ejecuta el script del plugin (Python 3.12, solo librería estándar), con lo que salió del descubrimiento:

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
4. **Repositorio remoto privado desde el inicio** (solo con la **confirmación explícita del usuario**, que se pide aquí y se obtiene antes de ejecutar nada): el CI de la plantilla (`.github/workflows/ci.yml`) solo corre cuando el repositorio tiene remoto, y un CI que nunca se ha ejecutado se rompe en el peor momento. Se **propone** el comando exacto y, con el "sí", se ejecuta con GitHub CLI (`gh auth status`; instalación y autenticación en `docs/instalacion.md`), tras pasar gitleaks (`${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py`): `gh repo create <organizacion>/<slug> --private --source . --remote origin --push`. Después de **cada push autorizado** revisa el CI (lectura): `gh run list --limit 3` y, si falla, `gh run view <id> --log-failed`. **Un CI en rojo es deuda**: se corrige antes de seguir con el siguiente elemento.
5. **Dependabot:** al subir el repositorio abrirá PR de dependencias que fallarán mientras el CI de `main` esté en rojo. Orden: primero el CI de `main` en verde, luego se **proponen** al usuario los `@dependabot rebase` y los merges de las **menores** (se ejecutan solo los que apruebe) y se revisan aparte las **versiones mayores** (cada una es un elemento del plan; ver el comentario de `.github/dependabot.yml`).
6. **Runner fijo:** los flujos usan `ubuntu-24.04` y no `ubuntu-latest`, para que GitHub no cambie la imagen por debajo del CI; subir de versión es un cambio a mano, probado y con su commit.

### Fase 4. Siguientes pasos (flujo completo)
1. SRS hasta la línea base de requisitos: RF, RNF, Anexo A, Anexo B con Gherkin, Anexo C (`devskills:redactar-srs`).
2. DISEÑO (`devskills:redactar-diseno`): módulos y su grafo de dependencias (que se vuelve `configuracion/modulos.py`), puertos, datos, estados, eventos, despliegue y ADR.
3. PLAN (`devskills:planear-entregas`): Entrega 0 de cimientos y entregas por valor; tablero con `plan_sprints.py`.
4. Entrega 0: los habilitadores de cimientos adaptan el esqueleto al proyecto (ver "Cargar el dominio en el esqueleto") y pasan el ciclo completo (`devskills:ciclo-historia`).
5. Ciclo por historia hasta cerrar cada entrega; `devskills:guarda-todo` al terminar cada sesión.

### Cargar el dominio en el esqueleto (roles, módulos y contratos)
El esqueleto solo trae lo genérico: `configuracion`, `nucleo`, `identidad`, `herramientas` y `despliegue`, más `auditoria` (un módulo hexagonal vacío que sirve de molde), con el rol **Administrador** y dos roles de ejemplo (`auditor`, sensible; `usuario`, sin segundo factor) que se sustituyen por los del SRS. Todo lo demás sale del SRS y del DISEÑO del proyecto, y lo carga el equipo en la Entrega 0 por el ciclo normal (el analista lo especifica; los desarrolladores lo implementan con sus pruebas):

| Qué | De dónde sale | Dónde se carga |
|-----|---------------|----------------|
| **Roles** | SRS 2.3 (clases de usuarios) y el RF de control de acceso | El catálogo de roles de `identidad` (una migración de datos nueva; nunca se edita una migración ya aplicada), con `exige_segundo_factor` para los roles sensibles que diga el SRS |
| **Permisos** | SRS (qué puede hacer cada rol) y el ADR de la matriz de permisos | `nucleo/permisos.py`: capacidades por rol, con denegación por defecto. Una sola fuente; los casos de uso la consultan |
| **Módulos de negocio** | DISEÑO D.1.2 (módulos) y D.1.3 (grafo de dependencias, sin ciclos) | `configuracion/modulos.py`: cada módulo con su esquema de PostgreSQL y sus dependencias permitidas; después se crea el paquete con `dominio/`, `aplicacion/`, `adaptadores/`, `api_publica.py` y `pruebas/` |
| **Contratos de import-linter** | Se **generan** desde `modulos.py` | `python -m herramientas.contratos_importlinter --escribir` (desde `codigo/`) reescribe `.importlinter`; después `lint-imports`. Nunca se editan a mano |
| **Puertos de integraciones** (solo si el SRS tiene sistemas externos) | SRS 5 y DISEÑO D.1.4 | `nucleo/puertos/` (los compartidos) o el módulo dueño, cada uno con su adaptador falso y su prueba de contrato |
| **Eventos** | DISEÑO D.5 | El catálogo de eventos de `nucleo`; cada módulo publica solo los suyos |
| **Asignación Dev A / Dev B** | DISEÑO D.1.2 | Tabla "Asignación de módulos" de `documentacion/CONTEXTO.md` |

El `README.md` de `codigo/` del proyecto explica los pasos exactos y los nombres de archivo del esqueleto; léelo antes de planear la Entrega 0.

## Commands

```bash
python "${CLAUDE_SKILL_DIR}/scripts/crear_proyecto.py" --help
```
