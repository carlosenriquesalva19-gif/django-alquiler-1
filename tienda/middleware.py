from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, "profile"):
            if request.user.profile.must_change_password:
                allowed = {
                    reverse("admin:password_change"),
                    reverse("admin:password_change_done"),
                    reverse("admin:logout"),
                }
                if not request.path.startswith("/static/") and request.path not in allowed:
                    messages.warning(request, "Debes cambiar tu contraseña inicial antes de continuar.")
                    return redirect("admin:password_change")
        return self.get_response(request)


class InactivityLogoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = timezone.now().timestamp()
            ultimo = request.session.get("last_activity_ts")
            max_idle = 60 * 15
            if ultimo and now - ultimo > max_idle:
                logout(request)
                messages.warning(request, "Tu sesión se cerró por inactividad.")
                return redirect("admin:login")
            request.session["last_activity_ts"] = now
        return self.get_response(request)
