---
name: recuperar-corte
description: >
  Qué hacer cuando un agente (o la sesión) se corta a media tarea, por ejemplo por límite de uso: revisar
  git status, stash y contenedores con su prefijo, hacer un commit de respaldo, reanudar con SendMessage al
  mismo agente sin rehacer su trabajo, y limpiar. Trigger: "se cortó el agente", "límite de uso", "rate limit",
  "el agente no terminó", "retoma donde se quedó".
license: MIT
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- Un subagente regresó sin terminar (límite de uso, error, tiempo agotado) o su notificación de término nunca llegó.
- La sesión principal se reinició a media ronda.

## Critical Patterns

### 1. Diagnóstico (sin tocar nada)
1. `git status --short`, `git diff --stat` y `git stash list` en el repositorio: qué dejó a medias el agente. Si hay un `stash` que no hizo el orquestador, **no lo apliques ni lo borres** todavía: revisa su contenido con `git stash show -p` y repórtalo (ningún agente debe usar `stash`).
2. `git log --oneline -5` y la rama actual: ¿sigue en la rama del elemento?
3. Contenedores, redes y volúmenes con el prefijo que se le asignó al agente: `docker ps -a --filter "name=<prefijo>"`, `docker network ls --filter "name=<prefijo>"`, `docker volume ls --filter "name=<prefijo>"`. No toques los de otros prefijos (pueden ser de otro agente u otra sesión).
4. Procesos huérfanos que el agente pudo dejar (por ejemplo, un PostgreSQL embebido de pruebas) y archivos temporales en su scratchpad.
5. Engram: `mem_search` con el ID del elemento por si el agente guardó su avance.

### 2. Respaldo
- Commit de respaldo **antes** de reanudar, para que nada se pierda, con el **mismo punto de control** de `devskills:ciclo-historia` (sección "Puntos de control"), que cubre todo lo que el desarrollador puede tocar: `git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-xx): avance del desarrollador antes del corte"`. Luego `git status --short` debe quedar vacío; lo que aparezca fuera de esas rutas se revisa antes de agregarlo.
- Si el árbol tiene un archivo dañado o vaciado: `git restore <archivo>` desde el último punto de control y anótalo. **Nunca** se reconstruye un archivo de memoria.

### 3. Reanudar sin rehacer
- Si el agente sigue disponible, **reanúdalo con `SendMessage` al mismo agente** (por su nombre o ID): conserva su contexto. Mensaje: qué commit de respaldo se hizo, qué quedó en el árbol, y "continúa exactamente desde donde te quedaste; no rehagas lo que ya está en el commit".
- Si no se puede reanudar (contexto perdido), lanza un agente nuevo del mismo tipo con: el ID, la rama, el commit de respaldo, el `git diff` del trabajo previo, la lista exacta de lo que falta y la instrucción de **no rehacer** lo que ya existe.
- Si el corte fue por límite de uso, espera a que se restablezca (o avisa al usuario por Telegram si el canal está activo con la hora estimada) antes de reanudar; no lances agentes en bucle.

### Si la corrida es no interactiva (`claude -p`)
Retoma la misma sesión con `claude -p "<instrucción>" --resume <id de sesión>`; el punto de control `wip` protege lo ya hecho. Detalle (`stream-json`, permisos, presupuesto, costo) en [docs/instalacion.md, sección "Uso no interactivo"](../../docs/instalacion.md#uso-no-interactivo).

### 4. Limpieza
- Quita los contenedores, redes y volúmenes huérfanos **del prefijo del agente** y los procesos huérfanos que identificaste.
- Si el `stash` era del agente y su contenido ya está respaldado en el commit, bórralo (`git stash drop`) y regístralo como incidente de proceso en el reporte.
- Registra el corte en el reporte del elemento (sección 4, ronda con "corte" y cómo se resolvió) y en engram.

## Commands

```bash
git status --short && git diff --stat && git stash list && git log --oneline -5
docker ps -a --filter "name=<slug>-<agente>" && docker volume ls --filter "name=<slug>-<agente>"   # solo si usaste Docker
git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-xx): avance del desarrollador antes del corte"
git status --short                                         # debe quedar vacío
```
