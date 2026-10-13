"""Quote–value entailment: a span in the note is not proof it supports the cell.

Lexical / ConText-style check (no second model, no CoT). Used by fusion when
``--quote-entail`` is on: ACCEPT → REVIEW ``quote_not_entailed`` when the sentence
does not assert this value. Default off (headline LEO unchanged).

Hits measured holes: quote about another drug; “may be considered” as a study done;
negated HS/IED used as a positive; seizure-type cell backed by an unrelated sentence.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.sentence_context import negated, option_only, sentence_span

_DRUG_STOP = re.compile(
    r"\b(?:was\s+|were\s+|has\s+been\s+|have\s+been\s+)?stopped\b|"
    r"\bdiscontinued\b|\bno longer\b|\bprior(?:ly)?\b|\bpreviously\b|\bfailed\b",
    re.I,
)
_PLAN = re.compile(
    r"\b(?:may be considered|consider(?:ed|ing)?|recommend(?:ed)?|plan(?:ned)?|"
    r"propos(?:e|ed)|await(?:ing)?|pending|if needed)\b",
    re.I,
)
_STYPE = {
    "generalized_tonic_clonic": r"generali[sz]ed\W+tonic\W*clonic|\bGTCS?\b|grand mal|tonic\W*clonic",
    "focal_to_bilateral_tonic_clonic": r"secondar(?:ily|y)\W+generali[sz]ed|focal\W+to\W+bilateral",
    "focal_impaired_awareness": r"impaired (?:awareness|consciousness)|complex partial|focal impaired",
    "focal_aware": r"focal aware|simple partial|without (?:loss|impair)",
    "generalized_absence_typical": r"\babsence\b",
    "generalized_myoclonic": r"myoclon",
    "generalized_atonic": r"atonic|drop attack",
    "generalized_epileptic_spasms": r"spasm",
    "focal_unknown_awareness": r"\bfocal\b|partial",
}
_ETYPE = {
    "generalized": r"generali[sz]ed epilepsy|\bGGE\b|\bJME\b",
    "focal": r"focal epilepsy|partial epilepsy|\bTLE\b|\bFLE\b|temporal lobe epilepsy",
    "combined_focal_generalized": r"combined|focal and generali[sz]ed",
    "unknown": r"unknown epilepsy|unclassified",
}


def _blob(quote: str, note: str) -> tuple[str, int, int]:
    from services.chain_llm import locate_quote
    q = (quote or "").strip()
    if note and q:
        span = locate_quote(q, note)
        if span is not None:
            s, e = sentence_span(note, span[0], span[1])
            return note[s:e], span[0], span[1]
    return q, 0, len(q)


def _val_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("generic_name") or value.get("value") or "")
    return str(getattr(value, "value", value) or "")


def quote_entails(field_path: str, value: Any, quote: str, note: str = "") -> bool:
    """True when the quote's sentence actually asserts this field value.

    Unknown fields pass (do not over-flag). Empty quote fails.
    """
    path = field_path or ""
    q = (quote or "").strip()
    if not q:
        return False
    blob, start, end = _blob(q, note)
    text_for_neg = note if note else blob
    # Offsets into note when we have them; else into the blob.
    ns, ne = start, end
    if note and (start, end) == (0, len(q)) and q not in note:
        ns, ne = 0, min(len(blob), 1)

    if path.endswith("predominant_seizure_type") or path.endswith("other_seizure_types"):
        rx = _STYPE.get(_val_text(value).lower())
        if not rx:
            return True
        if not re.search(rx, blob, re.I):
            return False
        return not (note and negated(note, ns, ne))

    if path.endswith("epilepsy_type"):
        raw = _val_text(value).lower()
        rx = _ETYPE.get(raw)
        if raw == "focal" and re.search(r"\bfocal epilepsy\b|\bpartial epilepsy\b", blob, re.I):
            return not (note and negated(note, ns, ne))
        if rx and not re.search(rx, blob, re.I):
            # grounding often uses a short type word; require it at least
            if raw and raw.replace("_", " ") not in blob.lower() and raw not in blob.lower():
                return False
        if note and negated(note, ns, ne):
            return False
        return True

    if path.endswith("current_asms") or path.endswith("failed_asms") or path.endswith("prior_asms"):
        name = _val_text(value).lower()
        if name and not re.search(r"\b" + re.escape(name) + r"\b", blob, re.I):
            return False
        if path.endswith("current_asms") and _DRUG_STOP.search(blob):
            return False
        return True

    if path.endswith("study_type") or path.endswith("eeg.study_type"):
        if _PLAN.search(blob) or (note and option_only(note, ns, ne)):
            return False
        return True

    if path.endswith("ied_present") or path.endswith("hippocampal_sclerosis") or path.endswith(
            "focal_cortical_dysplasia"):
        flag = value if isinstance(value, bool) else str(value).lower() in ("true", "1")
        is_neg = bool(note and negated(note, ns, ne)) or bool(
            re.search(r"\b(?:no|not|without|denies)\b", blob, re.I)
        )
        if flag and is_neg:
            return False
        if (not flag) and not is_neg:
            return True  # explicit false still needs a negation-ish quote; allow
        return True

    if path.endswith("surgery_history"):
        if note and option_only(note, ns, ne):
            return False
        return True

    return True


def entailment_reason(field_path: str, value: Any, quote: str, note: str = "") -> Optional[str]:
    """None if entailed; ``quote_not_entailed`` otherwise."""
    if quote_entails(field_path, value, quote, note):
        return None
    return "quote_not_entailed"


__all__ = ["quote_entails", "entailment_reason"]
