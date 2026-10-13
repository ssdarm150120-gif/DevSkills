from django.urls import include, path

from configuracion.salud import salud

urlpatterns = [
    path("salud", salud, name="salud"),
    # Ingreso y cuenta de usuario. El adaptador de entrada de `identidad` las define.
    path("", include("identidad.adaptadores.entrada.urls")),
]
