from __future__ import annotations

from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from .models import CleanDVFRecord, Commune, Department
from .services.charts import (
    DEFAULT_TOP_COMMUNES,
    build_chart_payload,
    compute_selection_metrics,
)
from .utils import normalize_commune_code, split_commune_code

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
        dept_part, commune_part = split_commune_code(commune_param)
        if dept_part and commune_part is not None:
            records = records.filter(
                code_departement=dept_part,
                code_commune=commune_part,
            )
            if not department_param:
                department_param = dept_part
        else:
            records = records.none()
    elif department_param:
        records = records.filter(code_departement=department_param)
    else:
        level = "department"

    metrics = compute_selection_metrics(records)

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
    summary.update(metrics)

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

@require_GET
def charts_data(request):
    department_param = (request.GET.get("department") or "").strip().upper()
    commune_param = (request.GET.get("commune") or "").strip().upper()
    try:
        top_limit = int(request.GET.get("top_limit") or DEFAULT_TOP_COMMUNES)
    except ValueError:
        top_limit = DEFAULT_TOP_COMMUNES
    payload = build_chart_payload(department_param, commune_param, top_limit)
    return JsonResponse(payload)

