"""
medication.py — Medication list extraction (ASMs; current / prior / failed).

Fields populated
----------------
- ``medication.current_asms``  (list[Evidence[Medication]])
- ``medication.prior_asms``    (list[Evidence[Medication]])
- ``medication.failed_asms``   (list[Evidence[Medication]])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/prescription.jape`` / ``prescription2.jape`` — canonical DRUG DOSE FREQ
- ``jape/prescriptionSentence.jape``      — sentence-scope guard
- ``jape/PrescriptionEpilepsy.jape``      — only ASMs (not e.g. paracetamol)
- ``jape/prescriptionFilter*.jape`` (5 files) — pseudo-negation exclusions
- ``jape/prescription-implicit.jape``     — "still on X" / "continue X"
- ``jape/prescription-coref.jape``        — pronoun-anaphoric "he takes it"
- ``jape/prescription-indicator.jape``    — dose-change indicators
- ``jape/PrescriptionML.jape`` / ``PrescriptionMLCreated.jape`` — ML-derived
                                            prescription spans (we skip; no ML)
- ``jape/KeepPrescription.jape`` / ``KeepPrescriptionInText.jape`` — coref keep
- ``jape/dose-change.jape``               — dose-modification detection
- ``jape/doses.jape`` / ``measurement.jape`` — numeric dose parse
- ``jape/routes.jape``                    — route (PO/IV/IM/…)
- ``jape/DrugPointInTime.jape``           — past/current classifier
- ``jape/LazyPrescription.jape``          — very-relaxed fallback
- ``jape/noMeds.jape``                    — "on no medications" detection
- ``Groovy/Prescription.groovy``          — output serializer
- ``Groovy/PrescriptionJson.groovy``      — JSON serializer

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. Anchor: every LinkedEntity with ``enum_class == "Medication"`` (from the
   ontology's ASM list).
2. Dose text: regex over ± 60 char window: ``NUMBER + mg|g|mcg|units +
   [BID|TID|QID|OD|BD|qds|nocte|mane|once|twice|three times|daily]``.
3. Status inference (sentence-scoped, matches ExECT DrugPointInTime):
     - "was on / used to take / previously / stopped / discontinued" → prior
     - "failed / did not respond / ineffective / not tolerated" → failed
     - "rash / adverse / side effect / allergic" → discontinued_adverse_effect
     - default → current
   These sentence statuses fill the prior / failed lists.
4. Current at the visit (``current_asms``): each mention is classed from its
   clause — stop (stopped, discontinued, weaned off, switched from), planned
   (object of a start cue: "please start X", "X to start"), past (weak past
   cue only: "previously", "in the past", "tried"), current (ongoing cue:
   taking, continue, reduce, switching from, switched from A *to* X) or bare
   (no cue).  Per drug: current if it has a current or bare mention and no
   stop after the last one; bare mentions after a planned one do not count.
   Weak past cues never remove a drug the letter lists as taken.  One entry
   per drug.
5. Extra surface forms (``rules/asm_surface.py``): standard abbreviations
   (LEV, CBZ, LTG, LCM, VPA, ...) and misspellings within 1-2 letters
   ("volproate", "Pregablin").
6. Deduplication: prior / failed — same generic_name + same status → keep
   first evidence.
7. ConText — negated → skip; family → skip; hypothetical → certainty POSSIBLE.

Cite: Fonferko-Shadrach et al. 2019; 2024. Drug list per RxNorm
(``rxnorm:2026-09-08``) + leftover US FDA brands in
``rules/asm_us_brand_aliases.py``. Status cues: Uzuner et al. 2010 (i2b2
current / discontinued / suggested); Chapman 2001 NegEx lineage.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.asm_lexicon import ASM_LEXICON
from rules.asm_us_brand_aliases import US_ASM_BRAND_ALIASES, leftover_brand_matches
from rules.base_rule import BaseFieldRule
from schema.enums import Certainty, MedicationStatus, TemporalStatus
from schema.evidence import Evidence
from schema.ontology import Medication
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Drug-name canonicalization (Phase 8, Iter 1)
# ---------------------------------------------------------------------------
# F-S gold uses collapsed lowercase strings ("sodiumvalproate", "brivitiracetam",
# "carbamazapine"), while synth-v1 gold uses shorter forms ("valproate"),
# and our ontology emits underscored ("sodium_valproate").  A single canonical
# key isn't possible without touching either corpus, so we emit a *primary*
# key that matches F-S convention (collapsed alphabetic lowercase) and also
# provides a look-up map for the scorer to canonicalize both sides at compare
# time.
#
# See ``scripts/score_medcat_vs_gold.py::_canonicalize_drug_name``.
_DRUG_NAME_CANONICAL: dict[str, str] = {
    # our_output_lower              → F-S primary key
    "sodium_valproate":     "sodiumvalproate",
    "sodium valproate":     "sodiumvalproate",
    "valproate":            "sodiumvalproate",
    "valproic acid":        "sodiumvalproate",
    "divalproex":           "sodiumvalproate",
    "depakote":             "sodiumvalproate",
    "depakene":             "sodiumvalproate",
    "stavzor":              "sodiumvalproate",
    "epilim":               "sodiumvalproate",
    "brivaracetam":         "brivaracetam",
    "brivetiracetam":       "brivaracetam",   # common misspelling / F-S "brivitiracetam"
    "brivitiracetam":       "brivaracetam",   # F-S spelling
    "briviact":             "brivaracetam",
    "carbamazepine":        "carbamazepine",
    "carbamazapine":        "carbamazepine",  # F-S misspelling variant
    "tegretol":             "carbamazepine",
    "tegretol xr":          "carbamazepine",
    "equetro":              "carbamazepine",
    "carnexiv":             "carbamazepine",
    "carbatrol":            "carbamazepine",
    "oxcarbazepine":        "oxcarbazepine",
    "oxcarbazepin":         "oxcarbazepine",
    "trileptal":            "oxcarbazepine",
    "lamotrigine":          "lamotrigine",
    "lamictal":             "lamotrigine",
    "lamictal xr":          "lamotrigine",
    "lamictal odt":         "lamotrigine",
    "lamotrigin":           "lamotrigine",
    "lamotiringe":          "lamotrigine",   # F-S misspelling
    "levetiracetam":        "levetiracetam",
    "keppra":               "levetiracetam",
    "keppra xr":            "levetiracetam",
    "topiramate":           "topiramate",
    "topamax":              "topiramate",
    "top":                  "topiramate",     # F-S truncation
    "phenytoin":            "phenytoin",
    "dilantin":             "phenytoin",
    "phenobarbital":        "phenobarbital",
    "phenobarbitone":       "phenobarbital",
    "luminal":              "phenobarbital",
    "clobazam":             "clobazam",
    "onfi":                 "clobazam",
    "clonazepam":           "clonazepam",
    "klonopin":             "clonazepam",
    "rivotril":             "clonazepam",
    "zonisamide":           "zonisamide",
    "zonismaide":           "zonisamide",     # F-S misspelling
    "zonegran":             "zonisamide",
    "gabapentin":           "gabapentin",
    "neurontin":            "gabapentin",
    "pregabalin":           "pregabalin",
    "lyrica":               "pregabalin",
    "eslicarbazepine":      "eslicarbazepine",
    "eslicarbazepine acetate": "eslicarbazepine",
    "aptiom":               "eslicarbazepine",
    "zebinix":              "eslicarbazepine",
    "lacosamide":           "lacosamide",
    "vimpat":               "lacosamide",
    "perampanel":           "perampanel",
    "fycompa":              "perampanel",
    "midazolam":            "midazolam",
    "versed":               "midazolam",
    "ethosuximide":         "ethosuximide",
    "zarontin":             "ethosuximide",
    "vigabatrin":           "vigabatrin",
    "sabril":               "vigabatrin",
    "tiagabine":            "tiagabine",
    "gabitril":             "tiagabine",
    "felbamate":            "felbamate",
    "felbatol":             "felbamate",
    "primidone":            "primidone",
    "mysoline":             "primidone",
    "stiripentol":          "stiripentol",
    "diacomit":             "stiripentol",
    "rufinamide":           "rufinamide",
    "banzel":               "rufinamide",
    "inovelon":             "rufinamide",
}


# EEG / EMU procedure tokens the model (and rarely a linker) treats as drug names.
# Cite: ACNS LTM/cEEG (Hirsch 2013). Not ASMs.
_EEG_STUDY_NOT_DRUG = re.compile(
    r"^(?:ltm|veeg|v-?eeg|c-?eeg|ceeg|emu|ecog|s-?eeg|seeg)$",
    re.IGNORECASE,
)


def is_eeg_study_token(name: str) -> bool:
    """True for LTM / VEEG / EMU / cEEG / ECoG / sEEG — studies, not medications."""
    if not name:
        return False
    solid = re.sub(r"[\s\-_]+", "", name.strip().lower())
    return bool(_EEG_STUDY_NOT_DRUG.match(solid))


def canonicalize_drug_name(name: str) -> str:
    """Normalize a drug string to the F-S primary key convention.

    Steps:
    1. Lowercase + strip.
    2. Look up in ``_DRUG_NAME_CANONICAL`` (exact match on lowercased key).
    3. If no match, collapse whitespace / underscores / hyphens and try again.
    4. If still no match, return the collapsed alphabetic lowercase form (this
       is what F-S gold uses for out-of-vocab drugs anyway).
    """
    if not name:
        return ""
    s = name.strip().lower()
    if s in _DRUG_NAME_CANONICAL:
        return _DRUG_NAME_CANONICAL[s]
    if s in US_ASM_BRAND_ALIASES:
        return US_ASM_BRAND_ALIASES[s]
    # try collapsed (no space/underscore/hyphen)
    collapsed = re.sub(r"[\s\-_]+", " ", s).strip()
    if collapsed in _DRUG_NAME_CANONICAL:
        return _DRUG_NAME_CANONICAL[collapsed]
    if collapsed in US_ASM_BRAND_ALIASES:
        return US_ASM_BRAND_ALIASES[collapsed]
    solid = re.sub(r"[\s\-_]+", "", s)
    if solid in _DRUG_NAME_CANONICAL:
        return _DRUG_NAME_CANONICAL[solid]
    if solid in US_ASM_BRAND_ALIASES:
        return US_ASM_BRAND_ALIASES[solid]
    return solid


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_DOSE_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>mg|g|mcg|units?|iu)"
    r"(?:\s+(?P<freq>"
    r"(?:once|twice|thrice|three\s+times|four\s+times|five\s+times)"
    r"\s+(?:a|per|each)\s+(?:day|week|month|hour)"
    r"|(?:daily|twice[- ]daily|nightly)"
    r"|(?:\bbd\b|\bbid\b|\btid\b|\btds\b|\bqds\b|\bqid\b|\bod\b|\bqod\b|"
    r"\bnocte\b|\bmane\b|\bprn\b|\bstat\b|\bam\b|\bpm\b)"
    r"|(?:in\s+the\s+morning|in\s+the\s+afternoon|at\s+night|at\s+bedtime)"
    r"))?",
    re.IGNORECASE,
)


_STATUS_PATTERNS: list[tuple[re.Pattern[str], MedicationStatus]] = [
    # DISCONTINUED_ADVERSE_EFFECT — adverse reaction phrases (goes to prior bucket).
    (re.compile(
        r"\b(rash|adverse|side[- ]effect|allergic|allergy|reaction|"
        r"not\s+tolerated|intolerance|caused\s+mood|"
        r"made\s+(?:his|her|them|his\s+mood|her\s+mood)\s+(?:worse|mood\s+worse)|"
        r"caused\s+(?:mood|depression|weight\s+gain|anxiety|"
        r"teratogenic))\b", re.IGNORECASE),
     MedicationStatus.DISCONTINUED_ADVERSE_EFFECT),
    # FAILED — explicit therapeutic failure.
    (re.compile(
        r"\b(failed|did\s+not\s+respond|inadequate\s+control|ineffective|"
        r"unresponsive\s+to|no\s+response\s+to|"
        r"trialled\s+but\s+ineffective|either\s+ineffective|"
        r"trial\s+of\s+.*\s+(?:failed|unsuccessful)|"
        r"not\s+effective|"
        r"tried\s+.*\s+but\s+(?:it|this|she|he|they)?\s*"
        r"(?:did\s+not\s+work|didn'?t\s+work|had\s+no\s+effect))\b",
        re.IGNORECASE), MedicationStatus.FAILED),
    # PRIOR — historical / discontinued use.
    # NOTE: "switching from" (present/gerund) does NOT go here — during a
    # transition, both drugs are still current per F-S/ILAE convention.
    # Only past-tense "switched from" implies the med is fully discontinued.
    (re.compile(
        r"\b(previous(?:ly)?|prior(?:\s+to)?|past|used\s+to\s+take|"
        r"was\s+on|had\s+been\s+on|has\s+been\s+on|formerly|"
        r"discontinued|withdrawn|weaned\s+off|tapered\s+off|"
        r"d/?c(?:'?d|ed)|dc(?:'?d|ed)|"  # US "d/c'd" / "dc'd" (Uzuner 2010)
        r"no\s+longer\s+taking|off\s+the\s+medication|ceased|"
        r"switched\s+from|"  # past-tense only
        r"of\s+(?:his|her)\s+own\s+accord|"
        r"many\s+years\s+ago|years\s+ago|during\s+childhood|"
        r"in\s+(?:his|her)\s+(?:teens|twenties|thirties)|"
        r"has\s+tried|had\s+tried|having\s+tried|had\s+been\s+tried\s+on|"
        r"she\s+has\s+tried|he\s+has\s+tried|"
        r"she\s+tried|he\s+tried|"
        r"in\s+the\s+past|history\s+of\s+taking|"
        r"(?:was|were|has\s+been|have\s+been)\s+stopped|"
        r"stopped\s+(?:taking|this|the))\b",
        re.IGNORECASE), MedicationStatus.PRIOR),
    (re.compile(
        r"\b(plans?\s+to\s+start|will\s+commence|will\s+start|will\s+begin|"
        r"to\s+be\s+started|going\s+to\s+start|"
        r"planned|proposed|considering|please\s+start|start\s+him\s+on|"
        r"start\s+her\s+on|initiate\s+.*\s+(?:on|with)|"
        r"i\s+would\s+suggest\s+(?:introducing|starting)|"
        r"we\s+will\s+add|adding\s+in|introducing|"
        r"if\s+.*\s+(?:not\s+successful|unsuccessful|fails?)|"
        r"if\s+necessary|"
        r"consider(?:ed)?\s+starting|"
        r"will\s+consider|"
        r"may\s+be\s+considered|"
        r"consider(?:ing|ed)?\s+(?:adding|starting|introducing|using)|"
        r"(?:if|should)\s+(?:she|he|they|there)\s+(?:has|have|be)\s+(?:a\s+)?cluster|"
        r"should\s+there\s+be\s+a\s+cluster|"
        r"in\s+the\s+event\s+of\s+(?:a\s+)?(?:cluster|prolonged\s+seizure))\b",
        re.IGNORECASE),
     MedicationStatus.PLANNED),
]


_SENT_END = re.compile(r"[.!?;\n]")


def _sentence_window(text: str, start: int, end: int) -> str:
    """Return the sentence enclosing ``[start:end]`` — bounded by . ! ? ; \n.

    Kept in-file (not shared with baseline_rules_medication) so the rule
    stays self-contained.
    """
    sent_start = 0
    for m in _SENT_END.finditer(text[:start]):
        sent_start = m.end()
    m = _SENT_END.search(text, end)
    sent_end = m.start() if m else len(text)
    return text[sent_start:sent_end]


def _infer_status(sentence: str) -> MedicationStatus:
    """Sentence-scoped status classifier."""
    for pat, status in _STATUS_PATTERNS:
        if pat.search(sentence):
            return status
    return MedicationStatus.CURRENT


# ---------------------------------------------------------------------------
# "Current at the visit" (mention level, then one decision per drug)
# ---------------------------------------------------------------------------
# A drug is current when the patient is taking it at the visit, including a
# drug continued from the last visit or being tapered / switched away from.
# Not current: stopped, only mentioned in the past, or newly started / planned
# at this visit (F-S gold: "Levetiracetam to start" is not a current ASM).

_CLAUSE_END = re.compile(r"[.!?;\n]|,|\bbut\b|\bwhereas\b|\bhowever\b", re.IGNORECASE)

_STOP_CUE = re.compile(
    r"\b(?:discontinued|discontinue|withdrawn|weaned\s+off|tapered\s+off|"
    r"came\s+off|come\s+off|d/?c(?:'?d|ed)|no\s+longer\s+(?:taking|on)|"
    r"off\s+the\s+medication|ceased|switched\s+from|stopped|stop\s+taking)\b",
    re.IGNORECASE)

_ONGOING_CUE = re.compile(
    r"\b(?:continue[sd]?|continuing|remains?\s+on|still\s+(?:on|taking)|currently|"
    r"now\s+(?:on|taking)|taking|started|commenced|switching\s+from|changing\s+from|"
    r"switched\s+to|changed\s+to|reduc(?:e|ed|ing)|taper(?:ing)?|wean(?:ing)?|"
    r"increas(?:e|ed|ing)|decreas(?:e|ed|ing)|controlled\s+on|is\s+on|are\s+on)\b",
    re.IGNORECASE)

# Drug as the object of a start cue: "please start X", "start him on X", "adding in X".
_PLAN_LEFT = re.compile(
    r"\b(?:start|starting|commence|commencing|introduce|introducing|add|adding(?:\s+in)?|"
    r"initiate|initiating|begin|beginning|try|trying|trial\s+of)"
    r"(?:\s+(?:him|her|them|on|with|a|low|dose|of|the|some|in))*\s+$",
    re.IGNORECASE)
_PLAN_RIGHT = re.compile(
    r"^\W*(?:\d+(?:\.\d+)?\s*mg\W*)?(?:is\s+|will\s+be\s+)?to\s+(?:be\s+)?"
    r"(?:start|commenc|introduc|begin|add)", re.IGNORECASE)
# "switched from X to Y" / "changing from X to Y": Y is current.
_SWITCH_TO_LEFT = re.compile(
    r"\b(?:switch|chang|convert|mov)\w*\s+(?:\w+\s+){0,3}?from\s+[\w\-]+"
    r"(?:\s+\d+\s*mg)?\s+(?:to|onto)\s+$", re.IGNORECASE)

# Linker mentions carry ConText's family flag; scanner mentions use this instead.
# Hypothetical cluster / "may be considered" — not current at this visit (EA0140-style plan;
# "If she has a cluster, use X. Not prescribed yet."). A prescribed rescue the patient
# already takes ("clobazam for clusters; he takes this infrequently") stays current.
_CLUSTER_IF = re.compile(
    r"\b(?:if|should)\s+(?:she|he|they|there)\s+(?:has|have|be)\s+(?:a\s+)?cluster\b|"
    r"\bshould there be a cluster\b|"
    r"\bin the event of\s+(?:a\s+)?(?:cluster|prolonged\s+seizure)\b|"
    r"\bnot prescribed yet\b",
    re.IGNORECASE)
_CONSIDER = re.compile(
    r"\bmay be considered\b|"
    r"\bconsider(?:ing|ed)?\s+(?:adding|starting|introducing|using)\b|"
    r"\bcan also use\b",
    re.IGNORECASE)

_FAMILY_CUE = re.compile(
    r"\b(?:mother|father|brother|sister|son|daughter|uncle|aunt|cousin|"
    r"grand(?:mother|father|parent)s?|sibling|parents?|family\s+history)(?:'s|’s)?\b",
    re.IGNORECASE)

_MENTION_CURRENT = "current"
_MENTION_BARE = "bare"
_MENTION_STOP = "stop"
_MENTION_PLANNED = "planned"
_MENTION_PAST = "past"


def _clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    c_start = 0
    for m in _CLAUSE_END.finditer(text, max(0, start - 300), start):
        c_start = m.end()
    m = _CLAUSE_END.search(text, end)
    return c_start, (m.start() if m else len(text))


def _nearest(pat: re.Pattern[str], text: str, lo: int, hi: int, start: int, end: int) -> Optional[int]:
    best = None
    for m in pat.finditer(text, lo, hi):
        d = start - m.end() if m.end() <= start else max(0, m.start() - end)
        best = d if best is None or d < best else best
    return best


def _mention_class(text: str, start: int, end: int, sentence_status: MedicationStatus,
                   is_hypothetical: bool = False, is_historical: bool = False) -> str:
    """Current / stop / planned / past for one drug mention."""
    c_lo, c_hi = _clause_bounds(text, start, end)
    left, right = text[c_lo:start], text[end:c_hi]
    if _SWITCH_TO_LEFT.search(left[-80:]):
        return _MENTION_CURRENT
    if _PLAN_LEFT.search(left[-40:]) or _PLAN_RIGHT.match(right[:40]):
        return _MENTION_PLANNED
    sent = _sentence_window(text, start, end)
    nxt = text[end: min(len(text), end + 50)]
    if _CLUSTER_IF.search(sent) or _CONSIDER.search(sent) or _CLUSTER_IF.search(nxt):
        return _MENTION_PLANNED
    stop = _nearest(_STOP_CUE, text, c_lo, c_hi, start, end)
    going = _nearest(_ONGOING_CUE, text, c_lo, c_hi, start, end)
    if stop is not None and (going is None or stop <= going):
        return _MENTION_STOP
    if going is not None:
        return _MENTION_CURRENT
    if sentence_status in (MedicationStatus.PRIOR, MedicationStatus.FAILED,
                           MedicationStatus.DISCONTINUED_ADVERSE_EFFECT) or is_historical:
        return _MENTION_PAST
    if is_hypothetical:
        return _MENTION_PLANNED
    return _MENTION_BARE


def _is_current_at_visit(classes: list[tuple[int, str]]) -> bool:
    """One drug: current unless stopped after its last current mention, or never current.

    A bare mention (no cue) after the drug was introduced as a plan talks
    about the plan ("Zonisamide can cause weight loss"), and a bare mention of
    a stopped drug talks about the stopped drug ("perampanel caused
    sedation"); neither counts.
    """
    first_plan = min((p for p, c in classes if c == _MENTION_PLANNED), default=None)
    stops = [p for p, c in classes if c == _MENTION_STOP]
    cur = [p for p, c in classes
           if c == _MENTION_CURRENT
           or (c == _MENTION_BARE and not stops and (first_plan is None or p < first_plan))]
    if not cur:
        return False
    return not stops or max(stops) < max(cur)


def _nearest_dose(text: str, start: int, end: int, window: int = 60) -> Optional[str]:
    """Find the first dose expression within ± window chars of the drug span."""
    ctx_start = max(0, start - 15)
    ctx_end = min(len(text), end + window)
    ctx = text[ctx_start:ctx_end]
    m = _DOSE_RE.search(ctx)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(0).strip())


# ---------------------------------------------------------------------------
# Rule (single class emits three list-valued outputs via dispatch)
# ---------------------------------------------------------------------------


def _med_evidence(meta: dict, canon: str, status: MedicationStatus, text: str,
                  start: int, end: int, surface: str, rxcui: Optional[str],
                  certainty: Certainty = Certainty.DEFINITE) -> Evidence:
    dose_text = _nearest_dose(text, start, end)
    if status in (MedicationStatus.PRIOR, MedicationStatus.FAILED,
                  MedicationStatus.DISCONTINUED_ADVERSE_EFFECT):
        temporal = TemporalStatus.HISTORICAL
    elif status == MedicationStatus.PLANNED:
        temporal = TemporalStatus.PLANNED
    else:
        temporal = TemporalStatus.CURRENT
    return Evidence[Medication](
        value=Medication(generic_name=canon, status=status, dose_text=dose_text,
                         reason_discontinued=None, rxnorm_cui=rxcui),
        certainty=certainty,
        temporal_status=temporal,
        evidence_text=f"{surface} {dose_text}".strip() if dose_text else surface,
        source_doc_id=meta["doc_id"],
        source_doc_type=meta["doc_type"],
        source_date=meta["doc_date"],
        char_start=start,
        char_end=end,
    )


def _extract_medications(
    entities: list[LinkedEntity],
    doc,
    meta: dict[str, Any],
) -> tuple[list[Evidence], list[Evidence], list[Evidence]]:
    """Return (current, prior, failed) lists of Evidence[Medication].

    Every drug mention (linker, leftover US brand, abbreviation, misspelling)
    is classed current / stop / planned / past; ``_is_current_at_visit`` then
    decides once per drug, so a weak past cue ("as per previous letter", "has
    tried higher doses in the past") never removes a drug the letter lists as
    taken.  Prior / failed lists keep the sentence-level status, one entry per
    drug and status.
    """
    from rules.asm_surface import surface_matches

    text = getattr(doc, "text", "") or ""
    mentions: list[dict] = []
    for e in entities:
        if e.enum_class != "Medication" or e.is_negated or e.is_family:
            continue
        raw_name = e.enum_value or e.label or e.text
        canon = canonicalize_drug_name(raw_name) or raw_name
        if is_eeg_study_token(raw_name) or is_eeg_study_token(canon):
            continue
        mentions.append(dict(
            start=e.char_start, end=e.char_end, surface=e.text, canon=canon,
            rxcui=ASM_LEXICON.get(e.enum_value or "", {}).get("rxcui"),
            sentence=e.sentence_text or _sentence_window(text, e.char_start, e.char_end),
            hyp=bool(e.is_hypothetical), hist=bool(e.is_historical)))
    linked = {m["canon"].lower() for m in mentions}
    for m, canon in leftover_brand_matches(text):
        if is_eeg_study_token(canon) or canon.lower() in linked:
            continue
        mentions.append(dict(start=m.start(), end=m.end(), surface=m.group(0), canon=canon,
                             rxcui=None, sentence=_sentence_window(text, m.start(), m.end()),
                             hyp=False, hist=False))
    taken = [(m["start"], m["end"]) for m in mentions]
    for s in surface_matches(text, canonicalize_drug_name, taken):
        sentence = _sentence_window(text, s.start, s.end)
        if _FAMILY_CUE.search(sentence):
            continue
        mentions.append(dict(start=s.start, end=s.end, surface=s.surface, canon=s.canon,
                             rxcui=None, sentence=sentence, hyp=False, hist=False))
    mentions.sort(key=lambda m: m["start"])

    classes: dict[str, list[tuple[int, str]]] = {}
    first_current: dict[str, dict] = {}
    prior, failed = [], []
    seen: set[tuple[str, str]] = set()
    for m in mentions:
        name = m["canon"].lower()
        status = _infer_status(m["sentence"])
        cls = _mention_class(text, m["start"], m["end"], status, m["hyp"], m["hist"])
        classes.setdefault(name, []).append((m["start"], cls))
        if cls in (_MENTION_CURRENT, _MENTION_BARE):
            m["clean"] = status == MedicationStatus.CURRENT and not m["hist"]
            if name not in first_current or (m["clean"] and not first_current[name]["clean"]):
                first_current[name] = m
        if m["hist"] and status == MedicationStatus.CURRENT:
            status = MedicationStatus.PRIOR
        if status not in (MedicationStatus.PRIOR, MedicationStatus.FAILED,
                          MedicationStatus.DISCONTINUED_ADVERSE_EFFECT):
            continue
        if (name, status.value) in seen:
            continue
        seen.add((name, status.value))
        ev = _med_evidence(meta, m["canon"], status, text, m["start"], m["end"],
                           m["surface"], m["rxcui"])
        (failed if status == MedicationStatus.FAILED else prior).append(ev)

    # Deixis: "stopped that drug" -> the last ASM before it was stopped (coref, not a gazetteer).
    from services.coref_temporal import resolve_med_deixis
    for e in resolve_med_deixis(text, entities):
        raw_name = e.enum_value or e.label or e.text
        canon = canonicalize_drug_name(raw_name) or raw_name
        if is_eeg_study_token(canon):
            continue
        name = canon.lower()
        classes.setdefault(name, []).append((e.char_end + 1, _MENTION_STOP))
        if (name, MedicationStatus.PRIOR.value) in seen:
            continue
        seen.add((name, MedicationStatus.PRIOR.value))
        prior.append(_med_evidence(meta, canon, MedicationStatus.PRIOR, text,
                                   e.char_start, e.char_end, e.text,
                                   ASM_LEXICON.get(e.enum_value or "", {}).get("rxcui")))

    current = []
    for name, m in first_current.items():
        if _is_current_at_visit(classes[name]):
            current.append(_med_evidence(
                meta, m["canon"], MedicationStatus.CURRENT, text, m["start"], m["end"],
                m["surface"], m["rxcui"],
                Certainty.POSSIBLE if m["hyp"] else Certainty.DEFINITE))

    # Phase 8 Iter 3 — F-S convention: if the doc explicitly says the med
    # was RESUMED (reintroduced / restarted / back on) and the same drug
    # appears in both prior and current, keep only current.  A bare
    # duplication (same drug in prior + current without a reintroduction
    # cue) is left alone; both are meaningful separate mentions in F-S.
    if re.search(
        r"\b(reintroduce|re[- ]?introduc|restart|re[- ]?start|"
        r"back\s+on|resume(?:d)?|"
        r"reinstitut(?:ed?|ion))\b",
        text, re.IGNORECASE,
    ):
        current_names = {ev.value.generic_name.lower() for ev in current
                         if ev.value is not None}
        if current_names:
            prior = [ev for ev in prior
                     if ev.value is None
                     or ev.value.generic_name.lower() not in current_names]
            failed = [ev for ev in failed
                      if ev.value is None
                      or ev.value.generic_name.lower() not in current_names]

    return current, prior, failed


class CurrentAsmsRule(BaseFieldRule):
    field_name = "medication.current_asms"

    def apply(self, entities, doc, meta):
        current, _prior, _failed = _extract_medications(entities, doc, meta)
        return current or None


class PriorAsmsRule(BaseFieldRule):
    field_name = "medication.prior_asms"

    def apply(self, entities, doc, meta):
        _current, prior, _failed = _extract_medications(entities, doc, meta)
        return prior or None


class FailedAsmsRule(BaseFieldRule):
    field_name = "medication.failed_asms"

    def apply(self, entities, doc, meta):
        _current, _prior, failed = _extract_medications(entities, doc, meta)
        return failed or None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(CurrentAsmsRule())
register_rule(PriorAsmsRule())
register_rule(FailedAsmsRule())

__all__ = ["CurrentAsmsRule", "PriorAsmsRule", "FailedAsmsRule",
           "canonicalize_drug_name", "is_eeg_study_token"]
