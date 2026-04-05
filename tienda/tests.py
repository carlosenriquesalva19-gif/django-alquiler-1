import datetime
import json
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_login_failed
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.http import HttpRequest
from django.test.client import RequestFactory
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.test.utils import CaptureQueriesContext

from .forms import AlquilerCreateForm, PeliculaForm
from .error_views import error_404, error_500
from .models import Alquiler, Categoria, Cliente, HistorialPrecioPelicula, LoginFallido, MetodoPago, Pelicula


class ModelosTest(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Acción")
        self.metodo = MetodoPago.objects.create(nombre="Efectivo")
        self.pelicula = Pelicula.objects.create(
            titulo="Matrix",
            anio=1999,
            categoria=self.categoria,
            precio_alquiler=Decimal("5.00"),
            stock=2,
        )
        self.cliente = Cliente.objects.create(nombre="Ana", dni="12345678")

    def test_pelicula_genera_slug(self):
        self.assertEqual(self.pelicula.slug, "matrix")

    def test_alquiler_no_permite_devolucion_antes_del_alquiler(self):
        alquiler = Alquiler(
            cliente=self.cliente,
            pelicula=self.pelicula,
            fecha_alquiler=datetime.date(2026, 4, 5),
            fecha_devolucion=datetime.date(2026, 4, 4),
        )
        with self.assertRaises(ValidationError):
            alquiler.full_clean()

    def test_marcar_pagado_registra_fecha_y_metodo(self):
        alquiler = Alquiler.objects.create(cliente=self.cliente, pelicula=self.pelicula)
        alquiler.marcar_pagado(fecha_pago=datetime.date(2026, 4, 6), metodo_pago=self.metodo)
        alquiler.refresh_from_db()
        self.assertEqual(alquiler.estado, Alquiler.ESTADO_PAGADO)
        self.assertEqual(alquiler.fecha_pago, datetime.date(2026, 4, 6))
        self.assertEqual(alquiler.metodo_pago, self.metodo)

    def test_cambio_de_precio_registra_historial(self):
        self.pelicula.precio_alquiler = Decimal("9.50")
        self.pelicula.save()
        historial = HistorialPrecioPelicula.objects.get(pelicula=self.pelicula)
        self.assertEqual(historial.precio_anterior, Decimal("5.00"))
        self.assertEqual(historial.precio_nuevo, Decimal("9.50"))


class FormulariosTest(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Drama")

    def test_pelicula_form_valida_titulo_y_anio(self):
        form = PeliculaForm(
            data={
                "titulo": "   ",
                "anio": 9999,
                "categoria": self.categoria.pk,
                "director": "",
                "pais_origen": "",
                "duracion_minutos": 90,
                "precio_alquiler": "5.00",
                "stock": 1,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("titulo", form.errors)
        self.assertIn("anio", form.errors)

    def test_alquiler_form_detecta_duplicado(self):
        cliente = Cliente.objects.create(nombre="Luis", dni="87654321")
        pelicula = Pelicula.objects.create(
            titulo="Avatar",
            anio=2009,
            categoria=self.categoria,
            precio_alquiler=Decimal("6.00"),
            stock=2,
        )
        Alquiler.objects.create(cliente=cliente, pelicula=pelicula, fecha_alquiler=datetime.date(2026, 4, 1))
        form = AlquilerCreateForm(
            data={
                "cliente": cliente.pk,
                "pelicula": pelicula.pk,
                "fecha_alquiler": "2026-04-01",
                "fecha_devolucion": "",
                "metodo_pago": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)


class VistasTest(TestCase):
    fixtures = ["base_data.json"]

    def setUp(self):
        categoria = Categoria.objects.get(pk=1)
        self.cliente = Cliente.objects.create(nombre="Mario", dni="11112222")
        self.pelicula = Pelicula.objects.create(
            titulo="Terminator",
            anio=1984,
            categoria=categoria,
            precio_alquiler=Decimal("7.00"),
            stock=3,
        )

    def test_dashboard_responde(self):
        response = self.client.get(reverse("tienda:index"))
        self.assertEqual(response.status_code, 200)

    def test_listado_peliculas_responde(self):
        response = self.client.get(reverse("tienda:pelicula_list"))
        self.assertContains(response, "Terminator")

    def test_exportacion_csv_ventas_devuelve_encabezado(self):
        alquiler = Alquiler.objects.create(cliente=self.cliente, pelicula=self.pelicula)
        alquiler.marcar_pagado()
        user = get_user_model().objects.create_user(username="staff", password="demo12345", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("tienda:ventas_export_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("id,fecha_pago,cliente,dni,pelicula,categoria,metodo_pago,precio", response.content.decode("utf-8"))

    def test_simular_ventas_requiere_supervisor(self):
        user = get_user_model().objects.create_user(username="cajero", password="demo12345")
        user.groups.add(Group.objects.create(name="cajero"))
        self.client.force_login(user)
        response = self.client.get(reverse("tienda:ventas_simular"))
        self.assertEqual(response.status_code, 403)

    def test_listado_alquileres_usa_consultas_optimizadas(self):
        Alquiler.objects.create(cliente=self.cliente, pelicula=self.pelicula)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("tienda:alquiler_list"))
            self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 8)


class ComandosTest(TestCase):
    def _make_workspace_tempdir(self):
        tempdir = Path.cwd() / "tmp_test_artifacts"
        tempdir.mkdir(exist_ok=True)
        return tempdir

    def test_setup_roles_crea_grupos(self):
        call_command("setup_roles")
        self.assertTrue(Group.objects.filter(name="cajero").exists())
        self.assertTrue(Group.objects.filter(name="supervisor").exists())

    def test_seed_data_crea_registros(self):
        call_command("seed_data", clientes=2, peliculas=2)
        self.assertGreaterEqual(Cliente.objects.count(), 2)
        self.assertGreaterEqual(Pelicula.objects.count(), 2)

    def test_limpiar_alquileres_prueba_elimina_datos(self):
        categoria = Categoria.objects.create(nombre="Limpieza")
        cliente = Cliente.objects.create(nombre="Temp", dni="33334444")
        pelicula = Pelicula.objects.create(
            titulo="Temporal",
            anio=2001,
            categoria=categoria,
            precio_alquiler=Decimal("4.00"),
            stock=2,
        )
        Alquiler.objects.create(cliente=cliente, pelicula=pelicula)
        call_command("limpiar_alquileres_prueba")
        self.assertEqual(Alquiler.objects.count(), 0)

    @override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(Path.cwd() / "tmp_test_artifacts" / "backup_source.sqlite3")}})
    def test_backup_sqlite_crea_archivo(self):
        tempdir = self._make_workspace_tempdir()
        origen = tempdir / "backup_source.sqlite3"
        origen.write_bytes(b"sqlite-source")
        call_command("backup_sqlite")
        backups = list((Path.cwd() / "backups").glob("db-*.sqlite3"))
        self.assertTrue(backups)

    @override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(Path.cwd() / "tmp_restore.sqlite3")}})
    def test_restore_backup_requiere_force_y_copia_archivo(self):
        tmpdir = self._make_workspace_tempdir()
        backup = tmpdir / "restore.sqlite3"
        backup.write_bytes(b"sqlite-backup")
        with self.assertRaises(CommandError):
            call_command("restore_backup", str(backup))
        call_command("restore_backup", str(backup), "--force")
        self.assertEqual((Path.cwd() / "tmp_restore.sqlite3").read_bytes(), b"sqlite-backup")

    def test_restore_backup_falla_si_no_existe_archivo(self):
        with self.assertRaises(CommandError):
            call_command("restore_backup", str(Path.cwd() / "tmp_test_artifacts" / "no-existe.sqlite3"), "--force")

    def test_generar_reto_personalizado_crea_json(self):
        tempdir = self._make_workspace_tempdir()
        call_command(
            "generar_reto_personalizado",
            alumno="Ana Perez",
            codigo="2026A001",
            cantidad=6,
            salida=str(tempdir),
            semilla_curso="curso-demo",
        )
        archivo = tempdir / "ana-perez-2026A001.json"
        self.assertTrue(archivo.exists())
        data = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertEqual(data["alumno"], "Ana Perez")
        self.assertEqual(data["codigo"], "2026A001")
        self.assertEqual(len(data["retos_asignados"]), 6)
        self.assertIn("token_entrega", data)
        self.assertIn("parametros_unicos", data)

    def test_generar_reto_personalizado_valida_cantidad(self):
        with self.assertRaises(CommandError):
            call_command(
                "generar_reto_personalizado",
                alumno="Ana Perez",
                codigo="2026A001",
                cantidad=4,
            )


