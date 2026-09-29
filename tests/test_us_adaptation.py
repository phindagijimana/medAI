"""Phase 4 tests — UK-to-US normalisation and SOAP section detection.

Covers:

- ``rules.uk_to_us_lexicon.normalize_uk_to_us`` on ~10 spelling pairs and
  5 drug-name pairs (positive + case-preservation cases).
- ``rules.uk_to_us_lexicon.case_aware_replace`` on hand-rolled inputs.
- ``rules.us_note_structure.detect_sections`` on a synthetic SOAP note.
- ``rules.context_config_us.apply_section_context`` on a mock entity list
  to prove ``section_type='PMH'`` propagates onto a seizure entity and
  ``is_historical`` is promoted to True.
- Round-trip idempotency of ``normalize_uk_to_us``.
"""

from __future__ import annotations

import pytest

from rules.uk_to_us_lexicon import (
    DRUG_ALIAS_MAP,
    SPELLING_MAP,
    case_aware_replace,
    normalize_uk_to_us,
    normalize_us_to_uk,
)
from rules.us_note_structure import (
    SECTION_ALIASES,
    Section,
    detect_sections,
    section_at,
)


# ---------------------------------------------------------------------------
# UK → US spelling
# ---------------------------------------------------------------------------

# 12 spelling pairs — covers ae / oe / -our / -ise / -yse / -ll / one-offs.
SPELLING_PAIRS = [
    ("paediatric", "pediatric"),
    ("paediatrics", "pediatrics"),
    ("oesophageal", "esophageal"),
    ("anaesthesia", "anesthesia"),
    ("haemorrhage", "hemorrhage"),
    ("oedema", "edema"),
    ("foetal", "fetal"),
    ("tumour", "tumor"),
    ("behaviour", "behavior"),
    ("generalised", "generalized"),
    ("localisation", "localization"),
    ("analyse", "analyze"),
]


@pytest.mark.parametrize("uk,us", SPELLING_PAIRS)
def test_spelling_map_contains_pair(uk: str, us: str) -> None:
    assert SPELLING_MAP.get(uk) == us


@pytest.mark.parametrize("uk,us", SPELLING_PAIRS)
def test_normalize_spelling(uk: str, us: str) -> None:
    src = f"Note: patient shows {uk} at exam."
    assert normalize_uk_to_us(src) == f"Note: patient shows {us} at exam."


def test_normalize_case_preservation_lower_title_upper() -> None:
    src = "Paediatric review scheduled. paediatric follow-up. PAEDIATRIC ward."
    out = normalize_uk_to_us(src)
    assert "Pediatric review" in out
    assert "pediatric follow-up" in out
    assert "PEDIATRIC ward" in out


def test_normalize_idempotent() -> None:
    src = "Paediatric oesophageal haemorrhage; anaemia; generalised oedema."
    once = normalize_uk_to_us(src)
    twice = normalize_uk_to_us(once)
    assert once == twice


# ---------------------------------------------------------------------------
# UK → US drug names
# ---------------------------------------------------------------------------

DRUG_PAIRS = [
    ("phenobarbitone", "phenobarbital"),
    ("adrenaline", "epinephrine"),
    ("paracetamol", "acetaminophen"),
    ("frusemide", "furosemide"),
    ("salbutamol", "albuterol"),
]


@pytest.mark.parametrize("uk,us", DRUG_PAIRS)
def test_drug_map_contains_pair(uk: str, us: str) -> None:
    assert DRUG_ALIAS_MAP.get(uk) == us


@pytest.mark.parametrize("uk,us", DRUG_PAIRS)
def test_normalize_drug(uk: str, us: str) -> None:
    src = f"Started on {uk} 25 mg BID."
    assert normalize_uk_to_us(src) == f"Started on {us} 25 mg BID."


def test_drug_case_preservation() -> None:
    assert normalize_uk_to_us("Phenobarbitone") == "Phenobarbital"
    assert normalize_uk_to_us("PARACETAMOL 500mg") == "ACETAMINOPHEN 500mg"


def test_round_trip_smoke() -> None:
    # UK -> US -> UK should recover the UK form for entries with a
    # deterministic reverse.
    src = "Paediatric oesophageal haemorrhage."
    us = normalize_uk_to_us(src)
    back = normalize_us_to_uk(us)
    assert back == src


# ---------------------------------------------------------------------------
# case_aware_replace helper
# ---------------------------------------------------------------------------

def test_case_aware_replace_lower() -> None:
    assert case_aware_replace("cats meow", "cats", "dogs") == "dogs meow"


def test_case_aware_replace_title() -> None:
    assert case_aware_replace("Cats meow", "cats", "dogs") == "Dogs meow"


def test_case_aware_replace_upper() -> None:
    assert case_aware_replace("CATS MEOW", "cats", "dogs") == "DOGS MEOW"


def test_case_aware_replace_word_boundary() -> None:
    # Should not eat 'category' — 'cat' with boundary is safe.
    assert case_aware_replace("category of cat", "cat", "dog") == "category of dog"


# ---------------------------------------------------------------------------
# SOAP section detection
# ---------------------------------------------------------------------------

