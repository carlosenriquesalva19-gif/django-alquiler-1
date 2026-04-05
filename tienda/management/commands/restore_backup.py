from pathlib import Path
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restaura un backup SQLite."

    def add_arguments(self, parser):
        parser.add_argument("backup_path")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        backup = Path(options["backup_path"])
        if not backup.exists():
            raise CommandError("El backup indicado no existe.")
        if not options["force"]:
            raise CommandError("Usa --force para confirmar la restauración.")
        destino = Path(settings.DATABASES["default"]["NAME"])
        shutil.copy2(backup, destino)
        self.stdout.write(self.style.SUCCESS(f"Base restaurada desde {backup}"))
