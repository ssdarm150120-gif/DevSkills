"""Valores por defecto de idioma y zona horaria del proyecto.

Son neutrales (`es` y `UTC`). `devskills init --idioma ... --zona ...` reescribe estas dos lineas al
crear el proyecto; despues se pueden cambiar a mano o, sin tocar el codigo, con las variables de
entorno `APP_IDIOMA` y `APP_ZONA_HORARIA` (que tienen prioridad sobre estos valores).
"""

IDIOMA_PREDETERMINADO = "es"
ZONA_PREDETERMINADA = "UTC"
