from django.apps import AppConfig


class IdentidadConfig(AppConfig):
    name = "identidad"
    verbose_name = "Identidad"

    def import_models(self) -> None:
        # Los modelos viven en el adaptador de salida (arquitectura hexagonal), no en `models.py`.
        super().import_models()
        from identidad.adaptadores.salida import modelos  # noqa: F401

    def ready(self) -> None:
        # el hash ficticio (para igualar el tiempo cuando el correo no existe) se genera al
        # arrancar; si no, la primera peticion con un correo inexistente tardaria mas que las demas
        # y delataria que no existe.
        from identidad.adaptadores.salida.contrasenas import hash_ficticio

        hash_ficticio()
