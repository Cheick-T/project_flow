from django.db import models


class Department(models.Model):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=150, blank=True)
    centroid_lon = models.FloatField(null=True, blank=True)
    centroid_lat = models.FloatField(null=True, blank=True)
    address_count = models.PositiveIntegerField(default=0)
    commune_count = models.PositiveIntegerField(default=0)
    min_lon = models.FloatField(null=True, blank=True)
    min_lat = models.FloatField(null=True, blank=True)
    max_lon = models.FloatField(null=True, blank=True)
    max_lat = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        label = self.name or ""
        return f"{self.code} - {label}".strip(" -")


class Commune(models.Model):
    code_commune = models.CharField(max_length=5, unique=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="communes")
    name = models.CharField(max_length=150)
    centroid_lon = models.FloatField(null=True, blank=True)
    centroid_lat = models.FloatField(null=True, blank=True)
    address_count = models.PositiveIntegerField(default=0)
    postal_codes = models.TextField(blank=True)
    min_lon = models.FloatField(null=True, blank=True)
    min_lat = models.FloatField(null=True, blank=True)
    max_lon = models.FloatField(null=True, blank=True)
    max_lat = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code_commune})"


class CleanDVFRecord(models.Model):
    date_mutation = models.DateField(null=True, blank=True)
    nature_mutation = models.CharField(max_length=100, blank=True)
    valeur_fonciere = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    no_voie = models.CharField(max_length=10, blank=True)
    btq = models.CharField(max_length=5, blank=True, verbose_name="B/T/Q")
    type_de_voie = models.CharField(max_length=100, blank=True)
    code_voie = models.CharField(max_length=10, blank=True)
    voie = models.CharField(max_length=200, blank=True)
    code_postal = models.CharField(max_length=10, blank=True)
    commune = models.CharField(max_length=150, blank=True)
    code_departement = models.CharField(max_length=3, blank=True)
    code_commune = models.CharField(max_length=10, blank=True)
    prefixe_de_section = models.CharField(max_length=10, blank=True)
    section = models.CharField(max_length=10, blank=True)
    no_plan = models.CharField(max_length=10, blank=True)
    no_volume = models.CharField(max_length=10, blank=True)
    nombre_de_lots = models.PositiveIntegerField(null=True, blank=True)
    code_type_local = models.CharField(max_length=10, blank=True)
    type_local = models.CharField(max_length=100, blank=True)
    identifiant_local = models.CharField(max_length=50, blank=True)
    surface_reelle_bati = models.PositiveIntegerField(null=True, blank=True)
    nombre_pieces_principales = models.PositiveIntegerField(null=True, blank=True)
    nature_culture = models.CharField(max_length=100, blank=True)
    nature_culture_speciale = models.CharField(max_length=100, blank=True)
    surface_terrain = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Clean DVF record"
        verbose_name_plural = "Clean DVF records"
        ordering = ["-date_mutation", "commune", "code_postal"]

    def __str__(self) -> str:
        commune = self.commune or "Unknown locality"
        date = self.date_mutation.isoformat() if self.date_mutation else "unknown date"
        return f"{commune} ({date})"

    def address(self) -> str:
        street_parts = [
            part
            for part in [self.no_voie, self.btq, self.type_de_voie, self.voie]
            if part
        ]
        street = " ".join(street_parts)
        locality_parts = [part for part in [self.code_postal, self.commune] if part]
        locality = ", ".join(locality_parts)

        if street and locality:
            return f"{street}, {locality}"
        return street or locality or ""

    address.short_description = "Address"
