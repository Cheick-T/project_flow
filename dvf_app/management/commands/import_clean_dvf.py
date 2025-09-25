from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, models

from dvf_app.models import CleanDVFRecord


class Command(BaseCommand):
    help = "Import rows from clean_dfv.csv into the CleanDVFRecord model."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            type=Path,
            help="Path to the cleaned CSV file (with decimal points)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of rows to accumulate before bulk inserting",
        )
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Delete existing records before importing the CSV",
        )

    def handle(self, *args, **options):
        csv_path: Path = options["csv_path"].resolve()
        batch_size: int = options["batch_size"]
        truncate: bool = options["truncate"]

        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        column_map = {
            "Date mutation": "date_mutation",
            "Nature mutation": "nature_mutation",
            "Valeur fonciere": "valeur_fonciere",
            "No voie": "no_voie",
            "B/T/Q": "btq",
            "Type de voie": "type_de_voie",
            "Code voie": "code_voie",
            "Voie": "voie",
            "Code postal": "code_postal",
            "Commune": "commune",
            "Code departement": "code_departement",
            "Code commune": "code_commune",
            "Prefixe de section": "prefixe_de_section",
            "Section": "section",
            "No plan": "no_plan",
            "No Volume": "no_volume",
            "Nombre de lots": "nombre_de_lots",
            "Code type local": "code_type_local",
            "Type local": "type_local",
            "Identifiant local": "identifiant_local",
            "Surface reelle bati": "surface_reelle_bati",
            "Nombre pieces principales": "nombre_pieces_principales",
            "Nature culture": "nature_culture",
            "Nature culture speciale": "nature_culture_speciale",
            "Surface terrain": "surface_terrain",
        }

        field_cache = {
            name: CleanDVFRecord._meta.get_field(name) for name in column_map.values()
        }

        def normalize_value(field_name: str, raw_value: str):
            field = field_cache[field_name]
            raw_value = (raw_value or "").strip()
            if raw_value == "":
                return None if field.null else ""
            if isinstance(field, models.DateField):
                try:
                    return datetime.strptime(raw_value, "%d/%m/%Y").date()
                except ValueError as exc:
                    raise CommandError(f"Invalid date '{raw_value}'") from exc
            if isinstance(field, models.DecimalField):
                try:
                    return Decimal(raw_value)
                except Exception as exc:  
                    raise CommandError(f"Invalid decimal '{raw_value}'") from exc
            if isinstance(field, models.IntegerField):
                try:
                    return int(raw_value)
                except ValueError as exc:
                    raise CommandError(f"Invalid integer '{raw_value}'") from exc
            return raw_value

        created_total = 0
        batch: list[CleanDVFRecord] = []

        with csv_path.open("r", encoding="utf-8", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            missing = [col for col in column_map if col not in reader.fieldnames]
            if missing:
                raise CommandError(
                    "CSV file is missing expected columns: " + ", ".join(missing)
                )

            if truncate:
                self.stdout.write("Truncating existing data...")
                CleanDVFRecord.objects.all().delete()

            with transaction.atomic():
                for row in reader:
                    record_kwargs = {}
                    for csv_col, model_field in column_map.items():
                        record_kwargs[model_field] = normalize_value(
                            model_field, row.get(csv_col, "")
                        )
                    batch.append(CleanDVFRecord(**record_kwargs))
                    if len(batch) >= batch_size:
                        CleanDVFRecord.objects.bulk_create(batch, batch_size=batch_size)
                        created_total += len(batch)
                        batch.clear()
                        self.stdout.write(f"Imported {created_total} rows...")

                if batch:
                    CleanDVFRecord.objects.bulk_create(batch, batch_size=batch_size)
                    created_total += len(batch)

        self.stdout.write(self.style.SUCCESS(f"Import complete. {created_total} rows created."))
