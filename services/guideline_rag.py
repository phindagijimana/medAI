"""Lexical RAG over a small ILAE/ACNS corpus for ask_/audit questions.

Not an extract-table tool. Passages are operational paraphrases (Fisher 2017, Scheffer 2017,
Kwan 2010, ACNS Hirsch), retrieved at question time and stuffed only into ``build_ask_prompt``.
L1C/X1C/P1C/F1C never import this module. Token overlap, no embeddings: deterministic, no GPU.

The quote check in ``services.leo_ask`` still requires the quote to sit in the *note*. A model
that echoes the guideline fails ``offsets_unresolved``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parent.parent
_CORPUS = _REPO / "data" / "guidelines" / "ilae_ask.json"
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an the of to for in on and or is are was were be been being this that with from by as "
    "not no if vs than into its it".split()
)
# Inject only when the question is a guideline-judgment ask, not "copy seizure_type".
_JUDGMENT = re.compile(
    r"\b(?:drug[- ]resistant|dre|intractable|refractory|two (?:adequate |tolerated )?trials|"
    r"first feature|onset or later|later evolution|begins with|followed by|"
    r"\bltm\b|long[- ]term monitoring|study or a drug|study vs drug|cEEG|continuous eeg)\b",
    re.I,
)
MIN_SCORE = 0.12
TOP_K = 3


@dataclass(frozen=True)
class Passage:
    id: str
    source: str
    cite: str
    topics: tuple[str, ...]
    text: str
    tokens: frozenset[str]


def _tok(s: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN.findall(s.lower()) if t not in _STOP and len(t) > 1)


@lru_cache(maxsize=1)
def load_corpus(path: Optional[str] = None) -> tuple[Passage, ...]:
    p = Path(path) if path else _CORPUS
    raw = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for row in raw.get("passages") or []:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        topics = tuple(str(t) for t in (row.get("topics") or []) if t)
        blob = " ".join((text, " ".join(topics), str(row.get("source") or "")))
        out.append(Passage(
            id=str(row.get("id") or ""),
            source=str(row.get("source") or ""),
            cite=str(row.get("cite") or ""),
            topics=topics,
            text=text,
            tokens=_tok(blob),
        ))
    return tuple(out)


def _score(query_tokens: frozenset[str], passage: Passage) -> float:
    if not query_tokens or not passage.tokens:
        return 0.0
    hit = query_tokens & passage.tokens
    return len(hit) / len(query_tokens)


def is_guideline_question(question: str, spec_id: str = "") -> bool:
    """True for the three judgment templates, or a free question that names a guideline job."""
    sid = (spec_id or "").lower()
    if sid.startswith("ask_"):
        sid = sid[4:]
    if sid in ("dre_kwan", "first_feature", "ltm_sense"):
        return True
    return bool(_JUDGMENT.search(question or ""))


def retrieve(question: str, *, spec_id: str = "", k: int = TOP_K,
             path: Optional[str] = None) -> list[Passage]:
    """Top-k passages for a guideline-judgment question. Empty if the question is span-copy."""
    if not question or not is_guideline_question(question, spec_id):
        return []
    qtok = _tok(question)
    ranked = sorted(
        (( _score(qtok, p), p) for p in load_corpus(path)),
        key=lambda x: (-x[0], x[1].id),
    )
    return [p for s, p in ranked if s >= MIN_SCORE][:k]


def format_passages(passages: list[Passage]) -> str:
    if not passages:
        return ""
    blocks = []
    for p in passages:
        blocks.append(f"[{p.id} | {p.source}] {p.text}")
    return "\n".join(blocks)


__all__ = ["Passage", "load_corpus", "retrieve", "format_passages", "is_guideline_question",
           "MIN_SCORE", "TOP_K"]
