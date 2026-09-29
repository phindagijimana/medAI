"""
mri_extra.py — Extra MRI-module fields (lesion localization, field strength).

Fields populated
----------------
- ``mri.lesion_lobe``          (Evidence[LobarLocalization])
- ``mri.lesion_laterality``    (Evidence[Laterality])
- ``mri.field_strength_tesla`` (Evidence[float])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/InvestigationsMRI.jape``        — MRI finding + localization
- ``jape/LocationAndFinding.jape``       — Lobe + Laterality composition
- ``jape/Lateralisation.jape``           — left/right tokens
- ``Groovy/Investigations.groovy``       — output serializer
- ``services/baseline_rules.py``         — internal reference (lifted logic)

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. Only fires when MRI context is present (MRI keywords appear in the doc).
2. lesion_lobe: nearest lobar word to the first MriFinding entity (or
   fallback: nearest lobar word to an MRI-context sentence).
3. lesion_laterality: same approach for left/right/bilateral.
4. field_strength_tesla: regex over "1.5T", "3T", "3.0T", "7T", "1.5 Tesla".

Cite: Rüber T et al. 2018 (Epilepsy Res 142:167) — 7T MRI in epilepsy;
ACR MRI practice guidelines. Fonferko-Shadrach et al. 2019; 2024.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import (
    Certainty,
    Laterality,
    LobarLocalization,
    TemporalStatus,
)
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


_MRI_CTX_RE = re.compile(
    r"\bMRI\b|\bMR\s+brain\b|neuroimaging|structural\s+imaging|"
    r"\bT1\b|\bT2\b|\bFLAIR\b|\bDWI\b|\bSWI\b|brain\s+scan",
    re.IGNORECASE,
)

_LATERALITY_MAP = {
    "left": Laterality.LEFT,
    "right": Laterality.RIGHT,
    "bilateral": Laterality.BILATERAL,
    "bilaterally": Laterality.BILATERAL,
    "midline": Laterality.MIDLINE,
    "diffuse": Laterality.DIFFUSE,
    "generalized": Laterality.DIFFUSE,
    "generalised": Laterality.DIFFUSE,
}

_LOBE_MAP = {
    "frontal": LobarLocalization.FRONTAL,
    "temporal": LobarLocalization.TEMPORAL,
    "parietal": LobarLocalization.PARIETAL,
    "occipital": LobarLocalization.OCCIPITAL,
    "insular": LobarLocalization.INSULAR,
    "cingulate": LobarLocalization.CINGULATE,
    "multifocal": LobarLocalization.MULTIFOCAL,
    "hippocampal": LobarLocalization.TEMPORAL,
    "mesial temporal": LobarLocalization.TEMPORAL,
}

_FIELD_STRENGTH_RE = re.compile(
    r"\b(1\.5|3|3\.0|7)\s*(?:T\b|Tesla\b|\-?T\s+MRI)",
    re.IGNORECASE,
)


def _mri_sentence(text: str) -> bool:
    return bool(_MRI_CTX_RE.search(text or ""))


def _nearest(text: str, start: int, end: int, word_map: dict,
             window: int = 80):
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    ctx = text[ctx_start:ctx_end].lower()
    hits: list[tuple[int, Any]] = []
    for key, value in word_map.items():
        for m in re.finditer(r"\b" + re.escape(key) + r"\b", ctx):
            hits.append((abs(m.start() - (start - ctx_start)), value))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


def _first_mri_finding_ent(entities: list[LinkedEntity]) -> Optional[LinkedEntity]:
    for e in entities:
        if e.enum_class != "MriFinding":
            continue
        if e.is_negated or e.is_family:
            continue
        return e
    return None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class MriLesionLobeRule(BaseFieldRule):
    """Populate ``mri.lesion_lobe``."""

    field_name = "mri.lesion_lobe"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not _mri_sentence(text):
            return None
        anchor = _first_mri_finding_ent(entities)
        if anchor is not None:
            lobe = _nearest(text, anchor.char_start, anchor.char_end, _LOBE_MAP,
                            window=100)
            if lobe is not None:
                return Evidence[LobarLocalization](
                    value=lobe,
                    certainty=Certainty.PROBABLE,
                    temporal_status=TemporalStatus.CURRENT,
                    evidence_text=anchor.text,
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=anchor.char_start,
                    char_end=anchor.char_end,
                )
        # Fallback: first lobar word after "MRI" keyword.
        m = _MRI_CTX_RE.search(text)
        if m:
            for lm in re.finditer(
                r"\b(frontal|temporal|parietal|occipital|insular|"
                r"cingulate|hippocampal|mesial\s+temporal)\b", text[m.end():],
                re.IGNORECASE,
            ):
                lobe = _LOBE_MAP.get(lm.group(1).lower())
                if lobe is None:
                    lobe = _LOBE_MAP.get(lm.group(1).lower().replace("-", " "))
                if lobe is not None:
                    cs = m.end() + lm.start()
                    ce = m.end() + lm.end()
                    return Evidence[LobarLocalization](
                        value=lobe,
                        certainty=Certainty.POSSIBLE,
                        temporal_status=TemporalStatus.CURRENT,
                        evidence_text=lm.group(0),
                        source_doc_id=meta["doc_id"],
                        source_doc_type=meta["doc_type"],
                        source_date=meta["doc_date"],
                        char_start=cs,
                        char_end=ce,
                    )
        return None


class MriLesionLateralityRule(BaseFieldRule):
    """Populate ``mri.lesion_laterality``."""

    field_name = "mri.lesion_laterality"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not _mri_sentence(text):
            return None
        anchor = _first_mri_finding_ent(entities)
        if anchor is not None:
            lat = _nearest(text, anchor.char_start, anchor.char_end,
                           _LATERALITY_MAP, window=100)
            if lat is not None:
                return Evidence[Laterality](
                    value=lat,
                    certainty=Certainty.PROBABLE,
                    temporal_status=TemporalStatus.CURRENT,
                    evidence_text=anchor.text,
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=anchor.char_start,
                    char_end=anchor.char_end,
                )
        # Fallback: locate a lobar-word anchor in an MRI-context window and
        # find the nearest laterality token. Handles cases where MedCAT does
        # not tag the lesion phrase (e.g. "hippocampal sclerosis") as a
        # MriFinding entity but a lobar word is present in the same clause.
        m = _MRI_CTX_RE.search(text)
        if m:
            for lm in re.finditer(
                r"\b(frontal|temporal|parietal|occipital|insular|"
                r"cingulate|hippocampal|mesial\s+temporal)\b",
                text[m.end():],
                re.IGNORECASE,
            ):
                cs = m.end() + lm.start()
                ce = m.end() + lm.end()
                lat = _nearest(text, cs, ce, _LATERALITY_MAP, window=80)
                if lat is not None:
                    return Evidence[Laterality](
                        value=lat,
                        certainty=Certainty.POSSIBLE,
                        temporal_status=TemporalStatus.CURRENT,
                        evidence_text=lm.group(0),
                        source_doc_id=meta["doc_id"],
                        source_doc_type=meta["doc_type"],
                        source_date=meta["doc_date"],
                        char_start=cs,
                        char_end=ce,
                    )
        return None


class MriFieldStrengthRule(BaseFieldRule):
    """Populate ``mri.field_strength_tesla``."""

    field_name = "mri.field_strength_tesla"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        m = _FIELD_STRENGTH_RE.search(text)
        if m:
            try:
                tesla = float(m.group(1))
            except ValueError:
                return None
            return Evidence[float](
                value=tesla,
                certainty=Certainty.DEFINITE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )
        return None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(MriLesionLobeRule())
register_rule(MriLesionLateralityRule())
register_rule(MriFieldStrengthRule())

__all__ = [
    "MriLesionLobeRule",
    "MriLesionLateralityRule",
    "MriFieldStrengthRule",
]
