# Estándares del repositorio DevSkills

Reglas para cualquier persona o agente que modifique este repositorio. (Los proyectos creados con DevSkills traen su propio `AGENTS.md`, que sale de `plantillas/raiz/AGENTS.md`.)

## Estructura

| Carpeta | Contenido |
|---------|-----------|
| `.claude-plugin/` | `plugin.json` y `marketplace.json` |
| `agents/` | Un archivo por agente del equipo |
| `skills/` | Una carpeta por skill, con su `SKILL.md` y sus recursos |
| `plantillas/` | `raiz/`, `codigo/` (esqueleto del stack fijo), `documentacion/` y `analisis/` (generadores) que se copian a cada proyecto nuevo |
| `scripts/` | Utilidades del plugin (gitleaks, validación) |
| `bin/devskills` | CLI en Bash |
| `install.sh`, `install.ps1`, `uninstall.sh`, `uninstall.ps1` | Instalación sin el sistema de plugins |
| `spec/` | Pruebas con ShellSpec |
| `docs/` | Documentación detallada |

## Reglas

1. **Español de México con tuteo** en todo el contenido. Commits en inglés con Conventional Commits y sin atribución de IA.
2. **No inventes reglas del método.** Si una regla no viene de un incidente o de una decisión real, no entra; lo dudoso se marca `<!-- por definir -->`.
3. **Nada específico de una organización** ni datos personales, correos, IP, tokens o secretos, ni en ejemplos. Corre `make gitleaks` antes de cada commit.
4. **Referencias internas:** otras skills y agentes se citan como `devskills:<nombre>`; rutas del plugin como `${CLAUDE_PLUGIN_ROOT}` o `${CLAUDE_SKILL_DIR}`. El instalador las reescribe; no escribas rutas absolutas.
5. **Contenido de las skills:** Claude Code sustituye `$ARGUMENTS`, `$0`, `$1`… y los argumentos declarados. No uses `$1` ni parecidos en bloques de código de una skill.
6. **Marcadores de las plantillas:** `{{NOMBRE_PROYECTO}}`, `{{SLUG}}`, `{{SLUG_GUION_BAJO}}`, `{{PUERTO_BASE}}`, `{{PUERTOS_RESERVADOS}}`, `{{FECHA}}`, `{{AUTOR}}`, `{{IDIOMA}}`, `{{IDIOMA_DESCRIPCION}}` (estos dos salen de `--idioma`). Los sustituye `skills/iniciar-proyecto/scripts/crear_proyecto.py`. Evítalos en archivos `.py`.
7. **El esqueleto debe pasar sus pruebas, sin Docker:** cualquier cambio en `plantillas/codigo` se verifica generando un proyecto y corriendo `pytest`, `ruff`, `mypy .`, `lint-imports`, `bandit`, `pip-audit` y `makemigrations --check`. El CI del plugin lo hace solo (job `esqueleto`: `devskills init` + ruff, mypy, lint-imports y pytest completo con `SIN_DOCKER=1`); en tu máquina corre lo mismo antes de un commit que toque `plantillas/`.
8. **Bash portable:** sin arreglos asociativos ni otras funciones de bash 4 en `install.sh`, `uninstall.sh` y `bin/devskills` (macOS trae bash 3.2); rutas con espacios siempre entre comillas.
9. **Los instaladores no pisan nada:** todo lo instalado va con el prefijo `devskills-` y queda en el manifiesto; lo que no está en el manifiesto no se toca.
10. **Fin de línea LF** (`.gitattributes`), UTF-8 sin BOM.

## Antes de un commit

```bash
make lint && make validate && python scripts/validar_plugin.py && make test && make gitleaks
```
