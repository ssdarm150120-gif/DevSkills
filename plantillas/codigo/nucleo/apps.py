from django.apps import AppConfig


class NucleoConfig(AppConfig):
    name = "nucleo"
    verbose_name = "Nucleo compartido"

    def import_models(self) -> None:
        # Los modelos viven en el adaptador (arquitectura hexagonal), no en `models.py`.
        super().import_models()
        from nucleo.adaptadores import modelos  # noqa: F401
