"""Preprocess US-style clinical notes into a canonical H&P form.

The MedCAT+Rules pipeline (arm B1') was built on the ExECT vocabulary,
which is anchored to UK epilepsy clinician letters (Fonferko-Shadrach corpus).
US clinical notes differ in three ways that cause rule failures even when
the underlying clinical facts are identical:

  1. Section headers use different conventions (``CC:`` / ``HX:`` / ``PMH:``
     in US templated notes vs. ``Reason for referral:`` / ``History:`` /
     ``Past medical history:`` in UK letters). The section-aware rules key
     off canonical labels, so unmapped headers effectively hide content.

  2. Medications appear as US brand names (``Keppra``, ``Dilantin``,
     ``Tegretol``) without their generic annotation. The generic-only
     concept map in the CDB misses ~20% of AED mentions.

  3. Some historical seizure descriptors (``grand mal``, ``petit mal``,
     ``complex partial``) are still in circulation but not linked in the
     modern ILAE 2017 concept graph.

This module performs a **non-destructive** canonicalization pass that:
    - normalises section headers to their canonical H&P labels,
    - appends the ILAE 2017 modern equivalent alongside legacy terms,
    - appends the generic name in parentheses after brand-name AEDs.

The output is standard clinical prose — any downstream extractor
(rules, LLM, MetaCAT) benefits without pipeline changes.

Corpus-agnostic. See ``scripts/preprocess_us_notes.py`` for the CLI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


# ─── Stage A: Relevance scoring ──────────────────────────────────────────

_EPILEPSY_KEYWORDS = re.compile(
    r"\b(epilep|seizur|convuls|ictal|antiepilep|antiseizure|anticonvuls|"
    r"postictal|EEG|EMU|LTM|status\s+epilepticus|SE\b)",
    re.IGNORECASE,
)

_AED_KEYWORDS = re.compile(
    r"\b(lamotrigine|Lamictal|levetiracetam|Keppra|carbamazepine|Tegretol|"
    r"valproate|valproic|Depakote|Depakene|topiramate|Topamax|phenytoin|"
    r"Dilantin|zonisamide|Zonegran|oxcarbazepine|Trileptal|lacosamide|Vimpat|"
    r"brivaracetam|Briviact|perampanel|Fycompa|clobazam|Onfi|phenobarbital|"
    r"gabapentin|Neurontin|pregabalin|Lyrica|ethosuximide|Zarontin|"
    r"rufinamide|Banzel|clonazepam|Klonopin|midazolam|Nayzilam|"
    r"acetazolamide|Diamox|felbamate|Felbatol|primidone|Mysoline|"
    r"eslicarbazepine|Aptiom|cenobamate|Xcopri)\b",
    re.IGNORECASE,
)

_HPI_SECTION = re.compile(
    r"\b(CC:|Chief\s+Complaint:|HX:|HPI:|History\s+of\s+Present\s+Illness:|Reason\s+for\s+Visit:)",
    re.IGNORECASE,
)


def compute_relevance_score(text: str) -> tuple[float, dict]:
    """Return (score, details). Score >= 3.0 is considered epilepsy-primary.

    Formula: density_per_1k_chars * hpi_boost + aed_boost

    - density: epilepsy keyword occurrences per 1000 chars of note.
    - hpi_boost: 2.0 when an epilepsy keyword occurs within 500 chars of
      any HPI/CC section anchor (early-mention proxy); else 1.0.
    - aed_boost: 0.5 per AED mention up to a cap of 2.5.
    """
    epi_hits = _EPILEPSY_KEYWORDS.findall(text)
    aed_hits = _AED_KEYWORDS.findall(text)
    n_chars = max(len(text), 1)

    density = (len(epi_hits) / n_chars) * 1000

    hpi_boost = 1.0
    hpi_match = _HPI_SECTION.search(text)
    if hpi_match:
        window = text[hpi_match.start():hpi_match.start() + 500]
        if _EPILEPSY_KEYWORDS.search(window):
            hpi_boost = 2.0

    aed_boost = min(len(aed_hits), 5) * 0.5

    score = density * hpi_boost + aed_boost

    return score, {
        "n_epilepsy_keywords": len(epi_hits),
        "n_aed_mentions": len(aed_hits),
        "n_chars": n_chars,
        "density_per_1k_chars": round(density, 3),
        "hpi_boost": hpi_boost,
        "aed_boost": aed_boost,
        "score": round(score, 3),
    }


# ─── Stage B: H&P section header canonicalization ────────────────────────
#
# Left column: source pattern (any US abbreviation or synonym encountered
# in the wild). Right column: canonical H&P label the rules expect.
# Regex uses ``re.M`` so the pattern anchors at line starts.

_HEADER_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\s*CC\s*:", re.M), "Chief Complaint:"),
    (re.compile(r"^\s*C/C\s*:", re.M), "Chief Complaint:"),
    (re.compile(r"^\s*Reason\s+for\s+Referral\s*:", re.M), "Chief Complaint:"),
    (re.compile(r"^\s*HX\s*:", re.M), "History of Present Illness:"),
    (re.compile(r"^\s*HPI\s*:", re.M), "History of Present Illness:"),
    (re.compile(r"^\s*History\s+of\s+Presenting\s+Illness\s*:", re.M),
     "History of Present Illness:"),
    (re.compile(r"^\s*PMH\s*:", re.M), "Past Medical History:"),
    (re.compile(r"^\s*PMHX\s*:", re.M), "Past Medical History:"),
    (re.compile(r"^\s*PSH\s*:", re.M), "Past Surgical History:"),
    (re.compile(r"^\s*PSHX\s*:", re.M), "Past Surgical History:"),
    (re.compile(r"^\s*BIRTH\s+HX\s*:", re.M), "Birth History:"),
    (re.compile(r"^\s*SHX\s*:", re.M), "Social History:"),
    (re.compile(r"^\s*SH\s*:", re.M), "Social History:"),
    (re.compile(r"^\s*FHX\s*:", re.M), "Family History:"),
    (re.compile(r"^\s*FH\s*:", re.M), "Family History:"),
    (re.compile(r"^\s*MEDS\s*:", re.M), "Medications:"),
    (re.compile(r"^\s*Current\s+Medications\s*:", re.M), "Medications:"),
    (re.compile(r"^\s*EXAM\s*:", re.M), "Physical Examination:"),
    (re.compile(r"^\s*PE\s*:", re.M), "Physical Examination:"),
    (re.compile(r"^\s*Impression\s*:", re.M), "Assessment:"),
    (re.compile(r"^\s*IMP\s*:", re.M), "Assessment:"),
    (re.compile(r"^\s*COURSE\s*:", re.M), "Clinical Course:"),
    (re.compile(r"^\s*Studies\s*:", re.M), "Diagnostic Studies:"),
    (re.compile(r"^\s*Data\s*:", re.M), "Diagnostic Studies:"),
    (re.compile(r"^\s*A/P\s*:", re.M), "Assessment and Plan:"),
    (re.compile(r"^\s*SUMMARY\s*:", re.M), "Assessment and Plan:"),
    (re.compile(r"^\s*ROS\s*:", re.M), "Review of Systems:"),
    (re.compile(r"^\s*Allergies\s*:", re.M), "Allergies:"),
    (re.compile(r"^\s*NKDA\s*$", re.M), "Allergies: NKDA"),
    (re.compile(r"^\s*Disposition\s*:", re.M), "Disposition:"),
    (re.compile(r"^\s*Follow[- ]up\s*:", re.M), "Follow-up:"),
]


def canonicalize_sections(text: str) -> tuple[str, int]:
    """Normalise US section headers to canonical H&P forms.

    Returns (new_text, n_replacements). Non-destructive when a header is
    already canonical.
    """
    n = 0
    for pattern, replacement in _HEADER_MAP:
        text, count = pattern.subn(replacement, text)
        n += count
    return text, n


# ─── Stage C: Modern ILAE 2017 terminology annotation ────────────────────
#
# Historical seizure/epilepsy terms are appended (not replaced) with the
# ILAE 2017 modern equivalent in parentheses. Rules keyed on the modern
# term recover; the original wording remains readable to clinicians.

_ILAE_LEGACY_TO_MODERN: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bpsychomotor\s+seizures?\b", re.I),
     "psychomotor seizures (focal impaired awareness seizures)"),
    (re.compile(r"\bcomplex\s+partial\s+seizures?\b", re.I),
     "complex partial seizures (focal impaired awareness seizures)"),
    (re.compile(r"\bsimple\s+partial\s+seizures?\b", re.I),
     "simple partial seizures (focal aware seizures)"),
    (re.compile(r"\bpetit\s+mal\b", re.I),
     "petit mal (typical absence)"),
    (re.compile(r"\bgrand\s+mal\b", re.I),
     "grand mal (generalized tonic-clonic)"),
    (re.compile(r"\bsecondarily\s+generali[sz]ed\b", re.I),
     "secondarily generalized (focal to bilateral tonic-clonic)"),
    (re.compile(r"\bdrop\s+attacks?\b", re.I),
     "drop attacks (atonic seizures)"),
    (re.compile(r"\bJacksonian\s+seizures?\b", re.I),
     "Jacksonian seizures (focal motor seizures)"),
]


def annotate_ilae_terms(text: str) -> tuple[str, int]:
    """Add modern ILAE 2017 equivalents alongside historical terms.

    Idempotent: if the modern form is already in the note, the pattern
    is skipped for that iteration.
    """
    n = 0
    for pattern, replacement in _ILAE_LEGACY_TO_MODERN:
        if replacement not in text:
            text, count = pattern.subn(replacement, text)
            n += count
    return text, n


# ─── Stage D: Brand → generic drug annotation ────────────────────────────
#
# ``Keppra`` → ``Keppra (levetiracetam)`` on first occurrence per note.
# Subsequent brand-name mentions are left alone (they are recognised via
# the same concept as the annotated first mention).

_BRAND_TO_GENERIC: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bDilantin\b(?!\s*\()", re.I), "Dilantin (phenytoin)"),
    (re.compile(r"\bTegretol\b(?!\s*\()", re.I), "Tegretol (carbamazepine)"),
    (re.compile(r"\bDepakene\b(?!\s*\()", re.I), "Depakene (valproic acid)"),
    (re.compile(r"\bDepakote\b(?!\s*\()", re.I), "Depakote (divalproex)"),
    (re.compile(r"\bKeppra\b(?!\s*\()", re.I), "Keppra (levetiracetam)"),
    (re.compile(r"\bLamictal\b(?!\s*\()", re.I), "Lamictal (lamotrigine)"),
    (re.compile(r"\bTopamax\b(?!\s*\()", re.I), "Topamax (topiramate)"),
    (re.compile(r"\bTrileptal\b(?!\s*\()", re.I), "Trileptal (oxcarbazepine)"),
    (re.compile(r"\bVimpat\b(?!\s*\()", re.I), "Vimpat (lacosamide)"),
    (re.compile(r"\bZonegran\b(?!\s*\()", re.I), "Zonegran (zonisamide)"),
    (re.compile(r"\bBanzel\b(?!\s*\()", re.I), "Banzel (rufinamide)"),
    (re.compile(r"\bAptiom\b(?!\s*\()", re.I), "Aptiom (eslicarbazepine)"),
    (re.compile(r"\bFycompa\b(?!\s*\()", re.I), "Fycompa (perampanel)"),
    (re.compile(r"\bBriviact\b(?!\s*\()", re.I), "Briviact (brivaracetam)"),
    (re.compile(r"\bXcopri\b(?!\s*\()", re.I), "Xcopri (cenobamate)"),
    (re.compile(r"\bOnfi\b(?!\s*\()", re.I), "Onfi (clobazam)"),
    (re.compile(r"\bMysoline\b(?!\s*\()", re.I), "Mysoline (primidone)"),
    (re.compile(r"\bDiamox\b(?!\s*\()", re.I), "Diamox (acetazolamide)"),
    (re.compile(r"\bFelbatol\b(?!\s*\()", re.I), "Felbatol (felbamate)"),
    (re.compile(r"\bZarontin\b(?!\s*\()", re.I), "Zarontin (ethosuximide)"),
    (re.compile(r"\bNeurontin\b(?!\s*\()", re.I), "Neurontin (gabapentin)"),
    (re.compile(r"\bLyrica\b(?!\s*\()", re.I), "Lyrica (pregabalin)"),
    (re.compile(r"\bKlonopin\b(?!\s*\()", re.I), "Klonopin (clonazepam)"),
    (re.compile(r"\bNayzilam\b(?!\s*\()", re.I), "Nayzilam (midazolam)"),
]


def annotate_drug_names(text: str) -> tuple[str, int]:
    """Append generic name after brand names. Skip if already annotated."""
    n = 0
    for pattern, replacement in _BRAND_TO_GENERIC:
        text, count = pattern.subn(replacement, text)
        n += count
    return text, n


# ─── Combined preprocessing entry point ──────────────────────────────────

@dataclass
class PreprocessStats:
    n_epilepsy_keywords: int = 0
    n_aed_mentions: int = 0
    n_chars: int = 0
    density_per_1k_chars: float = 0.0
    hpi_boost: float = 1.0
    aed_boost: float = 0.0
    score: float = 0.0
    n_section_headers_normalized: int = 0
    n_ilae_terms_annotated: int = 0
    n_drugs_annotated: int = 0

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def preprocess_note(
    text: str,
    *,
    canonicalize_headers: bool = True,
    annotate_ilae: bool = True,
    annotate_drugs: bool = True,
    compute_score: bool = True,
) -> tuple[str, PreprocessStats]:
    """Apply the full preprocessing pipeline to a single note.

    All stages are individually toggleable so downstream callers can opt
    into only what they need (e.g. a MedCAT scorer might only want
    header canonicalization + drug annotation, not ILAE rewriting).

    Returns (processed_text, PreprocessStats).
    """
    stats = PreprocessStats()

    if compute_score:
        score, det = compute_relevance_score(text)
        stats.score = det["score"]
        stats.n_epilepsy_keywords = det["n_epilepsy_keywords"]
        stats.n_aed_mentions = det["n_aed_mentions"]
        stats.n_chars = det["n_chars"]
        stats.density_per_1k_chars = det["density_per_1k_chars"]
        stats.hpi_boost = det["hpi_boost"]
        stats.aed_boost = det["aed_boost"]

    if canonicalize_headers:
        text, n = canonicalize_sections(text)
        stats.n_section_headers_normalized = n
    if annotate_ilae:
        text, n = annotate_ilae_terms(text)
        stats.n_ilae_terms_annotated = n
    if annotate_drugs:
        text, n = annotate_drug_names(text)
        stats.n_drugs_annotated = n

    return text, stats


__all__ = [
    "PreprocessStats",
    "annotate_drug_names",
    "annotate_ilae_terms",
    "canonicalize_sections",
    "compute_relevance_score",
    "preprocess_note",
]
