"""Note-author type from the signature block (Ojemann et al. 2025; ``writing/further_LEO.md`` U1).

Penn found LLM seizure-outcome accuracy differed on epileptologist vs general-neurologist notes. LEO should
report the same split when the author is written. Only the closing block is read (last 12 non-empty lines, or
from ``Yours``), so a plan to "ask the epilepsy nurse" in the body does not set the author.
"""

from __future__ import annotations

import re
from typing import Optional

EPILEPTOLOGIST = "epileptologist"
NURSE = "specialist_nurse"
TRAINEE = "trainee"
OTHER = "other"
UNKNOWN = "unknown"

_YOURS = re.compile(r"(?im)^[ \t]*yours\b")
_EPI = re.compile(
    r"\b(?:consultant\s+(?:neurologist|in\s+epilepsy)|epileptologist|consultant\s+epilepsy)\b", re.I)
_NURSE = re.compile(r"\b(?:epilepsy\s+(?:specialist\s+)?nurse|specialist\s+nurse|epilepsy\s+CNS)\b", re.I)
_TRAINEE = re.compile(
    r"\b(?:specialty\s+trainee|specialist\s+trainee|registrar|resident|fellow(?:\s+in\s+epilepsy)?)\b", re.I)
_OTHER = re.compile(r"\b(?:general\s+neurologist|general\s+practitioner|\bGP\b|physician\s+associate)\b", re.I)


_PLAN = re.compile(r"\b(?:ask|contact|see|refer|copy|cc|will)\b", re.I)


def _closing(text: str) -> str:
    text = text or ""
    m = list(_YOURS.finditer(text))
    if m:
        return text[m[-1].start():]
    # No "Yours": keep only short trailing lines (a signature), not clinic prose.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(ln for ln in lines[-8:] if len(ln) <= 60 and not _PLAN.search(ln))


def note_author(text: str) -> str:
    """One of epileptologist / specialist_nurse / trainee / other / unknown."""
    block = _closing(text)
    if _EPI.search(block):
        return EPILEPTOLOGIST
    if _NURSE.search(block):
        return NURSE
    if _TRAINEE.search(block):
        return TRAINEE
    if _OTHER.search(block):
        return OTHER
    return UNKNOWN


def author_label(text: str) -> Optional[str]:
    a = note_author(text)
    return None if a == UNKNOWN else a


__all__ = ["note_author", "author_label", "EPILEPTOLOGIST", "NURSE", "TRAINEE", "OTHER", "UNKNOWN"]
