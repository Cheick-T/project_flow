from django.urls import path

from . import views

app_name = "dvf_app"

urlpatterns = [
    path("", views.LeafletMapView.as_view(), name="map"),
    path("api/heatmap/", views.heatmap_data, name="heatmap-data"),
    path("api/communes/", views.commune_options, name="commune-options"),
]
