"""IED attributes from SACAR (Maldonado and Harabagiu 2019): frequency band, recurrence, dispersal.

Morphology is already ``IedType``; lobe and side are already on the finding. These three fill what LEO's
IED fields lacked (``writing/further_LEO.md`` G1). Words in a ±80 character window win; a Hz figure fills
the band when no band word is present (delta <4, theta <8, alpha <13, beta ≤30, else gamma).
"""

from __future__ import annotations

import re
from typing import Optional

from schema.enums import FrequencyBand, IedDispersal, IedRecurrence

_BAND_WORDS: list[tuple[re.Pattern[str], FrequencyBand]] = [
    (re.compile(r"\bdelta\b", re.I), FrequencyBand.DELTA),
    (re.compile(r"\btheta\b", re.I), FrequencyBand.THETA),
    (re.compile(r"\balpha\b", re.I), FrequencyBand.ALPHA),
    (re.compile(r"\bbeta\b", re.I), FrequencyBand.BETA),
    (re.compile(r"\bgamma\b", re.I), FrequencyBand.GAMMA),
]
_RECURRENCE: list[tuple[re.Pattern[str], IedRecurrence]] = [
    (re.compile(r"\bcontinuous(?:ly)?\b", re.I), IedRecurrence.CONTINUOUS),
    (re.compile(r"\babundant(?:ly)?\b", re.I), IedRecurrence.ABUNDANT),
    (re.compile(r"\bfrequent(?:ly)?\b", re.I), IedRecurrence.FREQUENT),
    (re.compile(r"\bintermittent(?:ly)?\b", re.I), IedRecurrence.INTERMITTENT),
    (re.compile(r"\boccasional(?:ly)?\b", re.I), IedRecurrence.OCCASIONAL),
    (re.compile(r"\b(?:rare(?:ly)?|infrequent(?:ly)?)\b", re.I), IedRecurrence.RARE),
]
_DISPERSAL: list[tuple[re.Pattern[str], IedDispersal]] = [
    (re.compile(r"\b(?:generali[sz]ed|diffuse|widespread)\b", re.I), IedDispersal.GENERALIZED),
    (re.compile(r"\bmultifocal\b", re.I), IedDispersal.MULTIFOCAL),
    (re.compile(r"\bhemispher(?:e|ic)\b", re.I), IedDispersal.HEMISPHERIC),
    (re.compile(r"\bregional\b", re.I), IedDispersal.REGIONAL),
    (re.compile(r"\bfocal\b", re.I), IedDispersal.FOCAL),
]


def band_from_hz(hz: Optional[float]) -> Optional[FrequencyBand]:
    if hz is None:
        return None
    if hz < 4:
        return FrequencyBand.DELTA
    if hz < 8:
        return FrequencyBand.THETA
    if hz < 13:
        return FrequencyBand.ALPHA
    if hz <= 30:
        return FrequencyBand.BETA
    return FrequencyBand.GAMMA


def _nearest_label(text: str, start: int, end: int, pairs, window: int = 80):
    ctx_start = max(0, start - window)
    ctx = text[ctx_start:min(len(text), end + window)]
    hits = []
    for pat, value in pairs:
        for m in pat.finditer(ctx):
            hits.append((abs(m.start() - (start - ctx_start)), value))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


def ied_attributes(text: str, start: int, end: int, hz: Optional[float] = None,
                   window: int = 80) -> tuple[Optional[FrequencyBand], Optional[IedRecurrence],
                                              Optional[IedDispersal]]:
    """Band, recurrence and dispersal for the IED span ``text[start:end]``."""
    band = _nearest_label(text, start, end, _BAND_WORDS, window) or band_from_hz(hz)
    rec = _nearest_label(text, start, end, _RECURRENCE, window)
    disp = _nearest_label(text, start, end, _DISPERSAL, window)
    return band, rec, disp


__all__ = ["ied_attributes", "band_from_hz"]
