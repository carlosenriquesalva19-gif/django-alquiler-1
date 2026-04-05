import csv
import datetime
import random
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.db.models.functions import TruncDay
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from .forms import (
    ActualizarPreciosCategoriaForm,
    AlquilerBusquedaForm,
    AlquilerCreateForm,
    CategoriaForm,
    ClienteForm,
    CobroMasivoForm,
    ImportarClientesCSVForm,
    MarcarPagadoForm,
    PeliculaFiltroForm,
    PeliculaForm,
    SimularVentasForm,
)
from .mixins import AuthenticatedWriteMixin, OrderedPaginatedListMixin
from .mixins import BreadcrumbMixin, GroupRequiredMixin, NextUrlMixin, SessionRateLimitMixin
from .models import Alquiler, CajaDiaria, Categoria, Cliente, EventoDominio, MetodoPago, Pelicula


class DashboardView(BreadcrumbMixin, TemplateView):
    template_name = "tienda/index.html"
    breadcrumbs = [{"label": "Inicio", "url": None}]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cache_key = "dashboard-tiempo-real"
        cached = cache.get(cache_key)
        if cached:
            ctx.update(cached)
            return ctx

        hoy = timezone.localdate()
        inicio_mes = hoy.replace(day=1)
        ventas_pagadas = Alquiler.objects.filter(estado=Alquiler.ESTADO_PAGADO)

        data = {
            "total_peliculas": Pelicula.objects.count(),
            "total_clientes": Cliente.objects.count(),
            "alquileres_pendientes": Alquiler.objects.filter(estado=Alquiler.ESTADO_PENDIENTE).count(),
            "ingresos": ventas_pagadas.aggregate(total=Sum("precio")).get("total") or 0,
            "ticket_promedio": ventas_pagadas.aggregate(promedio=Avg("precio")).get("promedio") or 0,
            "top_peliculas": (
                Pelicula.objects.annotate(total_alquileres=Count("alquileres"))
                .select_related("categoria")
                .order_by("-total_alquileres", "titulo")[:10]
            ),
            "ingresos_por_categoria": (
                Categoria.objects.values("nombre")
                .annotate(total=Sum("peliculas__alquileres__precio", filter=Q(peliculas__alquileres__estado=Alquiler.ESTADO_PAGADO)))
                .order_by("-total", "nombre")
            ),
            "clientes_sin_alquileres": (
                Cliente.objects.annotate(total_alquileres=Count("alquileres"))
                .filter(total_alquileres=0)
                .order_by("nombre")
            ),
            "alquileres_vencidos": (
                Alquiler.objects.filter(
                    estado=Alquiler.ESTADO_PENDIENTE,
                    fecha_alquiler__lt=hoy,
                )
                .select_related("cliente", "pelicula")
                .order_by("fecha_alquiler")
            ),
            "ranking_mensual_clientes": (
                Cliente.objects.annotate(
                    gasto_mes=Sum(
                        "alquileres__precio",
                        filter=Q(
                            alquileres__estado=Alquiler.ESTADO_PAGADO,
                            alquileres__fecha_pago__gte=inicio_mes,
                            alquileres__fecha_pago__lte=hoy,
                        ),
                    )
                )
                .filter(gasto_mes__gt=0)
                .order_by("-gasto_mes", "nombre")[:10]
            ),
            "ventas_por_dia": (
                ventas_pagadas.filter(fecha_pago__gte=inicio_mes, fecha_pago__lte=hoy)
                .annotate(dia=TruncDay("fecha_pago"))
                .values("dia")
                .annotate(total=Sum("precio"), cantidad=Count("id"))
                .order_by("dia")
            ),
        }
        cache.set(cache_key, data, 60)
        ctx.update(data)
        return ctx


index = DashboardView.as_view()


