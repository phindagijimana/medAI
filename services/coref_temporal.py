"""Coreference + temporal linking for medication status (no new ILAE gazetteer).

Resolves “that drug” / “this medication” to the last ASM mention before it when
the same sentence has a stop/fail cue. “Since then” on a drug sentence marks
historical. Offsets stay on the original note (no rewrite).

Synthetic notes under-test this; real EHR copy-forward needs it. Default callers
opt in via ``resolve_med_deixis`` from the medication rule (narrow, always-on
status pass — not a third reader).
"""

from __future__ import annotations

import re
from typing import Any

_DEIXIS = re.compile(
    r"\b(?:that|this|the)\s+(?:drug|medication|medicine|asm|aed)\b", re.I)
_STOP_FAIL = re.compile(
    r"\b(?:was\s+|were\s+|has\s+been\s+|have\s+been\s+)?stopped\b|"
    r"\bdiscontinued\b|\bfailed\b|\bno longer\b|\boff\b",
    re.I,
)
_SINCE_THEN = re.compile(
    r"\b(?:since then|after that|at that time|years ago|previously)\b", re.I)
_SENT_END = re.compile(r"[.!?;\n]")


def _sentence(text: str, start: int, end: int) -> str:
    s = 0
    for m in _SENT_END.finditer(text[:start]):
        s = m.end()
    m = _SENT_END.search(text, end)
    e = m.start() if m else len(text)
    return text[s:e]


def last_asm_before(entities: list[Any], pos: int, *, window: int = 400) -> Any:
    prev = [e for e in entities
            if getattr(e, "enum_class", None) == "Medication"
            and getattr(e, "char_end", 0) <= pos
            and pos - getattr(e, "char_end", 0) <= window]
    return prev[-1] if prev else None


def resolve_med_deixis(text: str, entities: list[Any]) -> list[Any]:
    """Entities that a stop/fail deixis (“stopped that drug”) refers to."""
    if not text or not entities:
        return []
    out = []
    seen: set[int] = set()
    for m in _DEIXIS.finditer(text):
        sent = _sentence(text, m.start(), m.end())
        if not _STOP_FAIL.search(sent):
            continue
        e = last_asm_before(entities, m.start())
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        out.append(e)
    return out


def sentence_is_historical(text: str, start: int, end: int) -> bool:
    return bool(_SINCE_THEN.search(_sentence(text, start, end)))


__all__ = ["resolve_med_deixis", "sentence_is_historical", "last_asm_before"]
