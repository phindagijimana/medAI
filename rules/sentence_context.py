"""Sentence-level context checks shared by the plain-text rules (surgery, MRI, drug resistance).

A mention is read in its own sentence (or list line).  Three questions, all answered from the words
before and after the mention inside that sentence:

* ``negated``  -- "No epilepsy surgery is documented", "No identified lesion, including MTS", "does not establish
  drug-resistant epilepsy", "MTS not seen".
* ``hedged``   -- "probable abnormality consistent with MTS", "cannot exclude HS", "if seizures become drug resistant".
* ``option``   -- a treatment that is only being discussed or planned: "future options could include VNS",
  "candidacy for resection", "would not pursue DBS".  A cue that the thing happened ("s/p", "underwent", "implanted",
  "in place") before the mention overrides it.

These are text patterns written from how clinical notes phrase absence, uncertainty and plans (no model).  They
are deliberately narrow: a false match drops a true finding.  Each pattern is covered in ``tests/test_sentence_rules.py``.
"""

from __future__ import annotations

import re

_END = re.compile(r"[.!?;]\s|\n|[.!?;]$")
_CLAUSE_BREAK = re.compile(r"\b(?:but|however|although|though|while|whereas|except)\b|[:]", re.IGNORECASE)


def sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Bounds of the sentence or line holding ``text[start:end]``."""
    s = 0
    for m in _END.finditer(text, 0, start):
        s = m.end()
    m = _END.search(text, end)
    e = m.start() + 1 if m and text[m.start()] != "\n" else (m.start() if m else len(text))
    return s, max(e, end)


def _pre_post(text: str, start: int, end: int) -> tuple[str, str]:
    s, e = sentence_span(text, start, end)
    pre = text[s:start]
    cut = list(_CLAUSE_BREAK.finditer(pre))
    if cut:
        pre = pre[cut[-1].end():]
    return pre, text[end:e]


# words that may sit between a negation and the thing it negates ("no prior epilepsy surgery", "no evidence of")
_FILL = (r"(?:history|hx|of|prior|previous|past|documented|documentation|evidence|record|records|report|reports|"
         r"any|identified|seen|definite|clear|known|suggestion|signs?|epilepsy|epileptogenic|structural|focal|"
         r"surgery|surgical|neuromodulation|neurostimulation|procedure|implanted|device|s/p|status|post|including|"
         r"or|and|a|an|the|abnormality|lesion|lesions|findings?|specific|obvious|significant|acute|other|new|implantation|"
         r"operative|inpatient|intervention|resection|ablation|laser|nerve|vagus|responsive|deep|brain|stimulation|"
         r"monitoring|intracranial|available|here|regarding|about)")
_NEG_BEFORE = re.compile(
    r"\b(?:no|without|absent|denies|denied|never|none|negative\s+for|free\s+of|nor|not\s+(?:identified|seen|"
    r"demonstrated|shown|visualized|evident|present|documented))\b(?:[\s,/-]+" + _FILL + r"\b){0,8}[\s,/-]*$",
    re.IGNORECASE)
_NEG_VERB_BEFORE = re.compile(
    r"\b(?:does|do|did|would|could|can)\s+not\s+(?:\w+\s+){0,2}(?:establish|show|demonstrate|support|confirm|meet|"
    r"indicate|suggest|identify)\b[^.;]*$|\b(?:criteria|definition)\b[^.;]{0,60}\bnot\s+(?:been\s+)?met\b[^.;]*$|"
    r"\b(?:rules?|ruled)\s+out\b[^.;]*$|\bnot\s+(?:a\s+)?(?:candidate|indicated|diagnostic)\b[^.;]*$",
    re.IGNORECASE)
# "There is no documentation available here regarding prior epilepsy surgery", "No information was provided regarding ..."
_ABSENT_DOC_BEFORE = re.compile(
    r"\b(?:no|insufficient|limited|lack\s+of|absence\s+of)\s+(?:\w+\s+){0,3}?(?:documentation|documented|information|records?|"
    r"history|evidence|mention|report)\b(?:\s+(?:is|are|was|were))?(?:\s+(?:\w+)){0,6}?\s+(?:regarding|about|of|for|on|concerning)\b[^.;]*$",
    re.IGNORECASE)
# "Prior epilepsy surgery or neuromodulation is not documented"
_NEG_AFTER_LIST = re.compile(
    r"^[^.;\n]{0,80}\b(?:is|are|was|were)\s+not\s+(?:documented|recorded|reported|provided|available|identified|established)\b",
    re.IGNORECASE)
_NEG_AFTER = re.compile(
    r"^\W{0,3}(?:(?:was|is|were|are|has\s+been|have\s+been)\s+)?(?:not\s+(?:seen|identified|present|demonstrated|"
    r"evident|documented|reported|established|confirmed)|absent|excluded|negative|ruled\s+out|"
    r"(?:is|are|was|were)\s+not\s+\w+)\b",
    re.IGNORECASE)
_NONE_DOC = re.compile(r"^\W{0,3}(?:is|are|was|were)?\s*(?:none|not)\s+documented\b|^\W{0,3}[:-]?\s*none\b", re.IGNORECASE)

_HEDGE_BEFORE = re.compile(
    r"\b(?:probable|possible|possibly|suspected|suspicious\s+for|questionable|equivocal|"
    r"consistent\s+with|concern(?:ing)?\s+for|raise[sd]?\s+concern\s+for|cannot\s+(?:be\s+)?exclude[d]?|"
    r"can\s*not\s+exclude|does\s+not\s+exclude|not\s+excluded|versus|vs\.?|if|unless|whether|"
    r"should\s+\w+\s+become|risk\s+of|becomes?|becoming|evaluate\s+for|evaluation\s+for)\b[^.;]{0,40}$", re.IGNORECASE)

_OPTION_ANY = re.compile(
    r"\b(?:consider(?:ed|ing|ation)?|candidacy|candidate|candidates|options?|evaluation|evaluate|discuss(?:ion|ed)?|"
    r"referral|refer(?:red)?|may\s+(?:eventually\s+)?(?:be|proceed|consider|include)|might|could|would|should|"
    r"recommend(?:ed|ation)?|eligible|eligibility|potential(?:ly)?|future|depending|pursue|indicated|proceed|"
    r"work-?up|planned|plan\s+to|not\s+(?:being\s+)?(?:initiated|pursued)|can\s+include|approaches|treatments?\s+used|"
    r"if\s+\w+|presurgical|pre-surgical|multidisciplinary|conference|PRC)\b", re.IGNORECASE)
_HISTORY_BEFORE = re.compile(
    r"\b(?:s/p|status\s+post|underwent|had\s+(?:an?\s+|his\s+|her\s+|the\s+)?|history\s+of|h/o|implanted|placed|in\s+place|"
    r"prior|previous(?!ly)|failed|has\s+(?:an?\s+)?)\b[^.;]{0,50}$", re.IGNORECASE)


def negated(text: str, start: int, end: int) -> bool:
    pre, post = _pre_post(text, start, end)
    return bool(_NEG_BEFORE.search(pre) or _NEG_VERB_BEFORE.search(pre) or _ABSENT_DOC_BEFORE.search(pre)
                or _NEG_AFTER.search(post) or _NEG_AFTER_LIST.search(post) or _NONE_DOC.search(post))


def hedged(text: str, start: int, end: int) -> bool:
    pre, _ = _pre_post(text, start, end)
    return bool(_HEDGE_BEFORE.search(pre))


def history_cue(text: str, start: int, end: int) -> bool:
    pre, _ = _pre_post(text, start, end)
    return bool(_HISTORY_BEFORE.search(pre[-70:]))


def option_only(text: str, start: int, end: int) -> bool:
    """The sentence discusses or plans the item and nothing before it says it happened."""
    pre, post = _pre_post(text, start, end)
    if not _OPTION_ANY.search(pre + " " + post):
        return False
    return not _HISTORY_BEFORE.search(pre[-70:])


__all__ = ["sentence_span", "negated", "hedged", "history_cue", "option_only"]
