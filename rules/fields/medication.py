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
4. Deduplication: same generic_name + same status → merge, keep first
   evidence.
5. ConText — negated → skip; family → skip; hypothetical → certainty POSSIBLE.

Cite: Fonferko-Shadrach et al. 2019; 2024. Drug list per RxNorm + BNF.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.asm_lexicon import ASM_LEXICON
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
    "epilim":               "sodiumvalproate",
    "brivaracetam":         "brivaracetam",
    "brivetiracetam":       "brivaracetam",   # common misspelling / F-S "brivitiracetam"
    "brivitiracetam":       "brivaracetam",   # F-S spelling
    "briviact":             "brivaracetam",
    "carbamazepine":        "carbamazepine",
    "carbamazapine":        "carbamazepine",  # F-S misspelling variant
    "tegretol":             "carbamazepine",
    "carbatrol":            "carbamazepine",
    "oxcarbazepine":        "oxcarbazepine",
    "oxcarbazepin":         "oxcarbazepine",
    "trileptal":            "oxcarbazepine",
    "lamotrigine":          "lamotrigine",
    "lamictal":             "lamotrigine",
    "lamotrigin":           "lamotrigine",
    "lamotiringe":          "lamotrigine",   # F-S misspelling
    "levetiracetam":        "levetiracetam",
    "keppra":               "levetiracetam",
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
    # try collapsed (no space/underscore/hyphen)
    collapsed = re.sub(r"[\s\-_]+", " ", s).strip()
    if collapsed in _DRUG_NAME_CANONICAL:
        return _DRUG_NAME_CANONICAL[collapsed]
    solid = re.sub(r"[\s\-_]+", "", s)
    if solid in _DRUG_NAME_CANONICAL:
        return _DRUG_NAME_CANONICAL[solid]
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
        r"no\s+longer\s+taking|off\s+the\s+medication|ceased|"
        r"switched\s+from|"  # past-tense only
        r"of\s+(?:his|her)\s+own\s+accord|"
        r"many\s+years\s+ago|years\s+ago|during\s+childhood|"
        r"in\s+(?:his|her)\s+(?:teens|twenties|thirties)|"
        r"has\s+tried|had\s+tried|had\s+been\s+tried\s+on|"
        r"she\s+has\s+tried|he\s+has\s+tried|"
        r"she\s+tried|he\s+tried|"
        r"in\s+the\s+past|history\s+of\s+taking)\b",
        re.IGNORECASE), MedicationStatus.PRIOR),
    (re.compile(
        r"\b(plans?\s+to\s+start|will\s+commence|will\s+start|to\s+be\s+started|"
        r"planned|proposed|considering|please\s+start|start\s+him\s+on|"
        r"start\s+her\s+on|initiate\s+.*\s+(?:on|with)|"
        r"i\s+would\s+suggest\s+(?:introducing|starting)|"
        r"we\s+will\s+add|adding\s+in|introducing|"
        r"if\s+.*\s+(?:not\s+successful|unsuccessful|fails?)|"
        r"if\s+necessary|"
        r"consider(?:ed)?\s+starting|"
        r"will\s+consider)\b",
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


def _extract_medications(
    entities: list[LinkedEntity],
    doc,
    meta: dict[str, Any],
) -> tuple[list[Evidence], list[Evidence], list[Evidence]]:
    """Return (current, prior, failed) lists of Evidence[Medication].

    Phase 8 Iter 3 refinement: F-S convention is that if the same ASM appears
    as both prior and current in a single letter (patient stopped then
    resumed), only the current mention counts.  We deduplicate at the end.
    """
    text = getattr(doc, "text", "") or ""
    current, prior, failed = [], [], []
    seen: set[tuple[str, str]] = set()

    for e in entities:
        if e.enum_class != "Medication":
            continue
        if e.is_negated or e.is_family:
            continue

        raw_name = e.enum_value or e.label or e.text
        # Phase 8 Iter 1 — normalize to F-S primary key convention.
        canon = canonicalize_drug_name(raw_name) or raw_name
        sentence = e.sentence_text or _sentence_window(text, e.char_start, e.char_end)
        status = _infer_status(sentence)

        key = (canon.lower(), status.value)
        if key in seen:
            continue
        seen.add(key)

        dose_text = _nearest_dose(text, e.char_start, e.char_end)

        med = Medication(
            generic_name=canon,
            status=status,
            dose_text=dose_text,
            reason_discontinued=None,
            rxnorm_cui=ASM_LEXICON.get(e.enum_value or "", {}).get("rxcui"),
        )

        certainty = Certainty.POSSIBLE if e.is_hypothetical else Certainty.DEFINITE
        if status in (MedicationStatus.PRIOR, MedicationStatus.FAILED,
                      MedicationStatus.DISCONTINUED_ADVERSE_EFFECT):
            temporal = TemporalStatus.HISTORICAL
        elif status == MedicationStatus.PLANNED:
            temporal = TemporalStatus.PLANNED
        elif e.is_historical:
            temporal = TemporalStatus.HISTORICAL
        else:
            temporal = TemporalStatus.CURRENT

        # Evidence text: prefer the drug span + dose if we found one.
        if dose_text:
            ev_text = f"{e.text} {dose_text}"
        else:
            ev_text = e.text

        ev = Evidence[Medication](
            value=med,
            certainty=certainty,
            temporal_status=temporal,
            evidence_text=ev_text,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=e.char_start,
            char_end=e.char_end,
        )
        if status == MedicationStatus.CURRENT or status == MedicationStatus.PLANNED:
            current.append(ev)
        elif status in (MedicationStatus.PRIOR,
                        MedicationStatus.DISCONTINUED_ADVERSE_EFFECT):
            prior.append(ev)
        else:
            failed.append(ev)

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

__all__ = ["CurrentAsmsRule", "PriorAsmsRule", "FailedAsmsRule"]
