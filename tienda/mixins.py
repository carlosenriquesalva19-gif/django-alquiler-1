from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.utils import timezone


class AuthenticatedWriteMixin(LoginRequiredMixin):
    login_url = reverse_lazy("admin:login")


class OrderedPaginatedListMixin:
    paginate_by = 20
    default_ordering = None

    def get_ordering(self):
        return self.request.GET.get("ordering") or self.default_ordering

    def get_queryset(self):
        queryset = super().get_queryset()
        ordering = self.get_ordering()
        if ordering:
            queryset = queryset.order_by(ordering)
        return queryset

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        querydict = self.request.GET.copy()
        querydict.pop("page", None)
        ctx["querystring"] = querydict.urlencode()
        return ctx


class MessageMixin:
    success_message = ""

    def add_success_message(self):
        if self.success_message:
            messages.success(self.request, self.success_message)


class NextUrlMixin:
    fallback_success_url = None

    def get_success_url(self):
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url:
            return next_url
        if self.fallback_success_url:
            return str(self.fallback_success_url)
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["next_url"] = self.request.GET.get("next") or self.request.POST.get("next")
        return ctx


class BreadcrumbMixin:
    breadcrumbs = None

    def get_breadcrumbs(self):
        return self.breadcrumbs or []

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["breadcrumbs"] = self.get_breadcrumbs()
        return ctx


class SessionRateLimitMixin:
    rate_limit_key = "generic"
    rate_limit_count = 5
    rate_limit_window_seconds = 60

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST":
            now = timezone.now()
            key = f"rate-limit:{self.rate_limit_key}"
            historial = request.session.get(key, [])
            limite = now - timedelta(seconds=self.rate_limit_window_seconds)
            historial = [stamp for stamp in historial if datetime.fromisoformat(stamp) > limite]
            if len(historial) >= self.rate_limit_count:
                raise PermissionDenied("Has excedido el número de intentos permitidos. Inténtalo más tarde.")
            historial.append(now.isoformat())
            request.session[key] = historial
        return super().dispatch(request, *args, **kwargs)


class GroupRequiredMixin:
    required_group = None

    def dispatch(self, request, *args, **kwargs):
        if self.required_group and not (
            request.user.is_superuser or request.user.groups.filter(name=self.required_group).exists()
        ):
            raise PermissionDenied("No tienes permisos suficientes para esta operación.")
        return super().dispatch(request, *args, **kwargs)
