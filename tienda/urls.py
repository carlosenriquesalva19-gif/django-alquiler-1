from django.urls import path

from . import views

app_name = "tienda"

urlpatterns = [
    path("", views.index, name="index"),
    # Categorias
    path("categorias/", views.CategoriaListView.as_view(), name="categoria_list"),
    path("categorias/nueva/", views.CategoriaCreateView.as_view(), name="categoria_create"),
    path("categorias/<int:pk>/editar/", views.CategoriaUpdateView.as_view(), name="categoria_update"),
    path("categorias/<int:pk>/eliminar/", views.CategoriaDeleteView.as_view(), name="categoria_delete"),
    path("categorias/<int:pk>/restaurar/", views.CategoriaRestoreView.as_view(), name="categoria_restore"),
    # Peliculas
    path("peliculas/", views.PeliculaListView.as_view(), name="pelicula_list"),
    path("peliculas/nueva/", views.PeliculaCreateView.as_view(), name="pelicula_create"),
    path("peliculas/<int:pk>/", views.PeliculaDetailView.as_view(), name="pelicula_detail"),
    path("peliculas/<int:pk>/editar/", views.PeliculaUpdateView.as_view(), name="pelicula_update"),
    path("peliculas/<int:pk>/eliminar/", views.PeliculaDeleteView.as_view(), name="pelicula_delete"),
    path("peliculas/<int:pk>/restaurar/", views.PeliculaRestoreView.as_view(), name="pelicula_restore"),
    path("peliculas/actualizar-precios/", views.ActualizarPreciosCategoriaView.as_view(), name="pelicula_actualizar_precios"),
    # Clientes
    path("clientes/", views.ClienteListView.as_view(), name="cliente_list"),
    path("clientes/nuevo/", views.ClienteCreateView.as_view(), name="cliente_create"),
    path("clientes/importar/", views.ImportarClientesCSVView.as_view(), name="cliente_importar"),
    path("clientes/<int:pk>/", views.ClienteDetailView.as_view(), name="cliente_detail"),
    path("clientes/<int:pk>/editar/", views.ClienteUpdateView.as_view(), name="cliente_update"),
    path("clientes/<int:pk>/eliminar/", views.ClienteDeleteView.as_view(), name="cliente_delete"),
    path("clientes/<int:pk>/restaurar/", views.ClienteRestoreView.as_view(), name="cliente_restore"),
    # Alquileres
    path("alquileres/", views.AlquilerListView.as_view(), name="alquiler_list"),
    path("alquileres/nuevo/", views.AlquilerCreateView.as_view(), name="alquiler_create"),
    path("alquileres/cobro-masivo/", views.CobroMasivoView.as_view(), name="alquiler_cobro_masivo"),
    path(
        "alquileres/<int:pk>/marcar-pagado/",
        views.MarcarPagadoView.as_view(),
        name="alquiler_marcar_pagado",
    ),
    # Ventas (en esta versión: alquileres pagados)
    path("ventas/", views.VentasListView.as_view(), name="ventas_list"),
    path("ventas/exportar.csv", views.VentasExportCSVView.as_view(), name="ventas_export_csv"),
    path("ventas/simular/", views.SimularVentasView.as_view(), name="ventas_simular"),
    path("auditoria/", views.AuditoriaListView.as_view(), name="auditoria_list"),
    path("caja/cerrar/", views.CerrarCajaView.as_view(), name="caja_cerrar"),
]

