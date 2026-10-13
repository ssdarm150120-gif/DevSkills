# Agentes

DevSkills, metodología y stack para construir cualquier sistema, trae 13 agentes sin dominio propio: lo que saben del negocio lo leen del SRS, del DISEÑO y de `documentacion/CONTEXTO.md` de cada proyecto. La sesión principal es el orquestador; los demás trabajan como subagentes.

```
Sesión principal (orquestador)
├── analista-arquitecto
├── dev-a
│   ├── dev-dominio
│   ├── dev-integraciones
│   └── dev-interfaz
├── dev-b
│   ├── dev-interfaz
│   ├── dev-servicios
│   ├── dev-dominio
│   └── dev-integraciones
├── qa
│   ├── qa-bdd
│   └── qa-no-funcional
├── angel-fixer
└── verificador
```

## Tabla de agentes

| Agente | Rol | Skills precargadas | Puede |
|--------|-----|--------------------|-------|
| `orquestador` | Coordina, decide lo técnico, pregunta lo de negocio, hace los commits | `orquestador`, `proyecto-contexto`, `ciclo-historia` | Delegar, git, estado del backlog. **No** escribe código |
| `analista-arquitecto` | SRS, DISEÑO, PLAN, Anexo C, pasadas documentales | `proyecto-contexto`, `redactar-srs`, `redactar-diseno`, `planear-entregas`, `pasada-documental` | Escribir en `documentacion/`. **No** toca `codigo/` |
| `dev-a` | Desarrollador A: dominio y datos | `proyecto-contexto`, `implementar-historia` | Implementar y delegar en sus subagentes |
| `dev-b` | Desarrollador B: canales, experiencia y servicios | `proyecto-contexto`, `implementar-historia` | Implementar y delegar en sus subagentes |
| `dev-dominio` | Dominio y casos de uso con TDD | `proyecto-contexto` | `dominio/` y `aplicacion/` |
| `dev-integraciones` | Adaptadores, outbox, Celery, migraciones | `proyecto-contexto` | `adaptadores/salida/` e infraestructura |
| `dev-interfaz` | Vistas Django + HTMX, accesibilidad | `proyecto-contexto` | `adaptadores/entrada/` y plantillas |
| `dev-servicios` | Servicios internos separados (por ejemplo, FastAPI) | `proyecto-contexto` | La carpeta del servicio |
| `qa` | Valida contra Gherkin y RNF, emite el veredicto | `proyecto-contexto`, `validar-historia` | Pruebas de aceptación. **No** corrige producción |
| `qa-bdd` | Gherkin del SRS → pytest-bdd | `proyecto-contexto` | Archivos `.feature` y pasos |
| `qa-no-funcional` | RNF con la verificación técnica del Anexo C | `proyecto-contexto` | Medir y reportar |
| `angel-fixer` | Evalúa cumplimiento, buenas prácticas y seguridad | `proyecto-contexto`, `angel-fixer` | Fixes quirúrgicos de CRÍTICO y ALTO |
| `verificador` | Verificación final o de lista congelada | `proyecto-contexto`, `validar-historia`, `angel-fixer` | Confirmar y corregir de forma quirúrgica |

## Qué generaliza cada uno

Los diez primeros agentes de la lista de desarrollo y calidad vienen del proyecto modelo, sin su dominio:

- `dev-servicios` generaliza al subagente que construía un servicio de recomendaciones: ahora cubre cualquier servicio interno separado del monolito.
- `analista-arquitecto` y `verificador` no tenían archivo: en el proyecto modelo los cubría el orquestador con agentes de propósito general. Aquí son agentes propios con sus reglas escritas.
- `orquestador` existe como skill (para la sesión principal) y como agente (para `claude --agent devskills:orquestador`).

## Reglas comunes a todos

Cada agente trae al final el mismo bloque de reglas:

- Español de México con tuteo.
- Cargar `proyecto-contexto` y leer `documentacion/CONTEXTO.md` antes de trabajar.
- No leer ni escribir `.env` ni `.env.*`.
- Docker solo con el prefijo y el rango de puertos asignados; nunca en puertos reservados del host; limpieza al terminar.
- Guardar en engram decisiones y hallazgos no obvios.
- Cero deuda.

Y un bloque de cuidado del repositorio según su papel:

| Papel | Regla de git |
|-------|--------------|
| Desarrolladores | Trabajan en la rama del elemento **sin hacer commit**. Solo `status`, `diff`, `log`, `show` y `restore` de un archivo que ellos dañaron |
| Revisores (QA, Angel Fixer, verificador) | No ejecutan en el repositorio nada que escriba archivos de `codigo/`. Si corrigen, usan solo la herramienta de edición y reportan `git diff --stat` |
| Todos | Mutaciones y experimentos en una copia del scratchpad. Si dañan un archivo: se detienen, `git restore`, y lo reportan. Nunca reconstruyen de memoria |

## Asignación de módulos

Qué desarrollador atiende cada módulo se define **por proyecto**, en la tabla "Asignación de módulos" de `documentacion/CONTEXTO.md`. Por defecto:

- **Dev A:** núcleo, identidad, auditoría, módulos centrados en datos, integraciones con sistemas fuente y los habilitadores de cimientos.
- **Dev B:** interfaz, canales y mensajería, flujos con el usuario final y servicios internos.

## Nombres según la instalación

| Instalación | Agente | Skill |
|-------------|--------|-------|
| Plugin de Claude Code | `devskills:dev-a` | `/devskills:ciclo` |
| `install.sh` / `install.ps1` | `devskills-dev-a` | `/devskills-ciclo` |
