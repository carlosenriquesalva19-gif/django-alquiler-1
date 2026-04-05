from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone

from .models import Alquiler, CajaDiaria, Categoria, Cliente, EventoDominio, HistorialPrecioPelicula, LoginFallido, MetodoPago, Pelicula, UserProfile


class FechaPagoRangoFilter(admin.SimpleListFilter):
    title = "rango fecha pago"
    parameter_name = "fecha_pago_rango"

    def lookups(self, request, model_admin):
        return [
            ("hoy", "Hoy"),
            ("7d", "Últimos 7 días"),
            ("30d", "Últimos 30 días"),
        ]

    def queryset(self, request, queryset):
        hoy = timezone.localdate()
        if self.value() == "hoy":
            return queryset.filter(fecha_pago=hoy)
        if self.value() == "7d":
            return queryset.filter(fecha_pago__gte=hoy - timedelta(days=7))
        if self.value() == "30d":
            return queryset.filter(fecha_pago__gte=hoy - timedelta(days=30))
        return queryset


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "descripcion"]
    search_fields = ["nombre"]

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        return super().save_model(request, obj, form, change)


class AlquilerInline(admin.TabularInline):
    model = Alquiler
    extra = 0
    fields = ["pelicula", "estado", "precio", "fecha_alquiler", "fecha_pago"]
    readonly_fields = fields
    show_change_link = True


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nombre", "dni", "email", "telefono", "total_gastado"]
    search_fields = ["nombre", "dni", "email"]
    inlines = [AlquilerInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(total_pagado=Sum("alquileres__precio"))

    @admin.display(ordering="total_pagado", description="Total gastado")
    def total_gastado(self, obj):
        return obj.total_pagado or 0

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        return super().save_model(request, obj, form, change)


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activo"]
    list_filter = ["activo"]
    search_fields = ["nombre"]


@admin.register(Pelicula)
class PeliculaAdmin(admin.ModelAdmin):
    list_display = ["titulo", "slug", "anio", "categoria", "director", "pais_origen", "precio_alquiler", "stock"]
    list_filter = ["categoria", "anio", "pais_origen"]
    search_fields = ["titulo", "slug", "director"]
    autocomplete_fields = ["categoria"]

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        return super().save_model(request, obj, form, change)


@admin.register(Alquiler)
class AlquilerAdmin(admin.ModelAdmin):
    list_display = [
        "fecha_alquiler",
        "fecha_pago",
        "cliente",
        "pelicula",
        "metodo_pago",
        "estado",
        "pagado",
        "precio",
        "fecha_devolucion",
    ]
    list_filter = ["estado", "pagado", "metodo_pago", "fecha_alquiler", "fecha_pago", FechaPagoRangoFilter, "fecha_devolucion"]
    search_fields = ["cliente__nombre", "cliente__dni", "pelicula__titulo"]
    autocomplete_fields = ["cliente", "pelicula", "metodo_pago"]
    actions = ["marcar_pagados_en_lote"]

    @admin.action(description="Marcar pagados en lote")
    def marcar_pagados_en_lote(self, request, queryset):
        total = 0
        for alquiler in queryset.filter(estado=Alquiler.ESTADO_PENDIENTE):
            alquiler.marcar_pagado()
            total += 1
        self.message_user(request, f"Se marcaron {total} alquileres como pagados.", level=messages.SUCCESS)

    def get_readonly_fields(self, request, obj=None):
        readonly = ["pagado"]
        if obj and obj.estado == Alquiler.ESTADO_PAGADO and not request.user.is_superuser:
            readonly.extend(["cliente", "pelicula", "precio", "fecha_alquiler"])
        return readonly

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        return super().save_model(request, obj, form, change)


@admin.register(EventoDominio)
class EventoDominioAdmin(admin.ModelAdmin):
    list_display = ["tipo", "alquiler", "creado_en"]
    list_filter = ["tipo", "creado_en"]
    search_fields = ["tipo", "descripcion"]
    readonly_fields = ["tipo", "descripcion", "alquiler", "creado_en"]


@admin.register(CajaDiaria)
class CajaDiariaAdmin(admin.ModelAdmin):
    list_display = ["fecha", "cerrada", "cerrada_en", "cerrada_por"]
    list_filter = ["cerrada", "fecha"]


@admin.register(HistorialPrecioPelicula)
class HistorialPrecioPeliculaAdmin(admin.ModelAdmin):
    list_display = ["pelicula", "precio_anterior", "precio_nuevo", "cambiado_en"]
    list_filter = ["cambiado_en"]
    autocomplete_fields = ["pelicula"]
    readonly_fields = ["pelicula", "precio_anterior", "precio_nuevo", "cambiado_en"]


@admin.register(LoginFallido)
class LoginFallidoAdmin(admin.ModelAdmin):
    list_display = ["username", "ip", "creado_en"]
    list_filter = ["creado_en"]
    readonly_fields = ["username", "ip", "user_agent", "creado_en"]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "must_change_password"]
