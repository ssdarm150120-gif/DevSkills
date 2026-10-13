<!--
  Flujo: primero un issue que describa el error o la mejora; después el PR que lo cierra.
-->

## Issue relacionado

Closes #<!-- número del issue -->

## Tipo de cambio

- [ ] `type:bug` — Corrección
- [ ] `type:feature` — Funcionalidad o mejora
- [ ] `type:docs` — Solo documentación
- [ ] `type:refactor` — Refactor sin cambio de comportamiento
- [ ] `type:chore` — Mantenimiento (CI, herramientas)
- [ ] `type:breaking-change` — Cambio incompatible (usa `!` en el tipo del commit)

## Resumen

<!-- 2 a 4 oraciones: qué hace este PR y por qué -->

## Cambios

| Área | Cambio |
|------|--------|
| `agents/` | |
| `skills/` | |
| `plantillas/` | |
| `bin/`, `install.*`, `uninstall.*` | |
| `spec/` | |

## Plan de pruebas

- [ ] `make lint` (ShellCheck) pasa
- [ ] `make validate` (`claude plugin validate .`) y `python scripts/validar_plugin.py` pasan
- [ ] `make test` (ShellSpec) pasa
- [ ] Si toqué `plantillas/codigo`: generé un proyecto con `devskills init` y pasan `pytest`, `ruff`, `mypy .`, `lint-imports`, `bandit`, `pip-audit` y `makemigrations --check`
- [ ] Si toqué un generador de `plantillas/analisis` o `plantillas/documentacion`: lo corrí en un proyecto de ejemplo y el archivo generado abre
- [ ] Prueba manual: <!-- describe -->

## Lista del contribuidor

- [ ] Todo el contenido está en español de México con tuteo
- [ ] No agregué nada específico de una empresa, datos personales, correos, IP, tokens ni secretos (`make gitleaks`)
- [ ] No inventé reglas del método: lo dudoso queda como `<!-- por definir -->`
- [ ] Commits en inglés con Conventional Commits (`feat:`, `fix:`, `docs:`…)
- [ ] NO agregué "Co-Authored-By" ni atribución de IA a los commits
- [ ] Actualicé `CHANGELOG.md` y la documentación (`README.md`, `docs/`)

## Notas para quien revisa

<!-- Opcional -->
