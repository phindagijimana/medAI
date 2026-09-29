"""
status_epilepticus.py — Status-epilepticus history extraction (bool).

Fields populated
----------------
- ``clinical_seizure.status_epilepticus_history``  (Evidence[bool])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/seizurechange.jape``    — mentions status epilepticus as a distinct
                                    seizure event category.
- ``jape/FebrileSeizures.jape``  — status vs febrile-status disambiguation.
- ``jape/SeizureMentions.jape``  — SE surface-form collection.
- ``Groovy/Diagnosis.groovy``    — SE emitted alongside seizure type.

Also draws on:
- Trinka E et al. 2015 (Epilepsia 56:1515-23): ILAE operational definition
  of status epilepticus, subtypes (convulsive vs non-convulsive).
- Neurocritical Care Society 2012 guidelines (Brophy et al.).

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. Direct surface-form match on "status epilepticus" (variants: "SE",
   "status", "NCSE", "CSE"). MedCAT may or may not link this depending
   on the CDB; the rule works on raw regex to guarantee coverage.
2. Subtype detection (not exposed in current schema field, but recorded
   in evidence_text): convulsive vs non-convulsive vs focal-motor status.
3. History vs current SE: current-episode SE ("presented in status") is
   also True — the schema field is a general "ever had SE" bool.
4. Negation-aware (sentence-scoped): "no history of status epilepticus"
   → False. "denies status epilepticus" → False.
5. ConText — family history of SE ("mother had SE") → skip.

Cite: Trinka et al. 2015; Fonferko-Shadrach et al. 2019; 2024.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import Certainty, TemporalStatus
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Positive SE mentions — surface forms.
# Note: bare "SE" is deliberately excluded to avoid false positives
# on random two-letter tokens; the abbreviations NCSE / CSE require
# a following qualifier to fire.
_SE_POS = re.compile(
    r"\bstatus\s+epilepticus\b|"
    r"\bconvulsive\s+status\b|\bnon[- ]?convulsive\s+status\b|"
    r"\bfebrile\s+status\b|"
    r"\b(?:NCSE|CSE)\b(?:\s+(?:history|episode|admission|admitted))?|"
    r"episode\s+of\s+status\s+epilepticus\b|"
    r"presented\s+in\s+status\s+epilepticus\b",
    re.IGNORECASE,
)

# Explicit negation of SE — must precede a status-epilepticus phrase.
_SE_NEG = re.compile(
    r"\b(?:no|denies?|without|absent|never\s+had|no\s+history\s+of|"
    r"not\s+had|no\s+episodes?\s+of|no\s+evidence\s+of)\s+"
    r"(?:previous\s+|prior\s+|any\s+)?"
    r"(?:convulsive\s+|non[- ]?convulsive\s+|febrile\s+)?"
    r"status\s+epilepticus\b",
    re.IGNORECASE,
)

# Family-history clause — skip SE mentions within.
_FAMILY_CLAUSE = re.compile(
    r"\b(?:father|mother|brother|sister|sibling|uncle|aunt|grandmother|"
    r"grandfather|cousin|son|daughter|parent|family\s+history)\b",
    re.IGNORECASE,
)


def _find_sentence_bounds(text: str, char: int) -> tuple[int, int]:
    """Return (start, end) char offsets of the sentence enclosing ``char``."""
    sent_start = 0
    for m in re.finditer(r"[.!?;\n]", text[:char]):
        sent_start = m.end()
    m = re.search(r"[.!?;\n]", text[char:])
    sent_end = char + m.start() if m else len(text)
    return sent_start, sent_end


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class StatusEpilepticusHistoryRule(BaseFieldRule):
    """Populate ``clinical_seizure.status_epilepticus_history``.

    Emits True on a non-negated non-family SE mention; False on an
    explicit negation ("no history of status epilepticus"); None
    otherwise.
    """

    field_name = "clinical_seizure.status_epilepticus_history"
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

        # 1. Explicit negation wins — check first so we don't accept a
        # positive mention that immediately follows a "no history of".
        for m in _SE_NEG.finditer(text):
            return Evidence[bool](
                value=False,
                certainty=Certainty.DEFINITE,
                temporal_status=TemporalStatus.HISTORICAL,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )

        # 2. Positive SE mention → True. Skip family-history clauses.
        for m in _SE_POS.finditer(text):
            sent_start, sent_end = _find_sentence_bounds(text, m.start())
            sent = text[sent_start:sent_end]
            if _FAMILY_CLAUSE.search(sent):
                continue
            # Ensure it's not part of a negation string missed by _SE_NEG.
            pre = text[max(0, m.start() - 40):m.start()].lower()
            if re.search(r"\b(?:no|without|denies?|never|not)\b\s*$", pre):
                continue
            # Historical is the norm for "history of SE" phrasing.
            is_hist = bool(re.search(
                r"\b(?:history\s+of|previous|prior|had\s+a?\s*|"
                r"in\s+the\s+past)\b", pre + m.group(0), re.IGNORECASE,
            ))
            temporal = TemporalStatus.HISTORICAL if is_hist else TemporalStatus.CURRENT
            return Evidence[bool](
                value=True,
                certainty=Certainty.DEFINITE,
                temporal_status=temporal,
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

register_rule(StatusEpilepticusHistoryRule())

__all__ = ["StatusEpilepticusHistoryRule"]
