---
name: redactar-diseno
description: >
  Construye el documento de diseño del proyecto (IEEE 1016) en orden, D.1 a D.6: módulos, puertos y
  adaptadores, modelo de datos, máquinas de estado, flujos de integración, contratos, despliegue y
  seguridad, con sus ADR y su historial. Trigger: "redacta el diseño", "documento de diseño", "agrega un
  ADR", "define el puerto", "el diseño no define", "siguiente paso del diseño".
license: MIT
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- Cuando el SRS ya tiene línea base y hay que escribir `documentacion/DISENO.md`.
- Cuando un desarrollador se detuvo porque el diseño no define algo que necesita.
- Cuando una decisión técnica nueva necesita un ADR.
- Lo ejecuta el agente `devskills:analista-arquitecto`. Para subir de versión un diseño ya validado, usa además `devskills:pasada-documental`.

## Critical Patterns

### 1. Regla del documento
El SRS dice **qué**; el diseño dice **cómo**. Aquí no se copian requisitos: se **referencian** por ID (RF, RNF, CU, HU). **Si una decisión de diseño obliga a cambiar un requisito, primero se cambia el SRS** (nueva versión, con su historial) y después el diseño se alinea a esa versión: el encabezado dice siempre con qué versión del SRS está alineado.

### 2. Orden (cada paso se valida antes del siguiente)
| Paso | Contenido | Qué debe quedar definido |
|------|-----------|--------------------------|
| D.1 | Mapa de módulos, puertos y adaptadores | Principios, tabla de módulos con sus RF y CU, **grafo de dependencias sin ciclos** (D.1.3), puertos hacia lo externo con adaptador real y falso (D.1.4), estructura de carpetas (D.1.5), ADR (D.1.6) |
| D.2 | Modelo de datos | Convenciones, diagramas ER por núcleo, catálogo de entidades por módulo, índices y restricciones con el requisito que los exige |
| D.3 | Máquinas de estado | Un diagrama por entidad con estados; quién ejecuta cada transición y qué evento emite |
| D.4 | Flujos de integración | Diagramas de secuencia que separan lo síncrono de lo asíncrono, con sus **puntos de falla** |
| D.5 | Contratos | Reglas y catálogo de eventos, `api_publica.py` por módulo, rutas HTTP, permisos por caso de uso |
| D.6 | Despliegue y seguridad | Topología, entornos y pipeline, controles de seguridad, observabilidad, crecimiento |

La tabla "Plan del diseño" del documento lleva el estado de cada paso.

### 3. Lo que ya decide el esqueleto (no se rediseña)
Los ADR-001 a ADR-008 de la plantilla están marcados "heredado del esqueleto DevSkills" y ya están implementados y probados en `codigo/`: monolito modular hexagonal, contratos de import-linter generados desde `configuracion/modulos.py`, outbox, puertos compartidos en `nucleo/puertos/`, matriz de permisos central, identidad propia, roles de base de datos con mínimo privilegio, settings por entorno con validación y Compose con nginx TLS. El diseño del proyecto **agrega** módulos, puertos, entidades, estados, flujos y controles encima de eso. Cambiar algo heredado es un ADR nuevo con su motivo.

### 4. Reglas que evitan retrabajo (lecciones del proyecto modelo)
- [ ] **Cada puerto tiene sus métodos, sus errores tipados (reintentable o no) y su lugar definidos** antes de implementarlo. Si el diseño no lo define, el desarrollador **se detiene y lo reporta**; el hueco se cierra aquí con una versión nueva y entonces sigue. Un desarrollador que inventa el contrato de un puerto es un defecto del proceso.
- [ ] **Cualquier flecha nueva entre módulos se agrega primero en el diagrama de D.1.3** y en `codigo/configuracion/modulos.py`; el CI rechaza la que no esté ahí. Si dos módulos se necesitan mutuamente, uno se comunica por eventos.
- [ ] Lo que comparten varios módulos (el actor, los permisos, los puertos compartidos) vive en `nucleo`; ningún módulo de negocio importa `identidad`.
- [ ] Todo sistema externo va detrás de un puerto, con **adaptador falso** y **prueba de contrato** reutilizable; producción se niega a arrancar con un adaptador falso.
- [ ] Un evento se nombra en pasado, lo publica solo su módulo emisor, no lleva datos personales y solo crece agregando campos.
- [ ] Los estados cambian solo por la tabla de transiciones del dominio; cada transición emite su evento.
- [ ] Los permisos se verifican en el caso de uso, contra la matriz central; D.5.6 lista quién ejecuta cada caso de uso.
- [ ] Nada propio de la empresa en el código: va en configuración.
- [ ] Docker: el prefijo, el rango de puertos y los puertos reservados del host salen de `documentacion/CONTEXTO.md`.

### 5. ADR
- Fila en D.1.6: `ADR-nnn | Decisión | Alternativa descartada | Motivo`. Numeración corrida; no se reutiliza.
- Indica **quién decidió**: "Decisión del Product Owner" si es de negocio o de costo; si es técnica, es decisión del orquestador y queda en el historial para validación.
- Un ADR rechazado conserva su fila con `**Rechazado (AAAA-MM-DD)**`. Si la decisión es comprar o construir, se documenta con `devskills:evaluacion-alternativas`.

### 6. Habilitadores
El trabajo que pide el diseño y que no es una historia de usuario se vuelve un habilitador `EN-nn` con su referencia al diseño (por ejemplo, "D.4.2, ADR-009"), y entra al plan con `devskills:planear-entregas`. Si un habilitador absorbe trabajo de otro elemento, se anota en ambos.

### 7. Cierre de cada paso
1. Encabezado (Versión, Fecha, versión del SRS de origen, Estado), fila del "Plan del diseño" y fila del historial (la más reciente arriba, con las decisiones y quién las tomó).
2. Actualiza `documentacion/CONTEXTO.md` si cambiaron los módulos, su desarrollador asignado o las integraciones.
3. Regenera el Word y haz el commit `docs:` (ver `devskills:pasada-documental`).

## Commands

```bash
python documentacion/analisis/md_a_word.py --mermaid <carpeta_mermaid_cli> --solo DISENO   # Word con los diagramas
# desde codigo/, cuando cambie el grafo de D.1.3:
python -m herramientas.contratos_importlinter --escribir && lint-imports
```

## Resources

- **Plantilla**: `${CLAUDE_PLUGIN_ROOT}/plantillas/documentacion/DISENO.md` (ya copiada al proyecto como `documentacion/DISENO.md`).
