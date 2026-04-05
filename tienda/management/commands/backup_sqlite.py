from datetime import datetime
from pathlib import Path
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Crea backup de SQLite con timestamp."

    def handle(self, *args, **options):
        origen = Path(settings.DATABASES["default"]["NAME"])
        destino_dir = Path(settings.BASE_DIR) / "backups"
        destino_dir.mkdir(exist_ok=True)
        destino = destino_dir / f"db-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
        shutil.copy2(origen, destino)
        self.stdout.write(self.style.SUCCESS(f"Backup creado: {destino}"))