class CategoriaListView(OrderedPaginatedListMixin, ListView):
    model = Categoria
    template_name = "tienda/categoria_list.html"
    context_object_name = "categorias"
    default_ordering = "nombre"

    def get_queryset(self):
        queryset = super().get_queryset()
        estado = self.request.GET.get("estado_lista", "activos")
        if estado == "inactivos":
            return queryset.filter(is_active=False)
        if estado == "todos":
            return queryset
        return queryset.filter(is_active=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["estado_lista"] = self.request.GET.get("estado_lista", "activos")
        return ctx


class CategoriaCreateView(AuthenticatedWriteMixin, BreadcrumbMixin, NextUrlMixin, SuccessMessageMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "tienda/categoria_form.html"
    fallback_success_url = reverse_lazy("tienda:categoria_list")
    success_message = "Categoría creada correctamente."
    breadcrumbs = [
        {"label": "Inicio", "url": reverse_lazy("tienda:index")},
        {"label": "Categorías", "url": reverse_lazy("tienda:categoria_list")},
        {"label": "Nueva", "url": None},
    ]


class CategoriaUpdateView(AuthenticatedWriteMixin, BreadcrumbMixin, NextUrlMixin, SuccessMessageMixin, UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "tienda/categoria_form.html"
    fallback_success_url = reverse_lazy("tienda:categoria_list")
    success_message = "Categoría actualizada correctamente."

    def get_queryset(self):
        return Categoria.objects.filter(is_active=True)


class CategoriaDeleteView(AuthenticatedWriteMixin, NextUrlMixin, DeleteView):
    model = Categoria
    template_name = "tienda/categoria_confirm_delete.html"
    fallback_success_url = reverse_lazy("tienda:categoria_list")

    def get_queryset(self):
        return Categoria.objects.filter(is_active=True)

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, "Categoría desactivada.")
        return redirect(self.get_success_url())


class CategoriaRestoreView(AuthenticatedWriteMixin, View):
    def post(self, request, pk):
        categoria = get_object_or_404(Categoria, pk=pk)
        categoria.is_active = True
        categoria.save(update_fields=["is_active"])
        messages.success(request, "Categoría restaurada.")
        return redirect(request.POST.get("next") or "tienda:categoria_list")


class ClienteListView(OrderedPaginatedListMixin, ListView):
    model = Cliente
    template_name = "tienda/cliente_list.html"
    context_object_name = "clientes"
    default_ordering = "nombre"

    def get_queryset(self):
        queryset = super().get_queryset()
        estado = self.request.GET.get("estado_lista", "activos")
        if estado == "inactivos":
            return queryset.filter(is_active=False)
        if estado == "todos":
            return queryset
        return queryset.filter(is_active=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["estado_lista"] = self.request.GET.get("estado_lista", "activos")
        return ctx


class ClienteDetailView(BreadcrumbMixin, DetailView):
    model = Cliente
    template_name = "tienda/cliente_detail.html"
    context_object_name = "cliente"

    def get_queryset(self):
        return Cliente.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "alquileres",
                queryset=Alquiler.objects.select_related("pelicula", "pelicula__categoria", "metodo_pago"),
            )
        )

    def get_breadcrumbs(self):
        return [
            {"label": "Inicio", "url": reverse("tienda:index")},
            {"label": "Clientes", "url": reverse("tienda:cliente_list")},
            {"label": self.get_object().nombre, "url": None},
        ]


class ClienteCreateView(AuthenticatedWriteMixin, BreadcrumbMixin, NextUrlMixin, SuccessMessageMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "tienda/cliente_form.html"
    fallback_success_url = reverse_lazy("tienda:cliente_list")
    success_message = "Cliente creado correctamente."
    breadcrumbs = [
        {"label": "Inicio", "url": reverse_lazy("tienda:index")},
        {"label": "Clientes", "url": reverse_lazy("tienda:cliente_list")},
        {"label": "Nuevo", "url": None},
    ]


class ClienteUpdateView(AuthenticatedWriteMixin, BreadcrumbMixin, NextUrlMixin, SuccessMessageMixin, UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "tienda/cliente_form.html"
    fallback_success_url = reverse_lazy("tienda:cliente_list")
    success_message = "Cliente actualizado correctamente."

    def get_queryset(self):
        return Cliente.objects.filter(is_active=True)


class ClienteDeleteView(AuthenticatedWriteMixin, NextUrlMixin, DeleteView):
    model = Cliente
    template_name = "tienda/cliente_confirm_delete.html"
    fallback_success_url = reverse_lazy("tienda:cliente_list")

    def get_queryset(self):
        return Cliente.objects.filter(is_active=True)

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, "Cliente desactivado.")
        return redirect(self.get_success_url())


class ClienteRestoreView(AuthenticatedWriteMixin, View):
    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        cliente.is_active = True
        cliente.save(update_fields=["is_active"])
        messages.success(request, "Cliente restaurado.")
        return redirect(request.POST.get("next") or "tienda:cliente_list")


class PeliculaListView(BreadcrumbMixin, OrderedPaginatedListMixin, ListView):
    model = Pelicula
    template_name = "tienda/pelicula_list.html"
    context_object_name = "peliculas"
    default_ordering = "titulo"
    breadcrumbs = [
        {"label": "Inicio", "url": reverse_lazy("tienda:index")},
        {"label": "Películas", "url": None},
    ]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("categoria")
        estado = self.request.GET.get("estado_lista", "activos")
        if estado == "inactivos":
            queryset = queryset.filter(is_active=False)
        elif estado != "todos":
            queryset = queryset.filter(is_active=True)
        self.filtro_form = PeliculaFiltroForm(self.request.GET or None)
        return self.filtro_form.filtrar(queryset)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filtro_form"] = self.filtro_form
        ctx["estado_lista"] = self.request.GET.get("estado_lista", "activos")
        return ctx


class PeliculaDetailView(BreadcrumbMixin, DetailView):
    model = Pelicula
    template_name = "tienda/pelicula_detail.html"
    context_object_name = "pelicula"

    def get_queryset(self):
        return Pelicula.objects.filter(is_active=True).select_related("categoria").annotate(total_alquileres=Count("alquileres"))

    def get_breadcrumbs(self):
        return [
            {"label": "Inicio", "url": reverse("tienda:index")},
            {"label": "Películas", "url": reverse("tienda:pelicula_list")},
            {"label": self.get_object().titulo, "url": None},
        ]


class PeliculaCreateView(AuthenticatedWriteMixin, BreadcrumbMixin, NextUrlMixin, SuccessMessageMixin, CreateView):
    model = Pelicula
    form_class = PeliculaForm
    template_name = "tienda/pelicula_form.html"
    fallback_success_url = reverse_lazy("tienda:pelicula_list")
    success_message = "Película creada correctamente."
    breadcrumbs = [
        {"label": "Inicio", "url": reverse_lazy("tienda:index")},
        {"label": "Películas", "url": reverse_lazy("tienda:pelicula_list")},
        {"label": "Nueva", "url": None},
    ]


class PeliculaUpdateView(AuthenticatedWriteMixin, BreadcrumbMixin, NextUrlMixin, SuccessMessageMixin, UpdateView):
    model = Pelicula
    form_class = PeliculaForm
    template_name = "tienda/pelicula_form.html"
    fallback_success_url = reverse_lazy("tienda:pelicula_list")
    success_message = "Película actualizada correctamente."

    def get_queryset(self):
        return Pelicula.objects.filter(is_active=True)


class PeliculaDeleteView(AuthenticatedWriteMixin, NextUrlMixin, DeleteView):
    model = Pelicula
    template_name = "tienda/pelicula_confirm_delete.html"
    fallback_success_url = reverse_lazy("tienda:pelicula_list")

    def get_queryset(self):
        return Pelicula.objects.filter(is_active=True)

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, "Película desactivada.")
        return redirect(self.get_success_url())


class PeliculaRestoreView(AuthenticatedWriteMixin, View):
    def post(self, request, pk):
        pelicula = get_object_or_404(Pelicula, pk=pk)
        pelicula.is_active = True
        pelicula.save(update_fields=["is_active"])
        messages.success(request, "Película restaurada.")
        return redirect(request.POST.get("next") or "tienda:pelicula_list")


class AlquilerCreateView(AuthenticatedWriteMixin, BreadcrumbMixin, NextUrlMixin, SuccessMessageMixin, CreateView):
    model = Alquiler
    form_class = AlquilerCreateForm
    template_name = "tienda/alquiler_form.html"
    fallback_success_url = reverse_lazy("tienda:alquiler_list")
    success_message = "Alquiler creado correctamente."
    breadcrumbs = [
        {"label": "Inicio", "url": reverse_lazy("tienda:index")},
        {"label": "Alquileres", "url": reverse_lazy("tienda:alquiler_list")},
        {"label": "Nuevo", "url": None},
    ]


class AlquilerListView(BreadcrumbMixin, OrderedPaginatedListMixin, ListView):
    model = Alquiler
    template_name = "tienda/alquiler_list.html"
    context_object_name = "alquileres"
    default_ordering = "-fecha_alquiler"
    breadcrumbs = [
        {"label": "Inicio", "url": reverse_lazy("tienda:index")},
        {"label": "Alquileres", "url": None},
    ]

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("cliente", "pelicula", "pelicula__categoria", "metodo_pago")
        )
        self.busqueda_form = AlquilerBusquedaForm(self.request.GET or None)
        return self.busqueda_form.filtrar(queryset)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["busqueda_form"] = self.busqueda_form
        return ctx


