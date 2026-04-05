from django.core.management.base import BaseCommand

from tienda.models import Alquiler, EventoDominio


class Command(BaseCommand):
    help = "Elimina alquileres de prueba y sus eventos asociados."

    def handle(self, *args, **options):
        eventos = EventoDominio.objects.filter(tipo__startswith="alquiler_")
        total_eventos = eventos.count()
        eventos.delete()
        total_alquileres = Alquiler.objects.count()
        Alquiler.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"Eliminados {total_alquileres} alquileres y {total_eventos} eventos."))
