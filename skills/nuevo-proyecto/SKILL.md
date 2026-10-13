---
name: nuevo-proyecto
description: >
  Atajo para arrancar un sistema nuevo con la skill `devskills:iniciar-proyecto`: descubrimiento con el
  Product Owner, carpeta del proyecto con el esqueleto del stack fijo y las plantillas, git init y primer
  commit. Uso: "/devskills:nuevo-proyecto <nombre>".
license: MIT
disable-model-invocation: true
arguments: [nombre]
argument-hint: "\"Nombre del sistema\""
metadata:
  author: devskills
  version: "1.0"
---

Ejecuta **ahora** la skill `devskills:iniciar-proyecto` para el sistema **$nombre**, siguiéndola al pie de la letra.
Si no se indicó un nombre, empieza el descubrimiento preguntando por el nombre y el problema que resuelve
(skill `devskills:preguntar-al-po`) y espera la respuesta antes de crear nada.
