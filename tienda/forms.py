from __future__ import annotations

import csv
import datetime
from decimal import Decimal
from io import StringIO

from django import forms
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Alquiler, Categoria, Cliente, MetodoPago, Pelicula


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre", "descripcion"]
        help_texts = {
            "nombre": "Usa un nombre corto y único para la categoría.",
            "descripcion": "Descripción opcional para el docente o el cajero.",
        }


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "dni", "email", "telefono"]
        help_texts = {
            "nombre": "Nombre completo del cliente.",
            "dni": "Debe tener exactamente 8 caracteres.",
            "email": "Correo opcional, pero si lo usas no se puede repetir.",
            "telefono": "Número de contacto opcional.",
        }

    def clean_dni(self):
        dni = (self.cleaned_data.get("dni") or "").strip()
        if len(dni) != 8:
            raise forms.ValidationError("El DNI debe tener exactamente 8 caracteres.")
        return dni


class PeliculaForm(forms.ModelForm):
    class Meta:
        model = Pelicula
        fields = [
            "titulo",
            "anio",
            "categoria",
            "director",
            "pais_origen",
            "duracion_minutos",
            "precio_alquiler",
            "stock",
        ]
        help_texts = {
            "titulo": "El título no puede quedar vacío ni con espacios.",
            "anio": "No debe ser mayor al año actual.",
            "categoria": "Selecciona la categoría principal.",
            "director": "Nombre del director, opcional.",
            "pais_origen": "País de producción, opcional.",
            "duracion_minutos": "Duración mínima: 1 minuto.",
            "precio_alquiler": "Debe respetar el mínimo definido en configuración.",
            "stock": "Cantidad disponible para alquilar.",
        }

    def clean_titulo(self):
        titulo = (self.cleaned_data.get("titulo") or "").strip()
        if not titulo:
            raise forms.ValidationError("El título no puede estar vacío.")
        return titulo

    def clean_anio(self):
        anio = self.cleaned_data["anio"]
        anio_actual = timezone.localdate().year
        if anio > anio_actual:
            raise forms.ValidationError("El año no puede ser mayor al actual.")
        return anio

    def clean_precio_alquiler(self):
        precio = self.cleaned_data["precio_alquiler"]
        minimo = getattr(settings, "PRECIO_ALQUILER_MINIMO", Decimal("0.00"))
        if precio < minimo:
            raise forms.ValidationError(f"El precio mínimo permitido es {minimo}.")
        return precio