class MarcarPagadoView(AuthenticatedWriteMixin, SessionRateLimitMixin, View):
    template_name = "tienda/marcar_pagado.html"
    rate_limit_key = "marcar-pagado"

    def _puede_operar(self, request, alquiler):
        if request.user.is_superuser or request.user.groups.filter(name="supervisor").exists():
            return True
        if request.user.groups.filter(name="cajero").exists() and alquiler.estado == Alquiler.ESTADO_PENDIENTE:
            return True
        return False

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        alquiler = get_object_or_404(Alquiler.objects.select_related("cliente", "pelicula", "pelicula__categoria"), pk=pk)
        if not self._puede_operar(request, alquiler):
            messages.error(request, "No tienes permiso para cobrar este alquiler.")
            return redirect("tienda:alquiler_list")
        form = MarcarPagadoForm(
            initial={
                "fecha_pago": timezone.localdate(),
                "fecha_devolucion": timezone.localdate(),
            }
        )
        return render(request, self.template_name, {"alquiler": alquiler, "form": form})

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        alquiler = get_object_or_404(Alquiler, pk=pk)
        if not self._puede_operar(request, alquiler):
            messages.error(request, "No tienes permiso para cobrar este alquiler.")
            return redirect("tienda:alquiler_list")
        form = MarcarPagadoForm(request.POST)
        if form.is_valid():
            alquiler.marcar_pagado(
                fecha_devolucion=form.cleaned_data.get("fecha_devolucion"),
                fecha_pago=form.cleaned_data.get("fecha_pago"),
                metodo_pago=form.cleaned_data.get("metodo_pago"),
            )
            messages.success(request, "Alquiler marcado como pagado.")
            return redirect(request.POST.get("next") or "tienda:alquiler_list")
        return render(request, self.template_name, {"alquiler": alquiler, "form": form})


