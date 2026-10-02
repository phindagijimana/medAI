"""Ask LEO a question: one question, one note, one answer with a quote that is checked.

This is the user-prompt path.  It is the LLM alone: nothing cross-checks the answer, so LEO treats
it the way it treats any LLM-only claim (``docs/LEO_ROUTING_RULES.md``): never accepted
automatically.  What LEO adds is the quote check.

* The model must copy the words that support its answer.  The quote is located in the note
  (exact, then whitespace-tolerant, ``chain_llm.locate_quote``).
* quote found       -> ``needs_review`` (``llm_only``), with character offsets
* quote not found   -> ``rejected`` (``offsets_unresolved``): the answer is shown but not trusted
* no answer stated  -> ``not_documented``
* the question names a drug and neither the quote nor the sentence it sits in mentions that drug (under any of its
  generic, salt or brand names) -> ``rejected`` (``quote_off_topic``).  Found on the synthetic questions: the model answered "yes" to "is the
  patient taking X?" for drugs the note never mentions, and the quote it gave (a real passage) was about other drugs.

Answers are constrained to the requested type (yes/no, number, one of a list, or short text) by
schema-constrained decoding.  Long notes are split and the per-chunk answers combined: the answer
given most often wins, a tie goes to the earliest chunk.  Not scored against gold; nothing here has
a measured accuracy.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from services.leo_catalog import AskSpec

logger = logging.getLogger(__name__)

ASK_PROMPT_VERSION = "ask.v1"
NOT_DOCUMENTED = "not_documented"


def _drug_names(question: str) -> list[set[str]]:
    """For each ASM the question names: all of its written forms (lower case)."""
    import re

    from rules.asm_lexicon import ASM_LEXICON
    q = question.lower()
    out = []
    for key, e in ASM_LEXICON.items():
        forms = {key, str(e.get("label") or key).lower(),
                 *(s.lower() for s in e.get("salts") or []), *(b.lower() for b in e.get("brands") or []),
                 *(o.lower() for o in e.get("other_names") or [])}
        if any(re.search(r"\b" + re.escape(f) + r"\b", q) for f in forms if len(f) > 3):
            out.append({f for f in forms if len(f) > 3})
    return out


def _quote_on_topic(quote: str, names: list[set[str]], note: str = "") -> bool:
    """True when the question names no drug, or every drug it names is in the quote or in the sentence holding it."""
    import re

    from rules.sentence_context import sentence_span
    from services.chain_llm import locate_quote
    ql = (quote or "").lower()
    if note and quote:
        span = locate_quote(quote, note)
        if span is not None:
            s, e = sentence_span(note, span[0], span[1])
            ql += " " + note[s:e].lower()
    return all(any(re.search(r"\b" + re.escape(f) + r"\b", ql) for f in forms) for forms in names)


@dataclass
class AskResult:
    spec_id: str
    question: str
    answer: Optional[str]
    quote: str
    status: str                     # needs_review | rejected | not_documented | error
    reason: str = ""
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    n_chunks: int = 1

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def answer_model(spec: AskSpec):
    """Pydantic model that constrains the output for ``spec`` (built per call; cheap)."""
    from typing import Literal

    from pydantic import Field, create_model

    if spec.answer_type == "yes_no":
        ans: Any = (Optional[Literal["yes", "no", NOT_DOCUMENTED]], None)       # type: ignore[valid-type]
    elif spec.answer_type == "choice":
        ans = (Optional[Literal[tuple(list(spec.choices) + [NOT_DOCUMENTED])]], None)  # type: ignore[valid-type]
    elif spec.answer_type == "number":
        ans = (Optional[float], None)
    else:
        ans = (Optional[str], Field(default=None, max_length=300))
    return create_model("AskAnswer", answer=ans,
                        quote=(Optional[str], Field(default=None, max_length=240)))


def build_ask_prompt(note: str, spec: AskSpec) -> str:
    kinds = {
        "yes_no": 'Answer "yes", "no" or "not_documented".',
        "choice": f"Answer with exactly one of: {', '.join(spec.choices)}, or not_documented.",
        "number": "Answer with a number, or null if the note does not state one.",
        "text": "Answer in at most one short sentence, in the note's own words where possible.",
    }[spec.answer_type]
    return (
        "You answer one question about one clinical note about a patient with epilepsy.\n"
        "Use only what the note says. Do not guess, diagnose or infer from general knowledge.\n"
        f'If the note does not state the answer, set "answer" to {NOT_DOCUMENTED!r} (or null) and "quote" to null.\n'
        'Every answer needs "quote": the exact words copied from the note that support it.\n'
        "Reply with ONE JSON object: "
        '{"answer": ..., "quote": ...} and nothing else.\n\n'
        f"Question: {spec.question}\n{kinds}\n\n"
        f'Note:\n"""\n{note}\n"""\nJSON:\n'
    )


def _norm_answer(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


class Asker:
    """Runs questions on a loaded backend (``Med42Backend`` or anything with ``generate_constrained``)."""

    def __init__(self, backend: Any, *, chunk_max_chars: int = 8000, overlap_chars: int = 400,
                 max_new_tokens: int = 320):
        self.backend = backend
        self.chunk_max_chars = chunk_max_chars
        self.overlap_chars = overlap_chars
        self.max_new_tokens = max_new_tokens
        self.model_name = getattr(backend, "model_name", "")

    def _once(self, note: str, spec: AskSpec) -> tuple[Optional[str], str]:
        from services.extract import DecodingConfig
        decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None,
                                  max_new_tokens=self.max_new_tokens, seed=0, constrained=False)
        raw, _ = self.backend.generate_constrained(build_ask_prompt(note, spec), answer_model(spec), decoding)
        from services.flat_extract import _json_obj
        obj = _json_obj(raw) or {}
        return _norm_answer(obj.get("answer")), (str(obj.get("quote") or "")).strip()

    def ask(self, note: str, spec: AskSpec) -> AskResult:
        from services.chain_llm import locate_quote
        if not note or not note.strip():
            return AskResult(spec.id, spec.question, None, "", "error", "empty_note")
        try:
            if len(note) <= self.chunk_max_chars:
                parts = [self._once(note, spec)]
            else:
                from services.chunker import chunk_text
                chunks = chunk_text(note, max_chars=self.chunk_max_chars, overlap_chars=self.overlap_chars, pack=True)
                parts = [self._once(c.text, spec) for c in chunks]
        except Exception as e:                               # a model error must not stop a batch
            logger.exception("ask failed")
            return AskResult(spec.id, spec.question, None, "", "error", f"{type(e).__name__}: {e}")
        n = len(parts)
        stated = [(a, q) for a, q in parts if a and a.lower() != NOT_DOCUMENTED]
        if not stated:
            return AskResult(spec.id, spec.question, NOT_DOCUMENTED, "", "not_documented", n_chunks=n)
        names = _drug_names(spec.question)
        if names:
            on_topic = [(a, q) for a, q in stated if _quote_on_topic(q, names, note)]
            if not on_topic:
                return AskResult(spec.id, spec.question, stated[0][0], stated[0][1], "rejected", "quote_off_topic",
                                 n_chunks=n)
            stated = on_topic
        counts: dict[str, list] = {}
        for a, q in stated:
            counts.setdefault(a.lower(), []).append((a, q))
        answer, quote = max(counts.values(), key=len)[0]
        span = locate_quote(quote, note) if quote else None
        if span is None:
            return AskResult(spec.id, spec.question, answer, quote, "rejected",
                             "offsets_unresolved" if quote else "no_quote", n_chunks=n)
        return AskResult(spec.id, spec.question, answer, note[span[0]:span[1]], "needs_review", "llm_only",
                         span[0], span[1], n)


__all__ = ["Asker", "AskResult", "AskSpec", "answer_model", "build_ask_prompt", "ASK_PROMPT_VERSION", "NOT_DOCUMENTED"]
