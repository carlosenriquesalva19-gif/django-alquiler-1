from django.apps import AppConfig


class TiendaConfig(AppConfig):
    name = "tienda"

    def ready(self):
        from . import checks  # noqa: F401
        from . import signals  # noqa: F401
