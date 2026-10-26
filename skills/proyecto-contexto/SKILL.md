---
name: proyecto-contexto
description: >
  Contexto y reglas obligatorias de un proyecto construido con DevSkills: dónde están los requisitos,
  el diseño y el plan, la arquitectura fija (Django modular hexagonal), las convenciones, la Definición
  de Listo y de Terminado, la política de cero deuda y el entorno local. Lee `documentacion/CONTEXTO.md`
  para lo propio de cada proyecto. Trigger: al empezar cualquier tarea de análisis, desarrollo, QA o evaluación.
license: MIT
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- Antes de redactar, implementar, probar o evaluar cualquier historia (HU) o habilitador (EN).
- Cuando haya dudas sobre una regla de negocio, la arquitectura o una convención.

## Lo propio de cada proyecto: `documentacion/CONTEXTO.md`

Esta skill trae las reglas **comunes** a todos los proyectos DevSkills. Lo específico (módulos, quién desarrolla cada uno, reglas de negocio que no se negocian, integraciones, prefijo de Docker, rango de puertos, puertos reservados del host, project de engram, canal de Telegram) vive en `documentacion/CONTEXTO.md`, que llena el `analista-arquitecto` al iniciar el proyecto (plantilla en `${CLAUDE_PLUGIN_ROOT}/plantillas/documentacion/CONTEXTO.md`). **Léelo siempre después de esta skill.** Si no existe o tiene secciones sin llenar que tu tarea necesita, detente y avisa al orquestador.

## Fuentes de verdad (en este orden)

| Qué | Dónde | Regla |
|-----|-------|-------|
| Requisitos, casos de uso, historias, trazabilidad | `documentacion/SRS.md` (secciones 3 a 6, Anexos A, B y C) | Es el **QUÉ**. Nunca se contradice desde el código |
| Diseño técnico | `documentacion/DISENO.md` (D.1 a D.6 y ADR) | Es el **CÓMO**. Un cambio de diseño que afecte requisitos va primero al SRS |
| Plan y backlog | `documentacion/PLAN.md` (generado) y `documentacion/avance/estado_backlog.json` | El plan **no se edita a mano**: se regenera con `documentacion/analisis/plan_sprints.py` |
| Avances y reportes | `documentacion/avance/S{NN}/{ID}.md` | Los escribe la skill `devskills:registrar-avance` |
| Contexto del proyecto | `documentacion/CONTEXTO.md` | Lo mantiene el `analista-arquitecto` |
| Código | `codigo/` (monolito Django) | Las herramientas se ejecutan desde `codigo/`. Ningún archivo nuevo va en la raíz del repositorio |

Si algo no está en el SRS, **no se implementa**: se reporta como pregunta al Product Owner (skill `devskills:preguntar-al-po`).

**Idioma: el de `documentacion/CONTEXTO.md` (por defecto español de México)**, que prevalece sobre el estilo del `CLAUDE.md` personal del usuario. En español de México: tuteo ("revisa", "detente", "tú corres"), nunca voseo ("revisá", "detenete"): documentos, comentarios, docstrings, mensajes para el usuario, reportes de QA y del Angel Fixer, y respuestas al orquestador. Los commits van en inglés (Conventional Commits) y **sin atribución de IA ni `Co-Authored-By`**.

**Nada propio de la empresa escrito en el código:** nombres, dominios, identificadores fiscales, números, cuentas, horarios o cualquier dato de la organización van en configuración (`.env`, catálogos, tablas), no en constantes. Así el sistema se instala para otra organización sin tocar el código (una instalación por organización).

## Critical Patterns

### Arquitectura fija (DISEÑO D.1)
- **Monolito modular Django** con arquitectura que "grita" el dominio: un paquete por módulo de negocio.
- **Hexagonal por módulo:** `dominio/` (Python puro, sin Django ni SQL) · `aplicacion/` (un caso de uso por archivo, nombrado como el CU) · `adaptadores/entrada|salida/` · `api_publica.py` (lo único importable desde otro módulo) · `pruebas/`.
- **Límites verificados por máquina:** los contratos de import-linter se **generan** desde `configuracion/modulos.py` con `herramientas/contratos_importlinter.py`; una prueba AST impone una lista blanca de la librería estándar en cada `dominio/` y prohíbe los imports dinámicos. Para agregar un módulo: se declara en `modulos.py` con sus dependencias del DISEÑO y se regeneran los contratos.
- **Cada módulo es dueño de sus tablas** (su propio esquema de PostgreSQL). Entre módulos: referencias por ID, sin claves foráneas cruzadas. Comunicación síncrona solo por `api_publica.py`; asíncrona por **eventos de dominio** (catálogo en DISEÑO D.5).
- **`nucleo`:** `Actor` (quién ejecuta un caso de uso, inmutable y validado), puertos compartidos en `nucleo/puertos/`, `Reloj`, matriz de permisos central (`nucleo/permisos.py`, capacidades por rol con denegación por defecto) y el **outbox** de eventos.
- **Todo lo externo detrás de un puerto**, con su adaptador falso y su prueba de contrato. Producción se niega a arrancar con un adaptador falso.
- **Outbox:** todo envío hacia afuera se guarda en la misma transacción que el cambio; Celery lo despacha (`worker-outbox`) con reintentos exponenciales; `beat` programa purga y tareas periódicas. Cada módulo solo publica sus propios eventos; un filtro rechaza datos sensibles en el contenido de los eventos.
- **Máquinas de estado:** los estados cambian solo por la tabla de transiciones del dominio; nunca se asignan a mano.
- **Permisos en el caso de uso**, no solo en la vista.
- **Base de datos con mínimo privilegio** (`herramientas/roles_bd.py`): un rol administra roles, otro es dueño del esquema y corre las migraciones, y la aplicación usa un rol que solo hace DML. Producción se niega a arrancar con credenciales de los otros roles.
- **Settings por entorno** (`dev`, `pruebas`, `prod`, `migraciones`) con validación del entorno al arrancar (`configuracion/entorno.py`): producción falla si falta un secreto o es débil.