class CobroMasivoView(AuthenticatedWriteMixin, SessionRateLimitMixin, FormView):
    template_name = "tienda/alquiler_cobro_masivo.html"
    form_class = CobroMasivoForm
    success_url = reverse_lazy("tienda:alquiler_list")
    rate_limit_key = "cobro-masivo"

    def form_valid(self, form):
        ids = form.cleaned_data["ids"]
        alquileres = Alquiler.objects.filter(id__in=ids, estado=Alquiler.ESTADO_PENDIENTE)
        total = 0
        for alquiler in alquileres:
            alquiler.marcar_pagado(
                fecha_pago=form.cleaned_data.get("fecha_pago"),
                metodo_pago=form.cleaned_data.get("metodo_pago"),
            )
            total += 1
        messages.success(self.request, f"Se cobraron {total} alquileres.")
        return super().form_valid(form)


class VentasListView(BreadcrumbMixin, OrderedPaginatedListMixin, ListView):
    model = Alquiler
    template_name = "tienda/ventas_list.html"
    context_object_name = "ventas"
    default_ordering = "-fecha_pago"
    breadcrumbs = [
        {"label": "Inicio", "url": reverse_lazy("tienda:index")},
        {"label": "Ventas", "url": None},
    ]

    def get_queryset(self):
        queryset = (
            Alquiler.objects.filter(estado=Alquiler.ESTADO_PAGADO)
            .select_related("cliente", "pelicula", "pelicula__categoria", "metodo_pago")
        )
        desde = self.request.GET.get("desde")
        hasta = self.request.GET.get("hasta")
        if desde:
            queryset = queryset.filter(fecha_pago__gte=desde)
        if hasta:
            queryset = queryset.filter(fecha_pago__lte=hasta)
        return queryset

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        ctx["total_ingresos"] = queryset.aggregate(total=Sum("precio")).get("total") or 0
        ctx["ventas_por_dia"] = (
            queryset.annotate(dia=TruncDay("fecha_pago"))
            .values("dia")
            .annotate(total=Sum("precio"))
            .order_by("dia")
        )
        return ctx


