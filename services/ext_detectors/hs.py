"""HS / FCD mention+NegEx sidecar (clinic-note text, not AutoHS imaging).

Dictionary of MTS / hippocampal sclerosis / FCD + Chapman NegEx. Independent
of ``rules.fields.mri`` (MedCAT + ExECT). Emits True on an affirmed mention
in MRI context; False only on a negated mention when the note also talks
about MRI. Never emits False because MRI was never mentioned.

Detector name: ``hs``.
Paths: ``mri.hippocampal_sclerosis``, ``mri.focal_cortical_dysplasia``.
"""

from __future__ import annotations

import re

from services.chain_llm import FieldItem
from services.ext_detectors.span import (
    NEG_PRE,
    NEG_PSEUDO,
    sentence_window,
    skip_mention,
)

DETECTOR = "hs"

_MRI = re.compile(
    r"\bMRI\b|\bMR\s+brain\b|\bMR\s+imaging\b|"
    r"brain\s+scan|brain\s+imaging|"
    r"\bT1\b|\bT2\b|\bFLAIR\b|\bDWI\b|"
    r"neuroimaging|structural\s+imaging",
    re.I,
)
_HS = re.compile(
    r"hippocampal\s+sclerosis|mesial\s+temporal\s+sclerosis|\bMTS\b|\bHS\b",
    re.I,
)
_FCD = re.compile(
    r"focal\s+cortical\s+dysplasia|\bFCD\b|Palmini|MOGHE",
    re.I,
)


def _item(path: str, value: bool, quote: str, start: int, end: int) -> FieldItem:
    return FieldItem(
        field_path=path,
        module="mri",
        ev={
            "value": value,
            "evidence_text": quote,
            "char_start": start,
            "char_end": end,
            "certainty": "definite",
            "temporal_status": "current",
            "reader": DETECTOR,
        },
        multi=False,
    )


def _near_mri(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 220): min(len(text), end + 220)]
    return bool(_MRI.search(window))


def _affirmed_or_negated(text: str, pat: re.Pattern[str]) -> tuple[str, re.Match] | None:
    """Return ('true'|'false', match) for the first MRI-context mention, else None."""
    for m in pat.finditer(text):
        start, end = m.start(), m.end()
        if not _near_mri(text, start, end):
            continue
        sent, a, _b = sentence_window(text, start, end)
        pre = sent[:a]
        negated = bool(NEG_PRE.search(pre)) and not NEG_PSEUDO.search(pre)
        post = sent[end:]
        if re.search(r"^\s*(?:not\s+(?:seen|identified|present)|absent|negative)\b",
                     post, re.I):
            negated = True
        if negated:
            return "false", m
        if skip_mention(sent, a):
            continue
        return "true", m
    return None


def _quote(text: str, m: re.Match) -> str:
    return re.sub(r"\s+", " ", text[m.start():m.end()].strip())


def extract_hs(text: str) -> list[FieldItem]:
    """HS/FCD bools when the note mentions the finding in MRI context."""
    if not (text or "").strip():
        return []
    note_has_mri = bool(_MRI.search(text))
    out: list[FieldItem] = []
    hs = _affirmed_or_negated(text, _HS)
    if hs is not None:
        kind, m = hs
        if kind == "true":
            out.append(_item("mri.hippocampal_sclerosis", True, _quote(text, m),
                             m.start(), m.end()))
        elif kind == "false" and note_has_mri:
            out.append(_item("mri.hippocampal_sclerosis", False, _quote(text, m),
                             m.start(), m.end()))
    fcd = _affirmed_or_negated(text, _FCD)
    if fcd is not None:
        kind, m = fcd
        if kind == "true":
            out.append(_item("mri.focal_cortical_dysplasia", True, _quote(text, m),
                             m.start(), m.end()))
        elif kind == "false" and note_has_mri:
            out.append(_item("mri.focal_cortical_dysplasia", False, _quote(text, m),
                             m.start(), m.end()))
    return out


__all__ = ["DETECTOR", "extract_hs"]
