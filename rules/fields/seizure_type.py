"""
seizure_type.py — SeizureType enum extraction (ILAE 2017 basic seizure types).

Fields populated
----------------
- ``clinical_seizure.predominant_seizure_type`` (single ``Evidence[SeizureType]``)
- ``clinical_seizure.other_seizure_types``      (``list[Evidence[SeizureType]]``)

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/seizurechange.jape``            — seizure-vs-frequency-change disambiguation
- ``jape/PartialSeizure.jape``           — simple/complex-partial → ILAE 2017 mapping
- ``jape/SingleSeizure.jape``            — single-seizure marker
- ``jape/SeizureMentions.jape``          — surface-form collection
- ``jape/PluralSeizuresJAVA.jape``       — plural-form normalisation
- ``jape/addSeziureType.jape``           — merge of type + qualifier
- ``jape/MultipleSeizures.jape``         — multiple types coordinated in one clause
- ``jape/implicitSeizure.jape``          — "usual/typical" pronoun resolution
- ``jape/SeizureFree.jape`` (as EXCLUDE) — "no seizures" → do not emit
- ``Groovy/Diagnosis.groovy``            — output serializer for a diagnosis mention
- ``Groovy/MarkupSeizureFrequency.groovy`` — clause-scoped seizure surface tagging
- ``Other/ILAE proposed map to UMLS and SNOMEDCT.xlsx`` — CUI ↔ ILAE 2017 label

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.
Semantics captured
------------------
1. **Direct match**: any non-negated, non-family, non-hypothetical LinkedEntity
   whose ``enum_class == "SeizureType"`` is a candidate.
2. **FBTC (focal-to-bilateral tonic-clonic)** composition — the ExECT
   ``seizurechange`` core case: a focal-onset entity + a GTC entity within
   ± 2 sentences and no terminator ("but", "however") between them collapses
   to :attr:`SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC`. Also covers the
   ILAE-2017 renaming of "secondarily generalised" → FBTC.
3. **Predominant selection**: among the surviving candidates, prefer the one
   with a "predominant" / "usual" / "typical" / "main" modifier in its sentence;
   otherwise use the first non-negated candidate in document order.
4. **Other types**: every distinct non-predominant SeizureType survives as an
   entry in ``other_seizure_types``.
5. **ConText flag handling**:
   - ``is_negated``  → drop from candidates (return None if this leaves nothing).
   - ``is_family``   → drop (family history, not patient's own type).
   - ``is_historical`` → keep but mark evidence ``temporal_status='historical'``.
   - ``is_hypothetical`` → keep but downgrade ``certainty`` to POSSIBLE.

Cite: Fonferko-Shadrach et al. 2019 BMC Med Res Methodol 19:52; 2024 J Biomed
Semantics 15:12 (ExECT-V2). Leftover historical names (psychomotor,
complex-partial, partial-onset, secondarily generalized seizures) map to
existing ILAE 2017 enums (Fisher 2017; Berg et al. 2010).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import Certainty, SeizureType, TemporalStatus
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


# Fallback seizure-type surface forms — used when MedCAT missed a mention
# (typically plural forms or typos absent from the ontology synonym list).
# Ordered by specificity descending.
_FALLBACK_SEIZURE_PATTERNS: list[tuple[re.Pattern[str], SeizureType]] = [
    (re.compile(
        r"focal[- ]?to[- ]?bilateral\s+tonic[- ]?clonic\s+seizures?|"
        r"secondar(?:ily|y)\s+generali[sz]ed\s+(?:tonic[- ]?clonic\s+)?seizures?|"
        r"\bFBTC\b",
        re.IGNORECASE), SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC),
    (re.compile(
        r"focal\s+impaired[- ]awareness\s+seizures?|"
        r"complex[- ]partial\s+seizures?|\bCPS\b|"
        r"psychomotor\s+seizures?",
        re.IGNORECASE), SeizureType.FOCAL_IMPAIRED_AWARENESS),
    (re.compile(
        r"focal\s+aware\s+seizures?|simple[- ]partial\s+seizures?|\bSPS\b",
        re.IGNORECASE), SeizureType.FOCAL_AWARE),
    (re.compile(
        r"typical\s+absence\s+seizures?|3[- ]?Hz\s+spike[- ]?wave\s+absences?",
        re.IGNORECASE), SeizureType.GENERALIZED_ABSENCE_TYPICAL),
    (re.compile(r"atypical\s+absence\s+seizures?", re.IGNORECASE),
     SeizureType.GENERALIZED_ABSENCE_ATYPICAL),
    (re.compile(
        r"generali[sz]ed\s+tonic[- ]?clonic\s+seizures?|"
        r"generali[sz]ed\s+tonic\s+chronic\s+seizures?|"   # F-S "chronic" typo
        r"\bGTC\b|\bGTCS\b|grand\s+mal\s+seizures?",
        re.IGNORECASE), SeizureType.GENERALIZED_TONIC_CLONIC),
    (re.compile(r"myoclonic\s+seizures?|myoclonic\s+jerks?|myoclonus\b",
                re.IGNORECASE), SeizureType.GENERALIZED_MYOCLONIC),
    (re.compile(r"atonic\s+seizures?|drop\s+attacks?", re.IGNORECASE),
     SeizureType.GENERALIZED_ATONIC),
    (re.compile(r"(?:epileptic|infantile)\s+spasms?", re.IGNORECASE),
     SeizureType.GENERALIZED_EPILEPTIC_SPASMS),
    (re.compile(r"tonic\s+seizures?(?!\s+clonic)", re.IGNORECASE),
     SeizureType.GENERALIZED_TONIC),
    (re.compile(r"generali[sz]ed\s+seizures?", re.IGNORECASE),
     SeizureType.UNKNOWN_ONSET_TONIC_CLONIC),  # ambiguous → default to TC-flavour
    (re.compile(
        r"focal\s+seizures?|partial[- ]onset\s+seizures?|partial\s+seizures?",
        re.IGNORECASE), SeizureType.FOCAL_UNKNOWN_AWARENESS),
]


def _fallback_seizure_matches(text: str) -> list[tuple[SeizureType, int, int, str]]:
    """Return (SeizureType, char_start, char_end, quote) for regex-matched
    seizure types not caught by MedCAT. Dedups by SeizureType."""
    seen: set[SeizureType] = set()
    out = []
    for pat, st in _FALLBACK_SEIZURE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if st in seen:
            continue
        # Sentence-level negation check.
        pre = text[max(0, m.start() - 30):m.start()]
        if re.search(r"\b(?:no|without|denies?|not|never)\s+(?:further\s+|any\s+)?",
                     pre, re.IGNORECASE):
            continue
        seen.add(st)
        out.append((st, m.start(), m.end(), m.group(0)))
    return out


# ---------------------------------------------------------------------------
# Lexical helpers — "predominant / usual / typical" modifiers (no verbatim
# JAPE trigger strings; these are US-clinical vernacular).
# ---------------------------------------------------------------------------

_PREDOMINANT_MARKERS = re.compile(
    r"\b(predominant|usual|typical|main|primary|characteristic|"
    r"most\s+common|most\s+frequent)\b",
    re.IGNORECASE,
)

# Focal-onset marker: needed for the FBTC composition rule when a focal
# entity co-occurs with a GTC entity in the same/next sentence.
_FOCAL_ONSET_MARKERS = re.compile(
    r"\bfocal\s+onset\b|"
    r"\b(?:secondar(?:ily|y))\s+generali[sz]ed\b|"
    r"\bfocal[- ]?to[- ]?bilateral\b|"
    r"\bstarts?\s+(?:as\s+)?focal\b",
    re.IGNORECASE,
)

# Terminator words scope the composition window (per ExECT ContextCorrection
# and NegationBack idioms).
_TERMINATOR = re.compile(r"\b(but|however|although|yet|nevertheless)\b", re.IGNORECASE)

# Phase 8 Iter 2 — markers that a seizure type is a *secondary* type, i.e.
# belongs in ``other_seizure_types``.  When present in the entity's sentence
# we keep the entity as an "other".  When absent we require the type to be
# a genuinely distinct ILAE category (not a subtype relationship) — this
# suppresses the flood of ``focal_unknown_awareness`` FPs that co-occurred
# with a more specific ``focal_impaired_awareness`` predominant in F-S.
_SECONDARY_MARKERS = re.compile(
    r"\b(?:also|additionally?|in\s+addition|other|another|"
    r"occasional(?:ly)?|sometimes|rarely|infrequent(?:ly)?|"
    r"secondary\s+type|different\s+type|two\s+different\s+types|"
    r"three\s+different\s+types|multiple\s+types)\b",
    re.IGNORECASE,
)

# Types that are related to each other in a subsumption sense — the
# more specific one should suppress the less specific in ``other_seizure_types``.
# Key: less specific type value; Value: set of more specific type values.
_SUBSUMES = {
    "focal_unknown_awareness": {
        "focal_aware",
        "focal_impaired_awareness",
        "focal_to_bilateral_tonic_clonic",
    },
    "unknown_onset_tonic_clonic": {
        "generalized_tonic_clonic",
        "focal_to_bilateral_tonic_clonic",
    },
    "generalized_tonic_clonic": {
        "focal_to_bilateral_tonic_clonic",
    },
}


def _is_focal(value: SeizureType) -> bool:
    return value.value.startswith("focal_") and value != SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC


def _is_generalized_tonic_clonic(value: SeizureType) -> bool:
    return value in (
        SeizureType.GENERALIZED_TONIC_CLONIC,
        SeizureType.UNKNOWN_ONSET_TONIC_CLONIC,
    )


# ---------------------------------------------------------------------------
# Rule 1 — Predominant seizure type
# ---------------------------------------------------------------------------


class PredominantSeizureTypeRule(BaseFieldRule):
    """Populate ``clinical_seizure.predominant_seizure_type``.

    See module docstring for the composition semantics.
    """

    field_name = "clinical_seizure.predominant_seizure_type"
    enum_class = SeizureType

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        cands = self.relevant_entities(entities, include_hypothetical=True)
        # Drop rules-only fillers like UNCLASSIFIED — they only fire on the
        # bare word "seizure" which is not a meaningful predominant type.
        cands = [e for e in cands if e.enum_value != SeizureType.UNCLASSIFIED.value]

        # Regex fallback — MedCAT may miss plural forms or typos.
        # Emit synthetic LinkedEntities for these, insert in char order,
        # skipping ones that duplicate an entity we already have.
        text = getattr(doc, "text", "") or ""
        seen_values = {e.enum_value for e in cands}
        for st, cs, ce, quote in _fallback_seizure_matches(text):
            if st.value in seen_values:
                continue
            # Build a synthetic LinkedEntity so the picker can uniformly
            # consume it. Sentence attrs left blank.
            synth = LinkedEntity(
                text=quote, cui="", sctid=None, label=st.value,
                enum_class="SeizureType", enum_value=st.value,
                char_start=cs, char_end=ce, confidence=0.7,
                linker_tier="fallback_regex",
                sentence_text="", sentence_start=-1,
            )
            cands.append(synth)
            seen_values.add(st.value)
        # Re-sort by char_start to preserve document order.
        cands.sort(key=lambda e: e.char_start)

        if not cands:
            return None

        # Try FBTC composition first: focal entity + GTC entity nearby, no
        # terminator between them.
        fbtc_result = self._compose_fbtc(cands, doc)
        if fbtc_result is not None:
            entity, extra_text = fbtc_result
            ev = self._make_evidence(
                SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC,
                entity,
                meta,
                evidence_text=extra_text or entity.text,
            )
            return ev

        # No FBTC → pick the "predominant" candidate.
        preferred = self._pick_predominant(cands)
        if preferred is None:
            return None

        try:
            value = SeizureType(preferred.enum_value)
        except ValueError:
            return None

        # Awareness refinement: generic ``focal_unknown_awareness`` is
        # frequently accompanied by an Awareness enum ("loss of awareness",
        # "impaired awareness") in the same sentence. Promote to the specific
        # subtype so the predominant matches ILAE-2017 nomenclature.
        if value == SeizureType.FOCAL_UNKNOWN_AWARENESS:
            promoted = self._promote_focal_awareness(preferred, entities)
            if promoted is not None:
                value = promoted
                # Widen the evidence text to include the awareness clause.
                sent_text = preferred.sentence_text or preferred.text
                return self._make_evidence(
                    value, preferred, meta,
                    evidence_text=sent_text.strip() or preferred.text,
                )

        # Historical / hypothetical are already handled by _make_evidence via
        # the entity's ConText flags.
        return self._make_evidence(value, preferred, meta)

    # ------------------------------------------------------------------

    @staticmethod
    def _promote_focal_awareness(
        focal_ent: LinkedEntity,
        entities: list[LinkedEntity],
    ) -> Optional[SeizureType]:
        """Look at Awareness LinkedEntities within the same sentence as
        ``focal_ent`` — promote focal_unknown_awareness → focal_impaired_awareness
        or focal_aware accordingly."""
        for e in entities:
            if e.enum_class != "Awareness":
                continue
            if e.is_negated or e.is_family:
                continue
            # Same sentence
            if e.sentence_start != focal_ent.sentence_start:
                continue
            if e.enum_value == "impaired":
                return SeizureType.FOCAL_IMPAIRED_AWARENESS
            if e.enum_value == "aware":
                return SeizureType.FOCAL_AWARE
        return None

    # ------------------------------------------------------------------

    def _pick_predominant(self, cands: list[LinkedEntity]) -> Optional[LinkedEntity]:
        # Highest-priority = has an explicit "predominant" marker in its sentence.
        for e in cands:
            if _PREDOMINANT_MARKERS.search(e.sentence_text or ""):
                return e
        # Second priority = the more specific ILAE type (drop generic
        # focal_unknown_awareness if a focal_aware / focal_impaired_awareness
        # co-occurs in the same document).
        specific_focal_seen = any(
            e.enum_value in (
                SeizureType.FOCAL_AWARE.value,
                SeizureType.FOCAL_IMPAIRED_AWARENESS.value,
            )
            for e in cands
        )
        if specific_focal_seen:
            for e in cands:
                if e.enum_value in (
                    SeizureType.FOCAL_AWARE.value,
                    SeizureType.FOCAL_IMPAIRED_AWARENESS.value,
                ):
                    return e
        # Fall through: first candidate in document order.
        return cands[0]

    # ------------------------------------------------------------------

    def _compose_fbtc(
        self,
        cands: list[LinkedEntity],
        doc,
    ) -> Optional[tuple[LinkedEntity, str]]:
        """Detect focal-to-bilateral-TC composition.

        Trigger conditions:
        1. An entity already labelled FBTC exists → return it directly.
        2. A focal-onset entity + a GTC entity are within 2 sentences of
           each other AND the enclosing text contains a focal-onset marker
           (e.g. "secondarily generalised", "focal-to-bilateral") AND no
           terminator word appears between them.
        """
        # Case 1 — pre-labelled FBTC.
        for e in cands:
            if e.enum_value == SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC.value:
                return e, e.sentence_text or e.text

        focal_ents = [
            e for e in cands
            if _is_focal(SeizureType(e.enum_value))
        ]
        gtc_ents = [
            e for e in cands
            if _is_generalized_tonic_clonic(SeizureType(e.enum_value))
        ]
        if not focal_ents or not gtc_ents:
            return None

        # Only fire composition if the surface text supports it — the
        # ExECT seizurechange rules always required either an explicit
        # "focal-to-bilateral" trigger or a "secondarily generalised" phrase.
        doc_text = getattr(doc, "text", "") or ""
        if not _FOCAL_ONSET_MARKERS.search(doc_text):
            return None

        # Sentence-proximity + no-terminator check.
        for f in focal_ents:
            for g in gtc_ents:
                lo = min(f.char_start, g.char_start)
                hi = max(f.char_end, g.char_end)
                between = doc_text[lo:hi]
                if _TERMINATOR.search(between):
                    continue
                # Distance heuristic: cap at 400 chars ≈ 2 clinical sentences.
                if hi - lo > 400:
                    continue
                # Return the focal entity as the anchor with combined
                # evidence text spanning the composition.
                return f, between.strip() or f.text
        return None


# ---------------------------------------------------------------------------
# Rule 2 — Other (secondary) seizure types
# ---------------------------------------------------------------------------


class OtherSeizureTypesRule(BaseFieldRule):
    """Populate ``clinical_seizure.other_seizure_types`` list.

    Emits one :class:`Evidence` entry per *distinct* SeizureType detected
    in the document that isn't the predominant type. Uses the same
    predominant-selection logic as :class:`PredominantSeizureTypeRule` to
    identify what to exclude, so the two rules stay in agreement.
    """

    field_name = "clinical_seizure.other_seizure_types"
    enum_class = SeizureType

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[list[Evidence]]:
        cands = self.relevant_entities(entities, include_hypothetical=True)
        cands = [e for e in cands if e.enum_value != SeizureType.UNCLASSIFIED.value]

        # Regex fallback (mirrors PredominantSeizureTypeRule).
        text = getattr(doc, "text", "") or ""
        seen_values = {e.enum_value for e in cands}
        for st, cs, ce, quote in _fallback_seizure_matches(text):
            if st.value in seen_values:
                continue
            synth = LinkedEntity(
                text=quote, cui="", sctid=None, label=st.value,
                enum_class="SeizureType", enum_value=st.value,
                char_start=cs, char_end=ce, confidence=0.7,
                linker_tier="fallback_regex",
                sentence_text="", sentence_start=-1,
            )
            cands.append(synth)
            seen_values.add(st.value)
        cands.sort(key=lambda e: e.char_start)

        if len(cands) < 2:
            return None

        # Identify the predominant using the same picker (delegation keeps
        # the two rules in lockstep).
        predom_rule = PredominantSeizureTypeRule()
        fbtc = predom_rule._compose_fbtc(cands, doc)
        predom = None
        if fbtc is not None:
            predom = SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC.value
        else:
            picked = predom_rule._pick_predominant(cands)
            predom = picked.enum_value if picked else None

        seen: set[str] = set()
        out: list[Evidence] = []

        # Determine the set of specific types present so we can suppress
        # less-specific parents. (Phase 8 Iter 2)
        cand_values = {e.enum_value for e in cands}
        subsume_hits: set[str] = set()
        for parent, specifics in _SUBSUMES.items():
            if parent in cand_values and (cand_values & specifics):
                subsume_hits.add(parent)

        # Batch A D5 (revised): retained the Phase 8 Iter 2 strict gate
        # after a relaxation experiment added 2 FPs on F-S EA0161 and
        # EA0183 without any TPs. F-S 40 gold uses unusual conventions
        # for `other_seizure_types` (duplicate predominant entries;
        # `unknown_onset_tonic_clonic` as a secondary when a specific
        # type is already predominant) that a rule-based system cannot
        # reproduce without over-generating. See docs/MedCAT.md §12.
        for e in cands:
            if e.enum_value == predom:
                continue
            if e.enum_value in seen:
                continue
            try:
                value = SeizureType(e.enum_value)
            except ValueError:
                continue
            # Suppress parent types when a more specific subtype is also
            # present in the doc.
            if e.enum_value in subsume_hits and e.enum_value != predom:
                continue
            sent = e.sentence_text or ""
            has_secondary_marker = bool(_SECONDARY_MARKERS.search(sent))
            if not has_secondary_marker:
                continue
            seen.add(e.enum_value)
            out.append(self._make_evidence(value, e, meta))
        return out or None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(PredominantSeizureTypeRule())
register_rule(OtherSeizureTypesRule())


__all__ = ["PredominantSeizureTypeRule", "OtherSeizureTypesRule"]
