"""US clinical note structure detector (SOAP + section headers).

Phase 4 deliverable §2.  Detects standard section headers in US-style
clinical notes (SOAP notes, admission H&P's, clinic letters, discharge
summaries) using a line-anchored regex over a canonical alias table.

Design
------
- **Line-anchored**: headers must begin on a new line (or the very start
  of the document).  This avoids false positives inside prose ("...the
  patient has no past medical history of hypertension.").
- **Colon-anchored** header text: the recognised aliases are followed
  by a colon, a newline, or (for short shorthand like ``HPI:``) either.
- **Case-insensitive** match, but the returned :attr:`Section.header_text`
  preserves the original casing so downstream reports show what the
  clinician wrote.
- **Non-overlapping**: sections are cut into contiguous ``[start, end)``
  spans; the first section covers everything from its header to the
  next header, the last runs to end-of-document.  A pre-amble region
  before the first header is discarded (not returned as a Section).

Canonical section names
-----------------------
Emitted section ``name`` values are UPPERCASE_SNAKE_CASE canonical keys.
The aliases table maps them to the surface forms we accept:

    HPI, PMH, PSH, MEDICATIONS, ALLERGIES, ROS, PE, NEURO_EXAM, LABS,
    IMAGING, ASSESSMENT, PLAN, IMPRESSION, RECOMMENDATIONS,
    FAMILY_HISTORY, SOCIAL_HISTORY, DIAGNOSTIC_STUDIES.

Notes on aliasing:

- ``HISTORY OF PRESENT ILLNESS`` and ``HPI`` both map to ``HPI``.
- ``IMPRESSION`` is treated as an ASSESSMENT synonym in some templates
  but kept as its own canonical key here because F-S letters commonly
  use "Impression:" as a standalone diagnosis line.
- ``NEURO EXAM`` and ``NEUROLOGIC EXAMINATION`` map to ``NEURO_EXAM``,
  which is treated as a specialisation of ``PE``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

SECTION_ALIASES: dict[str, list[str]] = {
    "HPI": [
        "HPI",
        "HISTORY OF PRESENT ILLNESS",
        "PRESENT ILLNESS",
        "PRESENTING COMPLAINT",     # UK synonym still commonly seen
        "HISTORY",                  # last-resort catch-all
        "HX",                       # MTSamples-style transcription abbreviation
        "CC",                       # chief complaint
        "COURSE",                   # clinical course narrative
        "CLINICAL COURSE",
        "HOSPITAL COURSE",
    ],
    "PMH": [
        "PMH",
        "PAST MEDICAL HISTORY",
        "MEDICAL HISTORY",
        "PAST HISTORY",
        "PMHX",                     # MTSamples/US variant
        "BIRTH HX",                 # MTSamples-specific perinatal history
        "BIRTH HISTORY",
    ],
    "PSH": [
        "PSH",
        "PAST SURGICAL HISTORY",
        "SURGICAL HISTORY",
    ],
    "MEDICATIONS": [
        "MEDICATIONS",
        "MEDS",
        "CURRENT MEDICATIONS",
        "HOME MEDICATIONS",
        "CURRENT MEDICATION",
        "CURRENT ANTIEPILEPTIC MEDICATION",
        "CURRENT ANTISEIZURE MEDICATION",
        "CURRENT ASM",
        "ACTIVE MEDICATIONS",
        "MEDICATION LIST",
    ],
    "ALLERGIES": [
        "ALLERGIES",
        "NKDA",
        "NO KNOWN DRUG ALLERGIES",
        "DRUG ALLERGIES",
    ],
    "ROS": [
        "ROS",
        "REVIEW OF SYSTEMS",
    ],
    "PE": [
        "PE",
        "PHYSICAL EXAM",
        "PHYSICAL EXAMINATION",
        "EXAM",
        "EXAMINATION",
    ],
    "NEURO_EXAM": [
        "NEURO EXAM",
        "NEUROLOGIC EXAM",
        "NEUROLOGICAL EXAM",
        "NEUROLOGICAL EXAMINATION",
        "NEURO EXAMINATION",
    ],
    "LABS": [
        "LABS",
        "LABORATORY",
        "LABORATORY DATA",
        "LABORATORY RESULTS",
        "LAB RESULTS",
    ],
    "IMAGING": [
        "IMAGING",
        "RADIOLOGY",
        "MRI",
        "MRI BRAIN",
        "CT",
        "CT HEAD",
        "EEG",
        "IMAGING STUDIES",
    ],
    "ASSESSMENT": [
        "ASSESSMENT",
        "A/P",
        "ASSESSMENT AND PLAN",
        "ASSESSMENT/PLAN",
        "CLINICAL ASSESSMENT",
    ],
    "IMPRESSION": [
        "IMPRESSION",
        "CLINICAL IMPRESSION",
        "DIAGNOSIS",
        "DIAGNOSES",
    ],
    "PLAN": [
        "PLAN",
        "TREATMENT PLAN",
        "MANAGEMENT PLAN",
    ],
    "RECOMMENDATIONS": [
        "RECOMMENDATIONS",
        "RECOMMENDATION",
    ],
    "FAMILY_HISTORY": [
        "FAMILY HISTORY",
        "FH",
        "FAM HX",
        "FAMILY HX",
        "FHX",
    ],
    "SOCIAL_HISTORY": [
        "SOCIAL HISTORY",
        "SH",
        "SOC HX",
        "SOCIAL HX",
        "SHX",
    ],
    "DIAGNOSTIC_STUDIES": [
        "DIAGNOSTIC STUDIES",
        "DIAGNOSTICS",
        "INVESTIGATIONS",
        "STUDIES",
    ],
}


# Context defaults applied to entities appearing inside a section.  These
# are used by :mod:`rules.context_config_us` to override medspaCy ConText
# results when the section itself signals stronger info than any
# per-sentence trigger.
#
# Keys:
#   temporal:    'current' | 'historical'
#   experiencer: 'patient' | 'family'
#   certainty:   'affirmed' | 'negated' | 'uncertain' | None
#   is_negated / is_historical / is_family override flags for the assembler.
SECTION_CONTEXT_DEFAULT: dict[str, dict[str, object]] = {
    "HPI":                {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "PMH":                {"temporal": "historical", "experiencer": "patient",
                           "is_historical": True,    "is_family": False},
    "PSH":                {"temporal": "historical", "experiencer": "patient",
                           "is_historical": True,    "is_family": False},
    "FAMILY_HISTORY":     {"temporal": "historical", "experiencer": "family",
                           "is_historical": True,    "is_family": True},
    "SOCIAL_HISTORY":     {"temporal": "historical", "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "MEDICATIONS":        {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "ALLERGIES":          {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "ROS":                {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "PE":                 {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "NEURO_EXAM":         {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "LABS":               {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "IMAGING":            {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "DIAGNOSTIC_STUDIES": {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "ASSESSMENT":         {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "IMPRESSION":         {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "PLAN":               {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
    "RECOMMENDATIONS":    {"temporal": "current",    "experiencer": "patient",
                           "is_historical": False,   "is_family": False},
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """One detected section span.

    Attributes
    ----------
    name
        Canonical UPPERCASE_SNAKE_CASE section key (see
        :data:`SECTION_ALIASES`).
    char_start
        Inclusive start of the section body (i.e. the character AFTER
        the header line).
    char_end
        Exclusive end of the section body (start of the next section
        header, or ``len(text)``).
    header_text
        The original header string as it appeared in the source (before
        the terminating colon / newline).
    header_start
        Inclusive start of the header itself.
    header_end
        Exclusive end of the header (== ``char_start``).
    """

    name: str
    char_start: int
    char_end: int
    header_text: str
    header_start: int = -1
    header_end: int = -1


# ---------------------------------------------------------------------------
# Regex construction
# ---------------------------------------------------------------------------

def _build_header_re() -> re.Pattern[str]:
    """Compile the single regex used to locate any section header.

    A header is one of the aliases, on its own line (or the start of the
    document), optionally followed by a colon.  Trailing content on the
    same line (after the colon) is allowed but not required.
    """
    # Longest alternatives first so 'HISTORY OF PRESENT ILLNESS' wins
    # over 'HISTORY' on the same line.
    aliases: list[str] = []
    for canon, forms in SECTION_ALIASES.items():
        for f in forms:
            aliases.append(f)
    aliases.sort(key=len, reverse=True)
    alt = "|".join(re.escape(a) for a in aliases)
    # Anchors:
    #   (?:^|\n)              — start of doc or after a newline
    #   [ \t]*                — optional leading whitespace / indent
    #   (?P<hdr>ALIAS)        — the alias, case-insensitive
    #   [ \t]*                — trailing whitespace before terminator
    #   (?::|(?=\n)|(?=$))    — colon OR end-of-line OR end-of-doc
    #
    # Requiring EITHER a colon OR an end-of-line lookahead keeps ordinary
    # sentences like "The patient has a history of seizures." out of the
    # match — they fail on the (?::|(?=\n)|$) branch because no colon and
    # more text follows on the same line.
    pat = (
        r"(?:^|\n)[ \t]*"
        rf"(?P<hdr>{alt})"
        r"[ \t]*"
        r"(?::|(?=\n)|(?=$))"
    )
    return re.compile(pat, flags=re.IGNORECASE)


_HEADER_RE: re.Pattern[str] = _build_header_re()


# alias -> canonical name (upper-case lookup)
_ALIAS_TO_CANON: dict[str, str] = {}
for _canon, _forms in SECTION_ALIASES.items():
    for _f in _forms:
        _ALIAS_TO_CANON[_f.upper()] = _canon


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_sections(text: str) -> list[Section]:
    """Return the non-overlapping section spans found in ``text``.

    Order of returned sections matches their document order.  If the
    document has no recognisable header, an empty list is returned.

    An implicit ``PREAMBLE`` region (text before the first header) is NOT
    returned as a Section; callers who need to classify pre-header
    entities can detect that via :func:`section_at` returning ``None``.
    """
    if not text:
        return []

    hits: list[tuple[str, int, int, str]] = []  # (canon, hdr_start, hdr_end, hdr_text)
    for m in _HEADER_RE.finditer(text):
        hdr = m.group("hdr")
        canon = _ALIAS_TO_CANON.get(hdr.upper())
        if canon is None:
            continue  # defensive; the regex is built from the same table
        # hdr_start = char index of the alias itself (not the preceding \n)
        hdr_start = m.start("hdr")
        # hdr_end = one past the terminating ':' if present, else end of alias
        # We approximate by using m.end() which is the end of the whole match
        # (alias + optional colon).
        hdr_end = m.end()
        hits.append((canon, hdr_start, hdr_end, hdr))

    if not hits:
        return []

    sections: list[Section] = []
    for i, (canon, h_start, h_end, hdr_text) in enumerate(hits):
        body_start = h_end
        # Skip a single trailing space or newline just after the header/colon
        while body_start < len(text) and text[body_start] in (" ", "\t"):
            body_start += 1
        # Consume at most one newline so the body starts on the content line.
        if body_start < len(text) and text[body_start] == "\n":
            body_start += 1
        body_end = hits[i + 1][1] if i + 1 < len(hits) else len(text)
        # A prior section that continued past our header should stop at
        # h_start; we already handle that because we use next-header start
        # for the previous section's end.  Guard against overlap.
        if body_end < body_start:
            body_end = body_start
        sections.append(Section(
            name=canon,
            char_start=body_start,
            char_end=body_end,
            header_text=hdr_text,
            header_start=h_start,
            header_end=h_end,
        ))
    return sections


def section_at(sections: list[Section], char_offset: int) -> Optional[str]:
    """Return the canonical section name covering ``char_offset``, or ``None``.

    Binary search would be nicer but section lists are tiny (~10 items);
    linear scan is fine and keeps the code obvious.
    """
    for sec in sections:
        if sec.char_start <= char_offset < sec.char_end:
            return sec.name
    return None


def section_default_context(section_name: Optional[str]) -> dict[str, object]:
    """Return the ConText override dict for a given section.

    If ``section_name`` is ``None`` (entity fell outside any detected
    section) the default is an empty dict so callers leave medspaCy
    results untouched.
    """
    if section_name is None:
        return {}
    return dict(SECTION_CONTEXT_DEFAULT.get(section_name, {}))


def iter_section_types(sections: list[Section]) -> Iterable[str]:
    """Yield the distinct canonical section names in encounter order."""
    seen: set[str] = set()
    for s in sections:
        if s.name not in seen:
            seen.add(s.name)
            yield s.name


__all__ = [
    "Section",
    "SECTION_ALIASES",
    "SECTION_CONTEXT_DEFAULT",
    "detect_sections",
    "section_at",
    "section_default_context",
    "iter_section_types",
]