SYNTHETIC_SOAP = (
    "Patient: John Doe\n"
    "\n"
    "HPI: 45yo M with intractable focal seizures for 10 years.\n"
    "\n"
    "PMH: seizure disorder, hypertension.\n"
    "Migraine.\n"
    "\n"
    "MEDICATIONS:\n"
    "- levetiracetam 500 mg BID\n"
    "- lamotrigine 100 mg BID\n"
    "\n"
    "FAMILY HISTORY: mother with epilepsy.\n"
    "\n"
    "ASSESSMENT: drug-resistant focal epilepsy.\n"
    "\n"
    "PLAN: consider vagal nerve stimulator.\n"
)


def test_detect_sections_finds_all_synthetic_headers() -> None:
    sections = detect_sections(SYNTHETIC_SOAP)
    names = [s.name for s in sections]
    assert "HPI" in names
    assert "PMH" in names
    assert "MEDICATIONS" in names
    assert "FAMILY_HISTORY" in names
    assert "ASSESSMENT" in names
    assert "PLAN" in names
    assert len(sections) >= 6


def test_detect_sections_document_order() -> None:
    sections = detect_sections(SYNTHETIC_SOAP)
    starts = [s.char_start for s in sections]
    assert starts == sorted(starts)


def test_detect_sections_empty_doc() -> None:
    assert detect_sections("") == []


def test_detect_sections_no_headers_returns_empty() -> None:
    # A free-form letter with no canonical header should return no sections
    # (callers treat that as one implicit 'unknown' region).
    doc = "Dear colleague, patient has generalised epilepsy. Regards, Dr X."
    assert detect_sections(doc) == []


def test_section_at_within_pmh_range() -> None:
    sections = detect_sections(SYNTHETIC_SOAP)
    pmh = next(s for s in sections if s.name == "PMH")
    # The word 'seizure' appears inside PMH.
    idx = SYNTHETIC_SOAP.index("seizure disorder")
    assert pmh.char_start <= idx < pmh.char_end
    assert section_at(sections, idx) == "PMH"


# ---------------------------------------------------------------------------
# Section-scope context override (Phase 4 §3)
# ---------------------------------------------------------------------------

class _MockEntity:
    """Duck-typed stand-in for :class:`LinkedEntity` — attribute access is
    all the assembler and section-scope helper require."""

    def __init__(self, text: str, start: int, end: int) -> None:
        self.text = text
        self.char_start = start
        self.char_end = end
        self.is_negated = False
        self.is_historical = False
        self.is_hypothetical = False
        self.is_family = False
        self.section_type: str | None = None


def test_section_type_pmh_propagates_and_promotes_historical() -> None:
    from rules.context_config_us import apply_section_context

    sections = detect_sections(SYNTHETIC_SOAP)
    # Locate the 'seizure' mention inside PMH.
    surface = "seizure disorder"
    start = SYNTHETIC_SOAP.index(surface)
    end = start + len(surface)
    ent = _MockEntity(surface, start, end)

    n = apply_section_context([ent], sections)
    assert ent.section_type == "PMH"
    assert ent.is_historical is True
    assert n >= 1


def test_section_type_family_history_promotes_family_flag() -> None:
    from rules.context_config_us import apply_section_context

    sections = detect_sections(SYNTHETIC_SOAP)
    surface = "mother with epilepsy"
    start = SYNTHETIC_SOAP.index(surface)
    end = start + len(surface)
    ent = _MockEntity(surface, start, end)

    apply_section_context([ent], sections)
    assert ent.section_type == "FAMILY_HISTORY"
    assert ent.is_family is True
    assert ent.is_historical is True


def test_section_type_plan_promotes_hypothetical() -> None:
    from rules.context_config_us import apply_section_context

    sections = detect_sections(SYNTHETIC_SOAP)
    surface = "vagal nerve stimulator"
    start = SYNTHETIC_SOAP.index(surface)
    end = start + len(surface)
    ent = _MockEntity(surface, start, end)

    apply_section_context([ent], sections)
    assert ent.section_type == "PLAN"
    assert ent.is_hypothetical is True


def test_section_defaults_do_not_demote() -> None:
    """When sentence-scope ConText already flagged ``is_negated=True``,
    a section-scope pass must not clear it, and must not touch flags it
    doesn't own (``is_negated`` is never in SECTION_SCOPE_OVERRIDES)."""
    from rules.context_config_us import apply_section_context

    sections = detect_sections(SYNTHETIC_SOAP)
    surface = "seizure disorder"
    start = SYNTHETIC_SOAP.index(surface)
    end = start + len(surface)
    ent = _MockEntity(surface, start, end)
    ent.is_negated = True

    apply_section_context([ent], sections)
    assert ent.section_type == "PMH"
    assert ent.is_negated is True  # untouched
    assert ent.is_historical is True  # promoted


# ---------------------------------------------------------------------------
# Section alias coverage
# ---------------------------------------------------------------------------

def test_section_aliases_include_expected_canonical_keys() -> None:
    """Every canonical key called out in the Phase 4 plan must exist."""
    expected = {
        "HPI", "PMH", "PSH", "MEDICATIONS", "ALLERGIES", "ROS", "PE",
        "LABS", "ASSESSMENT", "PLAN", "IMPRESSION", "RECOMMENDATIONS",
        "FAMILY_HISTORY", "SOCIAL_HISTORY",
    }
    missing = expected - set(SECTION_ALIASES.keys())
    assert not missing, f"Missing canonical section keys: {missing}"
