from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_login_failed
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Alquiler, EventoDominio, HistorialPrecioPelicula, LoginFallido, Pelicula, UserProfile

User = get_user_model()


@receiver(post_save, sender=Alquiler)
def registrar_evento_alquiler_guardado(sender, instance, created, **kwargs):
    tipo = "alquiler_creado" if created else f"alquiler_{instance.estado}"
    EventoDominio.objects.create(
        tipo=tipo,
        alquiler=instance,
        descripcion=f"Alquiler #{instance.pk} en estado {instance.estado}.",
    )


@receiver(post_delete, sender=Alquiler)
def registrar_evento_alquiler_eliminado(sender, instance, **kwargs):
    EventoDominio.objects.create(
        tipo="alquiler_eliminado",
        descripcion=f"Se eliminó el alquiler #{instance.pk}.",
    )


@receiver(pre_save, sender=Pelicula)
def registrar_historial_precio(sender, instance, **kwargs):
    if not instance.pk:
        return
    anterior = Pelicula.objects.filter(pk=instance.pk).values("precio_alquiler").first()
    if anterior and anterior["precio_alquiler"] != instance.precio_alquiler:
        HistorialPrecioPelicula.objects.create(
            pelicula=instance,
            precio_anterior=anterior["precio_alquiler"],
            precio_nuevo=instance.precio_alquiler,
        )


@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
        return
    if hasattr(instance, "profile"):
        instance.profile.must_change_password = False
        instance.profile.save(update_fields=["must_change_password"])


@receiver(user_login_failed)
def registrar_login_fallido(sender, credentials, request, **kwargs):
    LoginFallido.objects.create(
        username=credentials.get("username", ""),
        ip=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
    )
