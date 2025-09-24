from __future__ import annotations

import csv
import gzip
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Set

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dvf_app.models import Commune, Department

BASE_URL = "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv"
DEPARTMENT_META_URL = "https://geo.api.gouv.fr/departements"


def _extract_department_code(code_insee: str) -> Optional[str]:
    code_insee = (code_insee or "").strip()
    if not code_insee:
        return None
    if code_insee.startswith(("97", "98")):
        return code_insee[:3]
    return code_insee[:2]


@dataclass
class AreaAccumulator:
    name: str = ""
    department_code: Optional[str] = None
    lon_sum: float = 0.0
    lat_sum: float = 0.0
    count: int = 0
    min_lon: Optional[float] = None
    min_lat: Optional[float] = None
    max_lon: Optional[float] = None
    max_lat: Optional[float] = None
    postal_codes: Set[str] = field(default_factory=set)

    def add(self, *, lon: float, lat: float, postal_code: Optional[str] = None, name: Optional[str] = None) -> None:
        self.lon_sum += lon
        self.lat_sum += lat
        self.count += 1

        if self.min_lon is None or lon < self.min_lon:
            self.min_lon = lon
        if self.max_lon is None or lon > self.max_lon:
            self.max_lon = lon
        if self.min_lat is None or lat < self.min_lat:
            self.min_lat = lat
        if self.max_lat is None or lat > self.max_lat:
            self.max_lat = lat

        if postal_code:
            self.postal_codes.add(postal_code)
        if name and not self.name:
            self.name = name

    def centroid(self) -> tuple[Optional[float], Optional[float]]:
        if not self.count:
            return None, None
        return self.lon_sum / self.count, self.lat_sum / self.count

    def bounding_box(self) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        return self.min_lon, self.min_lat, self.max_lon, self.max_lat


