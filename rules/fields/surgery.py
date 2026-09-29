"""
surgery.py — Surgical / neurostimulation history extraction.

Fields populated
----------------
- ``medication.surgery_history``  (list[Evidence[SurgeryHistoryItem]])

No ExECT source — ExECT-V2 does not have a surgery-history JAPE pipeline.
Hand-authored from:
- Engel J Jr et al. 1993 (Surgical Treatment of the Epilepsies, 2nd ed.,
  Raven Press): post-op outcome classification IA-IVC.
- Wieser H G et al. 2001 (Epilepsia 42:282-6): ILAE outcome classes 1-6.
- ILAE 2019 surgical epilepsy classification (Lüders et al.).
- Fisher R S et al. 2010 (Neurology 75:e21-27): VNS overview.
- Morrell M J 2011 (Neurology 77:1295): RNS trial.
- Fisher R S et al. 2010 (SANTE trial, Epilepsia 51:899): DBS.

Semantics captured
------------------
1. Detect procedures by regex over each SurgeryType enum value:
     - "temporal lobectomy" / "anterior temporal lobectomy" / "ATL" →
       RESECTION (target='temporal lobe')
     - "laser ablation" / "LITT" / "SLAH" → LASER_ABLATION
     - "hemispherectomy" / "hemispherotomy" → HEMISPHERECTOMY
     - "corpus callosotomy" / "callosotomy" → CALLOSOTOMY
     - "VNS" / "vagus nerve stimulator" / "vagal nerve stimulator" →
       NEUROSTIMULATION_VNS
     - "RNS" / "responsive neurostimulation" / "NeuroPace" →
       NEUROSTIMULATION_RNS
     - "DBS" / "deep brain stimulation" → NEUROSTIMULATION_DBS
     - "focal resection" / "lesionectomy" → RESECTION
     - "corticectomy" / "topectomy" → RESECTION
2. Extract year from adjacent 4-digit numbers.
3. Extract laterality (left/right/bilateral) from surrounding text.
4. Outcome extraction — Engel IA/IB/IC/ID/IIA-IIC/IIIA/IIIB/IVA-IVC and
   ILAE class 1-6 mentions near the procedure.
5. Negation-aware: "no history of epilepsy surgery" → skip.

Cite: Engel 1993, Wieser 2001, ILAE 2019, Fisher 2010, Morrell 2011.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import (
    Certainty,
    EngelClass,
    IlaeOutcome,
    Laterality,
    SurgeryType,
    TemporalStatus,
)
from schema.evidence import Evidence
from schema.ontology import SurgeryHistoryItem
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_SURGERY_PATTERNS: list[tuple[re.Pattern[str], SurgeryType, Optional[str]]] = [
    # Neurostimulation — check before generic "resection"
    (re.compile(r"vagus\s+nerve\s+stimulat(?:or|ion)|vagal\s+nerve\s+stimulat|"
                r"\bVNS\b\s*(?:implant|placement|insertion)?",
                re.IGNORECASE), SurgeryType.NEUROSTIMULATION_VNS, "vagus nerve"),
    (re.compile(r"responsive\s+neurostimulat|\bRNS\b\s*(?:system|"
                r"implant|placement)?|NeuroPace",
                re.IGNORECASE), SurgeryType.NEUROSTIMULATION_RNS, None),
    (re.compile(r"deep\s+brain\s+stimulat(?:ion|or)?|\bDBS\b\s*(?:implant|"
                r"placement|electrodes?)?|anterior\s+nucleus\s+thalamic",
                re.IGNORECASE), SurgeryType.NEUROSTIMULATION_DBS, None),
    # Disconnection / hemispherectomy
    (re.compile(r"hemispherectomy|hemispherotomy",
                re.IGNORECASE), SurgeryType.HEMISPHERECTOMY, "hemisphere"),
    (re.compile(r"(?:corpus\s+)?callosotomy",
                re.IGNORECASE), SurgeryType.CALLOSOTOMY, "corpus callosum"),
    (re.compile(r"multiple\s+subpial\s+transection|MST\b",
                re.IGNORECASE), SurgeryType.DISCONNECTION, None),
    # Laser ablation
    (re.compile(r"laser\s+ablation|laser[- ]?induced\s+thermal|"
                r"\bLITT\b|\bSLAH\b|stereotactic\s+laser",
                re.IGNORECASE), SurgeryType.LASER_ABLATION, None),
    # Resection — specific targets first
    (re.compile(r"anterior\s+temporal\s+lobectomy|\bATL\b|"
                r"temporal\s+lobectomy|amygdalohippocampectomy|"
                r"selective\s+amygdalohippocampectomy",
                re.IGNORECASE), SurgeryType.RESECTION, "temporal lobe"),
    (re.compile(r"frontal\s+lobectomy|frontal\s+resection",
                re.IGNORECASE), SurgeryType.RESECTION, "frontal lobe"),
    (re.compile(r"parietal\s+resection|parietal\s+lobectomy",
                re.IGNORECASE), SurgeryType.RESECTION, "parietal lobe"),
    (re.compile(r"occipital\s+resection|occipital\s+lobectomy",
                re.IGNORECASE), SurgeryType.RESECTION, "occipital lobe"),
    (re.compile(r"lesionectomy|focal\s+resection|topectomy|corticectomy",
                re.IGNORECASE), SurgeryType.RESECTION, None),
    # Generic — last resort
    (re.compile(r"epilepsy\s+surgery|prior\s+surgical\s+treatment",
                re.IGNORECASE), SurgeryType.UNKNOWN, None),
]

_ENGEL_RE = re.compile(
    r"Engel\s+(?:class\s+)?(IA|IB|IC|ID|IIA|IIB|IIC|IID|IIIA|IIIB|"
    r"IVA|IVB|IVC)\b",
    re.IGNORECASE,
)

_ILAE_OUTCOME_RE = re.compile(
    r"ILAE\s+(?:class\s+|outcome\s+)?([1-6])\b",
    re.IGNORECASE,
)

_LATERALITY_MAP = {
    "left": Laterality.LEFT,
    "right": Laterality.RIGHT,
    "bilateral": Laterality.BILATERAL,
    "midline": Laterality.MIDLINE,
}

_NO_SURGERY_RE = re.compile(
    r"\bno\s+(?:history\s+of\s+|prior\s+|previous\s+)?"
    r"(?:epilepsy\s+)?surgery\b|"
    r"denies\s+(?:any\s+)?surgical\s+treatment",
    re.IGNORECASE,
)


def _find_year(text: str, start: int, end: int, window: int = 60) -> Optional[int]:
    """Return the first 4-digit year (1970-2099) within ± window chars."""
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    ctx = text[ctx_start:ctx_end]
    for m in re.finditer(r"\b(19[7-9]\d|20\d{2})\b", ctx):
        try:
            return int(m.group(1))
        except ValueError:
            continue
    return None


def _find_laterality(text: str, start: int, end: int,
                     window: int = 60) -> Optional[Laterality]:
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    ctx = text[ctx_start:ctx_end].lower()
    hits = []
    for key, val in _LATERALITY_MAP.items():
        for m in re.finditer(r"\b" + re.escape(key) + r"\b", ctx):
            hits.append((abs(m.start() - (start - ctx_start)), val))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


def _find_engel(text: str, start: int, end: int,
                window: int = 200) -> Optional[EngelClass]:
    ctx = text[max(0, start - window):min(len(text), end + window)]
    m = _ENGEL_RE.search(ctx)
    if not m:
        return None
    try:
        return EngelClass(m.group(1).upper())
    except (ValueError, TypeError):
        return None


def _find_ilae_outcome(text: str, start: int, end: int,
                       window: int = 200) -> Optional[IlaeOutcome]:
    ctx = text[max(0, start - window):min(len(text), end + window)]
    m = _ILAE_OUTCOME_RE.search(ctx)
    if not m:
        return None
    try:
        return IlaeOutcome(m.group(1))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class SurgeryHistoryRule(BaseFieldRule):
    """Populate ``medication.surgery_history`` list."""

    field_name = "medication.surgery_history"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[list[Evidence]]:
        text = getattr(doc, "text", "") or ""
        if not text:
            return None

        out: list[Evidence] = []
        seen: set[tuple[SurgeryType, Optional[str]]] = set()

        # Skip if the doc explicitly says no surgery.
        neg = _NO_SURGERY_RE.search(text)

        for pat, surg_type, default_target in _SURGERY_PATTERNS:
            for m in pat.finditer(text):
                # Skip mentions inside a "no history of surgery" clause.
                if neg and abs(neg.start() - m.start()) < 50:
                    continue
                # Basic negation guard.
                pre = text[max(0, m.start() - 30):m.start()].lower()
                if re.search(r"\b(?:no|without|denies?|never|not)\b\s*$", pre):
                    continue

                key = (surg_type, default_target)
                if key in seen:
                    continue
                seen.add(key)

                year = _find_year(text, m.start(), m.end())
                lat = _find_laterality(text, m.start(), m.end())
                engel = _find_engel(text, m.start(), m.end())
                ilae = _find_ilae_outcome(text, m.start(), m.end())

                item = SurgeryHistoryItem(
                    surgery_type=surg_type,
                    target=default_target,
                    laterality=lat,
                    year=year,
                    outcome_text=None,
                    engel_class=engel,
                    ilae_outcome=ilae,
                )
                quote = text[max(0, m.start() - 10):min(len(text), m.end() + 40)].strip()
                out.append(Evidence[SurgeryHistoryItem](
                    value=item,
                    certainty=Certainty.PROBABLE,
                    temporal_status=TemporalStatus.HISTORICAL,
                    evidence_text=quote,
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=m.start(),
                    char_end=m.end(),
                ))

        return out or None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(SurgeryHistoryRule())

__all__ = ["SurgeryHistoryRule"]
