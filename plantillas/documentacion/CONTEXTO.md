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
| Prefijo de Docker (contenedores, redes, volúmenes, proyecto de Compose) | `{{SLUG}}` |
| Rango de puertos del host | `{{PUERTO_BASE}}` a `{{PUERTO_BASE}} + 49` |
| Puertos reservados del host (nunca usarlos ni apuntar a ellos por defecto) | {{PUERTOS_RESERVADOS}} |
| Idioma | Español de México con tuteo (documentos, código, reportes y respuestas) |
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

## Entorno local

- El proyecto **nunca** apunta por defecto a un puerto reservado del host ({{PUERTOS_RESERVADOS}}).
- Contenedores, redes y volúmenes con el prefijo `{{SLUG}}`; puertos publicados solo dentro del rango `{{PUERTO_BASE}}` a `{{PUERTO_BASE}} + 49`.
- <!-- cómo se levanta la base de desarrollo y la de pruebas (ver codigo/README.md) -->

## Decisiones vigentes del Product Owner que afectan el trabajo diario

<!-- Resumen corto con referencia al SRS o al DISEÑO (p. ej. "Python 3.12 en local y CI (SRS 2.7)"). -->
- <!-- decisión (versión) -->
