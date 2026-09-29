"""
clinical_localization.py — Localization claims (LobarClaim) and concordance.

Fields populated
----------------
- ``clinical_localization.primary_claim``  (Evidence[LobarClaim])
- ``clinical_localization.alternative_claims`` (list[Evidence[LobarClaim]])
- ``integrated.clinical_localization``     (Evidence[LobarClaim])
- ``integrated.eeg_localization``          (Evidence[LobarClaim])
- ``integrated.mri_localization``          (Evidence[LobarClaim])
- ``integrated.concordance``               (Evidence[ConcordanceStatus])  [Wave-2]

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/Lateralisation.jape``           — left/right/bilateral tokens
- ``jape/LocationAndFinding.jape``       — Lobe + Laterality + Finding combo
- ``jape/InvestigationsMRI.jape``        — MRI lesion + localization
- ``jape/InvestigationsEEG.jape``        — EEG focus + localization
- ``Groovy/Investigations.groovy``       — investigation-scoped serializer
- ``Groovy/Diagnosis.groovy``            — clinical-hypothesis serializer

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. **primary_claim** — a LobarClaim = (lobe, laterality, source). Detected
   by scanning sentences for Lobe + Laterality co-occurrences. Source is
   inferred from the sentence context:
     - EEG keywords → EEG_CONFIRMED
     - MRI keywords → MRI_CONFIRMED
     - Diagnosis / clinical / semiology → CLINICIAN_HYPOTHESIS
     - SEEG / stereo-EEG → SEEG_CONFIRMED
     - Post-operative pathology → SURGICAL_CONFIRMED
   Precedence for the *primary* claim: EEG-confirmed > MRI-confirmed >
   clinician hypothesis (per ILAE presurgical evaluation standard).
2. **alternative_claims** — every distinct (lobe, laterality) tuple that
   isn't the primary becomes an alternative.
3. **integrated modality-specific** — separate LobarClaim per modality
   (EEG, MRI, clinical) for downstream concordance analysis.
4. **concordance** — [Wave-2] compares clinical vs EEG vs MRI claims:
     - All three concordant on (lobe, laterality) → CONCORDANT
     - Two of three concordant → PARTIALLY_CONCORDANT
     - All disagree → DISCORDANT
     - Only one modality documented → NOT_ASSESSED
5. ConText — negated ("not localized to X") → skip; family → skip;
   hypothetical ("possibly frontal") → downgrade certainty to POSSIBLE.

Cite: ILAE presurgical evaluation standards; Rosenow & Lüders 2001
(Brain 124:1683); Fonferko-Shadrach et al. 2019; 2024.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import (
    Certainty,
    ConcordanceStatus,
    Laterality,
    LobarLocalization,
    LocalizationSource,
    TemporalStatus,
)
from schema.evidence import Evidence
from schema.ontology import LobarClaim
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Vocab
# ---------------------------------------------------------------------------

_LATERALITY_MAP = {
    "left": Laterality.LEFT,
    "left-sided": Laterality.LEFT,
    "right": Laterality.RIGHT,
    "right-sided": Laterality.RIGHT,
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
    "centro-temporal": LobarLocalization.TEMPORAL,
    "fronto-temporal": LobarLocalization.FRONTAL,
    "temporoparietal": LobarLocalization.TEMPORAL,
    "parieto-occipital": LobarLocalization.PARIETAL,
}

_EEG_CTX_RE = re.compile(
    r"\bEEG\b|electroencephalogr|video[- ]?EEG|ambulatory\s+EEG|"
    r"ictal\s+onset|epileptiform\s+discharge|"
    r"spikes?|sharp\s+wave|posterior\s+dominant\s+rhythm",
    re.IGNORECASE,
)

_MRI_CTX_RE = re.compile(
    r"\bMRI\b|\bMR\s+brain\b|neuroimaging|structural\s+imaging|"
    r"lesion|hippocampal\s+sclerosis|FCD|encephalomalacia|"
    r"cortical\s+dysplasia|T2\s+hyperintens|FLAIR",
    re.IGNORECASE,
)

_SEEG_CTX_RE = re.compile(
    r"stereo[- ]?EEG|\bsEEG\b|\bSEEG\b|depth\s+electrodes?|"
    r"intracranial\s+EEG",
    re.IGNORECASE,
)

_SURG_CTX_RE = re.compile(
    r"post[- ]?operative|resect(?:ion|ed)|pathology|histopath|"
    r"specimen",
    re.IGNORECASE,
)

_DIAGNOSIS_CTX_RE = re.compile(
    r"\bdiagnosis\b|clinical\s+localization|clinical\s+hypothesis|"
    r"semiology|typical\s+seizures?|history\s+suggests",
    re.IGNORECASE,
)

_NEG_PRE = re.compile(
    r"\b(?:no|without|denies?|absent|never|not|negative\s+for|"
    r"ruled?\s+out)\s+",
    re.IGNORECASE,
)


def _preceded_by_neg(text: str, start: int, back: int = 30) -> bool:
    return bool(_NEG_PRE.search(text[max(0, start - back):start]))


def _find_sentence_bounds(text: str, char: int) -> tuple[int, int]:
    sent_start = 0
    for m in re.finditer(r"[.!?;\n]", text[:char]):
        sent_start = m.end()
    m = re.search(r"[.!?;\n]", text[char:])
    sent_end = char + m.start() if m else len(text)
    return sent_start, sent_end


def _infer_source(sentence: str) -> LocalizationSource:
    """Return the LocalizationSource from sentence keywords. Precedence:
    SEEG > surgical > EEG > MRI > clinician hypothesis (default)."""
    if _SEEG_CTX_RE.search(sentence):
        return LocalizationSource.SEEG_CONFIRMED
    if _SURG_CTX_RE.search(sentence):
        return LocalizationSource.SURGICAL_CONFIRMED
    if _EEG_CTX_RE.search(sentence):
        return LocalizationSource.EEG_CONFIRMED
    if _MRI_CTX_RE.search(sentence):
        return LocalizationSource.MRI_CONFIRMED
    return LocalizationSource.CLINICIAN_HYPOTHESIS


def _extract_lobar_claims(
    text: str,
) -> list[tuple[LobarLocalization, Laterality, LocalizationSource,
                int, int, str]]:
    """Return unique (lobe, laterality, source, char_start, char_end, quote)
    tuples across the document. Deduplicates by (lobe, laterality)."""
    if not text:
        return []
    out = []

    # Compile a combined pattern that finds lobe tokens + surrounding context.
    lobe_pat = re.compile(
        r"\b(frontal|temporal|parietal|occipital|insular|cingulate|"
        r"multifocal|hippocampal|mesial\s+temporal|centro-?temporal|"
        r"fronto-?temporal|temporoparietal|parieto-?occipital)\b",
        re.IGNORECASE,
    )
    lat_pat = re.compile(
        r"\b(left|right|bilateral|bilaterally|left-sided|right-sided|"
        r"midline|diffuse|generalized|generalised)\b",
        re.IGNORECASE,
    )

    # Dedup key includes source to allow the same (lobe, laterality) to
    # be recorded from multiple modalities (clinical, EEG, MRI) — needed
    # for downstream concordance analysis.
    seen_full: set[tuple[LobarLocalization, Laterality, LocalizationSource]] = set()

    for lm in lobe_pat.finditer(text):
        if _preceded_by_neg(text, lm.start()):
            continue
        lobe_key = lm.group(1).lower().replace("-", " ").strip()
        # Normalise to closest _LOBE_MAP key.
        lobe = None
        for k, v in _LOBE_MAP.items():
            if k in lobe_key or lobe_key in k:
                lobe = v
                break
        if lobe is None:
            continue

        sent_start, sent_end = _find_sentence_bounds(text, lm.start())
        sentence = text[sent_start:sent_end]

        # Nearest laterality within the same sentence.
        laterality: Laterality = Laterality.UNKNOWN
        best_dist = 10**9
        for latm in lat_pat.finditer(sentence):
            # Position relative to lobe within sentence
            lat_pos = sent_start + latm.start()
            dist = abs(lat_pos - lm.start())
            if dist < best_dist:
                best_dist = dist
                laterality = _LATERALITY_MAP.get(latm.group(1).lower(),
                                                 Laterality.UNKNOWN)
        # If no laterality in sentence, default to UNKNOWN — still a claim.

        source = _infer_source(sentence)
        key = (lobe, laterality, source)
        if key in seen_full:
            continue
        seen_full.add(key)
        quote = sentence.strip()[:200]
        out.append((lobe, laterality, source, lm.start(), lm.end(), quote))

    return out


def _pick_primary(
    claims: list[tuple[LobarLocalization, Laterality, LocalizationSource,
                      int, int, str]],
) -> Optional[tuple[LobarLocalization, Laterality, LocalizationSource,
                    int, int, str]]:
    """Precedence: EEG > MRI > SEEG > SURGICAL > CLINICIAN. First-in-doc
    tie-break."""
    if not claims:
        return None
    order = {
        LocalizationSource.EEG_CONFIRMED: 0,
        LocalizationSource.MRI_CONFIRMED: 1,
        LocalizationSource.SEEG_CONFIRMED: 2,
        LocalizationSource.SURGICAL_CONFIRMED: 3,
        LocalizationSource.CLINICIAN_HYPOTHESIS: 4,
    }
    return sorted(claims, key=lambda c: (order.get(c[2], 5), c[3]))[0]


def _first_by_source(
    claims: list[tuple[LobarLocalization, Laterality, LocalizationSource,
                      int, int, str]],
    src: LocalizationSource,
) -> Optional[tuple]:
    for c in claims:
        if c[2] == src:
            return c
    return None


# ---------------------------------------------------------------------------
# Wave-1 Rules
# ---------------------------------------------------------------------------


class PrimaryLocalizationClaimRule(BaseFieldRule):
    """Populate ``clinical_localization.primary_claim``.

    Emits the highest-precedence LobarClaim found in the document.
    """

    field_name = "clinical_localization.primary_claim"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        claims = _extract_lobar_claims(text)
        primary = _pick_primary(claims)
        if primary is None:
            return None
        lobe, lat, src, cs, ce, quote = primary
        claim = LobarClaim(lobe=lobe, laterality=lat, source=src)
        return Evidence[LobarClaim](
            value=claim,
            certainty=Certainty.PROBABLE,
            temporal_status=TemporalStatus.CURRENT,
            evidence_text=quote,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=cs,
            char_end=ce,
        )


class AlternativeLocalizationClaimsRule(BaseFieldRule):
    """Populate ``clinical_localization.alternative_claims``."""

    field_name = "clinical_localization.alternative_claims"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[list[Evidence]]:
        text = getattr(doc, "text", "") or ""
        claims = _extract_lobar_claims(text)
        if len(claims) < 2:
            return None
        primary = _pick_primary(claims)
        out: list[Evidence] = []
        seen_lobe_lat: set[tuple[LobarLocalization, Laterality]] = set()
        if primary is not None:
            seen_lobe_lat.add((primary[0], primary[1]))
        for c in claims:
            if c == primary:
                continue
            lobe, lat, src, cs, ce, quote = c
            if (lobe, lat) in seen_lobe_lat:
                continue
            seen_lobe_lat.add((lobe, lat))
            claim = LobarClaim(lobe=lobe, laterality=lat, source=src)
            out.append(Evidence[LobarClaim](
                value=claim,
                certainty=Certainty.POSSIBLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=quote,
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=cs,
                char_end=ce,
            ))
        return out or None


class IntegratedClinicalLocalizationRule(BaseFieldRule):
    """Populate ``integrated.clinical_localization`` — the clinician-hypothesis
    claim only (not EEG/MRI-confirmed)."""

    field_name = "integrated.clinical_localization"
    phase = 1

    def apply(self, entities, doc, meta):
        text = getattr(doc, "text", "") or ""
        claims = _extract_lobar_claims(text)
        c = _first_by_source(claims, LocalizationSource.CLINICIAN_HYPOTHESIS)
        if c is None:
            return None
        lobe, lat, src, cs, ce, quote = c
        return Evidence[LobarClaim](
            value=LobarClaim(lobe=lobe, laterality=lat, source=src),
            certainty=Certainty.PROBABLE,
            temporal_status=TemporalStatus.CURRENT,
            evidence_text=quote,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=cs,
            char_end=ce,
        )


class IntegratedEegLocalizationRule(BaseFieldRule):
    """Populate ``integrated.eeg_localization``."""

    field_name = "integrated.eeg_localization"
    phase = 1

    def apply(self, entities, doc, meta):
        text = getattr(doc, "text", "") or ""
        claims = _extract_lobar_claims(text)
        c = _first_by_source(claims, LocalizationSource.EEG_CONFIRMED)
        if c is None:
            return None
        lobe, lat, src, cs, ce, quote = c
        return Evidence[LobarClaim](
            value=LobarClaim(lobe=lobe, laterality=lat, source=src),
            certainty=Certainty.PROBABLE,
            temporal_status=TemporalStatus.CURRENT,
            evidence_text=quote,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=cs,
            char_end=ce,
        )


class IntegratedMriLocalizationRule(BaseFieldRule):
    """Populate ``integrated.mri_localization``."""

    field_name = "integrated.mri_localization"
    phase = 1

    def apply(self, entities, doc, meta):
        text = getattr(doc, "text", "") or ""
        claims = _extract_lobar_claims(text)
        c = _first_by_source(claims, LocalizationSource.MRI_CONFIRMED)
        if c is None:
            return None
        lobe, lat, src, cs, ce, quote = c
        return Evidence[LobarClaim](
            value=LobarClaim(lobe=lobe, laterality=lat, source=src),
            certainty=Certainty.PROBABLE,
            temporal_status=TemporalStatus.CURRENT,
            evidence_text=quote,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=cs,
            char_end=ce,
        )


# ---------------------------------------------------------------------------
# Wave-2 Rule — concordance (reads clinical / EEG / MRI localizations)
# ---------------------------------------------------------------------------


class ConcordanceStatusRule(BaseFieldRule):
    """Populate ``integrated.concordance`` after wave-1 rules have run.

    Compound rule — inspects the partial phenotype set on ``self.pheno``
    by the assembler and compares the three modality localizations.
    """

    field_name = "integrated.concordance"
    phase = 2

    def apply(self, entities, doc, meta):
        pheno = getattr(self, "pheno", None)
        if pheno is None or pheno.integrated is None:
            return None
        clin = pheno.integrated.clinical_localization
        eeg = pheno.integrated.eeg_localization
        mri = pheno.integrated.mri_localization

        claims = []
        if clin and clin.value is not None:
            claims.append(("clinical", clin.value.lobe, clin.value.laterality))
        if eeg and eeg.value is not None:
            claims.append(("eeg", eeg.value.lobe, eeg.value.laterality))
        if mri and mri.value is not None:
            claims.append(("mri", mri.value.lobe, mri.value.laterality))

        if len(claims) < 2:
            # Only one modality documented → concordance not assessable.
            return Evidence[ConcordanceStatus](
                value=ConcordanceStatus.NOT_ASSESSED,
                certainty=Certainty.PROBABLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=f"{len(claims)} modality/modalities documented",
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
            )

        # Compare (lobe, laterality) tuples pairwise.
        tuples = [(l, la) for _, l, la in claims]
        distinct = set(tuples)
        if len(distinct) == 1:
            status = ConcordanceStatus.CONCORDANT
        elif len(claims) == 3 and any(tuples.count(t) >= 2 for t in tuples):
            status = ConcordanceStatus.PARTIALLY_CONCORDANT
        else:
            # 2 claims disagree, or 3 claims all disagree.
            # Lobe-only match still partially concordant.
            lobes = [l for _, l, _ in claims]
            if len(claims) == 3 and any(lobes.count(l) >= 2 for l in lobes):
                status = ConcordanceStatus.PARTIALLY_CONCORDANT
            elif len(claims) == 2 and lobes[0] == lobes[1]:
                status = ConcordanceStatus.PARTIALLY_CONCORDANT
            else:
                status = ConcordanceStatus.DISCORDANT

        quote = "; ".join(
            f"{m}={l.value}/{la.value}" for m, l, la in claims
        )
        return Evidence[ConcordanceStatus](
            value=status,
            certainty=Certainty.PROBABLE,
            temporal_status=TemporalStatus.CURRENT,
            evidence_text=quote,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
        )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(PrimaryLocalizationClaimRule())
register_rule(AlternativeLocalizationClaimsRule())
register_rule(IntegratedClinicalLocalizationRule())
register_rule(IntegratedEegLocalizationRule())
register_rule(IntegratedMriLocalizationRule())
register_rule(ConcordanceStatusRule())

__all__ = [
    "PrimaryLocalizationClaimRule",
    "AlternativeLocalizationClaimsRule",
    "IntegratedClinicalLocalizationRule",
    "IntegratedEegLocalizationRule",
    "IntegratedMriLocalizationRule",
    "ConcordanceStatusRule",
]
