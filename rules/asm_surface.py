"""ASM surface forms the linker misses: standard abbreviations and near-miss spellings.

Abbreviations follow the usual epilepsy-clinic shorthand (LEV, CBZ, LTG, LCM,
VPA, ...).  They are matched only as whole upper-case tokens.  Letters that
collide with ordinary English or UK usage (PB, PER, ESL, GBP, TOP, ...) also
need a dose right after them ("GBP 300 mg").

Misspellings ("volproate", "Pregablin") are matched against the generic,
salt, brand and other names in ``rules/asm_lexicon.py`` with an edit distance
of 1 for words of 7-9 letters and 2 for 10 letters or more.  The first letter
must agree, the best match must be unique, and words found in the system word
list (``/usr/share/dict/words``, when present) are skipped, so "lyrical" never
becomes Lyrica.

Cite: Damerau 1964 (edit distance with transpositions).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Callable, NamedTuple

from rules.asm_lexicon import ASM_LEXICON

# abbreviation -> lexicon key (canonicalised by the caller)
ASM_ABBREVIATIONS: dict[str, str] = {
    "LEV": "levetiracetam",
    "LTG": "lamotrigine",
    "CBZ": "carbamazepine",
    "OXC": "oxcarbazepine",
    "ESL": "eslicarbazepine",
    "LCM": "lacosamide",
    "VPA": "sodium_valproate",
    "TPM": "topiramate",
    "TOP": "topiramate",
    "ZNS": "zonisamide",
    "PHT": "phenytoin",
    "PB": "phenobarbital",
    "PRM": "primidone",
    "CLB": "clobazam",
    "CZP": "clonazepam",
    "BRV": "brivaracetam",
    "PER": "perampanel",
    "PMP": "perampanel",
    "GBP": "gabapentin",
    "PGB": "pregabalin",
    "ESM": "ethosuximide",
    "VGB": "vigabatrin",
    "RUF": "rufinamide",
    "TGB": "tiagabine",
    "FBM": "felbamate",
    "STP": "stiripentol",
    "CNB": "cenobamate",
    "CBD": "cannabidiol",
}

# Abbreviations that are also ordinary words or common non-drug acronyms.
_NEEDS_DOSE = frozenset({"PB", "PER", "ESL", "GBP", "TOP", "PRM", "STP", "RUF", "FBM",
                         "TGB", "ESM", "CLB", "CBD"})

_ABBREV_RE = re.compile(r"\b(" + "|".join(sorted(ASM_ABBREVIATIONS, key=len, reverse=True)) + r")\b")
_DOSE_AFTER = re.compile(r"^\s*(?:XR\s+|ER\s+)?\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z]{7,}")
_WORDS_FILE = Path("/usr/share/dict/words")


class SurfaceMatch(NamedTuple):
    start: int
    end: int
    surface: str
    canon: str
    kind: str  # "abbreviation" | "misspelling"


@lru_cache(maxsize=1)
def _english_words() -> frozenset[str]:
    try:
        return frozenset(w.strip().lower() for w in _WORDS_FILE.read_text(errors="ignore").split())
    except OSError:
        return frozenset()


@lru_cache(maxsize=1)
def _fuzzy_targets() -> tuple[tuple[str, str], ...]:
    """(surface, lexicon key) pairs of single-word names of 7+ letters."""
    out: dict[str, str] = {}
    for key, row in ASM_LEXICON.items():
        names = [key, row.get("label") or ""]
        for k in ("salts", "brands", "other_names"):
            names += row.get(k) or []
        for n in names:
            n = n.strip().lower()
            if len(n) >= 7 and n.isalpha():
                out.setdefault(n, key)
    return tuple(sorted(out.items()))


def _edit_distance(a: str, b: str, cap: int) -> int:
    """Damerau (adjacent transposition) distance, early exit above ``cap``."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > cap:
            return cap + 1
        prev2, prev = prev, cur
    return prev[-1]


def fuzzy_drug(word: str) -> str | None:
    """Lexicon key for a near-miss spelling of an ASM name, else None."""
    w = word.lower()
    if len(w) < 7 or not w.isalpha() or w in _english_words():
        return None
    cap = 1 if len(w) <= 9 else 2
    best: dict[str, int] = {}
    for name, key in _fuzzy_targets():
        if name[0] != w[0]:
            continue
        if name == w:
            return key
        d = _edit_distance(w, name, cap)
        if d <= cap and d < best.get(key, cap + 1):
            best[key] = d
    if not best:
        return None
    lo = min(best.values())
    keys = [k for k, d in best.items() if d == lo]
    return keys[0] if len(keys) == 1 else None


def surface_matches(text: str, canonicalize: Callable[[str], str],
                    taken: list[tuple[int, int]] = ()) -> list[SurfaceMatch]:
    """Abbreviation and misspelling mentions in ``text`` outside the ``taken`` spans."""
    text = text or ""

    def free(s: int, e: int) -> bool:
        return all(e <= a or s >= b for a, b in taken)

    out: list[SurfaceMatch] = []
    for m in _ABBREV_RE.finditer(text):
        tok = m.group(1)
        if tok in _NEEDS_DOSE and not _DOSE_AFTER.match(text[m.end():m.end() + 25]):
            continue
        if free(m.start(), m.end()):
            out.append(SurfaceMatch(m.start(), m.end(), tok,
                                    canonicalize(ASM_ABBREVIATIONS[tok]), "abbreviation"))
    for m in _WORD_RE.finditer(text):
        if not free(m.start(), m.end()):
            continue
        key = fuzzy_drug(m.group(0))
        if key:
            out.append(SurfaceMatch(m.start(), m.end(), m.group(0), canonicalize(key), "misspelling"))
    return sorted(out)


__all__ = ["ASM_ABBREVIATIONS", "SurfaceMatch", "fuzzy_drug", "surface_matches"]
