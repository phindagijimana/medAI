"""
mri.py — MRI findings extraction (MriFinding enum + convenience booleans).

Fields populated
----------------
- ``mri.findings``             (list[Evidence[MriFinding]])
- ``mri.hippocampal_sclerosis`` (Evidence[bool])
- ``mri.focal_cortical_dysplasia`` (Evidence[bool])
- ``mri.mri_negative_for_epilepsy`` (Evidence[bool])
- ``mri.overall_normal``       (Evidence[bool])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/investigations.jape``         — top-level investigations composition
- ``jape/InvestigationsMRI.jape``      — MRI-specific patterns
- ``jape/InvestigationsCT.jape``       — CT-neg impact on MRI negativity
- ``jape/NegatedFindingMRI.jape``      — "no lesion" / "normal MRI"
- ``jape/InvestigationBlock.jape``     — sentence-block scoping
- ``jape/InvestigationWithin.jape``    — nested-clause finding
- ``jape/InvestigationsLookup.jape``   — gazetteer entry lookup
- ``jape/LocationAndFinding.jape``     — finding + laterality composition
- ``jape/Lateralisation.jape``         — left/right/bilateral
- ``jape/GenericInvestigations.jape``  — fallback for uncommon phrasings
- ``jape/InvestigationsMP.jape``       — MP-tagger + investigation combo
- ``jape/InvestConj.jape``             — conjunction ("and", "with") within
                                          multi-finding sentences
- ``resources/gazetteers/ct_mri_results.lst`` — finding vocabulary
- ``Groovy/Investigations.groovy``     — top-level serializer
- ``Groovy/MarkupInvestigations.groovy`` — span builder

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. LinkedEntity with ``enum_class == "MriFinding"`` — direct.
2. Sentence context: only count findings appearing in sentences that mention
   MRI-related keywords (MRI, brain scan, imaging, T1/T2/FLAIR) OR that
   appear in a section header like "Investigations:".
3. Negation-aware convenience booleans:
     - HS/FCD/MOGHE/FCD Palmini II* found → hippocampal_sclerosis /
       focal_cortical_dysplasia set True.
     - "MRI-negative" / "unremarkable MRI" / "normal MRI" → overall_normal True.
     - "MRI-negative for epilepsy" / "no epileptogenic lesion" →
       mri_negative_for_epilepsy True.
4. Consistency with the schema model_validator: booleans are only set True
   when the corresponding enum appears in ``findings`` — otherwise the
   convenience field falls back to False (with evidence text) or
   ``not_documented``.
5. ConText — negated → do not emit finding, but may flip the "no HS" boolean.
   Hypothetical → certainty POSSIBLE.

Cite: Fonferko-Shadrach et al. 2019; 2024.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import Certainty, MriFinding, TemporalStatus
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# MRI-context patterns
# ---------------------------------------------------------------------------

_MRI_CONTEXT_RE = re.compile(
    r"\bMRI\b|\bMR\s+brain\b|\bMR\s+imaging\b|"
    r"brain\s+scan|brain\s+imaging|"
    r"\bT1\b|\bT2\b|\bFLAIR\b|\bDWI\b|\bSWI\b|"
    r"neuroimaging|structural\s+imaging",
    re.IGNORECASE,
)

# Explicit "MRI is normal / unremarkable" — set both overall_normal=True
# and mri_negative_for_epilepsy=True.
# Allows up to 30 chars of intervening text (year, "of brain", etc.).
_NORMAL_MRI_RE = re.compile(
    r"MRI(?:[^.]{0,40})?\s(?:was\s+|is\s+|were\s+|are\s+)?"
    r"(?:normal|unremarkable)|"
    r"unremarkable\s+MRI|normal\s+MRI|"
    r"(?:MRI[- ]?negative)|no\s+epileptogenic\s+lesion|"
    r"no\s+epilepsy[- ]relevant\s+lesion",
    re.IGNORECASE,
)


# Extra findings pattern bank — anything we might not have in the CDB.
# Order = specificity descending.
_FINDING_FALLBACK: list[tuple[re.Pattern[str], MriFinding]] = [
    (re.compile(r"MOGHE|mild\s+MCD\s+with\s+oligodendroglial\s+hyperplasia",
                re.IGNORECASE), MriFinding.MOGHE),
    (re.compile(r"FCD\s*(?:Type\s*)?IIa|Palmini\s*IIa", re.IGNORECASE),
     MriFinding.FCD_PALMINI_IIA),
    (re.compile(r"FCD\s*(?:Type\s*)?IIb|Palmini\s*IIb", re.IGNORECASE),
     MriFinding.FCD_PALMINI_IIB),
    (re.compile(r"FCD\s*(?:Type\s*)?I(?![Ia-b])|Palmini\s*I(?![Ia-b])",
                re.IGNORECASE), MriFinding.FCD_PALMINI_I),
    (re.compile(r"focal\s+cortical\s+dysplasia|\bFCD\b(?!\s*[Tt]ype)",
                re.IGNORECASE), MriFinding.FOCAL_CORTICAL_DYSPLASIA),
    (re.compile(r"hippocampal\s+sclerosis|mesial\s+temporal\s+sclerosis|"
                r"\bHS\b|\bMTS\b"), MriFinding.HIPPOCAMPAL_SCLEROSIS),
    (re.compile(r"encephalomalacia", re.IGNORECASE), MriFinding.ENCEPHALOMALACIA),
    (re.compile(r"tuberous\s+sclerosis|cortical\s+tubers?",
                re.IGNORECASE), MriFinding.TUBEROUS_SCLEROSIS),
    (re.compile(r"polymicrogyria", re.IGNORECASE), MriFinding.POLYMICROGYRIA),
    (re.compile(r"heterotopia|nodular\s+heterotopia|band\s+heterotopia",
                re.IGNORECASE), MriFinding.HETEROTOPIA),
    (re.compile(r"lissencephaly", re.IGNORECASE), MriFinding.LISSENCEPHALY),
    (re.compile(r"vascular\s+malformation|\bAVM\b|arteriovenous\s+malformation|"
                r"cavernoma|cavernous\s+angioma|cavernous\s+malformation",
                re.IGNORECASE), MriFinding.VASCULAR_MALFORMATION),
    (re.compile(r"stroke\s+sequel(?:ae|a)|prior\s+infarct|old\s+infarct|"
                r"chronic\s+infarct", re.IGNORECASE),
     MriFinding.STROKE_SEQUELAE),
    (re.compile(r"\bgliosis\b", re.IGNORECASE), MriFinding.GLIOSIS),
    (re.compile(r"\btumo(?:u)?r\b|neoplasm|glioma|meningioma|"
                r"ganglioglioma|DNET|dysembryoplastic\s+neuroepithelial",
                re.IGNORECASE), MriFinding.TUMOR),
]


_NEG_PREFIX = re.compile(
    r"\b(?:no|without|absent|not\s+identified|negative\s+for|"
    r"rules?\s+out|denies)\s+",
    re.IGNORECASE,
)


def _preceded_by_negation(text: str, span_start: int, back: int = 30) -> bool:
    lookback = text[max(0, span_start - back):span_start]
    return bool(_NEG_PREFIX.search(lookback))


def _mri_sentence(sent_text: str) -> bool:
    return bool(_MRI_CONTEXT_RE.search(sent_text or ""))


def _detect_findings(
    entities: list[LinkedEntity],
    doc,
) -> list[tuple[MriFinding, int, int, str, bool, bool]]:
    """Return unique (finding, char_start, char_end, quote, is_hyp, is_hist)
    tuples. Deduplicates by finding enum."""
    text = getattr(doc, "text", "") or ""
    seen: set[MriFinding] = set()
    hits: list[tuple[MriFinding, int, int, str, bool, bool]] = []

    # 1. From LinkedEntity list — trust MedCAT + ConText for negation.
    for e in entities:
        if e.enum_class != "MriFinding":
            continue
        if e.is_family:
            continue
        # Require MRI context — otherwise "hippocampal sclerosis" mentioned in
        # a diagnosis line without imaging may not belong to the MRI module.
        if not _mri_sentence(e.sentence_text or "") and not _mri_sentence(text[:300]):
            # Section headers commonly appear at the top ("Investigations:").
            continue
        try:
            finding = MriFinding(e.enum_value)
        except ValueError:
            continue
        if e.is_negated:
            continue
        if finding in seen:
            continue
        seen.add(finding)
        hits.append((finding, e.char_start, e.char_end, e.text,
                     e.is_hypothetical, e.is_historical))

    # 2. Fallback regex — plug gaps for findings the CDB missed.
    for pat, finding in _FINDING_FALLBACK:
        for m in pat.finditer(text):
            if finding in seen:
                continue
            if _preceded_by_negation(text, m.start()):
                continue
            # Rough MRI-sentence check — same as above using rough sentence
            # boundaries.
            # Approximate: 200 chars either side must mention an MRI keyword,
            # OR the top of the note has "Investigations".
            window = text[max(0, m.start() - 200):min(len(text), m.end() + 200)]
            if not (_MRI_CONTEXT_RE.search(window) or
                    re.search(r"Investigations?\s*:", text[:300], re.IGNORECASE)):
                continue
            quote = text[max(0, m.start() - 5):min(len(text), m.end() + 30)].strip()
            seen.add(finding)
            hits.append((finding, m.start(), m.end(), quote, False, False))

    return hits


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class MriFindingsRule(BaseFieldRule):
    field_name = "mri.findings"

    def apply(self, entities, doc, meta):
        hits = _detect_findings(entities, doc)
        if not hits:
            return None
        out: list[Evidence] = []
        for finding, cs, ce, quote, is_hyp, is_hist in hits:
            certainty = Certainty.POSSIBLE if is_hyp else Certainty.DEFINITE
            temporal = TemporalStatus.HISTORICAL if is_hist else TemporalStatus.CURRENT
            out.append(Evidence[MriFinding](
                value=finding,
                certainty=certainty,
                temporal_status=temporal,
                evidence_text=quote,
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=cs,
                char_end=ce,
            ))
        return out or None


class MriHippocampalSclerosisRule(BaseFieldRule):
    field_name = "mri.hippocampal_sclerosis"

    def apply(self, entities, doc, meta):
        hits = _detect_findings(entities, doc)
        has_hs = any(f == MriFinding.HIPPOCAMPAL_SCLEROSIS for f, *_ in hits)
        if has_hs:
            for f, cs, ce, quote, is_hyp, is_hist in hits:
                if f == MriFinding.HIPPOCAMPAL_SCLEROSIS:
                    return Evidence[bool](
                        value=True,
                        certainty=Certainty.POSSIBLE if is_hyp else Certainty.DEFINITE,
                        temporal_status=(TemporalStatus.HISTORICAL if is_hist
                                         else TemporalStatus.CURRENT),
                        evidence_text=quote,
                        source_doc_id=meta["doc_id"],
                        source_doc_type=meta["doc_type"],
                        source_date=meta["doc_date"],
                        char_start=cs,
                        char_end=ce,
                    )
        # Explicit negation — "no hippocampal sclerosis" — set False.
        text = getattr(doc, "text", "") or ""
        m = re.search(r"no\s+(?:evidence\s+of\s+)?(?:hippocampal|mesial\s+temporal)\s+sclerosis",
                      text, re.IGNORECASE)
        if m:
            return Evidence[bool](
                value=False,
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


class MriFcdRule(BaseFieldRule):
    field_name = "mri.focal_cortical_dysplasia"

    _FCD_ENUMS = {
        MriFinding.FOCAL_CORTICAL_DYSPLASIA,
        MriFinding.FCD_PALMINI_I,
        MriFinding.FCD_PALMINI_IIA,
        MriFinding.FCD_PALMINI_IIB,
        MriFinding.MOGHE,
    }

    def apply(self, entities, doc, meta):
        hits = _detect_findings(entities, doc)
        for f, cs, ce, quote, is_hyp, is_hist in hits:
            if f in self._FCD_ENUMS:
                return Evidence[bool](
                    value=True,
                    certainty=Certainty.POSSIBLE if is_hyp else Certainty.DEFINITE,
                    temporal_status=(TemporalStatus.HISTORICAL if is_hist
                                     else TemporalStatus.CURRENT),
                    evidence_text=quote,
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=cs,
                    char_end=ce,
                )
        return None


class MriNegativeForEpilepsyRule(BaseFieldRule):
    field_name = "mri.mri_negative_for_epilepsy"

    def apply(self, entities, doc, meta):
        text = getattr(doc, "text", "") or ""
        m = _NORMAL_MRI_RE.search(text)
        if m:
            return Evidence[bool](
                value=True,
                certainty=Certainty.PROBABLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )
        return None


class MriOverallNormalRule(BaseFieldRule):
    field_name = "mri.overall_normal"

    def apply(self, entities, doc, meta):
        text = getattr(doc, "text", "") or ""
        hits = _detect_findings(entities, doc)
        # If we found any positive finding → overall_normal False.
        if hits:
            f, cs, ce, quote, _hyp, _hist = hits[0]
            return Evidence[bool](
                value=False,
                certainty=Certainty.DEFINITE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=quote,
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=cs,
                char_end=ce,
            )
        # Explicit "normal MRI" → True.
        m = _NORMAL_MRI_RE.search(text)
        if m:
            return Evidence[bool](
                value=True,
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

register_rule(MriFindingsRule())
register_rule(MriHippocampalSclerosisRule())
register_rule(MriFcdRule())
register_rule(MriNegativeForEpilepsyRule())
register_rule(MriOverallNormalRule())

__all__ = [
    "MriFindingsRule",
    "MriHippocampalSclerosisRule",
    "MriFcdRule",
    "MriNegativeForEpilepsyRule",
    "MriOverallNormalRule",
]
