"""Scalp EEG electrode names (10-20 / 10-10 system) to lobe and side.

"Sharp waves maximal at T8" means right temporal even when the note writes no
lobe or side word. The EEG rules use this only to fill a lobe or side that no
location word gave (Cui et al. 2014, PEEP, normalised electrodes to anatomy
through EpSO).

Side: odd number left, even number right, ``z`` midline; both sides together
is bilateral. Lobe: Fp/AF/F/FC frontal; FT/T/TP temporal; P/PO parietal; O
occipital. T3-T6 are the old names of T7/T8/P7/P8, and P7-P10 sit over the
posterior temporal lobe, so all of these are temporal. C and CP (central) have
no lobe in the schema. A1/A2/M1/M2 are reference electrodes and are ignored.
When the electrodes span more than one lobe the lobe is left empty.

Names such as T4 (thyroxine) or C3 (complement) are also other things, so an
electrode counts only after an EEG cue ("maximal at", "phase reversal at",
"electrode", "over"; a bare "at" is not enough) or with a second electrode
name in the window.
"""

from __future__ import annotations

import re
from typing import Optional

from schema.enums import Laterality, LobarLocalization

_ELECTRODE_RE = re.compile(
    r"(?<![A-Za-z0-9])(Fp|AF|FT|FC|TP|CP|PO|F|T|C|P|O)([1-9]|10|z|Z)(?![A-Za-z0-9])")

_CUE_RE = re.compile(
    r"\b(?:max(?:imal|imum|imally)?|phase[- ]revers\w*|electrodes?|channels?|"
    r"centred|centered|over|involving|field)(?:\s+(?:at|in|on|over))?\W*$",
    re.IGNORECASE)

_LOBE_BY_PREFIX = {
    "Fp": LobarLocalization.FRONTAL, "AF": LobarLocalization.FRONTAL,
    "F": LobarLocalization.FRONTAL, "FC": LobarLocalization.FRONTAL,
    "FT": LobarLocalization.TEMPORAL, "T": LobarLocalization.TEMPORAL,
    "TP": LobarLocalization.TEMPORAL,
    "P": LobarLocalization.PARIETAL, "PO": LobarLocalization.PARIETAL,
    "O": LobarLocalization.OCCIPITAL,
}

_VALID_NUMBERS = {
    "Fp": {"1", "2", "z"}, "AF": {"3", "4", "7", "8", "z"},
    "F": {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "z"},
    "FC": {"1", "2", "3", "4", "5", "6", "z"},
    "FT": {"7", "8", "9", "10"}, "T": {"3", "4", "5", "6", "7", "8", "9", "10"},
    "TP": {"7", "8", "9", "10"}, "C": {"1", "2", "3", "4", "5", "6", "z"},
    "CP": {"1", "2", "3", "4", "5", "6", "z"},
    "P": {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "z"},
    "PO": {"3", "4", "7", "8", "z"}, "O": {"1", "2", "z"},
}


def electrode_lobe(prefix: str, number: str) -> Optional[LobarLocalization]:
    if prefix == "P" and number in {"7", "8", "9", "10"}:
        return LobarLocalization.TEMPORAL
    return _LOBE_BY_PREFIX.get(prefix)


def electrode_side(number: str) -> Laterality:
    if number.lower() == "z":
        return Laterality.MIDLINE
    return Laterality.LEFT if int(number) % 2 else Laterality.RIGHT


def find_electrodes(text: str, lo: int, hi: int) -> list[tuple[int, str, str]]:
    """(position, prefix, number) for electrode names in text[lo:hi] that count."""
    hits = []
    for m in _ELECTRODE_RE.finditer(text, lo, hi):
        prefix, number = m.group(1), m.group(2).lower()
        if number not in _VALID_NUMBERS[prefix]:
            continue
        hits.append((m.start(), prefix, number))
    if len(hits) >= 2:
        return hits
    return [h for h in hits if _CUE_RE.search(text[max(0, h[0] - 25):h[0]])]


def electrode_location(text: str, start: int, end: int, window: int = 80
                       ) -> tuple[Optional[Laterality], Optional[LobarLocalization]]:
    """Side and lobe from the electrode names within ``window`` characters of a finding."""
    lo, hi = max(0, start - window), min(len(text), end + window)
    hits = find_electrodes(text, lo, hi)
    if not hits:
        return None, None
    sides = {electrode_side(n) for _p, _prefix, n in hits}
    lateral = sides - {Laterality.MIDLINE}
    if len(lateral) == 2:
        side = Laterality.BILATERAL
    elif lateral:
        side = next(iter(lateral))
    else:
        side = Laterality.MIDLINE
    lobes = {electrode_lobe(prefix, n) for _p, prefix, n in hits} - {None}
    lobe = next(iter(lobes)) if len(lobes) == 1 else None
    return side, lobe


__all__ = ["electrode_location", "electrode_lobe", "electrode_side", "find_electrodes"]
