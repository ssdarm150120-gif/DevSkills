# Cómo contribuir a DevSkills

Gracias por querer mejorar DevSkills. Este documento explica el flujo y los estándares del repositorio.

## Flujo: primero el issue

1. **Abre un issue** con la plantilla de [error](https://github.com/ssdarm150120-gif/DevSkills/issues/new?template=bug_report.yml) o de [mejora](https://github.com/ssdarm150120-gif/DevSkills/issues/new?template=feature_request.yml).
2. Espera a que un mantenedor lo apruebe (`status:approved`).
3. **Después** abre el pull request con `Closes #N` y una etiqueta `type:*`.

## Preparar el entorno

```bash
git clone https://github.com/ssdarm150120-gif/DevSkills.git
cd DevSkills
bin/devskills doctor        # obligatorios: git, Python 3.12, Claude Code, gitleaks; opcionales: Docker, semgrep, Node, mermaid-cli, gh, engram
```

Para las pruebas hace falta [ShellSpec](https://shellspec.info) 0.28 o superior y, para el lint, ShellCheck. Si no quieres instalar ShellSpec de forma global, clónalo en cualquier carpeta y pásalo a `make`:

```bash
git clone --depth 1 --branch 0.28.1 https://github.com/shellspec/shellspec.git ~/shellspec
make test SHELLSPEC=~/shellspec/shellspec
```

En Windows las pruebas se corren en **Git Bash** (con `TMPDIR=/tmp` si tu `TMP` tiene formato de Windows).

## Qué correr antes de un PR

| Comando | Qué valida |
|---------|------------|
| `make lint` | ShellCheck sobre `bin/devskills`, `install.sh`, `uninstall.sh` y las ayudas de las pruebas |
| `make validate` | `claude plugin validate .` (manifiestos del plugin y del marketplace) |
| `python scripts/validar_plugin.py` | Frontmatter de agentes y skills y referencias `devskills:<nombre>` |
| `make test` | Instalador (HOME temporal, idempotencia, desinstalación) y CLI (`init`, `doctor`, `version`) |
| `make gitleaks` | Secretos, con gitleaks nativo (Docker como alternativa) |

Si tocas `plantillas/codigo`, genera un proyecto (`bin/devskills init <carpeta> --slug demo --puerto-base 19100`) y corre desde `codigo/`: `pytest`, `ruff check .`, `ruff format --check .`, `mypy .`, `lint-imports`, `bandit`, `pip-audit` y `python manage.py makemigrations --check --dry-run`. Si tocas un generador, córrelo en un proyecto de ejemplo y comprueba que el archivo generado abre.

## Estándares

Los estándares completos están en [AGENTS.md](AGENTS.md). En corto:

- **Idioma:** todo el contenido (agentes, skills, plantillas, comentarios, documentación) en español de México con tuteo.
- **Sin reglas inventadas:** cada regla del método nace de un incidente o de una decisión real. Lo que no esté claro se deja como `<!-- por definir -->`.
- **Nada de una empresa:** ni nombres, dominios, correos, IP, tokens, ni datos reales en ejemplos.
- **Commits:** en inglés, [Conventional Commits](https://www.conventionalcommits.org) (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`), **sin `Co-Authored-By` ni atribución de IA**.
- **Bash portable:** el CLI y los instaladores deben funcionar en macOS (bash 3.2), Linux y Windows con Git Bash.

## Versionado

DevSkills usa versionado semántico. La versión vive en `.claude-plugin/plugin.json`; cada cambio visible se anota en [CHANGELOG.md](CHANGELOG.md).

## Licencia

Al contribuir aceptas que tu aporte se publica bajo la [licencia MIT](LICENSE).
