"""
eeg_extra.py — Extra EEG-module fields (study type, seizures captured,
ictal onset localization).

Fields populated
----------------
- ``eeg.study_type``                (Evidence[EegStudyType])
- ``eeg.seizures_captured``         (Evidence[bool])
- ``eeg.seizures_captured_count``   (Evidence[int])
- ``eeg.ictal_onset_lobe``          (Evidence[LobarLocalization])
- ``eeg.ictal_onset_laterality``    (Evidence[Laterality])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/InvestigationsEEG.jape``       — EEG-specific patterns
- ``jape/LocationAndFinding.jape``      — lobe + laterality composition
- ``jape/Lateralisation.jape``          — laterality tokens
- ``Groovy/Investigations.groovy``      — output serializer
- ``services/baseline_rules_eeg.py``    — internal reference (lifted logic)

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. **study_type** — regex bank (specificity descending): sEEG → video-EEG →
   EMU → ambulatory → prolonged → routine → intraoperative → ECoG.
2. **seizures_captured** — True on "N seizures were captured/recorded" (or
   variants); False on "no seizures captured". Extract N as
   seizures_captured_count.
3. **ictal_onset_lobe** / **_laterality** — nearest lobar / laterality
   word to an "ictal onset" / "seizure onset from" phrase.
4. Negation-aware throughout.

Cite: ACNS Standardized EEG Terminology (Hirsch et al. 2013);
Fonferko-Shadrach et al. 2019; 2024.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import (
    Certainty,
    EegStudyType,
    Laterality,
    LobarLocalization,
    TemporalStatus,
)
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_STUDY_TYPE_PATTERNS: list[tuple[re.Pattern[str], EegStudyType]] = [
    (re.compile(r"stereo[- ]?EEG|\bsEEG\b|\bSEEG\b"),
     EegStudyType.SEEG),
    (re.compile(r"\bECoG\b|electrocorticograph|intra[- ]?operative\s+EEG",
                re.IGNORECASE), EegStudyType.ECOG),
    (re.compile(r"video[- ]?EEG|vEEG", re.IGNORECASE),
     EegStudyType.VIDEO_EEG),
    (re.compile(
        r"epilepsy\s+monitoring\s+unit|\bEMU\b\s*(?:study|admission|"
        r"monitoring|admission)?",
        re.IGNORECASE), EegStudyType.EMU),
    (re.compile(r"ambulatory\s+EEG|\d+[- ]?hour\s+ambulatory",
                re.IGNORECASE), EegStudyType.AMBULATORY),
    (re.compile(r"prolonged\s+EEG|long[- ]?term\s+(?:EEG\s+)?monitoring",
                re.IGNORECASE), EegStudyType.PROLONGED),
    (re.compile(r"routine\s+EEG|standard\s+EEG|30[- ]?minute\s+EEG",
                re.IGNORECASE), EegStudyType.ROUTINE),
    (re.compile(r"intra[- ]?operative", re.IGNORECASE),
     EegStudyType.INTRAOPERATIVE),
]

_SEIZURES_CAPTURED_RE = re.compile(
    r"(\d+)\s+(?:electrographic\s+|clinical\s+|typical\s+)?seizures?\s+"
    r"(?:were\s+|was\s+)?(?:captured|recorded|observed|noted)|"
    r"captured\s+(\d+)\s+seizures?",
    re.IGNORECASE,
)

_SEIZURES_FREE_RE = re.compile(
    r"no\s+(?:electrographic\s+)?seizures?\s+(?:were\s+|was\s+)?"
    r"(?:captured|recorded|observed|noted)",
    re.IGNORECASE,
)

_ICTAL_ONSET_RE = re.compile(
    r"ictal\s+onset|seizure\s+onset\s+(?:in|at|localized\s+to|from)|"
    r"onset\s+(?:localized\s+)?(?:in|to|at|from)\s+the",
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

_EEG_CTX_RE = re.compile(
    r"\bEEG\b|electroencephalogr|video[- ]?EEG|ambulatory\s+EEG",
    re.IGNORECASE,
)


def _nearest(text: str, start: int, end: int, word_map: dict,
             window: int = 120):
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


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class EegStudyTypeRule(BaseFieldRule):
    """Populate ``eeg.study_type``. Highest-specificity pattern wins."""

    field_name = "eeg.study_type"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        for pat, val in _STUDY_TYPE_PATTERNS:
            m = pat.search(text)
            if m:
                quote = text[max(0, m.start() - 5):min(len(text), m.end() + 5)].strip()
                return Evidence[EegStudyType](
                    value=val,
                    certainty=Certainty.DEFINITE,
                    temporal_status=TemporalStatus.CURRENT,
                    evidence_text=quote,
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=m.start(),
                    char_end=m.end(),
                )
        return None


class EegSeizuresCapturedRule(BaseFieldRule):
    """Populate ``eeg.seizures_captured`` (bool)."""

    field_name = "eeg.seizures_captured"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        m = _SEIZURES_CAPTURED_RE.search(text)
        if m:
            return Evidence[bool](
                value=True,
                certainty=Certainty.DEFINITE,
                temporal_status=TemporalStatus.HISTORICAL,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )
        m = _SEIZURES_FREE_RE.search(text)
        if m:
            return Evidence[bool](
                value=False,
                certainty=Certainty.DEFINITE,
                temporal_status=TemporalStatus.HISTORICAL,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )
        return None


class EegSeizuresCapturedCountRule(BaseFieldRule):
    """Populate ``eeg.seizures_captured_count`` (int)."""

    field_name = "eeg.seizures_captured_count"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        m = _SEIZURES_CAPTURED_RE.search(text)
        if not m:
            return None
        num = m.group(1) or m.group(2)
        try:
            n = int(num)
        except (TypeError, ValueError):
            return None
        if n < 0 or n > 1000:
            return None
        return Evidence[int](
            value=n,
            certainty=Certainty.DEFINITE,
            temporal_status=TemporalStatus.HISTORICAL,
            evidence_text=m.group(0),
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=m.start(),
            char_end=m.end(),
        )


class EegIctalOnsetLobeRule(BaseFieldRule):
    """Populate ``eeg.ictal_onset_lobe``."""

    field_name = "eeg.ictal_onset_lobe"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not _EEG_CTX_RE.search(text):
            return None
        m = _ICTAL_ONSET_RE.search(text)
        if not m:
            return None
        lobe = _nearest(text, m.start(), m.end(), _LOBE_MAP, window=150)
        if lobe is None:
            return None
        quote = text[max(0, m.start() - 10):min(len(text), m.end() + 80)].strip()
        return Evidence[LobarLocalization](
            value=lobe,
            certainty=Certainty.PROBABLE,
            temporal_status=TemporalStatus.CURRENT,
            evidence_text=quote,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=m.start(),
            char_end=m.end(),
        )


class EegIctalOnsetLateralityRule(BaseFieldRule):
    """Populate ``eeg.ictal_onset_laterality``."""

    field_name = "eeg.ictal_onset_laterality"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not _EEG_CTX_RE.search(text):
            return None
        m = _ICTAL_ONSET_RE.search(text)
        if not m:
            return None
        lat = _nearest(text, m.start(), m.end(), _LATERALITY_MAP, window=150)
        if lat is None:
            return None
        quote = text[max(0, m.start() - 10):min(len(text), m.end() + 80)].strip()
        return Evidence[Laterality](
            value=lat,
            certainty=Certainty.PROBABLE,
            temporal_status=TemporalStatus.CURRENT,
            evidence_text=quote,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=m.start(),
            char_end=m.end(),
        )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(EegStudyTypeRule())
register_rule(EegSeizuresCapturedRule())
register_rule(EegSeizuresCapturedCountRule())
register_rule(EegIctalOnsetLobeRule())
register_rule(EegIctalOnsetLateralityRule())

__all__ = [
    "EegStudyTypeRule",
    "EegSeizuresCapturedRule",
    "EegSeizuresCapturedCountRule",
    "EegIctalOnsetLobeRule",
    "EegIctalOnsetLateralityRule",
]
