import csv


from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

from dvf_app.models import CleanDVFRecord, Commune, Department


class Command(BaseCommand):
    help = "Import Department, Commune, and CleanDVFRecord data from CSV dumps"

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-path",
            default="dvf_app/management/dumps",
            help="Directory containing Department.csv, Commune.csv, and CleanDVFRecord.csv",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-import data even if tables already contain rows (will wipe tables first)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=2000,
            help="Number of CleanDVFRecord rows to insert per bulk create",
        )

    def handle(self, *args, **options):
        base_path = Path(options["base_path"]).resolve()
        if not base_path.exists():
            raise CommandError(f"Dump directory not found: {base_path}")

        department_file = base_path / "Department.csv"
        commune_file = base_path / "Commune.csv"
        clean_file = base_path / "CleanDVFRecord.csv"

        for file_path in [department_file, commune_file, clean_file]:
            if not file_path.exists():
                raise CommandError(f"Required dump file missing: {file_path}")

        if options["force"]:
            self.stdout.write(self.style.WARNING("Force option enabled: clearing existing data"))
            self._clear_tables()
        else:
            if Department.objects.exists() or Commune.objects.exists() or CleanDVFRecord.objects.exists():
                self.stdout.write(
                    self.style.WARNING(
                        "Existing data detected. Skipping import. Use --force to overwrite existing rows."
                    )
                )
                return

        self._import_departments(department_file)
        self._import_communes(commune_file)
        self._import_clean_records(clean_file, batch_size=options["batch_size"])

        self.stdout.write(self.style.SUCCESS("Import completed successfully"))

    def _clear_tables(self):
        with transaction.atomic():
            CleanDVFRecord.objects.all().delete()
            Commune.objects.all().delete()
            Department.objects.all().delete()

    def _import_departments(self, path: Path):
        self.stdout.write("Importing departments...")
        departments = []
        with path.open("r", encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                departments.append(
                    Department(
                        code=row["code"].strip(),
                        name=row["name"].strip(),
                        centroid_lon=self._parse_float(row.get("centroid_lon")),
                        centroid_lat=self._parse_float(row.get("centroid_lat")),
                        address_count=self._parse_int(row.get("address_count"), allow_zero=True) or 0,
                        commune_count=self._parse_int(row.get("commune_count"), allow_zero=True) or 0,
                        min_lon=self._parse_float(row.get("min_lon")),
                        min_lat=self._parse_float(row.get("min_lat")),
                        max_lon=self._parse_float(row.get("max_lon")),
                        max_lat=self._parse_float(row.get("max_lat")),
                    )
                )
        Department.objects.bulk_create(departments, batch_size=1000)
        self.stdout.write(self.style.SUCCESS(f"Imported {len(departments)} departments"))

    def _import_communes(self, path: Path):
        self.stdout.write("Importing communes...")
        department_map = {dept.code: dept for dept in Department.objects.all()}
        communes = []
        skipped = 0
        with path.open("r", encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                department_code = row["department_code"].strip()
                department = department_map.get(department_code)
                if not department:
                    skipped += 1
                    continue
                communes.append(
                    Commune(
                        code_commune=row["code_commune"].strip(),
                        department=department,
                        name=row["name"].strip(),
                        centroid_lon=self._parse_float(row.get("centroid_lon")),
                        centroid_lat=self._parse_float(row.get("centroid_lat")),
                        address_count=self._parse_int(row.get("address_count"), allow_zero=True) or 0,
                        postal_codes=row.get("postal_codes", "").strip(),
                        min_lon=self._parse_float(row.get("min_lon")),
                        min_lat=self._parse_float(row.get("min_lat")),
                        max_lon=self._parse_float(row.get("max_lon")),
                        max_lat=self._parse_float(row.get("max_lat")),
                    )
                )
        Commune.objects.bulk_create(communes, batch_size=1000)
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(communes)} communes" + (f" (skipped {skipped} without department)" if skipped else "")
            )
        )

    def _import_clean_records(self, path: Path, batch_size: int):
        self.stdout.write("Importing CleanDVFRecord dataset...")
        records_to_create = []
        inserted = 0
        with path.open("r", encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                records_to_create.append(
                    CleanDVFRecord(
                        date_mutation=self._parse_date(row.get("date_mutation")),
                        nature_mutation=row.get("nature_mutation", "").strip(),
                        valeur_fonciere=self._parse_decimal(row.get("valeur_fonciere")),
                        no_voie=row.get("no_voie", "").strip(),
                        btq=row.get("btq", "").strip(),
                        type_de_voie=row.get("type_de_voie", "").strip(),
                        code_voie=row.get("code_voie", "").strip(),
                        voie=row.get("voie", "").strip(),
                        code_postal=row.get("code_postal", "").strip(),
                        commune=row.get("commune", "").strip(),
                        code_departement=row.get("code_departement", "").strip(),
                        code_commune=row.get("code_commune", "").strip(),
                        prefixe_de_section=row.get("prefixe_de_section", "").strip(),
                        section=row.get("section", "").strip(),
                        no_plan=row.get("no_plan", "").strip(),
                        no_volume=row.get("no_volume", "").strip(),
                        nombre_de_lots=self._parse_int(row.get("nombre_de_lots")),
                        code_type_local=row.get("code_type_local", "").strip(),
                        type_local=row.get("type_local", "").strip(),
                        identifiant_local=row.get("identifiant_local", "").strip(),
                        surface_reelle_bati=self._parse_int(row.get("surface_reelle_bati")),
                        nombre_pieces_principales=self._parse_int(row.get("nombre_pieces_principales")),
                        nature_culture=row.get("nature_culture", "").strip(),
                        nature_culture_speciale=row.get("nature_culture_speciale", "").strip(),
                        surface_terrain=self._parse_int(row.get("surface_terrain")),
                    )
                )
                if len(records_to_create) >= batch_size:
                    CleanDVFRecord.objects.bulk_create(records_to_create, batch_size=batch_size)
                    inserted += len(records_to_create)
                    self.stdout.write(f"  Inserted {inserted} rows...")
                    records_to_create.clear()
        if records_to_create:
            CleanDVFRecord.objects.bulk_create(records_to_create, batch_size=batch_size)
            inserted += len(records_to_create)
        self.stdout.write(self.style.SUCCESS(f"Imported {inserted} CleanDVFRecord rows"))

    def _parse_float(self, value: str):
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return float(value)

    def _parse_int(self, value: str, allow_zero: bool = False):
        if value is None:
            return None
        value = value.strip()
        if not value:
            return 0 if allow_zero else None
        return int(value)

    def _parse_decimal(self, value: str):
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return Decimal(value)

    def _parse_date(self, value: str):
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return parse_date(value)
