---
name: guarda-todo
description: >
  Cierre de sesión ("guarda todo"): gitleaks antes de cualquier commit, punto de control o commit lógico del
  trabajo pendiente, exportar la transcripción de la sesión a Markdown con `exportar_sesion.py`, commit de la
  transcripción y resumen de la sesión en engram. Nada sale del equipo (push, `gh`, merges de Dependabot) sin
  la confirmación explícita del usuario. Trigger: "/devskills:guarda-todo", "guarda todo", "cerrar sesión",
  "cierra la sesión", "ya me voy".
license: MIT
metadata:
  author: devskills
  version: "1.1"
---

## When to Use

- El usuario pide "guarda todo" o cerrar la sesión.
- Antes de un corte previsible (fin del día, límite de uso cercano, reinicio de Claude Code para activar el canal de Telegram).

## Critical Patterns

**Regla de oro: gitleaks va ANTES de cualquier commit de cierre y antes de cualquier push.** Y **nada sale del equipo sin que el usuario lo confirme en esa conversación**: ni `git push`, ni `gh` que escriba (crear repositorio, issues, PR, comentarios), ni merges de Dependabot. Esas acciones se **proponen** con el comando exacto y se ejecutan solo con un "sí" explícito; la autorización de una sesión anterior no cuenta.

Procedimiento (en este orden; no saltar pasos):

1. **Revisar lo pendiente.** `git status --short` y `git stash list` (debe estar vacía). Nunca `git add` de `.env*`, `.venv/`, `.pgdata*/` ni de archivos que no reconoces: si aparece algo inesperado, pregunta.
2. **Exportar la transcripción** de esta sesión a `documentacion/sesiones/AAAA-MM-DD_<tema>.md`:
   - La transcripción de Claude Code está en `~/.claude/projects/<carpeta-del-proyecto-codificada>/<id-de-sesión>.jsonl` (la carpeta es la ruta de trabajo con `:`, `\` y `/` cambiados por `-`). Toma el `.jsonl` más reciente de esa carpeta o el de la sesión actual.
   - `python documentacion/analisis/exportar_sesion.py --ultima documentacion/sesiones/<archivo>.md "<título>"` (`--ultima` toma el `.jsonl` más reciente de la carpeta de trabajo actual; también puedes pasar la ruta de un `.jsonl`). Usa el Python del entorno virtual del proyecto si lo hay (`.venv/Scripts/python` en Windows, `.venv/bin/python` en Unix).
   - Si la sesión ya se había exportado ese día, se **re-exporta completa** sobre el mismo archivo (reemplaza al anterior).
3. **gitleaks sobre todo lo que se va a commitear** (lo versionado, lo modificado y lo nuevo no ignorado, transcripción incluida: puede traer secretos pegados por error): `python "${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py"`. Usa el gitleaks nativo si está instalado y Docker solo como alternativa. Si hay hallazgos: **no se hace ningún commit**; se redacta el secreto (y se avisa al usuario para que lo rote) y se repite. Un falso positivo se suprime con `gitleaks:allow` en **esa misma línea** y el motivo; **nunca** se excluye una carpeta o un archivo del escaneo. Códigos de salida: 0 sin hallazgos, 1 hay hallazgos, 2 la herramienta no está disponible (sin binario ni Docker, o con el demonio apagado). Con 2 el cierre se detiene y se pide instalar gitleaks (`winget install Gitleaks.Gitleaks`): no se commitea sin escaneo, y tampoco se trata como si hubiera hallazgos.
4. **Commit del trabajo pendiente** (solo con gitleaks limpio):
   - En la rama de un elemento (`hu-xx`/`en-xx`): el **punto de control** de `devskills:ciclo-historia` (sección "Puntos de control"): `git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-xx): <qué quedó>"`. Si `git status --short` aún muestra archivos, reconócelos con el usuario antes de agregarlos.
   - En `main`: commits lógicos por tipo (`docs: …` separado de `feat/fix/chore: …`), en inglés, Conventional Commits, **sin atribución de IA**.
5. **Commit de la transcripción:** `git add documentacion/sesiones && git commit -m "docs: export session transcript <tema>"`.
6. **Pendientes de engram:** si existe `.devskills/engram_pendiente.md` y `mem_save` está disponible, guárdalos y bórralos del archivo. **Resumen en engram** con `mem_session_summary` (project de `CONTEXTO.md`): Objetivo, Instrucciones (preferencias del usuario descubiertas), Descubrimientos, Logrado (con commits), Siguientes pasos, Archivos relevantes. Incluye en "Siguientes pasos" el estado exacto del ciclo en curso (ID, rama, ronda, punto de control, lista pendiente) para retomarlo sin rehacer nada.
7. **Propuestas hacia afuera (solo proponer, esperar el "sí"):**
   - **Push:** si hay remoto, muestra `git log --oneline origin/<rama>..HEAD` y pregunta si subes. Con el "sí", sube con `git push` (gitleaks del paso 3 ya pasó sobre ese contenido); después revisa el CI con `gh run list --limit 3` (lectura) y, si falla, `gh run view <id> --log-failed`. Un CI en rojo es deuda: se anota en el resumen y se corrige antes de seguir. Sin remoto, **recomienda** crear el repositorio **privado** y deja el comando para que el usuario lo apruebe (`gh repo create <org>/<slug> --private --source . --remote origin`): el CI no corre hasta entonces.
   - **Dependabot:** con el CI de `main` en verde, **lista** los PR y propone, uno por uno, el `@dependabot rebase` y el merge de cada menor, y la revisión aparte de las versiones mayores. Ejecuta solo los que el usuario apruebe; mientras `main` esté en rojo, no toques sus PR.
   - **Nota de lecciones para DevSkills:** se redacta como **borrador local** en `.devskills/lecciones.md` (carpeta ignorada por git; sin nombres, datos ni código del proyecto) y se enseña al usuario; solo se publica como issue si él lo aprueba (ver `devskills:ciclo-historia`, "Mantenimiento de DevSkills").
8. Responder (y por Telegram si el canal está activo) con: commits hechos, archivo de la transcripción, resultado de gitleaks, propuestas pendientes de aprobación y siguientes pasos.

## Commands

```bash
git status --short && git stash list
python documentacion/analisis/exportar_sesion.py --ultima documentacion/sesiones/<AAAA-MM-DD_tema>.md "<título>"
python "${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py"          # ANTES de cualquier commit
git add -A -- codigo .github documentacion/avance && git commit -m "wip(hu-xx): <qué quedó>"   # solo en la rama de un elemento
git add documentacion/sesiones && git commit -m "docs: export session transcript <tema>"
# Solo con la aprobación explícita del usuario:
git push
gh run list --limit 3                                      # lectura; tras el push
```
