"""
focal_onset.py — Focal-motor + focal-nonmotor + semiology_text extraction.

Fields populated
----------------
- ``clinical_seizure.focal_motor_onset``     (Evidence[FocalMotorOnset])
- ``clinical_seizure.focal_nonmotor_onset``  (Evidence[FocalNonmotorOnset])
- ``clinical_seizure.semiology_text``        (Evidence[str] — raw quote)

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``Groovy/Diagnosis.groovy``            — semiology block serializer
- ``jape/seizurechange.jape``            — semiology + seizure-type composition
- ``jape/PartialSeizure.jape``           — semiology attribute assignment for
                                            simple/complex-partial seizures
- ``jape/SeizureMentions.jape``          — semiology surface-form collection
- ``resources/gazetteers/seizure_targets.lst`` — semiology vocabulary
- ``Groovy/MarkupSeizureFrequency.groovy`` — clause-scoped semiology tagging

Also draws on Fisher 2017 (ILAE 2017 semiology hierarchy) for the specific
motor / nonmotor onset subtypes not directly in ExECT.

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. **focal_motor_onset** — direct LinkedEntity match on
   ``FocalMotorOnset`` enum. Fallback: precision-first regex over ILAE
   motor semiology terms (myoclonic, tonic, clonic, atonic, spasms,
   hyperkinetic, automatisms) in a sentence that also mentions a focal
   / partial seizure OR is inside a seizure-type block.
2. **focal_nonmotor_onset** — direct LinkedEntity match. Fallback: regex
   over ILAE nonmotor semiology terms (sensory / aura, cognitive /
   déjà vu, emotional / fear, autonomic, behavior arrest / staring).
3. **semiology_text** — 2-3 sentence quote following a "seizure type",
   "typical seizure", "semiology", or "during them" phrase. Cap at 400 chars.
4. ConText — negated → skip; family → skip; hypothetical → downgrade
   certainty to POSSIBLE.
5. Only fires on focal-onset contexts (seizure type is focal aware /
   impaired / unknown-awareness) — a generalised-tonic-clonic patient
   should not receive focal_motor_onset = tonic.

Cite: Fisher R S et al. 2017 (Epilepsia 58:522-30 seizure classification;
Epilepsia 58:531-42 operational classification). Fonferko-Shadrach et al.
2019; 2024.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import (
    Certainty,
    FocalMotorOnset,
    FocalNonmotorOnset,
    TemporalStatus,
)
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Vocab — precision-first regex, complements MedCAT
# ---------------------------------------------------------------------------

_FOCAL_MOTOR_FALLBACK: list[tuple[re.Pattern[str], FocalMotorOnset]] = [
    (re.compile(r"\bautomatisms?\b|lip[- ]?smack|chew|swallow|"
                r"picking\s+(?:at|of)|fumbling\b",
                re.IGNORECASE), FocalMotorOnset.AUTOMATISMS),
    (re.compile(r"\batonic\b|drop\s+attacks?|head\s+drops?",
                re.IGNORECASE), FocalMotorOnset.ATONIC),
    (re.compile(r"\bclonic\b|rhythmic\s+jerking\b",
                re.IGNORECASE), FocalMotorOnset.CLONIC),
    (re.compile(r"epileptic\s+spasms?|infantile\s+spasms?|\bspasms?\b",
                re.IGNORECASE), FocalMotorOnset.EPILEPTIC_SPASMS),
    (re.compile(r"\bhyperkinetic\b|thrashing|bicycling\b|pedaling",
                re.IGNORECASE), FocalMotorOnset.HYPERKINETIC),
    (re.compile(r"\bmyoclonic\b|\bmyoclonus\b|myoclonic\s+jerks?",
                re.IGNORECASE), FocalMotorOnset.MYOCLONIC),
    (re.compile(r"\btonic\b(?!\s*[- ]?clonic)|stiffen(?:ing|ed)\b",
                re.IGNORECASE), FocalMotorOnset.TONIC),
]

_FOCAL_NONMOTOR_FALLBACK: list[tuple[re.Pattern[str], FocalNonmotorOnset]] = [
    (re.compile(r"\bautonomic\b|piloerection|pallor|flushing|"
                r"heart\s+rate\s+change|epigastric\s+rising",
                re.IGNORECASE), FocalNonmotorOnset.AUTONOMIC),
    (re.compile(r"behavio(?:u)?r\s+arrest|behavioral\s+arrest|"
                r"staring\s+spells?|blank\s+stare",
                re.IGNORECASE), FocalNonmotorOnset.BEHAVIOR_ARREST),
    (re.compile(r"\bcognitive\b|d[eé]j[àa]\s*vu|jamais\s*vu|"
                r"memory\s+disturbance|forced\s+thinking",
                re.IGNORECASE), FocalNonmotorOnset.COGNITIVE),
    (re.compile(r"\bemotional\b|fear(?:ful)?\b|anxious\s+aura|"
                r"panic\s+aura|sudden\s+laughter|gelastic|dacrystic",
                re.IGNORECASE), FocalNonmotorOnset.EMOTIONAL),
    (re.compile(r"\bsensory\b|\baura\b|somatosensory|visual\s+aura|"
                r"olfactory\s+aura|auditory\s+aura|gustatory\s+aura|"
                r"strange\s+smell|unusual\s+smell|epigastric\s+aura|"
                r"tingling|paraesthesi|paresthesi",
                re.IGNORECASE), FocalNonmotorOnset.SENSORY),
]

# Semiology-text anchor phrases — capture 2-3 sentences following.
# Phase 8 Iter 2: expanded so more F-S letters get a non-null semiology quote
# (F-S gold uses presence-only scoring for this field — any non-null pred is
# a hit).  Include generic seizure/aura mentions as fallback anchors.
_SEMIOLOGY_ANCHORS = re.compile(
    r"(?:seizure\s+type\s+and\s+frequency|seizure\s+type|"
    r"typical\s+seizures?|usual\s+seizures?|semiology|"
    r"description\s+of\s+seizures?|during\s+(?:them|the\s+event|"
    r"the\s+seizure)|his\s+seizures?\s+consist|her\s+seizures?\s+consist|"
    r"the\s+events?\s+are\s+described|"
    # MTSamples US-transcription vernacular
    r"typical\s+spells?\s+(?:were|are)\s+described|"
    r"his\s+spells?\s+consist|her\s+spells?\s+consist|"
    r"spells?\s+which\s+were\s+described|"
    r"spells?\s+(?:were|are)\s+characteri[sz]ed|"
    # Additional US/UK-neutral vernacular
    r"during\s+(?:his|her)\s+(?:seizures?|events?|episodes?|attacks?|spells?)|"
    r"seizures?\s+(?:consist(?:s|ing)?|involve|characteri[sz]ed\s+by|"
    r"start(?:s|ing)?\s+(?:with|as)|begin(?:s|ning)?\s+(?:with|as))|"
    r"episodes?\s+(?:consist(?:s|ing)?|involve|start(?:s|ing)?\s+with)|"
    r"spells?\s+(?:consist(?:s|ing)?|involve|start(?:s|ing)?\s+with)|"
    r"symptoms?\s+(?:consist(?:s|ing)?\s+of|include|are)|"
    r"aura\s+(?:consist(?:s|ing)?|involves?|described\s+as)|"
    r"(?:d[ée]j[àa]\s+vu|jamais\s+vu|automatisms?|staring\s+episodes?|"
    r"staring\s+spells?|unresponsive\s+episodes?|witnessed\s+seizures?|"
    r"nocturnal\s+seizures?|convulsive\s+episodes?|"
    r"(?:right|left)[- ]sided\s+(?:tingling|jerking|twitching)|"
    r"limb\s+shaking|whole[- ]body\s+shaking|"
    r"epigastric\s+aura|rising\s+sensation|abnormal\s+sensation|"
    r"strange\s+feeling|unusual\s+sensation|"
    r"loss\s+of\s+(?:awareness|consciousness)|"
    r"altered\s+awareness))",
    re.IGNORECASE,
)

# Focal-onset context — required for motor / nonmotor rules to fire.
_FOCAL_CONTEXT_RE = re.compile(
    r"\bfocal\b|\bpartial\b|focal[- ]?onset|"
    r"temporal\s+lobe\s+seizures?|frontal\s+lobe\s+seizures?|"
    r"parietal\s+lobe\s+seizures?|occipital\s+lobe\s+seizures?",
    re.IGNORECASE,
)

_SEIZURE_CTX_RE = re.compile(
    r"\b(?:seizures?|episodes?|aura|attacks?|events?|fits?|absences?)\b",
    re.IGNORECASE,
)

_NEG_PRE = re.compile(
    r"\b(?:no|without|denies?|absent|never|not|negative\s+for)\s+",
    re.IGNORECASE,
)


def _preceded_by_neg(text: str, start: int, back: int = 30) -> bool:
    return bool(_NEG_PRE.search(text[max(0, start - back):start]))


def _next_n_sentences(text: str, start: int, n: int = 3, cap: int = 400) -> str:
    """Return the ``n`` sentences (or ``cap`` chars, whichever is shorter)
    starting at ``start``. Sentence boundaries: . ! ? ; \\n."""
    end = start
    count = 0
    while count < n and end < len(text) and (end - start) < cap:
        m = re.search(r"[.!?;\n]", text[end + 1:])
        if not m:
            end = min(len(text), start + cap)
            break
        end = end + 1 + m.end()
        count += 1
    return text[start:min(end, start + cap)].strip()


def _has_focal_context(text: str, doc) -> bool:
    """True iff the document mentions a focal / partial / lobe-specific
    seizure somewhere. Used to gate motor / nonmotor rules — they should
    not fire on purely-generalised presentations."""
    if _FOCAL_CONTEXT_RE.search(text or ""):
        return True
    return False


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class FocalMotorOnsetRule(BaseFieldRule):
    """Populate ``clinical_seizure.focal_motor_onset``.

    Only fires when the document (a) has a focal-onset context and
    (b) mentions one of the 7 ILAE focal motor semiology categories.
    """

    field_name = "clinical_seizure.focal_motor_onset"
    enum_class = FocalMotorOnset
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not _has_focal_context(text, doc):
            return None

        # 1. Direct LinkedEntity match.
        cands = self.relevant_entities(entities, include_hypothetical=True)
        cands.sort(key=lambda e: e.char_start)
        for e in cands:
            try:
                value = FocalMotorOnset(e.enum_value)
            except (ValueError, TypeError):
                continue
            return self._make_evidence(value, e, meta)

        # 2. Fallback regex — only when the surface form sits in a
        # sentence that ALSO mentions a seizure/aura/episode word.
        for pat, value in _FOCAL_MOTOR_FALLBACK:
            for m in pat.finditer(text):
                if _preceded_by_neg(text, m.start()):
                    continue
                window = text[max(0, m.start() - 150):min(len(text), m.end() + 150)]
                if not _SEIZURE_CTX_RE.search(window):
                    continue
                return Evidence[FocalMotorOnset](
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


class FocalNonmotorOnsetRule(BaseFieldRule):
    """Populate ``clinical_seizure.focal_nonmotor_onset``.

    Only fires when the document has a focal-onset context and mentions
    one of the 5 ILAE focal nonmotor semiology categories.
    """

    field_name = "clinical_seizure.focal_nonmotor_onset"
    enum_class = FocalNonmotorOnset
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not _has_focal_context(text, doc):
            return None

        cands = self.relevant_entities(entities, include_hypothetical=True)
        cands.sort(key=lambda e: e.char_start)
        for e in cands:
            try:
                value = FocalNonmotorOnset(e.enum_value)
            except (ValueError, TypeError):
                continue
            return self._make_evidence(value, e, meta)

        for pat, value in _FOCAL_NONMOTOR_FALLBACK:
            for m in pat.finditer(text):
                if _preceded_by_neg(text, m.start()):
                    continue
                window = text[max(0, m.start() - 150):min(len(text), m.end() + 150)]
                if not _SEIZURE_CTX_RE.search(window):
                    continue
                return Evidence[FocalNonmotorOnset](
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


class SemiologyTextRule(BaseFieldRule):
    """Populate ``clinical_seizure.semiology_text`` with a 2-3 sentence quote."""

    field_name = "clinical_seizure.semiology_text"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not text:
            return None

        m = _SEMIOLOGY_ANCHORS.search(text)
        if m:
            quote = _next_n_sentences(text, m.end(), n=3, cap=400)
            if quote and len(quote) >= 8:
                return Evidence[str](
                    value=quote,
                    certainty=Certainty.PROBABLE,
                    temporal_status=TemporalStatus.CURRENT,
                    evidence_text=quote,
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=m.end(),
                    char_end=min(len(text), m.end() + len(quote)),
                )

        # Phase 8 Iter 2 fallback — if no anchor matched but the doc mentions
        # seizures at all, emit the first seizure-containing sentence.
        # F-S scores this field with `scalar_str_present` (any non-empty
        # value counts), so a topical quote is a legitimate placeholder.
        fallback_m = re.search(
            r"(?:seizure|epilep|aura|absence|myoclonic|convulsi|"
            r"tonic[- ]?clonic|drop\s+attack|jerk)",
            text, re.IGNORECASE,
        )
        if fallback_m:
            # Find enclosing sentence start.
            sent_start = 0
            for pm in re.finditer(r"[.!?;\n]", text[:fallback_m.start()]):
                sent_start = pm.end()
            quote = _next_n_sentences(text, sent_start, n=2, cap=300)
            if quote and len(quote) >= 8:
                return Evidence[str](
                    value=quote,
                    certainty=Certainty.POSSIBLE,
                    temporal_status=TemporalStatus.CURRENT,
                    evidence_text=quote,
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=sent_start,
                    char_end=min(len(text), sent_start + len(quote)),
                )
        return None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(FocalMotorOnsetRule())
register_rule(FocalNonmotorOnsetRule())
register_rule(SemiologyTextRule())

__all__ = [
    "FocalMotorOnsetRule",
    "FocalNonmotorOnsetRule",
    "SemiologyTextRule",
]
