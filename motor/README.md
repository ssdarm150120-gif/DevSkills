# Motor gráfico de DevSkills

Panel de control local, lanzador de servicios y orquestador opcional. Documentación completa en [`docs/motor.md`](../docs/motor.md).

| Carpeta | Contenido |
| --- | --- |
| `comun/` | Rutas del estado (`rutas.py`) y migración de datos (`migrar.py`) |
| `panel/` | Panel web local (`panel.py`, `index.html`) y la status line de límites (`statusline_limites.py`) |
| `servicios/` | Lanzador multiplataforma (`servicios.py`) con lista blanca de tipos de arranque |
| `orquestador/` | Orquestador **opcional** (código, pruebas, `DISENO.md`, `requirements.txt`) |
| `graphify/` | Integración con Graphify (hooks en Python, plantilla `.graphifyignore`, revisión del grafo) |
| `plantillas/` | `proyectos.ejemplo.json`: registro genérico |

El estado (registro, preferencias, tokens, historial, logs) vive FUERA del repositorio, en `DEVSKILLS_DATOS` o `~/.devskills`.

Uso: `devskills panel`, `devskills servicios listar`, `devskills motor iniciar`, `devskills orquestador instalar`.

Pruebas (desde esta carpeta): `python -m unittest discover -s comun/pruebas`, y lo mismo con `servicios/pruebas`, `panel/pruebas`, `graphify/pruebas`; el orquestador con `cd orquestador && python -m pytest`.