class Command(BaseCommand):
    help = "Import commune and department centroids from the BAN address dataset."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--department",
            "-d",
            action="append",
            dest="departments",
            help="Restrict processing to specific department codes (repeatable).",
        )
        parser.add_argument(
            "--base-url",
            dest="base_url",
            default=BASE_URL,
            help="Override the BAN CSV base URL (defaults to the latest official release).",
        )

    def handle(self, *args, **options):
        departments: Optional[Iterable[str]] = options.get("departments")
        base_url: str = options["base_url"].rstrip("/")

        if departments:
            codes = {code.strip() for code in departments if code.strip()}
        else:
            codes = self._discover_department_codes(base_url)
            if not codes:
                raise CommandError("Unable to discover department files at the BAN base URL.")

        department_names = self._fetch_department_names()


        commune_stats: Dict[str, AreaAccumulator] = {}
        department_stats: Dict[str, AreaAccumulator] = defaultdict(AreaAccumulator)
        department_communes: Dict[str, Set[str]] = defaultdict(set)

        for code in sorted(codes):
            url = f"{base_url}/adresses-{code}.csv.gz"
            self.stdout.write(f"Downloading {url}...")
            try:
                resp = requests.get(url, stream=True, timeout=120)
                resp.raise_for_status()
            except requests.RequestException as exc:
                raise CommandError(f"Failed to download {url}: {exc}") from exc

            resp.raw.decode_content = True
            processed = 0
            skipped = 0

            with gzip.GzipFile(fileobj=resp.raw) as gz:
                reader = csv.DictReader(
                    io.TextIOWrapper(gz, encoding="utf-8", newline=""),
                    delimiter=";",
                )
                for row in reader:
                    code_insee = (row.get("code_insee") or "").strip()
                    lon_raw = row.get("lon")
                    lat_raw = row.get("lat")
                    if not code_insee or not lon_raw or not lat_raw:
                        skipped += 1
                        continue

                    dept_code = _extract_department_code(code_insee)
                    if not dept_code:
                        skipped += 1
                        continue

                    try:
                        lon = float(lon_raw)
                        lat = float(lat_raw)
                    except ValueError:
                        skipped += 1
                        continue

                    commune_name = (row.get("nom_commune") or "").strip()
                    postal_code = (row.get("code_postal") or "").strip()

                    commune_entry = commune_stats.setdefault(
                        code_insee,
                        AreaAccumulator(name=commune_name, department_code=dept_code),
                    )
                    if commune_name and not commune_entry.name:
                        commune_entry.name = commune_name
                    commune_entry.department_code = dept_code
                    commune_entry.add(lon=lon, lat=lat, postal_code=postal_code, name=commune_name)

                    dept_entry = department_stats[dept_code]
                    dept_entry.department_code = dept_code
                    dept_entry.add(lon=lon, lat=lat)
                    department_communes[dept_code].add(code_insee)

                    processed += 1
                    if processed and processed % 500000 == 0:
                        self.stdout.write(f"  {code}: processed {processed:,} addresses", ending="\r")

            self.stdout.write(
                f"  {code}: processed {processed:,} addresses, skipped {skipped:,} rows."
            )

        self.stdout.write(
            f"Aggregated {len(commune_stats):,} communes across {len(department_stats):,} departments."
        )

        communes_payload = {}
        for code_commune, acc in commune_stats.items():
            lon, lat = acc.centroid()
            min_lon, min_lat, max_lon, max_lat = acc.bounding_box()
            communes_payload[code_commune] = {
                "department_code": acc.department_code,
                "name": acc.name or code_commune,
                "centroid_lon": lon,
                "centroid_lat": lat,
                "address_count": acc.count,
                "postal_codes": ",".join(sorted(acc.postal_codes)),
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            }

        departments_payload = {}
        for dept_code, acc in department_stats.items():
            lon, lat = acc.centroid()
            min_lon, min_lat, max_lon, max_lat = acc.bounding_box()
            departments_payload[dept_code] = {
                "name": department_names.get(dept_code, acc.name or f"Departement {dept_code}"),
                "centroid_lon": lon,
                "centroid_lat": lat,
                "address_count": acc.count,
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
                "commune_count": len(department_communes.get(dept_code, set())),
            }

        self._persist(communes_payload, departments_payload)
        self.stdout.write(self.style.SUCCESS("BAN centroid import completed."))

    def _fetch_department_names(self) -> Dict[str, str]:
        try:
            resp = requests.get(DEPARTMENT_META_URL, timeout=60)
            resp.raise_for_status()
        except requests.RequestException:
            return {}
        try:
            data = resp.json()
        except ValueError:
            return {}
        mapping = {}
        for item in data:
            code = str(item.get('code') or '').strip()
            name = (item.get('nom') or '').strip()
            if not code:
                continue
            mapping[code] = name
        return mapping

    def _discover_department_codes(self, base_url: str) -> Set[str]:
        try:
            resp = requests.get(base_url + "/", timeout=60)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"Failed to list BAN directory {base_url}/: {exc}") from exc

        pattern = re.compile(r"adresses-([0-9A-Z]{2,3})\.csv\.gz")
        codes = set(pattern.findall(resp.text))
        return codes

    @staticmethod
    @transaction.atomic
    def _persist(communes: Dict[str, dict], departments: Dict[str, dict]) -> None:
        Commune.objects.all().delete()
        Department.objects.all().delete()

        department_models = [
            Department(
                code=code,
                name=data.get("name") or "",
                centroid_lon=data.get("centroid_lon"),
                centroid_lat=data.get("centroid_lat"),
                address_count=data.get("address_count", 0),
                commune_count=data.get("commune_count", 0),
                min_lon=data.get("min_lon"),
                min_lat=data.get("min_lat"),
                max_lon=data.get("max_lon"),
                max_lat=data.get("max_lat"),
            )
            for code, data in departments.items()
        ]

        Department.objects.bulk_create(department_models, batch_size=500)
        department_map = {dept.code: dept for dept in Department.objects.all()}

        commune_models = []
        for code, data in communes.items():
            department_code = data.get("department_code")
            department = department_map.get(department_code)
            if department is None:
                continue
            commune_models.append(
                Commune(
                    code_commune=code,
                    department=department,
                    name=data.get("name", code),
                    centroid_lon=data.get("centroid_lon"),
                    centroid_lat=data.get("centroid_lat"),
                    address_count=data.get("address_count", 0),
                    postal_codes=data.get("postal_codes", ""),
                    min_lon=data.get("min_lon"),
                    min_lat=data.get("min_lat"),
                    max_lon=data.get("max_lon"),
                    max_lat=data.get("max_lat"),
                )
            )

        Commune.objects.bulk_create(commune_models, batch_size=1000)





