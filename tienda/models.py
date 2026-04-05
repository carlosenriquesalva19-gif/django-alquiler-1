from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MinLengthValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify


class Categoria(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    descripcion = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class MetodoPago(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Cliente(models.Model):
    nombre = models.CharField(max_length=120)
    dni = models.CharField(
        max_length=8,
        unique=True,
        null=True,
        validators=[MinLengthValidator(8), MaxLengthValidator(8)],
        help_text="Debe tener exactamente 8 caracteres.",
    )
    email = models.EmailField(blank=True, null=True, unique=True)
    telefono = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Pelicula(models.Model):
    titulo = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    anio = models.PositiveIntegerField(validators=[MinValueValidator(1900)], verbose_name="Año")
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="peliculas")
    director = models.CharField(max_length=120, blank=True)
    pais_origen = models.CharField(max_length=80, blank=True)
    duracion_minutos = models.PositiveIntegerField(default=90, validators=[MinValueValidator(1)])
    precio_alquiler = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    stock = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["titulo", "anio"]
        unique_together = [("titulo", "anio")]

    def __str__(self) -> str:
        return f"{self.titulo} ({self.anio})"

    def _generar_slug_unico(self) -> str:
        base_slug = slugify(self.titulo) or "pelicula"
        slug = base_slug
        contador = 2

        while Pelicula.objects.exclude(pk=self.pk).filter(slug=slug).exists():
            slug = f"{base_slug}-{contador}"
            contador += 1

        return slug

    def save(self, *args, **kwargs):
        self.slug = self._generar_slug_unico()
        super().save(*args, **kwargs)


class Alquiler(models.Model):
    ESTADO_PENDIENTE = "pendiente"
    ESTADO_PAGADO = "pagado"
    ESTADO_ANULADO = "anulado"
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_PAGADO, "Pagado"),
        (ESTADO_ANULADO, "Anulado"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="alquileres")
    pelicula = models.ForeignKey(Pelicula, on_delete=models.PROTECT, related_name="alquileres")
    metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.PROTECT,
        related_name="alquileres",
        blank=True,
        null=True,
    )
    fecha_alquiler = models.DateField(default=timezone.localdate)
    fecha_pago = models.DateField(blank=True, null=True)
    fecha_devolucion = models.DateField(blank=True, null=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    pagado = models.BooleanField(default=False)
    precio = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)

    class Meta:
        ordering = ["-fecha_alquiler", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "pelicula", "fecha_alquiler"],
                name="uniq_alquiler_cliente_pelicula_fecha",
            ),
        ]
        permissions = [
            ("can_simulate_sales", "Puede simular ventas"),
            ("can_close_cash", "Puede cerrar caja diaria"),
        ]

    def __str__(self) -> str:
        return f"Alquiler: {self.pelicula} - {self.cliente}"

    def clean(self):
        errors = {}

        if self.fecha_devolucion and self.fecha_alquiler and self.fecha_devolucion < self.fecha_alquiler:
            errors["fecha_devolucion"] = "La fecha de devolución no puede ser anterior a la fecha de alquiler."

        if self.estado == self.ESTADO_PAGADO and not self.fecha_pago:
            self.fecha_pago = timezone.localdate()

        if self.estado == self.ESTADO_ANULADO:
            self.pagado = False

        fecha_caja = self.fecha_pago or timezone.localdate()
        if self.estado == self.ESTADO_PAGADO and CajaDiaria.objects.filter(fecha=fecha_caja, cerrada=True).exists():
            errors["estado"] = "La caja de esa fecha ya está cerrada y no permite nuevas ventas."

        if errors:
            raise ValidationError(errors)

    def marcar_pagado(self, fecha_devolucion=None, fecha_pago=None, metodo_pago=None) -> None:
        if self.estado == self.ESTADO_ANULADO:
            raise ValidationError("No se puede cobrar un alquiler anulado.")

        if fecha_devolucion is None:
            fecha_devolucion = timezone.localdate()
        if fecha_pago is None:
            fecha_pago = timezone.localdate()

        with transaction.atomic():
            alquiler = Alquiler.objects.select_for_update().get(pk=self.pk)
            if alquiler.estado == self.ESTADO_PAGADO:
                return

            if alquiler.estado == self.ESTADO_PENDIENTE:
                Pelicula.objects.filter(pk=alquiler.pelicula_id).update(stock=models.F("stock") + 1)

            alquiler.estado = self.ESTADO_PAGADO
            alquiler.pagado = True
            alquiler.fecha_pago = fecha_pago
            alquiler.fecha_devolucion = fecha_devolucion
            if metodo_pago is not None:
                alquiler.metodo_pago = metodo_pago
            alquiler.save(update_fields=["estado", "pagado", "fecha_pago", "fecha_devolucion", "metodo_pago"])

            self.estado = alquiler.estado
            self.pagado = alquiler.pagado
            self.fecha_pago = alquiler.fecha_pago
            self.fecha_devolucion = alquiler.fecha_devolucion
            self.metodo_pago = alquiler.metodo_pago

    def anular(self) -> None:
        with transaction.atomic():
            alquiler = Alquiler.objects.select_for_update().get(pk=self.pk)
            if alquiler.estado == self.ESTADO_ANULADO:
                return

            if alquiler.estado == self.ESTADO_PENDIENTE:
                Pelicula.objects.filter(pk=alquiler.pelicula_id).update(stock=models.F("stock") + 1)

            alquiler.estado = self.ESTADO_ANULADO
            alquiler.pagado = False
            alquiler.fecha_pago = None
            alquiler.save(update_fields=["estado", "pagado", "fecha_pago"])

            self.estado = alquiler.estado
            self.pagado = alquiler.pagado
            self.fecha_pago = alquiler.fecha_pago

    def save(self, *args, **kwargs):
        self.full_clean()

        if self.precio is None:
            self.precio = self.pelicula.precio_alquiler

        self.pagado = self.estado == self.ESTADO_PAGADO

        if not self._state.adding:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            pelicula = Pelicula.objects.select_for_update().get(pk=self.pelicula_id)
            requiere_reservar_stock = self.estado == self.ESTADO_PENDIENTE

            if requiere_reservar_stock and pelicula.stock <= 0:
                raise ValidationError({"pelicula": "No hay stock disponible para esta película."})

            if requiere_reservar_stock:
                pelicula.stock -= 1
                pelicula.save(update_fields=["stock"])

            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            if self.estado == self.ESTADO_PENDIENTE:
                Pelicula.objects.filter(pk=self.pelicula_id).update(stock=models.F("stock") + 1)
            return super().delete(*args, **kwargs)