class AlquilerCreateForm(forms.ModelForm):
    class Meta:
        model = Alquiler
        fields = ["cliente", "pelicula", "fecha_alquiler", "fecha_devolucion", "metodo_pago"]
        help_texts = {
            "cliente": "Cliente que realiza el alquiler.",
            "pelicula": "Solo aparecerán películas válidas; el stock se verifica al guardar.",
            "fecha_alquiler": "Por defecto se usa la fecha de hoy.",
            "fecha_devolucion": "Opcional. Debe ser igual o posterior a la fecha de alquiler.",
            "metodo_pago": "Opcional hasta registrar el cobro.",
        }
        widgets = {
            "fecha_alquiler": forms.DateInput(attrs={"type": "date"}),
            "fecha_devolucion": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["metodo_pago"].queryset = MetodoPago.objects.filter(activo=True)

    def clean_pelicula(self):
        pelicula = self.cleaned_data["pelicula"]
        if pelicula.stock <= 0:
            raise forms.ValidationError("No hay stock disponible para esta película.")
        return pelicula

    def clean(self):
        cleaned = super().clean()
        fecha_alquiler = cleaned.get("fecha_alquiler")
        fecha_devolucion = cleaned.get("fecha_devolucion")

        if fecha_alquiler and fecha_devolucion and fecha_devolucion < fecha_alquiler:
            raise forms.ValidationError("La devolución no puede marcarse antes del alquiler.")

        cliente = cleaned.get("cliente")
        pelicula = cleaned.get("pelicula")
        if cliente and pelicula and fecha_alquiler:
            duplicado = Alquiler.objects.filter(
                cliente=cliente,
                pelicula=pelicula,
                fecha_alquiler=fecha_alquiler,
            )
            if self.instance.pk:
                duplicado = duplicado.exclude(pk=self.instance.pk)
            if duplicado.exists():
                raise forms.ValidationError("Ya existe un alquiler para ese cliente, película y fecha.")

        return cleaned


class MarcarPagadoForm(forms.Form):
    fecha_pago = forms.DateField(
        required=False,
        label="Fecha de pago (opcional)",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Si no la indicas, se usará la fecha actual.",
    )
    fecha_devolucion = forms.DateField(
        required=False,
        label="Fecha de devolución (opcional)",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Si no la indicas, se usará la fecha actual.",
    )
    metodo_pago = forms.ModelChoiceField(
        queryset=MetodoPago.objects.none(),
        required=False,
        help_text="Método de pago opcional para registrar el cobro.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["metodo_pago"].queryset = MetodoPago.objects.filter(activo=True)

    def clean(self):
        cleaned = super().clean()
        fecha_pago = cleaned.get("fecha_pago")
        fecha_devolucion = cleaned.get("fecha_devolucion")
        if fecha_pago and fecha_devolucion and fecha_devolucion < fecha_pago:
            raise forms.ValidationError("La devolución no puede ser anterior a la fecha de pago.")
        return cleaned


class SimularVentasForm(forms.Form):
    numero_ventas = forms.IntegerField(
        min_value=1,
        max_value=200,
        label="Cantidad de ventas a simular",
        help_text="Máximo 200 para mantener la simulación ligera.",
    )
    desde = forms.DateField(required=False, label="Desde (opcional)", widget=forms.DateInput(attrs={"type": "date"}))
    hasta = forms.DateField(required=False, label="Hasta (opcional)", widget=forms.DateInput(attrs={"type": "date"}))
    metodo_pago = forms.ModelChoiceField(
        queryset=MetodoPago.objects.none(),
        required=False,
        help_text="Opcional. Si no eliges uno, se dejará vacío.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["metodo_pago"].queryset = MetodoPago.objects.filter(activo=True)

    def clean(self):
        cleaned = super().clean()
        desde = cleaned.get("desde")
        hasta = cleaned.get("hasta")

        if desde and hasta and desde > hasta:
            raise forms.ValidationError("La fecha 'Desde' no puede ser posterior a 'Hasta'.")

        if not desde and not hasta:
            today = datetime.date.today()
            cleaned["desde"] = today
            cleaned["hasta"] = today

        return cleaned


class AlquilerBusquedaForm(forms.Form):
    texto = forms.CharField(required=False, label="Texto")
    estado = forms.ChoiceField(required=False, choices=[("", "Todos")] + Alquiler.ESTADO_CHOICES)
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.all(), required=False)
    fecha_desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    fecha_hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    vencidos = forms.BooleanField(required=False)

    def filtrar(self, queryset):
        if not self.is_valid():
            return queryset

        texto = self.cleaned_data.get("texto")
        estado = self.cleaned_data.get("estado")
        categoria = self.cleaned_data.get("categoria")
        fecha_desde = self.cleaned_data.get("fecha_desde")
        fecha_hasta = self.cleaned_data.get("fecha_hasta")
        vencidos = self.cleaned_data.get("vencidos")

        if texto:
            queryset = queryset.filter(
                Q(cliente__nombre__icontains=texto)
                | Q(cliente__dni__icontains=texto)
                | Q(pelicula__titulo__icontains=texto)
            )
        if estado:
            queryset = queryset.filter(estado=estado)
        if categoria:
            queryset = queryset.filter(pelicula__categoria=categoria)
        if fecha_desde:
            queryset = queryset.filter(fecha_alquiler__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha_alquiler__lte=fecha_hasta)
        if vencidos:
            queryset = queryset.filter(
                estado=Alquiler.ESTADO_PENDIENTE,
                fecha_alquiler__lt=timezone.localdate(),
            )
        return queryset


class CobroMasivoForm(forms.Form):
    ids = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Ingresa IDs separados por coma o espacios.",
    )
    fecha_pago = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    metodo_pago = forms.ModelChoiceField(queryset=MetodoPago.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["metodo_pago"].queryset = MetodoPago.objects.filter(activo=True)

    def clean_ids(self):
        raw = self.cleaned_data["ids"]
        partes = [fragmento.strip() for fragmento in raw.replace("\n", ",").replace(" ", ",").split(",")]
        ids = []
        for parte in partes:
            if not parte:
                continue
            if not parte.isdigit():
                raise forms.ValidationError("Todos los IDs deben ser numéricos.")
            ids.append(int(parte))
        if not ids:
            raise forms.ValidationError("Debes ingresar al menos un ID.")
        return ids


class ImportarClientesCSVForm(forms.Form):
    archivo = forms.FileField(help_text="CSV con columnas: nombre,dni,email,telefono")

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if not archivo.name.lower().endswith(".csv"):
            raise forms.ValidationError("El archivo debe ser CSV.")
        return archivo

    def parse_rows(self):
        archivo = self.cleaned_data["archivo"]
        contenido = archivo.read().decode("utf-8")
        lector = csv.DictReader(StringIO(contenido))
        requeridas = {"nombre", "dni", "email", "telefono"}
        if not lector.fieldnames or set(lector.fieldnames) != requeridas:
            raise forms.ValidationError("El CSV debe tener exactamente las columnas: nombre,dni,email,telefono")
        return list(lector)


class ActualizarPreciosCategoriaForm(forms.Form):
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.all())
    porcentaje = forms.DecimalField(
        min_value=Decimal("-100"),
        max_value=Decimal("1000"),
        decimal_places=2,
        max_digits=7,
        help_text="Usa 10 para subir 10% o -5 para bajar 5%.",
    )


class PeliculaFiltroForm(forms.Form):
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.all(), required=False)
    anio = forms.IntegerField(required=False)
    precio_min = forms.DecimalField(required=False, decimal_places=2, max_digits=8)
    precio_max = forms.DecimalField(required=False, decimal_places=2, max_digits=8)

    def filtrar(self, queryset):
        if not self.is_valid():
            return queryset
        categoria = self.cleaned_data.get("categoria")
        anio = self.cleaned_data.get("anio")
        precio_min = self.cleaned_data.get("precio_min")
        precio_max = self.cleaned_data.get("precio_max")
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        if anio:
            queryset = queryset.filter(anio=anio)
        if precio_min is not None:
            queryset = queryset.filter(precio_alquiler__gte=precio_min)
        if precio_max is not None:
            queryset = queryset.filter(precio_alquiler__lte=precio_max)
        return queryset

