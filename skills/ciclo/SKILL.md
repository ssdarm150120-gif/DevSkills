---
name: ciclo
description: >
  Atajo de `devskills:ciclo-historia`: no tiene reglas propias, solo la invoca con el ID.
  Uso: "/devskills:ciclo HU-35", "/devskills:ciclo S05", "/devskills:ciclo cierre-S05".
license: MIT
disable-model-invocation: true
arguments: [id]
argument-hint: "HU-35 | EN-04 | S05 | cierre-S05"
metadata:
  author: devskills
  version: "1.2"
---

Invoca **ahora** la skill `devskills:ciclo-historia` con el ID **$id** y síguela. Las reglas viven solo ahí (incluido el ciclo híbrido: revisión por historia, QA de cierre de sprint y la excepción de ciclo completo).
Si no se indicó un ID, pregunta cuál con `devskills:preguntar-al-po` y espera la respuesta.