class FlujoIntegracionTest(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nombre="SciFi")
        metodo = MetodoPago.objects.create(nombre="Tarjeta")
        self.user = get_user_model().objects.create_user(username="admin", password="demo12345")
        self.user.groups.add(Group.objects.create(name="cajero"))
        self.cliente = Cliente.objects.create(nombre="Laura", dni="22223333")
        self.pelicula = Pelicula.objects.create(
            titulo="Alien",
            anio=1979,
            categoria=categoria,
            precio_alquiler=Decimal("8.00"),
            stock=2,
        )
        self.metodo = metodo

    def test_crear_alquiler_pagar_y_ver_en_ventas(self):
        alquiler = Alquiler.objects.create(cliente=self.cliente, pelicula=self.pelicula)
        alquiler.marcar_pagado(metodo_pago=self.metodo)
        response = self.client.get(reverse("tienda:ventas_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alien")


class RegresionErroresReportadosTest(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nombre="Regresion")
        self.cliente = Cliente.objects.create(nombre="Rosa", dni="44445555")
        self.pelicula = Pelicula.objects.create(
            titulo="Sin Stock",
            anio=2005,
            categoria=categoria,
            precio_alquiler=Decimal("5.00"),
            stock=0,
        )

    def test_no_permite_crear_alquiler_sin_stock(self):
        form = AlquilerCreateForm(
            data={
                "cliente": self.cliente.pk,
                "pelicula": self.pelicula.pk,
                "fecha_alquiler": "2026-04-04",
                "fecha_devolucion": "",
                "metodo_pago": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("pelicula", form.errors)


class SeguridadTest(TestCase):
    def test_usuario_nuevo_marca_cambio_de_password_pendiente(self):
        user = get_user_model().objects.create_user(username="nuevo", password="demo12345")
        self.assertTrue(user.profile.must_change_password)

    def test_login_fallido_se_registra_en_auditoria(self):
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "pytest-agent"
        user_login_failed.send(sender=get_user_model(), credentials={"username": "fallido"}, request=request)
        self.assertEqual(LoginFallido.objects.count(), 1)


class ConsistenciaTransaccionalTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Tx")
        self.metodo = MetodoPago.objects.create(nombre="Yape")
        self.cliente = Cliente.objects.create(nombre="Tx Cliente", dni="55556666")
        self.pelicula = Pelicula.objects.create(
            titulo="Tx Movie",
            anio=2010,
            categoria=self.categoria,
            precio_alquiler=Decimal("6.00"),
            stock=2,
        )

    def test_doble_cobro_mantiene_operacion_idempotente(self):
        alquiler = Alquiler.objects.create(cliente=self.cliente, pelicula=self.pelicula)
        alquiler_a = Alquiler.objects.get(pk=alquiler.pk)
        alquiler_b = Alquiler.objects.get(pk=alquiler.pk)
        alquiler_a.marcar_pagado(metodo_pago=self.metodo)
        alquiler_b.marcar_pagado(metodo_pago=self.metodo)
        alquiler.refresh_from_db()
        self.pelicula.refresh_from_db()
        self.assertEqual(alquiler.estado, Alquiler.ESTADO_PAGADO)
        self.assertEqual(self.pelicula.stock, 2)


class ErrorViewsTest(TestCase):
    def test_error_404_renderiza_pagina_personalizada(self):
        request = RequestFactory().get("/ruta-inexistente/")
        response = error_404(request, Exception("no existe"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Página no encontrada", response.content.decode("utf-8"))

    def test_error_500_renderiza_pagina_personalizada(self):
        request = RequestFactory().get("/error/")
        response = error_500(request)
        self.assertEqual(response.status_code, 500)
        self.assertIn("Ocurrió un error interno", response.content.decode("utf-8"))
