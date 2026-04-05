from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def tienda_settings_check(app_configs, **kwargs):
    issues = []
    if not getattr(settings, "PRECIO_ALQUILER_MINIMO", None):
        issues.append(Warning("PRECIO_ALQUILER_MINIMO no está configurado.", id="tienda.W001"))
    if not settings.DEBUG and str(settings.SECRET_KEY).startswith("django-insecure-dev-key"):
        issues.append(Error("SECRET_KEY insegura en producción.", id="tienda.E001"))
    return issues
