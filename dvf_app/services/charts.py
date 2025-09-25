from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce, TruncMonth

from ..models import CleanDVFRecord, Commune, Department
from ..utils import normalize_commune_code, split_commune_code

MAX_TOP_COMMUNES = 20
DEFAULT_TOP_COMMUNES = 10
MAX_TYPE_CATEGORIES = 5

DECIMAL_ZERO = Value(0, output_field=DecimalField(max_digits=20, decimal_places=2))

def _to_float(value: Optional[Decimal]) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def _clean_type_label(value: Optional[str]) -> str:
    label = (value or '').strip()
    if not label:
        return 'Autre'
    return label.title()

def _percentile(sorted_values: Sequence[float], ratio: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    clamped = min(max(ratio, 0.0), 1.0)
    position = (len(sorted_values) - 1) * clamped
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    if lower_index == upper_index:
        return float(lower)
    weight = position - lower_index
    return float(lower + (upper - lower) * weight)

def _compute_box_stats(values: List[float]) -> Optional[Dict[str, float]]:
    if not values:
        return None
    ordered = sorted(values)
    q1 = _percentile(ordered, 0.25)
    median = _percentile(ordered, 0.5)
    q3 = _percentile(ordered, 0.75)
    iqr = max(q3 - q1, 0.0)
    lower_candidate = q1 - 1.5 * iqr if iqr else ordered[0]
    upper_candidate = q3 + 1.5 * iqr if iqr else ordered[-1]
    display_min = float(max(ordered[0], lower_candidate))
    display_max = float(min(ordered[-1], upper_candidate))
    if display_min > q1:
        display_min = float(ordered[0])
    if display_max < q3:
        display_max = float(ordered[-1])
    outliers = [float(value) for value in ordered if value < display_min or value > display_max]
    return {
        'min': display_min,
        'q1': q1,
        'median': median,
        'q3': q3,
        'max': display_max,
        'whiskerLow': display_min,
        'whiskerHigh': display_max,
        'outliers': outliers,
        'rawMin': float(ordered[0]),
        'rawMax': float(ordered[-1]),
        'count': len(ordered),
    }

def _build_type_filter(type_keys: Sequence[str]) -> Optional[Q]:
    if not type_keys:
        return None
    non_empty = [key for key in type_keys if key]
    clauses: List[Q] = []
    if non_empty:
        clauses.append(Q(type_local__in=non_empty))
    if '' in type_keys:
        clauses.append(Q(type_local__isnull=True) | Q(type_local__exact=''))
    if not clauses:
        return None
    query = clauses[0]
    for condition in clauses[1:]:
        query |= condition
    return query

def _resolve_selection(department_code: str, commune_code: str):
    department_code = (department_code or '').strip().upper()
    commune_code = (commune_code or '').strip().upper()

    records = CleanDVFRecord.objects.all()
    level = 'national'
    department: Optional[Department] = None
    commune: Optional[Commune] = None
    top_scope_department_code: Optional[str] = None

    if commune_code:
        commune = (
            Commune.objects.select_related('department')
            .filter(code_commune=commune_code)
            .first()
        )
        dept_part, commune_part = split_commune_code(commune_code)
        if dept_part:
            top_scope_department_code = dept_part
            records = records.filter(code_departement=dept_part)
        if commune_part is not None:
            records = records.filter(code_commune=commune_part)
        else:
            records = records.none()
        if commune and commune.department:
            department = commune.department
        elif dept_part:
            department = Department.objects.filter(code=dept_part).first()
        level = 'commune'
        department_code = department.code if department else (dept_part or department_code)
    elif department_code:
        records = records.filter(code_departement=department_code)
        department = Department.objects.filter(code=department_code).first()
        top_scope_department_code = department_code
        level = 'department'

    return {
        'level': level,
        'department': department,
        'department_code': department_code,
        'commune': commune,
        'records': records,
        'top_scope_department_code': top_scope_department_code,
        'selected_commune_code': commune.code_commune if commune else commune_code,
    }

def _build_top_communes(department_code: Optional[str], selected_commune_code: Optional[str], limit: int) -> Dict[str, object]:
    limit = max(3, min(limit, MAX_TOP_COMMUNES))
    qs = CleanDVFRecord.objects.exclude(code_commune__isnull=True).exclude(code_commune='')
    scope_label = 'France entiere'
    if department_code:
        qs = qs.filter(code_departement=department_code)
        scope = Department.objects.filter(code=department_code).first()
        if scope:
            scope_label = scope.name or f'Departement {scope.code}'
        else:
            scope_label = f'Departement {department_code}'
    aggregates = list(
        qs.values('code_departement', 'code_commune')
        .annotate(
            sales_count=Count('id'),
            total_value=Coalesce(Sum('valeur_fonciere'), DECIMAL_ZERO),
        )
    )
    items = []
    commune_codes: List[str] = []
    for row in aggregates:
        code = normalize_commune_code(row.get('code_departement'), row.get('code_commune'))
        if not code:
            continue
        commune_codes.append(code)
        items.append(
            {
                'code': code,
                'sales_count': int(row['sales_count'] or 0),
                'total_value': _to_float(row['total_value']),
            }
        )
    commune_lookup = {
        commune.code_commune: commune
        for commune in Commune.objects.filter(code_commune__in=commune_codes).select_related('department')
    }
    selected_code = (selected_commune_code or '').strip().upper()
    for item in items:
        commune = commune_lookup.get(item['code'])
        if commune:
            item['label'] = commune.name
            item['department_code'] = commune.department.code if commune.department else None
        else:
            item['label'] = item['code']
            item['department_code'] = None
        item['is_selected'] = item['code'] == selected_code
    items.sort(key=lambda entry: entry['sales_count'], reverse=True)
    top_items = items[:limit]
    selected_entry = next((entry for entry in items if entry['is_selected']), None)
    if selected_entry and selected_entry not in top_items:
        top_items.append(selected_entry)
        top_items.sort(key=lambda entry: entry['sales_count'], reverse=True)
    for index, entry in enumerate(top_items, start=1):
        entry['rank'] = index
    return {
        'scope_label': scope_label,
        'items': top_items,
        'limit': limit,
    }

def _build_time_series(records) -> Dict[str, List[Dict[str, object]]]:
    points = []
    qs = (
        records.exclude(date_mutation__isnull=True)
        .annotate(month=TruncMonth('date_mutation'))
        .values('month')
        .annotate(
            sales_count=Count('id'),
            total_value=Coalesce(Sum('valeur_fonciere'), DECIMAL_ZERO),
        )
        .order_by('month')
    )
    for row in qs:
        month = row['month']
        if month is None:
            continue
        iso_month = month.date().isoformat() if hasattr(month, 'date') else month.isoformat()
        points.append(
            {
                'month': iso_month,
                'sales_count': int(row['sales_count'] or 0),
                'total_value': _to_float(row['total_value']),
            }
        )
    return {'points': points}

def _build_type_metrics(records) -> Tuple[List[str], Dict[str, int]]:
    type_totals: Dict[str, int] = {}
    qs = (
        records.values('type_local')
        .annotate(sales_count=Count('id'))
        .order_by('-sales_count')
    )
    for row in qs:
        key = row['type_local'] or ''
        type_totals[key] = type_totals.get(key, 0) + int(row['sales_count'] or 0)
    ordered = sorted(type_totals.items(), key=lambda entry: entry[1], reverse=True)
    top_keys = [key for key, _ in ordered[:MAX_TYPE_CATEGORIES]]
    return top_keys, type_totals

def _build_price_boxplot(records, top_type_keys: Sequence[str]) -> Dict[str, object]:
    type_filter = _build_type_filter(top_type_keys)
    if type_filter is None:
        return {'items': [], 'unit': 'EUR/m2'}
    price_expr = Case(
        When(
            surface_reelle_bati__gt=0,
            then=ExpressionWrapper(
                F('valeur_fonciere') / F('surface_reelle_bati'),
                output_field=DecimalField(max_digits=20, decimal_places=2),
            ),
        ),
        When(
            surface_terrain__gt=0,
            then=ExpressionWrapper(
                F('valeur_fonciere') / F('surface_terrain'),
                output_field=DecimalField(max_digits=20, decimal_places=2),
            ),
        ),
        default=None,
        output_field=DecimalField(max_digits=20, decimal_places=2),
    )
    price_values: Dict[str, List[float]] = defaultdict(list)
    qs = (
        records.filter(type_filter)
        .exclude(valeur_fonciere__isnull=True)
        .exclude(valeur_fonciere=0)
        .annotate(price_per_sqm=price_expr)
        .exclude(price_per_sqm__isnull=True)
        .values_list('type_local', 'price_per_sqm')
    )
    top_set = set(top_type_keys)
    for type_value, price in qs.iterator():
        key = type_value or ''
        if key not in top_set:
            continue
        price_values[key].append(float(price))
    items = []
    for key in top_type_keys:
        stats = _compute_box_stats(price_values.get(key, []))
        if not stats:
            continue
        items.append(
            {
                'label': _clean_type_label(key),
                'stats': stats,
            }
        )
    return {'items': items, 'unit': 'EUR/m2'}

def _build_mutation_stack(records, top_type_keys: Sequence[str]) -> Dict[str, object]:
    type_filter = _build_type_filter(top_type_keys)
    if type_filter is None:
        return {'labels': [], 'series': []}
    type_list = list(top_type_keys)
    labels = [_clean_type_label(key) for key in type_list]
    mutation_data: Dict[str, List[int]] = {}
    totals: Dict[str, int] = defaultdict(int)
    qs = (
        records.filter(type_filter)
        .values('type_local', 'nature_mutation')
        .annotate(sales_count=Count('id'))
    )
    index_by_type = {key: idx for idx, key in enumerate(type_list)}
    for row in qs:
        key = row['type_local'] or ''
        if key not in index_by_type:
            continue
        nature = (row['nature_mutation'] or 'Autre').strip() or 'Autre'
        if nature not in mutation_data:
            mutation_data[nature] = [0] * len(type_list)
        idx = index_by_type[key]
        count = int(row['sales_count'] or 0)
        mutation_data[nature][idx] += count
        totals[nature] += count
    ordered_series = sorted(
        mutation_data.items(),
        key=lambda entry: totals.get(entry[0], 0),
        reverse=True,
    )
    series = [
        {
            'label': nature,
            'data': values,
            'total': totals.get(nature, 0),
        }
        for nature, values in ordered_series
    ]
    return {'labels': labels, 'series': series}

def build_chart_payload(department_code: str, commune_code: str, top_limit: int = DEFAULT_TOP_COMMUNES) -> Dict[str, object]:
    selection = _resolve_selection(department_code, commune_code)
    records = selection['records']
    top_type_keys, type_totals = _build_type_metrics(records)
    payload = {
        'selection': {
            'level': selection['level'],
            'department': None,
            'commune': None,
        }
    }
    department = selection['department']
    if department:
        payload['selection']['department'] = {
            'code': department.code,
            'name': department.name or f'Departement {department.code}',
        }
    elif selection['department_code']:
        code_value = selection['department_code']
        payload['selection']['department'] = {
            'code': code_value,
            'name': f'Departement {code_value}',
        }
    commune = selection['commune']
    if commune:
        payload['selection']['commune'] = {
            'code': commune.code_commune,
            'name': commune.name,
        }
    payload['top_communes'] = _build_top_communes(
        selection['top_scope_department_code'],
        selection['selected_commune_code'],
        top_limit,
    )
    payload['time_series'] = _build_time_series(records)
    payload['price_boxplot'] = _build_price_boxplot(records, top_type_keys)
    payload['mutation_stack'] = _build_mutation_stack(records, top_type_keys)
    payload['type_totals'] = {
        _clean_type_label(key): count
        for key, count in type_totals.items()
        if key in top_type_keys
    }
    return payload
