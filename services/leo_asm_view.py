"""Display convention for current ASMs. Does not change extract, D17, or ACCEPT/REVIEW.

Two views of the same extracted columns:

* ``maintenance`` (default) — ``current_asms`` as extracted (daily regimen). Rescue stays in
  ``rescue_medication``.
* ``rescue-as-current`` — ExECT / F-S gold convention: show current ∪ rescue as
  ``current_asms_view``. The extracted columns are not overwritten.

A clinician still chooses which view is the study headline. This module only makes both
available. Scoring scripts keep their own ``--rescue-as-current`` flags.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

VIEWS = ("maintenance", "rescue-as-current")
DEFAULT_VIEW = "maintenance"
_ALIASES = {
    "maintenance": "maintenance",
    "maint": "maintenance",
    "daily": "maintenance",
    "rescue-as-current": "rescue-as-current",
    "rescue_as_current": "rescue-as-current",
    "rescue": "rescue-as-current",
    "exec": "rescue-as-current",
    "fs": "rescue-as-current",
}


def parse_asm_view(raw: Any) -> str:
    key = str(raw or DEFAULT_VIEW).strip().lower().replace(" ", "-")
    if key not in _ALIASES:
        raise ValueError(f"asm_view must be {' or '.join(VIEWS)}; got {raw!r}")
    return _ALIASES[key]


def _parts(cell: Any) -> list[str]:
    seen: list[str] = []
    low: set[str] = set()
    for part in str(cell or "").replace("|", ";").split(";"):
        name = part.strip()
        if not name:
            continue
        k = name.lower()
        if k in low:
            continue
        low.add(k)
        seen.append(name)
    return seen


def union_display(current: Any, rescue: Any) -> str:
    return "; ".join(_parts(current) + [n for n in _parts(rescue) if n.lower() not in {x.lower() for x in _parts(current)}])


def apply_asm_view_row(row: dict, view: str = DEFAULT_VIEW) -> dict:
    view = parse_asm_view(view)
    out = dict(row)
    current = out.get("current_asms", "")
    rescue = out.get("rescue_medication", "")
    out["asm_view"] = view
    out["current_asms_view"] = current if view == "maintenance" else union_display(current, rescue)
    return out


def apply_asm_view(table: pd.DataFrame, view: str = DEFAULT_VIEW) -> pd.DataFrame:
    view = parse_asm_view(view)
    t = table.copy()
    t["asm_view"] = view
    if "current_asms" not in t.columns:
        t["current_asms_view"] = ""
        return t
    rescue = t["rescue_medication"] if "rescue_medication" in t.columns else ""
    if view == "maintenance":
        t["current_asms_view"] = t["current_asms"]
    else:
        t["current_asms_view"] = [
            union_display(c, r) for c, r in zip(t["current_asms"], rescue if isinstance(rescue, pd.Series) else [""] * len(t))
        ]
    return t


__all__ = ["VIEWS", "DEFAULT_VIEW", "parse_asm_view", "union_display", "apply_asm_view_row", "apply_asm_view"]
