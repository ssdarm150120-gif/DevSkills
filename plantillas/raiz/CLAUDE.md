@AGENTS.md

# Claude Code: idioma y estilo del proyecto

Claude Code lee `CLAUDE.md`, no `AGENTS.md`; la línea de arriba importa `AGENTS.md` para que las reglas del equipo se carguen siempre.

- **El idioma del proyecto es el del campo Idioma de `documentacion/CONTEXTO.md`** ({{IDIOMA_DESCRIPCION}}; código `{{IDIOMA}}`) y **prevalece sobre el estilo personal del usuario** (su `CLAUDE.md` global: voseo, tono, muletillas). Aplica a documentos, código, comentarios, reportes y respuestas, también las de los agentes.
- Los commits van en inglés, con Conventional Commits y sin atribución de IA.
- Lo propio del proyecto (módulos, puertos, project de engram) está en `documentacion/CONTEXTO.md`.
