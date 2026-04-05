import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from tienda.models import Categoria, Cliente, MetodoPago, Pelicula


class Command(BaseCommand):
    help = "Carga datos de ejemplo."

    def add_arguments(self, parser):
        parser.add_argument("--clientes", type=int, default=10)
        parser.add_argument("--peliculas", type=int, default=10)

    def handle(self, *args, **options):
        categorias = ["Acción", "Drama", "Comedia", "Terror"]
        for nombre in categorias:
            Categoria.objects.get_or_create(nombre=nombre)

        MetodoPago.objects.get_or_create(nombre="Efectivo")
        MetodoPago.objects.get_or_create(nombre="Tarjeta")

        for i in range(options["clientes"]):
            Cliente.objects.get_or_create(
                dni=f"{10000000 + i}",
                defaults={"nombre": f"Cliente {i+1}", "email": f"cliente{i+1}@demo.local"},
            )

        categorias_db = list(Categoria.objects.all())
        for i in range(options["peliculas"]):
            Pelicula.objects.get_or_create(
                titulo=f"Pelicula {i+1}",
                anio=2000 + (i % 20),
                defaults={
                    "categoria": random.choice(categorias_db),
                    "precio_alquiler": Decimal("5.00") + Decimal(i % 5),
                    "stock": 3,
                    "duracion_minutos": 90 + i,
                    "director": f"Director {i+1}",
                    "pais_origen": "Perú",
                },
            )

        self.stdout.write(self.style.SUCCESS(f"Seed completado {timezone.localdate()}"))
