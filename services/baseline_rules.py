"""B0 rules baseline — MRI (paper Table 6).

A transparent regex/keyword extractor that produces a valid `MriModule`.
This is the conventional-NLP control the paper explicitly asks for. It runs
without an LLM at all.

Design:
- Wraps as a `ModelBackend` so it plugs into the existing extraction
  pipeline (writes manifests, records raw/final validity, etc.).
- The "raw response" is the JSON the rules produced. Raw parse should
  always succeed by construction, so `raw_valid=True` is the norm — the
  interesting metric here is per-field accuracy vs. gold.
- Only MRI is implemented in this first pass. EEG, medication, and
  clinical-seizure baselines are candidate v2 additions. B0 for those
  modules is genuinely harder because the language is less templated.

Detection strategy per field:
- overall_normal: True iff "normal" appears with no epilepsy-relevant
  finding phrases, or the impression explicitly states normal.
- findings: keyword ∪ MriFinding enum synonyms.
- lesion_lobe / laterality: nearest-lobe/lateral word within a fixed
  window around a finding token.
- hippocampal_sclerosis / focal_cortical_dysplasia: enum-aware boolean.
- mri_negative_for_epilepsy: only True on explicit statement.
- field_strength_tesla: first "N.N T" or "N T" number.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from schema import Certainty, DocumentMetadata, MriFinding, TemporalStatus


# ---------------------------------------------------------------------------
# Regex bank
# ---------------------------------------------------------------------------

# Field strength — "3T", "3 T", "3 Tesla", "1.5T"
_RE_TESLA = re.compile(r"(\d+(?:\.\d+)?)\s*(?:T\b|Tesla)", re.IGNORECASE)

# Laterality words
_LATERALITY_WORDS = {
    "left": "left", "right": "right",
    "bilateral": "bilateral", "midline": "midline",
    "diffuse": "diffuse",
}

# Lobar words. Anatomical synonyms map to the ILAE-canonical lobe: hippocampal
# structures are mesial temporal by definition, so any near-mention counts as
# temporal for lesion localization purposes.
_LOBAR_WORDS = {
    "frontal": "frontal", "temporal": "temporal", "parietal": "parietal",
    "occipital": "occipital", "insular": "insular", "cingulate": "cingulate",
    "multifocal": "multifocal",
    "hippocampal": "temporal", "hippocampus": "temporal",
    "mesial temporal": "temporal", "amygdala": "temporal",
}

# Finding phrase → MriFinding value. Order matters: check more specific first.
_FINDING_PATTERNS: list[tuple[re.Pattern[str], MriFinding]] = [
    (re.compile(r"MOGHE|mild malformation of cortical development with oligodendroglial hyperplasia",
                re.IGNORECASE), MriFinding.MOGHE),
    (re.compile(r"FCD\s*(?:Type\s*)?IIa|Palmini\s*IIa", re.IGNORECASE), MriFinding.FCD_PALMINI_IIA),
    (re.compile(r"FCD\s*(?:Type\s*)?IIb|Palmini\s*IIb", re.IGNORECASE), MriFinding.FCD_PALMINI_IIB),
    (re.compile(r"FCD\s*(?:Type\s*)?I(?![Ia-b])|Palmini\s*I(?![Ia-b])", re.IGNORECASE),
     MriFinding.FCD_PALMINI_I),
    (re.compile(r"focal cortical dysplasia|\bFCD\b", re.IGNORECASE),
     MriFinding.FOCAL_CORTICAL_DYSPLASIA),
    (re.compile(r"hippocampal sclerosis|mesial temporal sclerosis|\bHS\b|\bMTS\b"),
     MriFinding.HIPPOCAMPAL_SCLEROSIS),
    (re.compile(r"encephalomalacia", re.IGNORECASE), MriFinding.ENCEPHALOMALACIA),
    (re.compile(r"tuberous sclerosis|tubers", re.IGNORECASE), MriFinding.TUBEROUS_SCLEROSIS),
    (re.compile(r"polymicrogyria", re.IGNORECASE), MriFinding.POLYMICROGYRIA),
    (re.compile(r"heterotopia", re.IGNORECASE), MriFinding.HETEROTOPIA),
    (re.compile(r"lissencephaly", re.IGNORECASE), MriFinding.LISSENCEPHALY),
    (re.compile(r"vascular malformation|AVM|cavernoma|cavernous angioma", re.IGNORECASE),
     MriFinding.VASCULAR_MALFORMATION),
    (re.compile(r"stroke\s+sequel(?:ae|a)|prior infarct|old infarct", re.IGNORECASE),
     MriFinding.STROKE_SEQUELAE),
    (re.compile(r"gliosis", re.IGNORECASE), MriFinding.GLIOSIS),
    (re.compile(r"tumor|neoplasm|glioma|meningioma", re.IGNORECASE), MriFinding.TUMOR),
    (re.compile(
        r"MRI(?:-|\s+)?negative|no\s+epilepsy(?:-|\s+)?relevant\s+lesion|"
        r"no\s+epileptogenic\s+lesion",
        re.IGNORECASE), MriFinding.MRI_NEGATIVE),
]

_NEG_PREFIX = re.compile(
    r"(?:no|without|absent|not\s+identified|negative for|rules? out)\s+",
    re.IGNORECASE,
)


def _find_first_tesla(text: str) -> Optional[float]:
    m = _RE_TESLA.search(text)
    if not m:
        return None
    try:
        v = float(m.group(1))
        return v if 0.5 <= v <= 10 else None
    except ValueError:
        return None


def _find_nearest_word(text: str, span_start: int, span_end: int,
                       word_map: dict[str, str], window: int = 80) -> Optional[str]:
    """Look for any word from word_map within `window` chars around the span."""
    start = max(0, span_start - window)
    end = min(len(text), span_end + window)
    context = text[start:end].lower()
    # Search backwards from the span so nearer words win
    hits: list[tuple[int, str]] = []
    for key in word_map:
        for m in re.finditer(r"\b" + re.escape(key) + r"\b", context):
            hits.append((abs(m.start() - (span_start - start)), word_map[key]))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


def _ev(value, evidence_text: str, doc: DocumentMetadata,
        certainty: str = "definite", temporal: str = "current") -> dict[str, Any]:
    if isinstance(value, MriFinding):
        value = value.value
    return {
        "value": value,
        "certainty": certainty,
        "temporal_status": temporal,
        "evidence_text": evidence_text,
        "source_doc_id": doc.doc_id,
        "source_doc_type": doc.doc_type.value,
        "source_date": doc.doc_date.isoformat(),
    }


def _null_ev(doc: DocumentMetadata) -> dict[str, Any]:
    return {
        "value": None,
        "certainty": "not_documented",
        "temporal_status": "unspecified",
        "evidence_text": None,
        "source_doc_id": doc.doc_id,
        "source_doc_type": doc.doc_type.value,
        "source_date": doc.doc_date.isoformat(),
    }


def _preceded_by_negation(text: str, span_start: int, back: int = 30) -> bool:
    lookback = text[max(0, span_start - back):span_start]
    return bool(_NEG_PREFIX.search(lookback))


# ---------------------------------------------------------------------------
# Rules extractor
# ---------------------------------------------------------------------------


def extract_mri(text: str, doc: DocumentMetadata) -> dict[str, Any]:
    """Produce a dict matching MriModule's JSON schema from a rules-only pass."""
    text_norm = text  # preserve casing for evidence quotes; regexes handle case
    findings_dicts: list[dict[str, Any]] = []
    hs_flag: Optional[bool] = None
    fcd_flag: Optional[bool] = None
    lesion_span: Optional[tuple[int, int, str]] = None  # (start, end, quote)
    mri_negative_flag: Optional[bool] = None

    seen: set[MriFinding] = set()
    for pat, finding in _FINDING_PATTERNS:
        for m in pat.finditer(text_norm):
            negated = _preceded_by_negation(text_norm, m.start())
            quote = text_norm[max(0, m.start() - 5):min(len(text_norm), m.end() + 5)].strip()

            if finding == MriFinding.MRI_NEGATIVE:
                # Only count MRI-negative when it's an affirmative statement
                if not negated:
                    mri_negative_flag = True
                continue

            if finding == MriFinding.HIPPOCAMPAL_SCLEROSIS:
                hs_flag = not negated
                if not negated and finding not in seen:
                    findings_dicts.append(_ev(finding.value, quote, doc,
                                              certainty="negated" if negated else "definite"))
                    seen.add(finding)
                if not negated and lesion_span is None:
                    lesion_span = (m.start(), m.end(), quote)
                continue

            if finding in (
                MriFinding.FOCAL_CORTICAL_DYSPLASIA,
                MriFinding.FCD_PALMINI_I,
                MriFinding.FCD_PALMINI_IIA,
                MriFinding.FCD_PALMINI_IIB,
                MriFinding.MOGHE,
            ):
                if not negated:
                    fcd_flag = True
                if not negated and finding not in seen:
                    findings_dicts.append(_ev(finding.value, quote, doc))
                    seen.add(finding)
                if not negated and lesion_span is None:
                    lesion_span = (m.start(), m.end(), quote)
                continue

            if not negated and finding not in seen:
                findings_dicts.append(_ev(finding.value, quote, doc))
                seen.add(finding)
                if lesion_span is None:
                    lesion_span = (m.start(), m.end(), quote)

    # Lesion lobe + laterality from the nearest lobar/lateral word
    lesion_lobe = _null_ev(doc)
    lesion_laterality = _null_ev(doc)
    if lesion_span is not None:
        s, e, quote = lesion_span
        lobe = _find_nearest_word(text_norm, s, e, _LOBAR_WORDS)
        lat = _find_nearest_word(text_norm, s, e, _LATERALITY_WORDS)
        if lobe:
            lesion_lobe = _ev(lobe, quote, doc, certainty="probable")
        if lat:
            lesion_laterality = _ev(lat, quote, doc, certainty="probable")

    # overall_normal: True only if explicit and no findings emitted
    overall_normal_val = None
    overall_normal_ev = _null_ev(doc)
    if findings_dicts:
        overall_normal_val = False
    else:
        if re.search(r"\bimpression[:\s]+normal\b|MRI.*is\s+normal|unremarkable\s+MRI",
                     text_norm, re.IGNORECASE):
            overall_normal_val = True
            overall_normal_ev = _ev(True, "normal MRI", doc)
    if overall_normal_val is False:
        # find a snippet for evidence
        first = findings_dicts[0]
        overall_normal_ev = _ev(False, first["evidence_text"], doc)

    # Consistency validator on the schema will require booleans to match findings.
    # If we detected findings but didn't mark hs/fcd bool, default False (not negated) —
    # only True when we affirmatively saw the enum finding.
    hs_ev = _ev(hs_flag, "hippocampal sclerosis" if hs_flag else "no hippocampal sclerosis",
                doc, certainty="definite" if hs_flag is not None else "not_documented") \
        if hs_flag is not None else _null_ev(doc)
    fcd_ev = _ev(fcd_flag, "focal cortical dysplasia" if fcd_flag else "no FCD",
                 doc, certainty="definite" if fcd_flag is not None else "not_documented") \
        if fcd_flag is not None else _null_ev(doc)

    # mri_negative_for_epilepsy defaults False when we found ≥1 finding; only True
    # on explicit statement; else not_documented.
    if mri_negative_flag is True:
        mri_negative_ev = _ev(True, "MRI-negative", doc)
    elif findings_dicts:
        mri_negative_ev = _ev(False, findings_dicts[0]["evidence_text"], doc)
    else:
        mri_negative_ev = _null_ev(doc)

    # Field strength
    tesla = _find_first_tesla(text_norm)
    if tesla is not None:
        m = _RE_TESLA.search(text_norm)
        quote = text_norm[max(0, m.start() - 5):min(len(text_norm), m.end() + 5)].strip()
        field_strength_ev = _ev(tesla, quote, doc)
    else:
        field_strength_ev = _null_ev(doc)

    return {
        "overall_normal": overall_normal_ev,
        "findings": findings_dicts,
        "lesion_lobe": lesion_lobe,
        "lesion_laterality": lesion_laterality,
        "hippocampal_sclerosis": hs_ev,
        "focal_cortical_dysplasia": fcd_ev,
        "mri_negative_for_epilepsy": mri_negative_ev,
        "field_strength_tesla": field_strength_ev,
    }


