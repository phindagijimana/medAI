"""EEG-report sections: grab findings from description and impression, not from history.

SACAR (Maldonado and Harabagiu, J Biomed Inform 2019; ``writing/further_LEO.md`` G1) annotates TUH EEG
reports by section. Findings live in the description and impression; history and medications mention prior
studies and drugs. Clinic letters have no those headers, so this module leaves them unchanged.

A note is treated as an EEG report only when it has ``DESCRIPTION OF THE RECORD``, or both ``INTRODUCTION``
and ``IMPRESSION`` as labeled headers. A lone ``Impression:`` in a clinic letter is not enough.
"""

from __future__ import annotations

import re
from typing import Optional

_HEADER = re.compile(
    r"(?m)^[ \t]*(?P<name>CLINICAL\s+HISTORY|HISTORY|MEDICATIONS|INTRODUCTION|"
    r"TECHNICAL(?:\s+DESCRIPTION)?|DESCRIPTION(?:\s+OF\s+THE\s+RECORD)?|"
    r"IMPRESSION|CLINICAL\s+CORRELATION|FINDINGS)\s*:",
    re.IGNORECASE,
)

_FINDING = frozenset({
    "description", "description of the record", "impression", "clinical correlation", "findings",
})
_SKIP = frozenset({
    "clinical history", "history", "medications", "introduction", "technical", "technical description",
})


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def section_spans(text: str) -> list[tuple[str, int, int]]:
    """``(normalized name, start of body, end of body)`` in document order."""
    hits = list(_HEADER.finditer(text or ""))
    if not hits:
        return []
    out = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        out.append((_norm(m.group("name")), m.end(), end))
    return out


def is_eeg_report(text: str) -> bool:
    names = {n for n, _, _ in section_spans(text)}
    return "description of the record" in names or (
        "introduction" in names and "impression" in names)


def section_at(text: str, start: int) -> Optional[str]:
    for name, lo, hi in section_spans(text):
        if lo <= start < hi:
            return name
    return None


def in_finding_section(text: str, start: int, end: int = -1) -> bool:
    """True unless this is an EEG report and the span sits in history, medications or the introduction."""
    if not is_eeg_report(text):
        return True
    name = section_at(text, start)
    if name is None:
        return True
    if name in _SKIP:
        return False
    return name in _FINDING


__all__ = ["section_spans", "is_eeg_report", "section_at", "in_finding_section"]
