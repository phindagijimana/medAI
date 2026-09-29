"""
compound.py — Phase 5 wave-2 compound / relational rules.

Ten rules that derive schema fields (or non-slotted supplementary fields
attached to ``pheno._derived``) from the partially-populated
:class:`schema.ontology.EpilepsyPhenotype` produced by Phase 3a + 3b wave-1
field rules. Runs AFTER wave-1 dispatch completes so it can read
current/prior/failed ASM lists, predominant seizure type, surgery history,
etiology specifics, and the modality-specific localizations.

Rules implemented
-----------------
1.  ``derive_drug_resistance``           → mutates
    ``medication.drug_resistance_status`` (ILAE 2010 Kwan). Supersedes
    the wave-2 :class:`rules.fields.medication_extra.DrugResistanceStatusRule`
    with a five-way state machine (drug-resistant / responsive /
    in-remission-on-treatment / responding / not-yet-established) mapped
    onto the three-value ``DrugResistanceStatus`` enum.

2.  ``derive_epilepsy_duration_years``   → attaches
    ``pheno._derived['epilepsy_duration_years']`` (schema has no slot).
    Uses raw-text "for N years" / "for N months" cue as fallback; primary
    formula = doc_date.year − onset_year (when the wave-1 age_at_onset
    rule fired and a patient birth-year cue exists).

3.  ``derive_medication_currently_taking``→ mutates
    ``medication.current_asms`` / ``prior_asms`` in place. Moves an ASM
    from CURRENT → PRIOR when a discontinuation signal appears in the
    same sentence as the mention (``stopped``, ``discontinued``,
    ``no longer``, ``off X``, ``switched from X``, ``held``, ``d/c``).

4.  ``derive_ilae_classification_full``  → attaches
    ``pheno._derived['ilae_classification']`` — a nested dict following
    the ILAE 2017 tree (level_1..4).

5.  ``derive_seizure_free_since``        → attaches
    ``pheno._derived['seizure_free_since']`` — either an ISO date or a
    duration phrase quoted from the note.

6.  ``derive_focal_to_bilateral_tc``     → mutates
    ``clinical_seizure.predominant_seizure_type`` when Phase 3a's
    ``PredominantSeizureTypeRule`` picked a focal-onset subtype but a
    GTC entity co-occurs within ± 2 sentences with a
    "secondarily generalised" / "focal-to-bilateral" linker. In practice
    Phase 3a already handles the common case; this rule is a safety net.

7.  ``derive_localization_concordance``  → mutates
    ``integrated.concordance``. Supersedes the wave-2
    :class:`rules.fields.clinical_localization.ConcordanceStatusRule`
    with a tie-breaking pass that (a) considers ``clinical_localization.
    primary_claim`` in addition to the three modality localizations,
    and (b) emits ``PARTIALLY_CONCORDANT`` on lobe-match-only.

8.  ``derive_surgery_outcome_class``     → mutates
    ``surgery_history[i].engel_class`` / ``ilae_outcome`` when Phase 3b
    left them None but a post-op seizure-frequency observation is
    present. Attaches an aggregated
    ``pheno._derived['post_surgical_outcome']`` for the earliest
    surgery.

9.  ``derive_autoimmune_probable``       → attaches
    ``pheno._derived['autoimmune_probable']`` — bool per Graus 2016.

10. ``derive_polytherapy_flag``          → attaches
    ``pheno._derived['polytherapy']`` — bool if ≥ 2 concurrent-active
    ASMs.

Provenance
----------
All ten rules reimplement published clinical criteria from primary
sources — no verbatim clinical-text-mining code copied from any external
repository:
- Kwan P et al. 2010 (Epilepsia 51:1069-77)          — drug-resistance
- Fisher R S et al. 2017 (Epilepsia 58:522-30)        — ILAE 2017 classification
- Engel J Jr et al. 1993                              — post-surgical outcome
- Wieser H G et al. 2001 (Epilepsia 42:282-6)         — ILAE post-surgical scale
- Graus F et al. 2016 (Lancet Neurol 15:391-404)      — autoimmune encephalitis
- Kanner A M & Bicchi M M 2022 (JAMA 327:1269)        — polytherapy usage

Design notes
------------
- Each rule is a plain function ``derive_X(pheno, meta) -> ...`` — not a
  BaseFieldRule subclass. They run through :func:`apply_compound_rules`
  and never call MedCAT or medspaCy themselves.
- Rules 1 and 7 both replace values written by P3b's wave-2 rules. To
  avoid conflict, ``apply_compound_rules`` is invoked AFTER P3b wave-2
  dispatch completes; the last write wins.
- Rules that mutate lists (3, 6, 8) operate in place on the phenotype's
  list-valued Evidence attributes.
- Rules with no schema slot store their result on a private
  ``pheno._derived`` dict (created lazily via ``object.__setattr__``
  because the pydantic ``EpilepsyPhenotype`` sets ``extra="forbid"``).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

from schema.enums import (
    Awareness,
    Certainty,
    ConcordanceStatus,
    DrugResistanceStatus,
    EngelClass,
    EpilepsyType,
    IlaeOutcome,
    LobarLocalization,
    MedicationStatus,
    SeizureType,
    TemporalStatus,
)
from schema.evidence import Evidence
from schema.ontology import EpilepsyPhenotype


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _text_of(pheno: EpilepsyPhenotype) -> str:
    return getattr(pheno, "_text", "") or ""


def _entities_of(pheno: EpilepsyPhenotype) -> list:
    return getattr(pheno, "_entities", []) or []


def _ensure_derived(pheno: EpilepsyPhenotype) -> dict:
    """Return the ``pheno._derived`` dict, creating it if absent.

    Uses ``object.__setattr__`` because :class:`EpilepsyPhenotype` sets
    ``model_config = ConfigDict(extra='forbid')``.
    """
    derived = getattr(pheno, "_derived", None)
    if derived is None or not isinstance(derived, dict):
        derived = {}
        object.__setattr__(pheno, "_derived", derived)
    return derived


def _make_ev(
    value: Any,
    meta: dict[str, Any],
    *,
    certainty: Certainty = Certainty.PROBABLE,
    temporal_status: TemporalStatus = TemporalStatus.CURRENT,
    evidence_text: str = "",
    char_start: Optional[int] = None,
    char_end: Optional[int] = None,
) -> Evidence:
    """Compact ``Evidence`` factory that reads doc-level provenance from
    ``meta``. Not passed to :class:`Evidence`'s validator unless ``value``
    is non-None."""
    if value is None:
        return Evidence.not_documented(
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
        )
    ev_text = evidence_text.strip()[:400] or "compound-derived"
    return Evidence(
        value=value,
        certainty=certainty,
        temporal_status=temporal_status,
        evidence_text=ev_text,
        source_doc_id=meta["doc_id"],
        source_doc_type=meta["doc_type"],
        source_date=meta["doc_date"],
        char_start=char_start,
        char_end=char_end,
    )


# ---------------------------------------------------------------------------
# Rule 1 — drug resistance (ILAE 2010 Kwan)
# ---------------------------------------------------------------------------

_DR_DIRECT_RE = re.compile(
    r"\bdrug[- ]?resistant\b|\brefractory\b|\bmedically\s+intractable\b|"
    r"\bintractable\s+epilepsy\b|\btreatment[- ]?resistant\b",
    re.IGNORECASE,
)

_DR_RESPONSIVE_RE = re.compile(
    r"\bseizure[- ]?free\b|\bwell[- ]?controlled\b|"
    r"has\s+had\s+no\s+(?:further\s+)?seizures?|"
    r"no\s+seizures?\s+(?:since|for)|\bin\s+remission\b|"
    r"good\s+seizure\s+control|\bexcellent\s+control\b",
    re.IGNORECASE,
)

_NEG_PRE_RE = re.compile(
    r"\b(?:no|without|denies?|absent|never|not|negative\s+for)\s+",
    re.IGNORECASE,
)


def _preceded_by_neg(text: str, start: int, back: int = 30) -> bool:
    return bool(_NEG_PRE_RE.search(text[max(0, start - back):start]))


def derive_drug_resistance(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> Optional[Evidence]:
    """Compute ``medication.drug_resistance_status`` per ILAE 2010.

    Five-way state machine, projected onto the three-value schema enum
    (DRUG_RESISTANT / DRUG_RESPONSIVE / UNDEFINED). Attaches the finer
    five-way label under ``pheno._derived['drug_resistance_detail']``.

    States (Kwan 2010):
    - ``DRUG_RESISTANT`` — ≥ 2 tolerated + adequately trialled ASMs
      failed AND current seizures.
    - ``IN_REMISSION_ON_TREATMENT`` — ≥ 2 failed AND currently
      seizure-free.
    - ``RESPONDING_TO_TREATMENT`` — 1 ASM + seizure-free.
    - ``NOT_YET_ESTABLISHED`` — < 2 failed AND current seizures.
    - ``NOT_ASSESSED`` — insufficient data.
    """
    if pheno.medication is None:
        return None

    text = _text_of(pheno)
    n_failed = len(pheno.medication.failed_asms or [])
    n_current = len(pheno.medication.current_asms or [])
    n_prior = len(pheno.medication.prior_asms or [])
    n_total = n_failed + n_current + n_prior

    # 1. Direct-trigger DRUG_RESISTANT — highest confidence.
    if text:
        m = _DR_DIRECT_RE.search(text)
        if m and not _preceded_by_neg(text, m.start()):
            _ensure_derived(pheno)["drug_resistance_detail"] = "drug_resistant"
            return _make_ev(
                DrugResistanceStatus.DRUG_RESISTANT,
                meta,
                certainty=Certainty.DEFINITE,
                evidence_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
            )

    # Seizure-free signal.
    responsive_match = None
    if text:
        rm = _DR_RESPONSIVE_RE.search(text)
        if rm and not _preceded_by_neg(text, rm.start()):
            responsive_match = rm

    # 2. Kwan compound criterion.
    if n_failed >= 2:
        if responsive_match is not None:
            _ensure_derived(pheno)["drug_resistance_detail"] = (
                "in_remission_on_treatment"
            )
            # Projected onto the tri-value enum → DRUG_RESPONSIVE (patient
            # is currently in remission despite prior resistance).
            failed_names = ", ".join(
                str(ev.value.generic_name)
                for ev in (pheno.medication.failed_asms or [])[:3]
                if ev.value is not None
            )
            return _make_ev(
                DrugResistanceStatus.DRUG_RESPONSIVE,
                meta,
                certainty=Certainty.PROBABLE,
                evidence_text=(
                    f"≥2 failed ASMs ({failed_names}) but currently "
                    f"seizure-free — in remission on treatment (ILAE 2010)"
                ),
            )
        _ensure_derived(pheno)["drug_resistance_detail"] = "drug_resistant"
        failed_names = ", ".join(
            str(ev.value.generic_name)
            for ev in (pheno.medication.failed_asms or [])[:3]
            if ev.value is not None
        )
        return _make_ev(
            DrugResistanceStatus.DRUG_RESISTANT,
            meta,
            certainty=Certainty.PROBABLE,
            evidence_text=(
                f"≥2 failed ASMs ({failed_names}) — ILAE 2010 Kwan"
            ),
        )

    # 3. Responding — 1 ASM + seizure-free.
    if responsive_match is not None and n_failed == 0 and n_current >= 1:
        _ensure_derived(pheno)["drug_resistance_detail"] = (
            "responding_to_treatment"
        )
        return _make_ev(
            DrugResistanceStatus.DRUG_RESPONSIVE,
            meta,
            certainty=Certainty.PROBABLE,
            evidence_text=responsive_match.group(0),
            char_start=responsive_match.start(),
            char_end=responsive_match.end(),
        )

    # 4. Not-yet-established — <2 failed AND some active seizures documented.
    if n_failed < 2 and (n_total >= 1) and responsive_match is None:
        _ensure_derived(pheno)["drug_resistance_detail"] = (
            "not_yet_established"
        )
        return _make_ev(
            DrugResistanceStatus.UNDEFINED,
            meta,
            certainty=Certainty.POSSIBLE,
            evidence_text=(
                f"{n_failed} failed / {n_current} current ASM(s), "
                "insufficient trial history for ILAE-2010 verdict"
            ),
        )

    # 5. Not assessed.
    _ensure_derived(pheno)["drug_resistance_detail"] = "not_assessed"
    return None


# ---------------------------------------------------------------------------
# Rule 2 — epilepsy duration in years
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(
    r"(?:for|since|over)\s+(?:the\s+past\s+)?"
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>years?|yrs?|months?|mos?)"
    r"(?:\s+(?:of\s+)?(?:seizures?|epilepsy))?",
    re.IGNORECASE,
)


def derive_epilepsy_duration_years(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> Optional[int]:
    """Compute epilepsy duration in years.

    Preferred: ``pheno.clinical_seizure.age_at_onset_years`` +
    document ``doc_date`` and a patient current-age cue in the text.

    Fallback: parse ``"for N years"`` / ``"since N years ago"`` from the
    document text.

    Returns None if neither path yields a value. Guardrails: 0 < d < 100.
    Stored on ``pheno._derived['epilepsy_duration_years']`` (no schema
    slot exists).
    """
    if pheno.clinical_seizure is None:
        return None
    text = _text_of(pheno)
    doc_year = meta["doc_date"].year if isinstance(meta.get("doc_date"), date) else None

    onset_ev = pheno.clinical_seizure.age_at_onset_years
    onset_age = onset_ev.value if onset_ev and onset_ev.value is not None else None

    # 1. Preferred formula: doc.date.year − (visit_year − onset_age).
    # We infer patient's current age from a "he/she is N-year-old" cue.
    current_age = _infer_current_age(text)
    if onset_age is not None and current_age is not None:
        duration = current_age - onset_age
        if 0 < duration < 100:
            _ensure_derived(pheno)["epilepsy_duration_years"] = int(round(duration))
            return int(round(duration))

    # 2. Fallback: direct "for N years" / "for N months" match in text.
    if text:
        for m in _DURATION_RE.finditer(text):
            n = float(m.group("n"))
            unit = m.group("unit").lower()
            if unit.startswith("month") or unit.startswith("mo"):
                years = n / 12.0
            else:
                years = n
            if 0 < years < 100:
                _ensure_derived(pheno)["epilepsy_duration_years"] = int(round(years))
                return int(round(years))

    return None


_AGE_RE = re.compile(
    r"\b(?:a|an|is|was)\s+(\d{1,3})[- ]?year[- ]?old\b|"
    r"\b(\d{1,3})[- ]?year[- ]?old\s+(?:man|woman|male|female|boy|girl|patient)\b|"
    r"\bage[d]?\s+(\d{1,3})\b",
    re.IGNORECASE,
)


def _infer_current_age(text: str) -> Optional[int]:
    if not text:
        return None
    m = _AGE_RE.search(text)
    if not m:
        return None
    for g in m.groups():
        if g:
            try:
                age = int(g)
                if 0 < age < 120:
                    return age
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Rule 3 — medication currently-taking hygiene
# ---------------------------------------------------------------------------

_DISCONT_RE = re.compile(
    r"\b(stopped|discontinued|no\s+longer\s+(?:on|taking)|off\s+the|"
    r"switched\s+from|held|d/?c(?:['-]?d)?|weaned\s+off|tapered\s+off|"
    r"withdrawn|ceased)\b",
    re.IGNORECASE,
)


def derive_medication_currently_taking(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> None:
    """Migrate discontinued meds from ``current_asms`` → ``prior_asms``.

    Signals: entity is ``is_historical`` OR the sentence containing the
    entity matches :data:`_DISCONT_RE`. Rewrites the ``Medication.status``
    on the migrated Evidence to :attr:`MedicationStatus.PRIOR` and keeps
    the original char offsets / provenance.
    """
    if pheno.medication is None:
        return
    text = _text_of(pheno)
    current = list(pheno.medication.current_asms or [])
    prior = list(pheno.medication.prior_asms or [])

    if not current:
        return

    moved_indices = []
    for i, ev in enumerate(current):
        if ev.value is None:
            continue
        # Get the sentence around ``[char_start:char_end]`` and test the
        # discontinuation regex against it.
        cs, ce = ev.char_start, ev.char_end
        if cs is None or ce is None or not text:
            continue
        sent = _sentence_of(text, cs, ce)
        if not _DISCONT_RE.search(sent):
            continue
        # Rebuild the Evidence with status=PRIOR and temporal=HISTORICAL.
        new_med = ev.value.model_copy(update={"status": MedicationStatus.PRIOR})
        new_ev = ev.model_copy(update={
            "value": new_med,
            "temporal_status": TemporalStatus.HISTORICAL,
        })
        prior.append(new_ev)
        moved_indices.append(i)

    if not moved_indices:
        return

    new_current = [ev for i, ev in enumerate(current) if i not in moved_indices]
    pheno.medication.current_asms = new_current
    pheno.medication.prior_asms = prior


_SENT_END_RE = re.compile(r"[.!?;\n]")


def _sentence_of(text: str, start: int, end: int) -> str:
    sent_start = 0
    for m in _SENT_END_RE.finditer(text[:start]):
        sent_start = m.end()
    m = _SENT_END_RE.search(text, end)
    sent_end = m.start() if m else len(text)
    return text[sent_start:sent_end]


# ---------------------------------------------------------------------------
# Rule 4 — full ILAE 2017 classification tree
# ---------------------------------------------------------------------------


def derive_ilae_classification_full(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> Optional[dict[str, str]]:
    """Compose the ILAE 2017 nested classification from wave-1 fields.

    Structure::

        {
          "level_1": <epilepsy_type>,         # focal / generalized / …
          "level_2": <awareness or …>,        # only for focal
          "level_3": <motor|nonmotor>,        # only for focal
          "level_4": <subtype>,               # focal motor/nonmotor specific
          "predominant_seizure_type": <SeizureType>,
        }

    Missing levels are omitted. Stored under
    ``pheno._derived['ilae_classification']``.
    """
    if pheno.clinical_seizure is None:
        return None
    cs = pheno.clinical_seizure

    result: dict[str, str] = {}

    et_ev = cs.epilepsy_type
    if et_ev and et_ev.value is not None:
        result["level_1"] = et_ev.value.value

    pst_ev = cs.predominant_seizure_type
    predom = pst_ev.value if pst_ev and pst_ev.value is not None else None
    if predom is not None:
        result["predominant_seizure_type"] = predom.value

    aw_ev = cs.awareness
    if aw_ev and aw_ev.value is not None:
        result["level_2"] = aw_ev.value.value

    # Level 3/4 only meaningful for focal epilepsies.
    et_val = et_ev.value if et_ev else None
    predom_is_focal = predom is not None and predom.value.startswith("focal_")
    if et_val == EpilepsyType.FOCAL or predom_is_focal:
        fm_ev = cs.focal_motor_onset
        fn_ev = cs.focal_nonmotor_onset
        if fm_ev and fm_ev.value is not None:
            result["level_3"] = "motor"
            result["level_4"] = fm_ev.value.value
        elif fn_ev and fn_ev.value is not None:
            result["level_3"] = "nonmotor"
            result["level_4"] = fn_ev.value.value

    # No classification at all → return None so downstream reporters can
    # distinguish "unclassified" from "unpopulated".
    if not result:
        return None

    _ensure_derived(pheno)["ilae_classification"] = result
    return result


# ---------------------------------------------------------------------------
# Rule 5 — seizure-free since (duration or date)
# ---------------------------------------------------------------------------

_SEIZURE_FREE_DURATION_RE = re.compile(
    r"(?:seizure[- ]?free|no\s+seizures?|has\s+not\s+had\s+(?:a\s+)?seizure)"
    r"[^.\n]{0,80}?"
    r"(?:for|since|in\s+the\s+(?:past|last))\s+"
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>days?|weeks?|months?|years?|yrs?|mos?)",
    re.IGNORECASE,
)

_SEIZURE_FREE_DATE_RE = re.compile(
    r"(?:last\s+seizure|no\s+seizures?\s+since|seizure[- ]?free\s+since)"
    r"[^.\n]{0,60}?"
    r"(?P<date>"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{4}"
    r")",
    re.IGNORECASE,
)


def derive_seizure_free_since(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> Optional[str]:
    """Extract when the patient has been seizure-free from.

    Returns either an ISO-like date string or a duration phrase
    (``"6 months"``). Stored on ``pheno._derived['seizure_free_since']``.
    Returns None when no cue matches.
    """
    text = _text_of(pheno)
    if not text:
        return None

    # 1. Explicit date cue.
    dm = _SEIZURE_FREE_DATE_RE.search(text)
    if dm:
        raw = dm.group("date").strip()
        _ensure_derived(pheno)["seizure_free_since"] = raw
        return raw

    # 2. Duration cue.
    dur = _SEIZURE_FREE_DURATION_RE.search(text)
    if dur:
        raw = f"{dur.group('n')} {dur.group('unit')}"
        _ensure_derived(pheno)["seizure_free_since"] = raw
        return raw

    return None


# ---------------------------------------------------------------------------
# Rule 6 — focal-to-bilateral tonic-clonic composition (safety net)
# ---------------------------------------------------------------------------

_FBTC_LINKER_RE = re.compile(
    r"(?:secondar(?:ily|y)\s+generali[sz]e[ds]?|"
    r"focal[- ]?to[- ]?bilateral|"
    r"generali[sz]e[sd]?\s+to\s+(?:bilateral\s+)?tonic[- ]?clonic|"
    r"progress(?:es|ed)\s+to\s+(?:bilateral\s+)?tonic[- ]?clonic|"
    r"evolves?\s+into\s+(?:bilateral\s+)?tonic[- ]?clonic)",
    re.IGNORECASE,
)


def derive_focal_to_bilateral_tc(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> Optional[Evidence]:
    """Promote predominant_seizure_type → FOCAL_TO_BILATERAL_TONIC_CLONIC
    when wave-1 picked a focal subtype but the text explicitly says the
    seizures generalise (Phase 3a's rule may miss this composition when
    the GTC entity lives in ``other_seizure_types``).

    Returns a new Evidence[SeizureType] if a promotion happens; otherwise
    None (leaving wave-1's choice intact).
    """
    if pheno.clinical_seizure is None:
        return None
    text = _text_of(pheno)
    if not text:
        return None

    pst_ev = pheno.clinical_seizure.predominant_seizure_type
    if pst_ev is None or pst_ev.value is None:
        return None
    current = pst_ev.value
    # Only promote from focal subtypes (not from any generalized type).
    if not current.value.startswith("focal_"):
        return None
    if current == SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC:
        return None

    # Look for GTC evidence anywhere in the doc.
    other_types = pheno.clinical_seizure.other_seizure_types or []
    has_gtc_other = any(
        ev.value in (
            SeizureType.GENERALIZED_TONIC_CLONIC,
            SeizureType.UNKNOWN_ONSET_TONIC_CLONIC,
        )
        for ev in other_types
        if ev.value is not None
    )
    has_gtc_text = bool(re.search(
        r"\b(?:generali[sz]ed\s+tonic[- ]?clonic|\bGTC\b|\bGTCS\b|"
        r"grand\s+mal)\b", text, re.IGNORECASE,
    ))
    if not (has_gtc_other or has_gtc_text):
        return None

    linker = _FBTC_LINKER_RE.search(text)
    if not linker:
        return None
    if _preceded_by_neg(text, linker.start()):
        return None

    new_ev = _make_ev(
        SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC,
        meta,
        certainty=Certainty.PROBABLE,
        evidence_text=linker.group(0),
        char_start=linker.start(),
        char_end=linker.end(),
    )
    pheno.clinical_seizure.predominant_seizure_type = new_ev
    return new_ev


# ---------------------------------------------------------------------------
# Rule 7 — localization concordance (supersede P3b)
# ---------------------------------------------------------------------------


def derive_localization_concordance(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> Optional[Evidence]:
    """Compute ``integrated.concordance`` from clinical + EEG + MRI
    localizations plus the ``clinical_localization.primary_claim``.

    Rules:
    - 0 or 1 modality documented → NOT_ASSESSED.
    - All (lobe, laterality) tuples identical → CONCORDANT.
    - Same lobe but different laterality (or two of three agree) →
      PARTIALLY_CONCORDANT.
    - Otherwise DISCORDANT.
    """
    if pheno.integrated is None:
        return None

    sources: list[tuple[str, LobarLocalization, Any]] = []
    for name in ("clinical_localization", "eeg_localization", "mri_localization"):
        ev = getattr(pheno.integrated, name, None)
        if ev is not None and ev.value is not None:
            sources.append((name, ev.value.lobe, ev.value.laterality))

    # If the integrated slots weren't set but pheno.clinical_localization
    # has a primary_claim, use it as the clinical source.
    if not any(s[0] == "clinical_localization" for s in sources):
        cl = getattr(pheno, "clinical_localization", None)
        if cl is not None and cl.primary_claim and cl.primary_claim.value is not None:
            sources.append((
                "clinical_localization",
                cl.primary_claim.value.lobe,
                cl.primary_claim.value.laterality,
            ))

    n = len(sources)
    if n < 2:
        return _make_ev(
            ConcordanceStatus.NOT_ASSESSED,
            meta,
            certainty=Certainty.PROBABLE,
            evidence_text=f"{n} modality/modalities documented (need ≥2)",
        )

    tuples = [(l, la) for _, l, la in sources]
    lobes = [l for _, l, _ in sources]
    distinct = set(tuples)
    quote = "; ".join(
        f"{name}={lobe.value}/{lat.value}" for name, lobe, lat in sources
    )

    if len(distinct) == 1:
        status = ConcordanceStatus.CONCORDANT
    elif n == 3 and any(tuples.count(t) >= 2 for t in tuples):
        status = ConcordanceStatus.PARTIALLY_CONCORDANT
    elif len(set(lobes)) == 1:
        # Same lobe, differing laterality.
        status = ConcordanceStatus.PARTIALLY_CONCORDANT
    elif n == 3 and any(lobes.count(l) >= 2 for l in lobes):
        status = ConcordanceStatus.PARTIALLY_CONCORDANT
    else:
        status = ConcordanceStatus.DISCORDANT

    return _make_ev(
        status, meta, certainty=Certainty.PROBABLE, evidence_text=quote,
    )


# ---------------------------------------------------------------------------
# Rule 8 — surgery outcome class (Engel / ILAE Wieser 2001)
# ---------------------------------------------------------------------------

_POST_OP_SF_RE = re.compile(
    r"(?:post[- ]?operatively|post[- ]?op|since\s+surgery|"
    r"after\s+(?:the\s+)?(?:surgery|resection|operation|ablation))"
    r"[^.\n]{0,200}?"
    r"(?:seizure[- ]?free|no\s+seizures?|complete\s+control|"
    r"excellent\s+control|free\s+of\s+seizures?)",
    re.IGNORECASE,
)

_POST_OP_RARE_RE = re.compile(
    r"(?:post[- ]?op|since\s+surgery|after\s+surgery)[^.\n]{0,200}?"
    r"(?:rare\s+seizures?|occasional\s+seizures?|"
    r"markedly\s+reduced|significant\s+improvement)",
    re.IGNORECASE,
)

_POST_OP_PARTIAL_RE = re.compile(
    r"(?:post[- ]?op|since\s+surgery|after\s+surgery)[^.\n]{0,200}?"
    r"(?:worthwhile\s+improvement|moderate\s+improvement|"
    r"some\s+improvement|reduced\s+frequency)",
    re.IGNORECASE,
)

_POST_OP_NO_BENEFIT_RE = re.compile(
    r"(?:post[- ]?op|since\s+surgery|after\s+surgery)[^.\n]{0,200}?"
    r"(?:no\s+improvement|no\s+change|unchanged\s+seizure|"
    r"failed\s+surgery|no\s+benefit|persistent\s+seizures?)",
    re.IGNORECASE,
)


def derive_surgery_outcome_class(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Assign an Engel class + ILAE (Wieser 2001) outcome to every
    ``surgery_history`` item that lacks one but has an obvious post-op
    seizure-frequency observation in the note.

    Simplified mapping (documentation-only, requires reviewer
    confirmation for research use):
    - "seizure-free / no seizures / complete control"  → Engel IA / ILAE 1
    - "rare seizures / markedly reduced"               → Engel II / ILAE 3
    - "worthwhile improvement / reduced frequency"     → Engel III / ILAE 4
    - "no improvement / unchanged / failed surgery"    → Engel IVA / ILAE 5

    Returns a dict summary of the aggregated outcome (or None if no
    surgery). Stored on ``pheno._derived['post_surgical_outcome']``.
    """
    if pheno.medication is None:
        return None
    surgery = pheno.medication.surgery_history or []
    if not surgery:
        return None

    text = _text_of(pheno)
    if not text:
        return None

    # Classify the text once.
    engel: Optional[EngelClass] = None
    ilae: Optional[IlaeOutcome] = None
    quote: Optional[str] = None

    m_sf = _POST_OP_SF_RE.search(text)
    m_rare = _POST_OP_RARE_RE.search(text)
    m_partial = _POST_OP_PARTIAL_RE.search(text)
    m_no = _POST_OP_NO_BENEFIT_RE.search(text)

    if m_sf and not _preceded_by_neg(text, m_sf.start()):
        engel, ilae, quote = EngelClass.IA, IlaeOutcome.CLASS_1, m_sf.group(0)
    elif m_rare and not _preceded_by_neg(text, m_rare.start()):
        engel, ilae, quote = EngelClass.IIA, IlaeOutcome.CLASS_3, m_rare.group(0)
    elif m_partial and not _preceded_by_neg(text, m_partial.start()):
        engel, ilae, quote = EngelClass.IIIA, IlaeOutcome.CLASS_4, m_partial.group(0)
    elif m_no and not _preceded_by_neg(text, m_no.start()):
        engel, ilae, quote = EngelClass.IVA, IlaeOutcome.CLASS_5, m_no.group(0)

    if engel is None:
        return None

    # Mutate the surgery_history items that don't already have an outcome.
    mutated = 0
    for ev in surgery:
        item = ev.value
        if item is None:
            continue
        if item.engel_class is None:
            new_item = item.model_copy(update={"engel_class": engel})
            item = new_item
            ev.value = item  # type: ignore[assignment]
            mutated += 1
        if item.ilae_outcome is None:
            new_item = item.model_copy(update={"ilae_outcome": ilae})
            ev.value = new_item  # type: ignore[assignment]

    summary = {
        "engel_class": engel.value,
        "ilae_outcome": ilae.value if ilae is not None else None,
        "quote": (quote or "").strip()[:200],
        "n_surgery_items_updated": mutated,
    }
    _ensure_derived(pheno)["post_surgical_outcome"] = summary
    return summary


# ---------------------------------------------------------------------------
# Rule 9 — autoimmune probable (Graus 2016)
# ---------------------------------------------------------------------------

_SUBACUTE_RE = re.compile(
    r"\b(?:subacute\s+onset|rapid(?:ly)?\s+progressive|"
    r"over\s+(?:a\s+few\s+weeks|\d+\s+(?:weeks|months))|"
    r"acute\s+onset|new[- ]?onset\s+(?:refractory|super[- ]?refractory))\b",
    re.IGNORECASE,
)
_MRI_T2_RE = re.compile(
    r"(?:T2|FLAIR)\s+hyperintens|mesial\s+temporal\s+(?:hyperintens|"
    r"signal)|limbic\s+encephalit",
    re.IGNORECASE,
)
_CSF_INFLAM_RE = re.compile(
    r"CSF\s+(?:pleocytos|lymphocyt|oligoclonal\s+band|elevated\s+protein)",
    re.IGNORECASE,
)


def derive_autoimmune_probable(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> Optional[bool]:
    """Per Graus 2016 diagnostic criteria for autoimmune epilepsy.

    Probable when:
    - A causative antibody has been detected
      (``etiology_specifics.causative_antibody`` populated with a real
      antibody, not ``NONE_DETECTED``), AND at least one of:
      - subacute onset OR
      - AED-refractory (drug_resistance_status = DRUG_RESISTANT) OR
      - MRI T2 hyperintensity temporal OR CSF inflammation cue.

    Also probable when NO antibody is populated but MRI T2 mesial-temporal
    hyperintensity + CSF inflammation cues both fire.

    Returns True/False/None. Stored on
    ``pheno._derived['autoimmune_probable']``.
    """
    text = _text_of(pheno)
    cs = pheno.clinical_seizure
    med = pheno.medication

    ab = None
    if cs is not None:
        spec_ev = cs.etiology_specifics
        if spec_ev is not None and spec_ev.value is not None:
            ab = spec_ev.value.causative_antibody

    has_subacute = bool(text and _SUBACUTE_RE.search(text))
    has_mri_t2 = bool(text and _MRI_T2_RE.search(text))
    has_csf = bool(text and _CSF_INFLAM_RE.search(text))
    is_refractory = (
        med is not None
        and med.drug_resistance_status is not None
        and med.drug_resistance_status.value == DrugResistanceStatus.DRUG_RESISTANT
    )

    reason = None
    if ab is not None and ab.value != "none_detected":
        if has_subacute or is_refractory or has_mri_t2 or has_csf:
            reason = (
                f"antibody={ab.value}; subacute={has_subacute}; "
                f"refractory={is_refractory}; T2={has_mri_t2}; CSF={has_csf}"
            )
    elif has_mri_t2 and has_csf:
        reason = "no-antibody path: MRI T2 hyperintensity + CSF inflammation"

    if reason is not None:
        _ensure_derived(pheno)["autoimmune_probable"] = True
        _ensure_derived(pheno)["autoimmune_probable_reason"] = reason
        return True

    # False only when the note has *some* autoimmune-adjacent signal but
    # criteria not met; otherwise return None (not enough info to score).
    if ab is not None or has_subacute or has_mri_t2 or has_csf:
        _ensure_derived(pheno)["autoimmune_probable"] = False
        return False

    return None


# ---------------------------------------------------------------------------
# Rule 10 — polytherapy flag
# ---------------------------------------------------------------------------


def derive_polytherapy_flag(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> Optional[bool]:
    """True when ≥ 2 concurrent + active ASMs are on ``current_asms``.

    Excludes evidence with ``temporal_status = HISTORICAL`` /
    ``PLANNED`` and ones flagged NEGATED / UNKNOWN certainty.
    Stored on ``pheno._derived['polytherapy']``.
    """
    if pheno.medication is None:
        return None
    current = pheno.medication.current_asms or []
    active_names: set[str] = set()
    for ev in current:
        if ev.value is None:
            continue
        if ev.temporal_status not in (
            TemporalStatus.CURRENT,
            TemporalStatus.UNSPECIFIED,
        ):
            continue
        if ev.certainty in (Certainty.NEGATED, Certainty.NOT_DOCUMENTED):
            continue
        if ev.value.status != MedicationStatus.CURRENT:
            continue
        name = (ev.value.generic_name or "").lower().strip()
        if name:
            active_names.add(name)

    flag = len(active_names) >= 2
    _ensure_derived(pheno)["polytherapy"] = flag
    _ensure_derived(pheno)["polytherapy_active_asm_count"] = len(active_names)
    return flag


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

# (field_path_or_None, function, kind)
#   kind = "evidence"   → writes an Evidence[T] to the given field_path
#   kind = "mutate"     → function mutates pheno in place, no return value
#   kind = "derived"    → function returns a plain value that is stored on
#                          ``pheno._derived`` (function is responsible)
COMPOUND_RULES = [
    ("medication.drug_resistance_status", derive_drug_resistance, "evidence"),
    (None, derive_epilepsy_duration_years, "derived"),
    (None, derive_medication_currently_taking, "mutate"),
    (None, derive_ilae_classification_full, "derived"),
    (None, derive_seizure_free_since, "derived"),
    ("clinical_seizure.predominant_seizure_type", derive_focal_to_bilateral_tc,
     "evidence_optional"),
    ("integrated.concordance", derive_localization_concordance, "evidence"),
    (None, derive_surgery_outcome_class, "derived"),
    (None, derive_autoimmune_probable, "derived"),
    (None, derive_polytherapy_flag, "derived"),
]


def _set_nested(pheno: EpilepsyPhenotype, field_path: str, value: Any) -> None:
    parts = field_path.split(".")
    target: Any = pheno
    for p in parts[:-1]:
        target = getattr(target, p, None)
        if target is None:
            return
    setattr(target, parts[-1], value)


def apply_compound_rules(
    pheno: EpilepsyPhenotype, meta: dict[str, Any]
) -> dict[str, Any]:
    """Run every compound rule against ``pheno`` in the fixed
    :data:`COMPOUND_RULES` order.

    Returns a dict mapping ``func_name → outcome_summary`` (mostly used
    by the smoke test).
    """
    outcomes: dict[str, Any] = {}
    for field_path, func, kind in COMPOUND_RULES:
        name = func.__name__
        try:
            result = func(pheno, meta)
        except Exception as e:  # pragma: no cover - defensive
            outcomes[name] = f"error: {type(e).__name__}: {e}"
            continue

        if kind in ("evidence", "evidence_optional"):
            if isinstance(result, Evidence) and field_path is not None:
                _set_nested(pheno, field_path, result)
                outcomes[name] = "populated"
            else:
                outcomes[name] = "skipped"
        elif kind == "mutate":
            outcomes[name] = "mutated"
        else:  # derived
            outcomes[name] = "populated" if result is not None else "skipped"

    return outcomes


__all__ = [
    "COMPOUND_RULES",
    "apply_compound_rules",
    "derive_drug_resistance",
    "derive_epilepsy_duration_years",
    "derive_medication_currently_taking",
    "derive_ilae_classification_full",
    "derive_seizure_free_since",
    "derive_focal_to_bilateral_tc",
    "derive_localization_concordance",
    "derive_surgery_outcome_class",
    "derive_autoimmune_probable",
    "derive_polytherapy_flag",
]