# ---------------------------------------------------------------------------
# ModelBackend adapter — allows the rules baseline to run through the exact
# same extraction pipeline the LLM arms use.
# ---------------------------------------------------------------------------


@dataclass
class RulesMriBackend:
    """Deterministic non-LLM 'backend' that returns rules-generated JSON.

    Because the pipeline requires a ModelBackend, we implement one whose
    `generate()` ignores the prompt entirely and reads the source doc from
    an attribute set immediately before each call. Not thread-safe by design —
    call sites use this synchronously.
    """
    doc: DocumentMetadata
    model_name: str = "baseline/rules-mri"
    model_cache_dir: str = ""

    def generate(self, prompt: str, decoding) -> tuple[str, Optional[int]]:
        # The pipeline passes the source doc inside `prompt`. Rather than
        # parse it back out, callers use the higher-level `run_b0_mri()`
        # helper which sets `self._current_source`.
        source = getattr(self, "_current_source", None)
        if source is None:
            return json.dumps({}), 0
        payload = extract_mri(source, self.doc)
        return json.dumps(payload), None


def run_b0_mri(source_text: str, doc: DocumentMetadata) -> dict[str, Any]:
    """One-shot B0 extraction (no pipeline). Returns a dict conforming to
    MriModule's JSON schema. Callers can `MriModule.model_validate(...)` it."""
    return extract_mri(source_text, doc)