class EventoDominio(models.Model):
    tipo = models.CharField(max_length=80)
    descripcion = models.TextField()
    alquiler = models.ForeignKey(
        Alquiler,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]

    def __str__(self) -> str:
        return f"{self.tipo} - {self.creado_en:%Y-%m-%d %H:%M}"


class CajaDiaria(models.Model):
    fecha = models.DateField(unique=True)
    cerrada = models.BooleanField(default=False)
    cerrada_en = models.DateTimeField(blank=True, null=True)
    cerrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cajas_cerradas",
    )

    class Meta:
        ordering = ["-fecha"]

    def __str__(self) -> str:
        return f"Caja {self.fecha} - {'cerrada' if self.cerrada else 'abierta'}"


class HistorialPrecioPelicula(models.Model):
    pelicula = models.ForeignKey(Pelicula, on_delete=models.CASCADE, related_name="historial_precios")
    precio_anterior = models.DecimalField(max_digits=8, decimal_places=2)
    precio_nuevo = models.DecimalField(max_digits=8, decimal_places=2)
    cambiado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cambiado_en", "-id"]

    def __str__(self) -> str:
        return f"{self.pelicula} {self.precio_anterior} -> {self.precio_nuevo}"


class LoginFallido(models.Model):
    username = models.CharField(max_length=150, blank=True)
    ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    must_change_password = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.user.get_username()
