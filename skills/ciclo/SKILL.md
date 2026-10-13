---
name: ciclo
description: >
  Atajo para ejecutar el ciclo completo de un elemento del backlog o de un sprint con la skill
  `devskills:ciclo-historia`. Uso: "/devskills:ciclo HU-35", "/devskills:ciclo S05".
license: MIT
disable-model-invocation: true
arguments: [id]
argument-hint: "HU-35 | EN-04 | S05"
metadata:
  author: devskills
  version: "1.0"
---

Ejecuta **ahora** la skill `devskills:ciclo-historia` para el elemento **$id**, siguiéndola al pie de la letra
(rama y puntos de control, desarrollo, QA, Angel Fixer, rondas, verificación final, registro del avance,
regeneración del plan, gitleaks y squash a main). Si no se indicó un ID, pregunta cuál con
`devskills:preguntar-al-po` y espera la respuesta.