### Convenciones de código
- Python **3.12**, Django 5, DRF, Celery, Redis, PostgreSQL 16, HTMX. Estilo: `ruff` + `ruff format`; `mypy .` revisa todo y debe dar 0 errores (estricto en `dominio/`).
- Nombres de dominio **en español**, iguales a los del SRS.
- Dinero: monto + moneda (nunca `float`); fechas en UTC con zona explícita; teléfonos E.164.
- Logs estructurados sin datos personales (sin correos, teléfonos completos, identificadores fiscales ni contenido de mensajes).
- En la terminal se prefieren `rg`, `fd`, `bat`, `eza`, `sd` cuando estén instalados.

### Definición de Listo y de Terminado
- **Listo para empezar (DoR):** la historia tiene RF trazados, criterios Gherkin y ningún pendiente `P-nn` abierto que la afecte (SRS B.0, PLAN).
- **Terminado (DoD) — esta es la única definición del método** (el SRS B.0 y el PLAN la referencian y solo agregan criterios propios del proyecto): escenarios Gherkin automatizados y en verde, `import-linter` y análisis de seguridad en verde, RNF aplicables verificados, QA **APROBADA sin observaciones abiertas**, Angel Fixer **sin hallazgos abiertos de ninguna severidad**, verificación final aprobada (cuando hubo correcciones) y avance registrado. En el **ciclo híbrido** (`devskills:ciclo-historia`) un elemento normal cumple el Angel Fixer en su revisión por historia (con su verificación ligera) y el QA en el **cierre de su sprint**: hasta entonces está integrado en `main` pero `En validación`, no Terminado. Los elementos de la excepción (seguridad, plataforma o núcleo compartido, críticos) cumplen las dos revisiones por historia antes del merge.
- **Política de cero deuda (decisión del usuario):** no se registra deuda técnica. Todo hallazgo (CRÍTICO, ALTO, MEDIO o BAJO) y toda observación de QA se corrige antes de tachar. Lo que pertenece a otro elemento del plan **no es deuda**: se anota con el ID que lo cubre.

### Entorno local
- El sistema **nunca** apunta por defecto a un puerto reservado del host (por ejemplo `localhost:5432`, donde puede haber otro PostgreSQL). En **dev**, `DATABASE_URL` es obligatoria: `python -m herramientas.base_local` levanta un PostgreSQL 16 embebido (en `.pgdata/` en la raíz del proyecto) e imprime la URL. En **pruebas**, sin `DATABASE_URL`, `conftest.py` levanta **otro** PostgreSQL embebido en `.pgdata_pruebas/`, separado del de dev para que correr pytest no lo apague.
- **Docker es opcional.** Se desarrolla y se prueba sin él: PostgreSQL embebido (`pgserver`) y Celery en modo local, sin Redis. Docker Compose solo hace falta para desplegar (o para reproducir el stack completo). Si un agente lo usa, lleva el prefijo `<slug>-<agente>` y el subrango que le asigna el orquestador (base en `CONTEXTO.md`), limpia solo lo suyo y nunca corre `down -v` ni `prune` sobre el stack principal. Las pruebas de Compose se omiten solas sin Docker y corren siempre en el CI.
- Nadie lee ni escribe `.env` ni `.env.*`; los cambios a `.env.ejemplo` se entregan como texto al Product Owner.
- **Dependencias:** las versiones de lo que se instala están fijas (lock con hashes de pip-tools en `codigo/`, `package-lock.json` con `npm ci`, mermaid-cli y los Word con versión exacta); subirlas es un cambio a propósito.

## Commands

```bash
# desde codigo/
python -m pytest                                        # todas las pruebas
python -m pytest --gherkin-terminal-reporter -k HU_35   # una historia
lint-imports                                            # límites entre módulos
ruff check . && ruff format --check . && mypy .
pip-audit -r requirements.txt && bandit -c pyproject.toml -r .
python manage.py makemigrations --check --dry-run
# desde la raíz del proyecto
python documentacion/analisis/plan_sprints.py                       # regenera PLAN.md y el tablero
python documentacion/analisis/trazabilidad.py _tmp.md --escribir    # regenera el Anexo C del SRS
```
