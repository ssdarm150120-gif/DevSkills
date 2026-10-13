# Instalación

Hay dos formas de instalar DevSkills. Las dos traen lo mismo; cambia cómo se llaman los agentes y las skills.

| Forma | Nombres | Cuándo conviene |
|-------|---------|-----------------|
| **Plugin de Claude Code** | `devskills:<nombre>` (por ejemplo `/devskills:ciclo`) | La recomendada: se actualiza y se desactiva desde `/plugin` |
| **Instalador** (`install.sh` o `install.ps1`) | `devskills-<nombre>` (por ejemplo `/devskills-ciclo`) | Si no usas el sistema de plugins o quieres el CLI `devskills` en tu PATH |

Puedes usar las dos a la vez (el plugin para Claude Code y el instalador solo por el CLI); no chocan porque usan nombres distintos.

## Como plugin de Claude Code

Dentro de una sesión de Claude Code:

```text
/plugin marketplace add ssdarm150120-gif/DevSkills
/plugin install devskills@devskills-local
```

O desde un clon local:

```text
/plugin marketplace add C:\ruta\a\DevSkills
/plugin install devskills@devskills-local
```

Lo mismo desde la terminal:

```bash
claude plugin marketplace add ssdarm150120-gif/DevSkills
claude plugin install devskills@devskills-local
claude plugin details devskills        # inventario de agentes y skills
```

Para probarlo sin instalar: `claude --plugin-dir /ruta/a/DevSkills`.

## Manual (macOS, Linux)

```bash
git clone https://github.com/ssdarm150120-gif/DevSkills.git
cd DevSkills
./install.sh
```

## Windows con Git Bash

```bash
git clone https://github.com/ssdarm150120-gif/DevSkills.git
cd DevSkills
bash install.sh
```

Si `devskills` no se encuentra después, agrega a tu `~/.bashrc`:

```bash
export PATH="$HOME/bin:$PATH"
```

## Windows con PowerShell

```powershell
git clone https://github.com/ssdarm150120-gif/DevSkills.git
cd DevSkills
powershell -ExecutionPolicy Bypass -File install.ps1
```

`install.ps1` instala además un lanzador `devskills.cmd`. El CLI está escrito en Bash, así que necesita **Git Bash** en el PATH (viene con Git para Windows).

## Qué hace el instalador

| Qué | Dónde |
|-----|-------|
| Agentes | `~/.claude/agents/devskills-<nombre>.md` |
| Skills | `~/.claude/skills/devskills-<nombre>/` |
| CLI | Windows: `~/bin/devskills` · Unix: `/usr/local/bin/devskills` si se puede escribir ahí; si no, `~/.local/bin/devskills` |
| Carga útil (plantillas, scripts) | Windows: `~/bin/lib/devskills/` · Unix: `~/.local/share/devskills/` |
| Manifiesto | `manifiesto.txt` dentro de la carga útil: la lista exacta de archivos instalados |

Al copiar, el instalador adapta el contenido: `devskills:<nombre>` pasa a `devskills-<nombre>` y las variables del plugin (`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_SKILL_DIR}`) se resuelven a la carpeta instalada.

**No pisa nada tuyo:**

- Si un archivo de destino existe y no lo instaló DevSkills, pregunta antes de sobrescribirlo; sin terminal, aborta sin instalar nada. `--forzar` (`-Forzar`) lo sobrescribe a propósito.
- Si la carpeta de la carga útil existe y no es una instalación de DevSkills, no la toca.
- Es idempotente: reinstalar deja exactamente los mismos archivos.

Opciones: `--si` (`-Si`) no pregunta al reinstalar. Variables: `CLAUDE_CONFIG_DIR`, `DEVSKILLS_BIN_DIR`, `DEVSKILLS_SHARE_DIR`.

## Actualizar

```bash
devskills update        # git pull en el clon de origen y reinstala
```

Como plugin: `/plugin marketplace update devskills-local`.

## Desinstalar

```bash
./uninstall.sh                                             # macOS, Linux, Git Bash
powershell -ExecutionPolicy Bypass -File uninstall.ps1     # PowerShell
```

Quita exactamente lo que está en el manifiesto y la carpeta de la carga útil. No toca tus otros agentes y skills ni los proyectos creados con `devskills init`.

Como plugin: `/plugin uninstall devskills@devskills-local`.

## Requisitos

Corre `devskills doctor` para revisarlos todos.

| Requisito | Para qué | Cómo instalarlo |
|-----------|----------|-----------------|
| Git | Todo | <https://git-scm.com/downloads> |
| Claude Code | Agentes y skills | <https://code.claude.com> |
| Docker | Compose del proyecto, gitleaks | Docker Desktop o Docker Engine |
| Python 3.12 | Esqueleto y generadores | `winget install Python.Python.3.12` · `brew install python@3.12` |
| Node.js LTS | Presentación y mermaid-cli | <https://nodejs.org> |
| mermaid-cli | Diagramas en los Word | En una carpeta local, ver [generadores](generadores.md) |
| gitleaks | Búsqueda de secretos | `docker pull zricethezav/gitleaks:v8.21.2` |
| Plugin engram | Memoria entre sesiones | Como plugin de Claude Code |

Opcional: el plugin de Telegram, para trabajar desde el celular ([telegram](telegram.md)).
