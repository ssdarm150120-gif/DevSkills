---
name: guarda-todo
description: >
  Cierre de sesión ("guarda todo"): commit del trabajo pendiente, exportar la transcripción de la sesión a
  Markdown con `exportar_sesion.py`, gitleaks por Docker, commit de la transcripción y resumen de la sesión
  en engram. Trigger: "/devskills:guarda-todo", "guarda todo", "cerrar sesión", "cierra la sesión", "ya me voy".
license: Apache-2.0
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- El usuario pide "guarda todo" o cerrar la sesión.
- Antes de un corte previsible (fin del día, límite de uso cercano, reinicio de Claude Code para activar el canal de Telegram).

## Critical Patterns

Procedimiento (en este orden; no saltar pasos):

1. **Commit del trabajo pendiente.** `git status --short` y `git stash list` (debe estar vacía). Si hay cambios:
   - En la rama de un elemento (`hu-xx`/`en-xx`): punto de control `git add -A && git commit -m "wip(hu-xx): <qué quedó>"`.
   - En `main`: commits lógicos por tipo (`docs: …` separado de `feat/fix/chore: …`), en inglés, Conventional Commits, **sin atribución de IA**.
   - Nunca `git add` de `.env*`, `.venv/`, `.pgdata*/` ni de archivos que no reconoces: si aparece algo inesperado, pregunta.
2. **Exportar la transcripción** de esta sesión a `documentacion/sesiones/AAAA-MM-DD_<tema>.md`:
   - La transcripción de Claude Code está en `~/.claude/projects/<carpeta-del-proyecto-codificada>/<id-de-sesión>.jsonl` (la carpeta es la ruta de trabajo con `:`, `\` y `/` cambiados por `-`). Toma el `.jsonl` más reciente de esa carpeta o el de la sesión actual.
   - `python documentacion/analisis/exportar_sesion.py <sesion.jsonl> documentacion/sesiones/<archivo>.md "<título>"`.
   - Si la sesión ya se había exportado ese día, se **re-exporta completa** sobre el mismo archivo (reemplaza al anterior).
3. **gitleaks** por Docker sobre lo versionado y lo nuevo no ignorado (la transcripción puede contener secretos pegados por error): `python "${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py"`. Si hay hallazgos: **no** se hace commit; se redacta el secreto en la transcripción (y se avisa al usuario para que lo rote) y se repite.
4. **Commit** de la transcripción: `git add documentacion/sesiones && git commit -m "docs: export session transcript <tema>"`.
5. **Resumen en engram** con `mem_session_summary` (project de `CONTEXTO.md`): Objetivo, Instrucciones (preferencias del usuario descubiertas), Descubrimientos, Logrado (con commits), Siguientes pasos, Archivos relevantes. Incluye en "Siguientes pasos" el estado exacto del ciclo en curso (ID, rama, ronda, punto de control, lista pendiente) para retomarlo sin rehacer nada.
6. Responder (y por Telegram si el canal está activo) con: commits hechos, archivo de la transcripción, resultado de gitleaks y siguientes pasos.

## Commands

```bash
git status --short && git stash list
python documentacion/analisis/exportar_sesion.py <sesion.jsonl> documentacion/sesiones/<AAAA-MM-DD_tema>.md "<título>"
python "${CLAUDE_PLUGIN_ROOT}/scripts/gitleaks_archivos.py"
git add documentacion/sesiones && git commit -m "docs: export session transcript <tema>"
```
