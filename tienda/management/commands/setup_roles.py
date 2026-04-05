from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Crea grupos cajero y supervisor con permisos base."

    def handle(self, *args, **options):
        cajero, _ = Group.objects.get_or_create(name="cajero")
        supervisor, _ = Group.objects.get_or_create(name="supervisor")
        perms = Permission.objects.filter(codename__in=["can_simulate_sales", "can_close_cash", "add_alquiler", "change_alquiler"])
        supervisor.permissions.set(perms)
        cajero.permissions.set(Permission.objects.filter(codename__in=["add_alquiler", "change_alquiler"]))
        self.stdout.write(self.style.SUCCESS("Grupos creados/actualizados."))
