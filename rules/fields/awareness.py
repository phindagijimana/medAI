"""
awareness.py — Awareness (aware / impaired / unknown) extraction.

Fields populated
----------------
- ``clinical_seizure.awareness``  (Evidence[Awareness])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/seizurechange.jape``            — ILAE 2017 renaming of "simple/complex
                                            partial" → "focal-with/without impaired
                                            awareness"; encodes the awareness
                                            attribute of the current seizure.
- ``Groovy/Diagnosis.groovy``            — serializer that emits an Awareness
                                            slot alongside seizure type.
- ``jape/PartialSeizure.jape``           — simple/complex-partial fold-in.
- ``resources/gazetteers/seizure_targets.lst`` — awareness surface forms.

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. Direct match: any non-negated, non-family LinkedEntity with
   ``enum_class == "Awareness"`` is a candidate.
2. Sentence context: awareness terms outside a seizure/consciousness
   sentence are ignored (e.g. an "aware" that means socially aware).
3. Predominant selection: the FIRST awareness mention in document order
   wins (matches ExECT ``Diagnosis.groovy`` ordering).
4. ConText — negated → skip; family (mother/father) → skip;
   hypothetical → downgrade certainty to POSSIBLE; historical → keep
   but temporal_status='historical'.
5. Fallback regex: recognises common surface forms if MedCAT missed
   them (e.g. "loss of awareness", "retained awareness", "impaired
   consciousness").

Cite: Fisher R S et al. 2017 (Epilepsia 58:522-30, ILAE 2017 seizure
classification). Fonferko-Shadrach et al. 2019; 2024.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import Awareness, Certainty, TemporalStatus
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Sentence-context patterns
# ---------------------------------------------------------------------------

# An Awareness mention only counts when its sentence also references a
# seizure / consciousness event (per ExECT `PartialSeizure` guard).
_SEIZURE_CONTEXT_RE = re.compile(
    r"\b(?:seizures?|episodes?|attacks?|events?|fits?|convulsions?|"
    r"consciousness|awareness|LOC|blackouts?|absences?|aura)\b",
    re.IGNORECASE,
)

# Fallback surface-form → Awareness mapping (specificity descending).
_FALLBACK_AWARENESS: list[tuple[re.Pattern[str], Awareness]] = [
    (re.compile(
        r"(?:loss\s+of|impaired|altered|reduced|decreased|clouded)\s+"
        r"(?:awareness|consciousness)|\bLOC\b|\bunresponsive\b|"
        r"unaware\b|blank\s+stare|lost\s+consciousness",
        re.IGNORECASE), Awareness.IMPAIRED),
    (re.compile(
        r"(?:retained|preserved|fully|intact)\s+(?:awareness|consciousness)|"
        r"remain(?:ed|s)\s+(?:aware|conscious)|awareness\s+preserved|"
        r"consciousness\s+preserved|conscious\s+throughout",
        re.IGNORECASE), Awareness.AWARE),
    (re.compile(
        r"awareness\s+(?:unknown|unclear|not\s+documented|"
        r"not\s+specified|cannot\s+be\s+determined)",
        re.IGNORECASE), Awareness.UNKNOWN),
]


_NEG_PRE = re.compile(
    r"\b(?:no|without|denies?|absent|not|never|negative\s+for)\s+",
    re.IGNORECASE,
)


def _preceded_by_neg(text: str, start: int, back: int = 30) -> bool:
    return bool(_NEG_PRE.search(text[max(0, start - back):start]))


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class AwarenessRule(BaseFieldRule):
    """Populate ``clinical_seizure.awareness``.

    Trivial emitter — the Awareness LinkedEntity already comes from
    :mod:`services.medcat_extractor`; this rule just picks the earliest
    in-context mention, applies ConText, and wraps it in Evidence.
    """

    field_name = "clinical_seizure.awareness"
    enum_class = Awareness
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        cands = self.relevant_entities(entities, include_hypothetical=True)

        # Sort by char_start to pick the earliest mention.
        cands.sort(key=lambda e: e.char_start)

        for e in cands:
            # Only apply the sentence-context guard when we have a
            # sentence — an entity whose ConText attachment failed keeps
            # sentence_text="" and would otherwise always be rejected.
            if e.sentence_text and not _SEIZURE_CONTEXT_RE.search(e.sentence_text):
                # Awareness word outside a seizure/consciousness sentence
                # is almost always a false positive ("she was aware of
                # her rights"). Skip.
                continue
            try:
                value = Awareness(e.enum_value)
            except (ValueError, TypeError):
                continue
            return self._make_evidence(value, e, meta)

        # Regex fallback — only fires if MedCAT missed the surface form.
        text = getattr(doc, "text", "") or ""
        for pat, value in _FALLBACK_AWARENESS:
            for m in pat.finditer(text):
                if _preceded_by_neg(text, m.start()):
                    continue
                # Sentence-context guard (rough): ± 200 chars must contain
                # a seizure/consciousness word.
                window = text[max(0, m.start() - 200):min(len(text), m.end() + 200)]
                if not _SEIZURE_CONTEXT_RE.search(window):
                    continue
                return Evidence[Awareness](
                    value=value,
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


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(AwarenessRule())

__all__ = ["AwarenessRule"]
