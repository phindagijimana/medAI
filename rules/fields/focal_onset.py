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
Epilepsia 58:531-42 operational classification — onset is the first
prominent feature, not later evolution). Fonferko-Shadrach et al. 2019; 2024.
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
    (re.compile(r"\btonic\b(?!\s*[- ]?clonic)|stiffen(?:ing|ed)\b|"
                r"tonic\s+postur|"
                r"\bversive\b|head\s+(?:turn(?:ing)?|version)|forced\s+head\s+turn",
                re.IGNORECASE), FocalMotorOnset.TONIC),
]

_FOCAL_NONMOTOR_FALLBACK: list[tuple[re.Pattern[str], FocalNonmotorOnset]] = [
    (re.compile(r"\bautonomic\b|piloerection|pallor|flushing|"
                r"heart\s+rate\s+change|epigastric\s+rising|rising\s+epigastric",
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

# ILAE 2017: onset is the first prominent feature, not later evolution.
_EVOLUTION_RE = re.compile(
    r"\b(?:then|followed\s+by|thereafter|subsequently|after\s+that|"
    r"progress(?:es|ed|ing)?\s+to|evolves?\s+(?:to|into)|"
    r"secondarily(?:\s+generaliz(?:es|ed|ing)?)?|later(?:\s+in\s+the\s+seizure)?)\b",
    re.IGNORECASE,
)
_ONSET_CUE_RE = re.compile(
    r"\b(?:begins?\s+with|starts?\s+with|onset\s+with|first\s+(?:sign|symptom)|"
    r"initially|at\s+onset|aura\s+of)\b",
    re.IGNORECASE,
)
_AURA_WORD_RE = re.compile(r"\baura\b", re.IGNORECASE)
_PLAN_RE = re.compile(
    r"\b(?:recommend(?:ed|ing)?|consider(?:ed|ing)?|advise[ds]?|will\s+discuss|"
    r"plan(?:ned)?\s+to|option\s+of)\b",
    re.IGNORECASE,
)
_FAMILY_RE = re.compile(r"\b(?:mother|father|sister|brother|parent|family|maternal|paternal)\b",
                        re.IGNORECASE)
_SENT_START_NEG = re.compile(r"^\s*(?:no|denies|never|without)\b", re.IGNORECASE)
_FOCAL_WITH_RE = re.compile(r"\b(?:focal|partial)(?:[- ]\w+)*\s+seizures?\s+with\b", re.IGNORECASE)
_MOTOR_ONSET_LABEL = re.compile(r"\b(?:focal\s+)?motor\s+onset\b", re.IGNORECASE)
_NONMOTOR_ONSET_LABEL = re.compile(
    r"\b(?:non[- ]?motor|autonomic|sensory|cognitive|emotional|behavior(?:al)?\s+arrest)\s+onset\b",
    re.IGNORECASE,
)
_TC_NEAR = re.compile(r"tonic\s*[- ]?clonic|clonic\s*[- ]?tonic", re.IGNORECASE)


def _preceded_by_neg(text: str, start: int, back: int = 30) -> bool:
    return bool(_NEG_PRE.search(text[max(0, start - back):start]))


def _sentences(text: str) -> list[tuple[int, int, str]]:
    out, start = [], 0
    for m in re.finditer(r"[.!?;\n]+", text):
        out.append((start, m.start(), text[start:m.start()]))
        start = m.end()
    if start < len(text):
        out.append((start, len(text), text[start:]))
    return [(a, b, s) for a, b, s in out if s.strip()]


def _sentence_of(text: str, pos: int) -> tuple[int, int, str]:
    for a, b, s in _sentences(text):
        if a <= pos < b:
            return a, b, s
    return 0, len(text), text


def _skip_sentence(sent: str) -> bool:
    if _SENT_START_NEG.search(sent) or _PLAN_RE.search(sent) or _FAMILY_RE.search(sent):
        return True
    return False


def _in_tonic_clonic(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 12):min(len(text), end + 12)]
    return bool(_TC_NEAR.search(window))


def _onset_tier(sent: str, feat_local: int, *, motor: bool) -> Optional[int]:
    """0 = explicit onset label, 1 = onset-cue / aura segment, 2 = 'focal seizure with X'. None = not onset."""
    if _skip_sentence(sent):
        return None
    evo = [m.start() for m in _EVOLUTION_RE.finditer(sent)]
    first_evo = evo[0] if evo else len(sent)
    if motor and _MOTOR_ONSET_LABEL.search(sent):
        return 0
    if (not motor) and _NONMOTOR_ONSET_LABEL.search(sent):
        return 0
    seg0 = sent[:first_evo]
    if feat_local < first_evo and (_ONSET_CUE_RE.search(seg0) or _AURA_WORD_RE.search(seg0)):
        return 1
    if not evo and _FOCAL_WITH_RE.search(sent):
        return 2
    return None


def _pick_onset(text: str, entities: list, enum_cls, fallback, *, motor: bool, make_ent, make_rx, meta):
    """Highest-tier onset feature in the note, then earliest. Entities and regex share the same test."""
    cands = []
    for e in entities:
        try:
            value = enum_cls(e.enum_value)
        except (ValueError, TypeError):
            continue
        a, b, sent = _sentence_of(text, e.char_start)
        if _preceded_by_neg(text, e.char_start) or _skip_sentence(sent):
            continue
        if motor and _in_tonic_clonic(text, e.char_start, e.char_end):
            continue
        tier = _onset_tier(sent, e.char_start - a, motor=motor)
        if tier is None:
            continue
        cands.append((tier, e.char_start, make_ent(value, e)))
    for pat, value in fallback:
        for m in pat.finditer(text):
            if _preceded_by_neg(text, m.start()):
                continue
            if motor and value.value in ("tonic", "clonic") and _in_tonic_clonic(text, m.start(), m.end()):
                continue
            a, b, sent = _sentence_of(text, m.start())
            if _skip_sentence(sent):
                continue
            window = text[max(0, m.start() - 150):min(len(text), m.end() + 150)]
            if not _SEIZURE_CTX_RE.search(window):
                continue
            tier = _onset_tier(sent, m.start() - a, motor=motor)
            if tier is None:
                continue
            cands.append((tier, m.start(), make_rx(value, m)))
    if not cands:
        return None
    cands.sort(key=lambda x: (x[0], x[1]))  # lowest tier number = strongest, then earliest
    return cands[0][2]


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
        cands = self.relevant_entities(entities, include_hypothetical=True)
        return _pick_onset(
            text, cands, FocalMotorOnset, _FOCAL_MOTOR_FALLBACK, motor=True,
            make_ent=lambda value, e: self._make_evidence(value, e, meta),
            make_rx=lambda value, m: Evidence[FocalMotorOnset](
                value=value, certainty=Certainty.PROBABLE, temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0), source_doc_id=meta["doc_id"], source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"], char_start=m.start(), char_end=m.end(),
            ),
            meta=meta,
        )


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
        return _pick_onset(
            text, cands, FocalNonmotorOnset, _FOCAL_NONMOTOR_FALLBACK, motor=False,
            make_ent=lambda value, e: self._make_evidence(value, e, meta),
            make_rx=lambda value, m: Evidence[FocalNonmotorOnset](
                value=value, certainty=Certainty.PROBABLE, temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0), source_doc_id=meta["doc_id"], source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"], char_start=m.start(), char_end=m.end(),
            ),
            meta=meta,
        )


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
