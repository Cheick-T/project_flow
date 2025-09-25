from __future__ import annotations

from typing import Optional, Tuple

def split_commune_code(commune_code: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    code = (commune_code or '').strip().upper()
    if not code:
        return None, None
    if code.startswith(('2A', '2B')):
        dept = code[:2]
        rest = code[2:]
    elif code.startswith(('97', '98')) and len(code) >= 4:
        dept = code[:3]
        rest = code[3:]
    else:
        dept = code[:2]
        rest = code[2:]
    rest = rest.lstrip('0') or '0'
    return dept, rest

def normalize_commune_code(department_code: Optional[str], commune_code: Optional[str]) -> Optional[str]:
    dept = (department_code or '').strip().upper()
    commune = (commune_code or '').strip()
    if not dept or not commune:
        return None
    if dept in {'2A', '2B'}:
        padded_commune = commune.zfill(3)
    elif dept.startswith('97') or dept.startswith('98'):
        padded_commune = commune.zfill(2)
    else:
        padded_commune = commune.zfill(3)
        dept = dept.zfill(2)
    return f"{dept}{padded_commune}"
