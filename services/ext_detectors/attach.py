"""Attach sidecar FieldItems to existing LEO claims without changing verdicts.

Agree → append the sidecar detector name.
Same drug, different medication role path → ``sidecar_alternative``.
Same scalar path, different value (frequency / type / HS) → ``sidecar_alternative``.
Unpaired sidecar items are returned for the caller to emit as review-only.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from services.chain_llm import display_value, values_agree, FieldItem

MED_PATHS = frozenset({
    "medication.current_asms",
    "medication.prior_asms",
    "medication.failed_asms",
    "medication.rescue_medication",
    "medication.acute_administration",
})

_PATH_LABEL = {
    "medication.current_asms": "current",
    "medication.prior_asms": "prior",
    "medication.failed_asms": "failed",
    "medication.rescue_medication": "rescue",
    "medication.acute_administration": "acute",
}


def _drug_key(value: Any) -> str:
    if isinstance(value, dict):
        name = value.get("generic_name") or ""
    else:
        name = value or ""
    try:
        from rules.fields.medication import canonicalize_drug_name
        return canonicalize_drug_name(str(name))
    except Exception:
        return str(name).strip().lower()


def _detector_name(item: FieldItem) -> str:
    return str((item.ev or {}).get("reader") or "ctakes")


class SidecarIndex:
    def __init__(self, items: Iterable[FieldItem]):
        self._items = list(items or [])
        self._used: set[int] = set()
        self.n_agree = 0
        self.n_mismatch = 0

    def apply(self, claim: Any) -> None:
        """Mutate ``claim.detectors`` / ``sidecar_alternative``. Verdict untouched."""
        path = claim.field_path or ""
        value = claim.value
        hit = self._take_agree(path, value)
        if hit is not None:
            name = _detector_name(hit)
            if name not in (claim.detectors or []):
                claim.detectors = list(claim.detectors or []) + [name]
            self.n_agree += 1
            return
        hit = self._take_mismatch(path, value)
        if hit is not None:
            shown = display_value(hit.ev.get("value"))
            if hit.field_path in MED_PATHS and hit.field_path != path:
                label = _PATH_LABEL.get(hit.field_path, hit.field_path)
                claim.sidecar_alternative = f"{label} {shown}".strip()
            else:
                claim.sidecar_alternative = shown
            self.n_mismatch += 1

    def leftovers(self) -> list[FieldItem]:
        return [it for i, it in enumerate(self._items) if i not in self._used]

    def _take_agree(self, path: str, value: Any) -> Optional[FieldItem]:
        for i, it in enumerate(self._items):
            if i in self._used or it.field_path != path:
                continue
            if values_agree(value, it.ev.get("value")):
                self._used.add(i)
                return it
        return None

    def _take_mismatch(self, path: str, value: Any) -> Optional[FieldItem]:
        if path in MED_PATHS:
            key = _drug_key(value)
            if not key:
                return None
            for i, it in enumerate(self._items):
                if i in self._used or it.field_path not in MED_PATHS:
                    continue
                if it.field_path == path:
                    continue
                if _drug_key(it.ev.get("value")) == key:
                    self._used.add(i)
                    return it
            return None
        for i, it in enumerate(self._items):
            if i in self._used or it.field_path != path:
                continue
            if not values_agree(value, it.ev.get("value")):
                self._used.add(i)
                return it
        return None


__all__ = ["SidecarIndex", "MED_PATHS"]
