"""Leftover US FDA ASM brand strings not already in the generated lexicon.

The generated file ``rules/asm_lexicon.py`` is built from RxNorm
(``rxnorm:2026-09-08``) and already carries Keppra, Vimpat, Xcopri, Valtoco,
Nayzilam, Diastat, Onfi, Lamictal, Depakote, FYCOMPA, and XR stems such as
Oxtellar / Elepsia / Trokendi / Qudexy / Motpoly. Do not edit that file by
hand. This overlay adds brand → generic rows that still appear on FDA labels
and in US notes but are missing from the generated ``brands`` lists.

Cite: NLM RxNorm (pinned ``rxnorm:2026-09-08``); FDA product labels.
Not a new ontology — string aliases only.
"""

from __future__ import annotations

import re

from rules.asm_lexicon import RXNORM_RELEASE

# Surface form (lowercase) → F-S canonical generic used by canonicalize_drug_name.
US_ASM_BRAND_ALIASES: dict[str, str] = {
    "depakene": "sodiumvalproate",
    "stavzor": "sodiumvalproate",
    "equetro": "carbamazepine",
    "tegretol xr": "carbamazepine",
    "tegretolxr": "carbamazepine",
    "carnexiv": "carbamazepine",
    "keppra xr": "levetiracetam",
    "keppraxr": "levetiracetam",
    "lamictal xr": "lamotrigine",
    "lamictalxr": "lamotrigine",
    "lamictal odt": "lamotrigine",
    "lamictalodt": "lamotrigine",
}

_BRAND_FALLBACK_RE = re.compile(
    r"\b(?:" + "|".join(
        re.escape(k).replace(r"\ ", r"[\s\-]+") for k in (
            "depakene", "stavzor", "equetro", "carnexiv",
            "tegretol xr", "keppra xr", "lamictal xr", "lamictal odt",
        )
    ) + r")\b",
    re.IGNORECASE,
)


def leftover_brand_matches(text: str) -> list[tuple[re.Match[str], str]]:
    """Return (match, F-S canonical generic) for leftover US brand strings."""
    out: list[tuple[re.Match[str], str]] = []
    seen_spans: set[tuple[int, int]] = set()
    for m in _BRAND_FALLBACK_RE.finditer(text or ""):
        span = (m.start(), m.end())
        if span in seen_spans:
            continue
        key = re.sub(r"[\s\-]+", " ", m.group(0).strip().lower())
        solid = re.sub(r"[\s\-]+", "", key)
        canon = US_ASM_BRAND_ALIASES.get(key) or US_ASM_BRAND_ALIASES.get(solid)
        if not canon:
            continue
        seen_spans.add(span)
        out.append((m, canon))
    return out


__all__ = [
    "RXNORM_RELEASE",
    "US_ASM_BRAND_ALIASES",
    "leftover_brand_matches",
]
