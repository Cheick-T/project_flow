from __future__ import annotations

from typing import Optional

from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from .models import CleanDVFRecord, Commune, Department


def normalize_commune_code(department_code: Optional[str], commune_code: Optional[str]) -> Optional[str]:
    dept = (department_code or "").strip().upper()
    commune = (commune_code or "").strip().upper()
    if not dept or not commune:
        return None
    if len(commune) >= 5:
        return commune
    if dept in {"2A", "2B"}:
        return f"{dept}{commune.zfill(3)}"
    if dept.startswith("97") or dept.startswith("98"):
        return f"{dept}{commune.zfill(2)}"
    return f"{dept.zfill(2)}{commune.zfill(3)}"


class LeafletMapView(TemplateView):
    template_name = "dvf_app/map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        departments = Department.objects.order_by("code").values("code", "name")
        context["departments"] = [
            {
                "code": dept["code"],
                "name": dept["name"] or f"Departement {dept['code']}",
            }
            for dept in departments
        ]
        return context


@require_GET
def heatmap_data(request):
    department_param = (request.GET.get("department") or "").strip().upper()
    commune_param = (request.GET.get("commune") or "").strip().upper()

    records = CleanDVFRecord.objects.exclude(code_commune__isnull=True).exclude(
        code_commune=""
    )

    level = "commune"
    points = []

    if commune_param:
        if commune_param.startswith(("2A", "2B")):
            dept_part = commune_param[:2]
            commune_part = commune_param[2:]
        elif commune_param.startswith("97") or commune_param.startswith("98"):
            dept_part = commune_param[:3]
            commune_part = commune_param[3:]
        else:
            dept_part = commune_param[:2]
            commune_part = commune_param[2:]
        records = records.filter(
            code_departement=dept_part,
            code_commune=commune_part.lstrip("0") or "0",
        )
    elif department_param:
        records = records.filter(code_departement=department_param)
    else:
        level = "department"

    if level == "department":
        department_totals = (
            records.values("code_departement").annotate(sales_count=Count("id"))
        )
        for row in department_totals:
            code = (row["code_departement"] or "").upper()
            department = Department.objects.filter(code=code).first()
            if not department:
                continue
            points.append(
                {
                    "code": department.code,
                    "name": department.name or f"Departement {department.code}",
                    "centroid_lat": department.centroid_lat,
                    "centroid_lon": department.centroid_lon,
                    "address_count": department.address_count,
                    "commune_count": department.commune_count,
                    "sales_count": row["sales_count"],
                }
            )
    else:
        aggregates = []
        for row in records.values("code_departement", "code_commune").annotate(
            sales_count=Count("id")
        ):
            normalized = normalize_commune_code(
                row["code_departement"], row["code_commune"]
            )
            if not normalized:
                continue
            aggregates.append(
                {
                    "code_commune": normalized,
                    "sales_count": row["sales_count"],
                }
            )

        commune_codes = [row["code_commune"] for row in aggregates]
        commune_lookup = {
            commune.code_commune: commune
            for commune in Commune.objects.filter(code_commune__in=commune_codes).select_related("department")
        }

        for row in aggregates:
            code = row["code_commune"]
            commune = commune_lookup.get(code)
            if not commune:
                continue
            points.append(
                {
                    "code": code,
                    "name": commune.name,
                    "department_code": commune.department.code,
                    "centroid_lat": commune.centroid_lat,
                    "centroid_lon": commune.centroid_lon,
                    "address_count": commune.address_count,
                    "postal_codes": [pc for pc in commune.postal_codes.split(",") if pc],
                    "sales_count": row["sales_count"],
                }
            )

    points.sort(key=lambda item: item["sales_count"], reverse=True)

    total_sales = sum(point["sales_count"] for point in points)
    max_sales = max((point["sales_count"] for point in points), default=0)

    summary = {
        "total_sales": total_sales,
        "entity_count": len(points),
        "max_sales": max_sales,
        "level": level,
    }

    if department_param:
        department = (
            Department.objects.filter(code=department_param)
            .values("code", "name", "address_count", "commune_count")
            .first()
        )
        if department:
            summary["department"] = {
                "code": department["code"],
                "name": department["name"] or f"Departement {department['code']}",
                "address_count": department["address_count"],
                "commune_count": department["commune_count"],
            }

    if commune_param and level == "commune":
        commune = next((p for p in points if p["code"] == commune_param), None)
        if commune:
            summary["commune"] = {
                "code": commune["code"],
                "name": commune["name"],
                "department_code": commune.get("department_code"),
            }

    return JsonResponse({"summary": summary, "points": points})


@require_GET
def commune_options(request):
    department_code = (request.GET.get("department") or "").strip().upper()
    if not department_code:
        return JsonResponse({"communes": []})

    communes = (
        Commune.objects.filter(department__code=department_code)
        .order_by("name")
        .values("code_commune", "name")
    )
    options = [
        {"code_commune": commune["code_commune"], "name": commune["name"]}
        for commune in communes
    ]
    return JsonResponse({"communes": options})
