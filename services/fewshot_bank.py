"""Retrieval-based few-shot exemplars from the F-S *training* letters (arm L2).

For a target note, pick the ``k`` most similar annotated letters from the bank
(letters EA0001-EA0160 only; the 40 held-out letters EA0161-EA0200 are never
in the bank) and show them to the model as worked examples, with answers in the
flat JSON shape of ``services.flat_extract`` and **verbatim quotes taken from
the clinicians' own character spans** (so the model is shown what a real quote
looks like; the fine-tuned adapter was trained on templated, non-verbatim
evidence text and learned the wrong habit - see docs/EVAL_PROTOCOL_LEO.md 10.3).

No torch, no sklearn: a small TF-IDF cosine in pure python.

Gold conventions kept identical to ``scripts/score_llm_arms_vs_fs_gold.py``
(first epilepsy diagnosis, first seizure-type diagnosis, first onset, first
frequency, every non-negated prescription).  One deliberate difference: a gold
epilepsy type of "unknown" (the regex found no type words in the diagnosis
text, e.g. plain "epilepsy") is shown to the model as ``null``, because
"not stated" is the correct answer to give.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
FS_TEXT_DIR = (REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8381080"
               / "Gold1-200_corrected_spelling")
FS_GOLD_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8356494" / "Json"

BANK_IDS = [f"EA{i:04d}" for i in range(1, 161)]          # never EA0161+
HELD_OUT_IDS = {f"EA{i:04d}" for i in range(161, 201)}

_EPI = [
    (re.compile(r"generali[sz]ed", re.I), "generalized"),
    (re.compile(r"focal|temporal|frontal|parietal|occipital|insular", re.I), "focal"),
]
_SZ = [
    (re.compile(r"secondar(?:ily|y).*generali[sz]ed|focal.*bilateral.*tonic.*clonic|bilateral.*tonic.*clonic", re.I),
     "focal_to_bilateral_tonic_clonic"),
    (re.compile(r"generali[sz]ed.*tonic.*clonic|GTCS|primary.*generali[sz]ed", re.I), "generalized_tonic_clonic"),
    (re.compile(r"absence", re.I), "generalized_absence_typical"),
    (re.compile(r"myoclonic", re.I), "generalized_myoclonic"),
    (re.compile(r"atonic|drop.*attack", re.I), "generalized_atonic"),
    (re.compile(r"focal.*(loss.*awareness|impaired.*awareness|complex.*partial)", re.I), "focal_impaired_awareness"),
    (re.compile(r"focal.*aware|simple.*partial", re.I), "focal_aware"),
    (re.compile(r"focal", re.I), "focal_unknown_awareness"),
]
_PERIOD = {"day", "week", "month", "year"}


def _first(rules, txt):
    for rx, tag in rules:
        if rx.search(txt):
            return tag
    return None


def _num(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _clean(n: Optional[float]):
    if n is None:
        return None
    return int(n) if float(n).is_integer() else n


_NUMWORDS = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|once|twice|"
                       r"daily|weekly|monthly|yearly|annual|every|per|each|free|no seizures|fortnight)\b", re.I)


def _plausible_span(q: str) -> bool:
    """A span that can support a number: it has a digit or a number word."""
    return bool(re.search(r"\d", q) or _NUMWORDS.search(q))


def _sentence(text: str, ent: dict, max_len: int = 220) -> str:
    """The sentence (or line) around an entity span, verbatim."""
    try:
        s, e = int(ent["start_index"]), int(ent["end_index"])
    except (KeyError, TypeError, ValueError):
        return ""
    a = max(text.rfind(". ", 0, s) + 2, text.rfind("\n", 0, s) + 1, 0)
    cands = [i for i in (text.find(". ", e), text.find("\n", e)) if i >= 0]
    b = (min(cands) + 1) if cands else len(text)
    sent = text[a:b].strip()
    return sent if len(sent) <= max_len else ""


def _span(text: str, ent: dict) -> str:
    try:
        s, e = int(ent["start_index"]), int(ent["end_index"])
    except (KeyError, TypeError, ValueError):
        return ""
    return text[s:e].strip()


def build_answer(pid: str) -> Optional[dict]:
    """Flat-JSON answer (with verbatim quotes) for one annotated letter."""
    gf, tf = FS_GOLD_DIR / f"{pid}.json", FS_TEXT_DIR / f"{pid}.txt"
    if not gf.exists() or not tf.exists():
        return None
    text = tf.read_text(encoding="utf-8")
    ents = json.loads(gf.read_text(encoding="utf-8"))
    ans = {
        "epilepsy_type": {"value": None, "quote": None},
        "predominant_seizure_type": {"value": None, "quote": None},
        "age_at_onset_years": {"value": None, "quote": None},
        "seizure_frequency": {"count_min": None, "count_max": None, "period": None,
                              "seizure_free": None, "quote": None},
        "current_asms": [],
    }
    for ent in ents:
        a = ent.get("attributes") or {}
        if (a.get("Negation") or "").lower() == "negated":
            continue
        kind, q = ent.get("entity"), _span(text, ent)
        low = q.lower()
        if not q:
            continue
        if kind == "Prescription":
            drug = (a.get("DrugName") or "").strip().lower().replace("-", " ")
            if not drug:
                continue
            i = low.find(drug.split()[-1]) if drug.split() else -1
            j = low.find(drug)
            i = j if j >= 0 else i
            quote = q[i:] if i >= 0 else q
            dose = " ".join(x for x in (a.get("DrugDose"), a.get("DoseUnit")) if x)
            ans["current_asms"].append({"name": drug, "dose": dose or None, "quote": quote.strip()})
        elif kind == "Diagnosis":
            cat = (a.get("DiagCategory") or "").lower()
            if cat == "epilepsy" and ans["epilepsy_type"]["value"] is None:
                v = _first(_EPI, low)
                if v:
                    ans["epilepsy_type"] = {"value": v, "quote": q}
            elif cat in ("multipleseizures", "singleseizure") and ans["predominant_seizure_type"]["value"] is None:
                v = _first(_SZ, low)
                if v:
                    ans["predominant_seizure_type"] = {"value": v, "quote": q}
        elif kind == "Onset" and ans["age_at_onset_years"]["value"] is None:
            age = _num(a.get("Age") or a.get("AgeLower"))
            if age is not None and not _plausible_span(q):
                q = _sentence(text, ent)
            if age is not None and q and _plausible_span(q):
                if (a.get("AgeUnit") or "years").lower().startswith("month"):
                    age /= 12.0
                ans["age_at_onset_years"] = {"value": _clean(round(age, 1)), "quote": q}
        elif kind == "SeizureFrequency" and ans["seizure_frequency"]["quote"] is None:
            tp = (a.get("TimePeriod") or "").strip().lower()
            lo, hi = _num(a.get("LowerNumberOfSeizures")), _num(a.get("UpperNumberOfSeizures"))
            n0 = _num(a.get("NumberOfSeizures"))
            if not _plausible_span(q):
                q = _sentence(text, ent)
            if not q or not _plausible_span(q):
                continue
            if tp in _PERIOD or lo is not None or hi is not None:
                ans["seizure_frequency"] = {
                    "count_min": _clean(lo), "count_max": _clean(hi if hi is not None else lo),
                    "period": tp if tp in _PERIOD else None, "seizure_free": False, "quote": q}
            elif n0 == 0:
                ans["seizure_frequency"] = {"count_min": None, "count_max": None, "period": None,
                                            "seizure_free": True, "quote": q}
    # unique drugs only, keep first mention
    seen, uniq = set(), []
    for d in ans["current_asms"]:
        if d["name"] not in seen:
            seen.add(d["name"])
            uniq.append(d)
    ans["current_asms"] = uniq
    return ans


# ─── similarity ───────────────────────────────────────────────────────────

_TOK = re.compile(r"[a-z]{3,}")


def _tokens(t: str) -> list[str]:
    return _TOK.findall(t.lower())


@dataclass
class Exemplar:
    pid: str
    text: str
    answer: dict
    n_words: int


class ExemplarBank:
    def __init__(self, ids: list[str] = BANK_IDS):
        self.items: list[Exemplar] = []
        for pid in ids:
            if pid in HELD_OUT_IDS:
                raise ValueError(f"{pid} is a held-out letter; it must never be in the bank")
            ans = build_answer(pid)
            if ans is None:
                continue
            text = (FS_TEXT_DIR / f"{pid}.txt").read_text(encoding="utf-8")
            self.items.append(Exemplar(pid, text, ans, len(text.split())))
        df: Counter = Counter()
        self._tf: list[Counter] = []
        for ex in self.items:
            c = Counter(_tokens(ex.text))
            self._tf.append(c)
            df.update(c.keys())
        n = max(len(self.items), 1)
        self._idf = {w: math.log((1 + n) / (1 + d)) + 1.0 for w, d in df.items()}
        self._norm = [self._vecnorm(c) for c in self._tf]

    def _vecnorm(self, c: Counter) -> float:
        return math.sqrt(sum((v * self._idf.get(w, 1.0)) ** 2 for w, v in c.items())) or 1.0

    def select(self, note: str, k: int = 3, exclude: str = "", max_words: int = 650,
               min_fields: int = 3) -> list[Exemplar]:
        """Most similar letters; skip very long ones and ones with too few annotated fields."""
        q = Counter(_tokens(note))
        qn = self._vecnorm(q)
        scored = []
        for ex, tf, nrm in zip(self.items, self._tf, self._norm):
            if ex.pid == exclude or ex.n_words > max_words:
                continue
            if _filled(ex.answer) < min_fields:
                continue
            dot = sum(v * tf.get(w, 0) * self._idf.get(w, 1.0) ** 2 for w, v in q.items())
            scored.append((dot / (qn * nrm), ex))
        scored.sort(key=lambda x: -x[0])
        return [ex for _, ex in scored[:k]]


def _filled(ans: dict) -> int:
    n = sum(1 for k in ("epilepsy_type", "predominant_seizure_type", "age_at_onset_years")
            if ans[k]["value"] is not None)
    n += 1 if ans["seizure_frequency"]["quote"] else 0
    n += 1 if ans["current_asms"] else 0
    return n


__all__ = ["ExemplarBank", "Exemplar", "build_answer", "BANK_IDS", "HELD_OUT_IDS"]