class VentasExportCSVView(AuthenticatedWriteMixin, View):
    def get(self, request):
        ventas = (
            Alquiler.objects.filter(estado=Alquiler.ESTADO_PAGADO)
            .select_related("cliente", "pelicula", "pelicula__categoria", "metodo_pago")
            .order_by("-fecha_pago", "-id")
        )
        desde = request.GET.get("desde")
        hasta = request.GET.get("hasta")
        if desde:
            ventas = ventas.filter(fecha_pago__gte=desde)
        if hasta:
            ventas = ventas.filter(fecha_pago__lte=hasta)

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="ventas.csv"'
        writer = csv.writer(response)
        writer.writerow(["id", "fecha_pago", "cliente", "dni", "pelicula", "categoria", "metodo_pago", "precio"])
        for venta in ventas:
            writer.writerow(
                [
                    venta.pk,
                    venta.fecha_pago,
                    venta.cliente.nombre,
                    venta.cliente.dni,
                    venta.pelicula.titulo,
                    venta.pelicula.categoria.nombre,
                    venta.metodo_pago.nombre if venta.metodo_pago else "",
                    venta.precio,
                ]
            )
        return response


class SimularVentasView(AuthenticatedWriteMixin, GroupRequiredMixin, PermissionRequiredMixin, FormView):
    template_name = "tienda/simular_ventas.html"
    form_class = SimularVentasForm
    success_url = reverse_lazy("tienda:ventas_list")
    permission_required = "tienda.can_simulate_sales"
    required_group = "supervisor"

    def get_initial(self):
        return {
            "numero_ventas": 10,
            "desde": timezone.localdate(),
            "hasta": timezone.localdate(),
        }

    def form_valid(self, form):
        numero = form.cleaned_data["numero_ventas"]
        desde = form.cleaned_data["desde"]
        hasta = form.cleaned_data["hasta"]
        metodo_pago = form.cleaned_data.get("metodo_pago")

        clientes = list(Cliente.objects.all())
        peliculas = list(Pelicula.objects.all())

        if not clientes or not peliculas:
            form.add_error(None, "Necesitas al menos 1 cliente y 1 película para simular.")
            return self.form_invalid(form)

        alquileres_creados = 0
        delta_dias = (hasta - desde).days if hasta >= desde else 0

        for _ in range(numero * 3):
            if alquileres_creados >= numero:
                break
            cliente = random.choice(clientes)
            pelicula = random.choice(peliculas)
            offset = random.randint(0, max(delta_dias, 0))
            fecha_alquiler = desde + datetime.timedelta(days=offset)
            fecha_devolucion = fecha_alquiler + datetime.timedelta(days=random.randint(0, 7))

            try:
                Alquiler.objects.create(
                    cliente=cliente,
                    pelicula=pelicula,
                    fecha_alquiler=fecha_alquiler,
                    fecha_pago=fecha_alquiler,
                    fecha_devolucion=fecha_devolucion,
                    estado=Alquiler.ESTADO_PAGADO,
                    metodo_pago=metodo_pago,
                )
                alquileres_creados += 1
            except (IntegrityError, ValidationError):
                continue

        self.request.session["ultimo_resumen_simulacion"] = {
            "cantidad": alquileres_creados,
            "desde": str(desde),
            "hasta": str(hasta),
        }
        messages.success(self.request, f"Se simularon {alquileres_creados} ventas.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["resumen"] = self.request.session.get("ultimo_resumen_simulacion")
        return ctx


class ImportarClientesCSVView(AuthenticatedWriteMixin, SessionRateLimitMixin, FormView):
    template_name = "tienda/clientes_importar.html"
    form_class = ImportarClientesCSVForm
    success_url = reverse_lazy("tienda:cliente_list")
    rate_limit_key = "importar-clientes"

    def form_valid(self, form):
        filas = form.parse_rows()
        creados = 0
        actualizados = 0
        for fila in filas:
            defaults = {
                "nombre": fila["nombre"].strip(),
                "email": fila["email"].strip() or None,
                "telefono": fila["telefono"].strip(),
            }
            _, created = Cliente.objects.update_or_create(dni=fila["dni"].strip(), defaults=defaults)
            if created:
                creados += 1
            else:
                actualizados += 1
        messages.success(self.request, f"Importación completada. Nuevos: {creados}. Actualizados: {actualizados}.")
        return super().form_valid(form)


class ActualizarPreciosCategoriaView(AuthenticatedWriteMixin, FormView):
    template_name = "tienda/pelicula_actualizar_precios.html"
    form_class = ActualizarPreciosCategoriaForm
    success_url = reverse_lazy("tienda:pelicula_list")

    def form_valid(self, form):
        categoria = form.cleaned_data["categoria"]
        porcentaje = form.cleaned_data["porcentaje"]
        factor = Decimal("1") + (porcentaje / Decimal("100"))
        peliculas = Pelicula.objects.filter(categoria=categoria)
        total = 0
        for pelicula in peliculas:
            pelicula.precio_alquiler = (pelicula.precio_alquiler * factor).quantize(Decimal("0.01"))
            pelicula.save(update_fields=["precio_alquiler", "slug"])
            total += 1
        messages.success(self.request, f"Se actualizaron {total} películas de la categoría {categoria.nombre}.")
        return super().form_valid(form)


class AuditoriaListView(AuthenticatedWriteMixin, ListView):
    model = EventoDominio
    template_name = "tienda/auditoria_list.html"
    context_object_name = "eventos"
    paginate_by = 30


class CerrarCajaView(AuthenticatedWriteMixin, PermissionRequiredMixin, View):
    permission_required = "tienda.can_close_cash"

    def post(self, request):
        hoy = timezone.localdate()
        caja, _ = CajaDiaria.objects.get_or_create(fecha=hoy)
        caja.cerrada = True
        caja.cerrada_en = timezone.now()
        caja.cerrada_por = request.user
        caja.save(update_fields=["cerrada", "cerrada_en", "cerrada_por"])
        messages.success(request, f"Caja del día {hoy} cerrada.")
        return redirect(request.POST.get("next") or "tienda:index")




