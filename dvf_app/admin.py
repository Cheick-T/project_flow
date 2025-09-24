from django.contrib import admin

from .models import CleanDVFRecord, Commune, Department


@admin.register(CleanDVFRecord)
class CleanDVFRecordAdmin(admin.ModelAdmin):
    list_display = ("date_mutation", "address", "commune", "valeur_fonciere", "type_local")
    list_filter = ("nature_mutation", "code_departement", "type_local")
    search_fields = ("commune", "voie", "code_postal", "code_voie", "identifiant_local")
    ordering = ("-date_mutation", "commune")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "commune_count", "address_count", "centroid_lon", "centroid_lat", "updated_at")
    search_fields = ("code", "name")
    ordering = ("code",)


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = (
        "code_commune",
        "name",
        "department",
        "address_count",
        "centroid_lon",
        "centroid_lat",
        "updated_at",
    )
    search_fields = ("code_commune", "name", "department__code", "postal_codes")
    list_filter = ("department__code",)
    ordering = ("name",)
