"""Medication context in the n2c2 2022 CMED dimensions, built on EpExtra's mention cues.

CMED (Mahajan et al., J Biomed Inform 2023; ``writing/further_LEO.md`` M1) labels each medication mention with
a disposition (is a change discussed?) and five context dimensions: action, negation, temporality, certainty and
actor.  EpExtra decides "current at this visit" from clause-level cues (``rules.fields.medication``); this module
re-expresses those cues in CMED's terms so the rule can be compared with the shared task and tested on outside
data, without changing what EpExtra emits.

``casi_status`` maps the per-drug decision onto the three labels of the CASI medication-status set (Agrawal et
al., EMNLP 2022; ``writing/further_LEO.md`` M2): active, discontinued, neither.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Optional

from rules.fields.medication import (
    _MENTION_BARE, _MENTION_CURRENT, _MENTION_PAST, _MENTION_PLANNED, _MENTION_STOP, _clause_bounds,
    _infer_status, _is_current_at_visit, _mention_class, _sentence_window,
)

_INCREASE = re.compile(r"\b(?:increas\w*|titrat\w*\s+up|up[- ]?titrat\w*|uptitrat\w*|rais\w*|double[ds]?)\b", re.I)
_DECREASE = re.compile(r"\b(?:decreas\w*|reduc\w*|lower\w*|taper\w*|wean\w*|cut\s+(?:back|down)|halve[ds]?)\b", re.I)
_UNIQUE = re.compile(r"\b(?:loading\s+dose|single\s+dose|one[- ]off|stat\b|once\s+only|bolus|given\s+once)\b", re.I)
_SWITCH = re.compile(r"\b(?:switch\w*|chang\w*\s+(?:to|from)|convert\w*|replac\w*)\b", re.I)
_START = re.compile(r"\b(?:start\w*|commenc\w*|initiat\w*|introduc\w*|add\w*|begin|began|begun|tri(?:al|ed)?)\b", re.I)
_NEGATION = re.compile(
    r"\b(?:not\s+(?:start\w*|tak\w*|on|been\s+taking|prescrib\w*|given)|never\s+(?:took|taken|started|on)|"
    r"declined|refused|no\s+longer\s+wish\w*|did\s+not\s+(?:start|take|want)|didn't\s+(?:start|take)|"
    r"denies\s+taking|without)\b", re.I)
_HYPOTHETICAL = re.compile(
    r"\b(?:consider\w*|could|might|may|option\w*|discuss\w*|possibl\w*|potential\w*|would\s+(?:like|recommend)|"
    r"alternative\w*|in\s+future|future\s+option)\b", re.I)
_CONDITIONAL = re.compile(r"\b(?:if|unless|should\s+(?:she|he|they|seizures?)|in\s+the\s+event|in\s+case)\b", re.I)
_FUTURE = re.compile(r"\b(?:will|plan\w*|going\s+to|next|to\s+(?:start|begin|commence|increase|reduce|stop))\b", re.I)
_PAST = re.compile(r"\b(?:previously|in\s+the\s+past|was\s+on|were\s+on|had\s+been|formerly|prior|history\s+of|"
                   r"used\s+to|tried)\b", re.I)
_PATIENT_ACTOR = re.compile(
    r"\b(?:(?:she|he|they|patient|pt)\s+(?:has\s+)?(?:stopped|discontinued|reduced|increased|ran\s+out|forgot|missed|"
    r"self[- ]\w+|decided|chose)|self[- ](?:discontinu\w*|titrat\w*|stopp\w*)|ran\s+out|non[- ]?complian\w*|"
    r"non[- ]?adheren\w*|of\s+(?:her|his|their)\s+own\s+accord)\b", re.I)
_PHYSICIAN_ACTOR = re.compile(
    r"\b(?:I\s+(?:have|would|will|suggest\w*|recommend\w*|advis\w*|prescrib\w*)|we\s+(?:have|will|would|agreed|decided)|"
    r"recommend\w*|advis\w*|prescrib\w*|suggest\w*|please|GP\s+to|neurolog\w+\s+(?:started|stopped|increased))\b")


@dataclass(frozen=True)
class CmedContext:
    disposition: str   # Disposition | NoDisposition
    action: str        # Start | Stop | Increase | Decrease | UniqueDose | OtherChange | Unknown | (none)
    negation: str      # Negated | NotNegated
    temporality: str   # Past | Present | Future | Unknown
    certainty: str     # Certain | Hypothetical | Conditional | Unknown
    actor: str         # Physician | Patient | Unknown
    epextra_class: str  # current | bare | stop | planned | past

    def as_dict(self) -> dict:
        return asdict(self)


def cmed_context(text: str, start: int, end: int) -> CmedContext:
    """CMED dimensions for the drug mention at ``text[start:end]``."""
    sentence = _sentence_window(text, start, end)
    cls = _mention_class(text, start, end, _infer_status(sentence))
    lo, hi = _clause_bounds(text, start, end)
    clause = text[lo:hi]

    if cls == _MENTION_STOP:
        action = "Stop"
    elif _UNIQUE.search(clause):
        action = "UniqueDose"
    elif _SWITCH.search(clause):
        action = "OtherChange"
    elif _INCREASE.search(clause):
        action = "Increase"
    elif _DECREASE.search(clause):
        action = "Decrease"
    elif cls == _MENTION_PLANNED or _START.search(clause):
        action = "Start"
    else:
        action = ""
    disposition = "Disposition" if action else "NoDisposition"

    negation = "Negated" if _NEGATION.search(clause) else "NotNegated"

    if _CONDITIONAL.search(clause):
        certainty = "Conditional"
    elif _HYPOTHETICAL.search(clause):
        certainty = "Hypothetical"
    else:
        certainty = "Certain"

    if cls == _MENTION_PLANNED or (_FUTURE.search(clause) and cls != _MENTION_STOP):
        temporality = "Future"
    elif cls in (_MENTION_STOP, _MENTION_PAST) or _PAST.search(clause):
        temporality = "Past"
    elif cls in (_MENTION_CURRENT, _MENTION_BARE):
        temporality = "Present"
    else:
        temporality = "Unknown"

    if _PATIENT_ACTOR.search(clause):
        actor = "Patient"
    elif _PHYSICIAN_ACTOR.search(clause) or (disposition == "Disposition" and cls == _MENTION_PLANNED):
        actor = "Physician"
    else:
        actor = "Unknown"

    return CmedContext(disposition, action or "", negation, temporality, certainty, actor, cls)


def drug_spans(text: str, name: str) -> list[tuple[int, int]]:
    """Whole-word, case-insensitive spans of a drug name in ``text``."""
    if not name.strip():
        return []
    rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(name.strip()) + r"(?![A-Za-z0-9])", re.I)
    return [(m.start(), m.end()) for m in rx.finditer(text)]


def casi_status(text: str, name: str) -> Optional[str]:
    """active / discontinued / neither for one drug in a snippet, from EpExtra's per-drug decision.

    Active: current at the visit (``_is_current_at_visit``).  Discontinued: not current and some mention was
    stopped or past.  Neither: only planned, negated or hypothetical mentions.  None if the name is not found.
    """
    spans = drug_spans(text, name)
    if not spans:
        return None
    classes: list[tuple[int, str]] = []
    for s, e in spans:
        ctx = cmed_context(text, s, e)
        cls = ctx.epextra_class
        if ctx.negation == "Negated" and cls in (_MENTION_BARE, _MENTION_CURRENT):
            cls = _MENTION_PLANNED
        if ctx.certainty in ("Hypothetical", "Conditional") and cls == _MENTION_BARE:
            cls = _MENTION_PLANNED
        classes.append((s, cls))
    if _is_current_at_visit(classes):
        return "active"
    if any(c in (_MENTION_STOP, _MENTION_PAST) for _, c in classes):
        return "discontinued"
    return "neither"


__all__ = ["CmedContext", "cmed_context", "casi_status", "drug_spans"]
