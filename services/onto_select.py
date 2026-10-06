"""Arm E: the model picks an ontology code from a retrieved list, or abstains.

The retriever (``OntologyCandidateService``) proposes identifiers.  This module is the only place
the model is allowed to attach a code, and it may only choose an index on that list.  A code that
is not in the list is discarded (abstain).  The model never writes an HPO / SNOMED / RxNorm id of
its own.

Used by ``ChainPipeline`` on mentions whose top lexical hit is not an exact label/synonym
(score < 0.9).  Exact hits skip this call.  One batched constrained decode per note.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

SELECT_PROMPT_VERSION = "v1"
SELECT_ARM = "E"
SELECT_K = 5

logger = logging.getLogger(__name__)


class _Pick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    choice: Optional[int] = Field(None, ge=1, le=SELECT_K)
    quote: Optional[str] = None


class _SelectBatch(BaseModel):
    """Constrained-decode target: one pick per mention id, choice = 1-based index or null."""
    model_config = ConfigDict(extra="forbid")
    picks: list[_Pick] = Field(default_factory=list)


def select_answer_model():
    return _SelectBatch


def snapshot(cands: list[Any], k: int = SELECT_K) -> list[dict]:
    """JSON-safe view of the top-k candidates (what the claim and the prompt both see)."""
    out = []
    for i, c in enumerate(cands[:k], 1):
        out.append({
            "index": i,
            "system": getattr(c, "system", "") or (c.get("system") if isinstance(c, dict) else ""),
            "id": getattr(c, "id", "") or (c.get("id") if isinstance(c, dict) else ""),
            "label": getattr(c, "label", "") or (c.get("label") if isinstance(c, dict) else ""),
            "rank_score": float(getattr(c, "rank_score", None)
                                or (c.get("rank_score") if isinstance(c, dict) else 0) or 0),
        })
    return out


def _cand_line(c: dict) -> str:
    defn = (c.get("definition") or "").strip().replace("\n", " ")
    if len(defn) > 160:
        defn = defn[:159] + "…"
    extra = f" — {defn}" if defn else ""
    return f"    {c['index']}. {c['system']} {c['id']}  {c['label']}{extra}"


def build_select_prompt(note: str, items: list[dict]) -> str:
    """``items``: ``{id, mention, field_path, candidates}`` with candidates already snapshotted."""
    blocks = []
    for it in items:
        lines = "\n".join(_cand_line(c) for c in it["candidates"])
        blocks.append(
            f"Mention id={it['id']!r}  field={it.get('field_path') or ''}\n"
            f"  quote: {it['mention']!r}\n  candidates:\n{lines or '    (none)'}"
        )
    body = "\n\n".join(blocks)
    note_bit = (note or "").strip()
    if len(note_bit) > 2500:
        note_bit = note_bit[:2500] + "…"
    return (
        "You assign ontology codes for epilepsy clinic extraction.\n"
        "For each mention, pick which listed candidate the quote refers to, or null if none fits.\n"
        "Rules:\n"
        "- choice is the 1-based index of a candidate on THAT mention's list, or null.\n"
        "- You MUST NOT invent a code, system, or index that is not on the list.\n"
        "- If the quote is advice, family history, or does not name this concept, choice is null.\n"
        "- quote, when you pick, is a short span copied from the mention (not a new id).\n"
        "Reply with ONE JSON object: {\"picks\": [{\"id\": \"...\", \"choice\": 1, \"quote\": \"...\"}, ...]}\n"
        "Every mention id below must appear once. Use null choice when abstaining.\n\n"
        f"Note (context):\n{note_bit}\n\n{body}\n"
    )


@dataclass
class SelectResult:
    """Per-mention outcome.  ``choice`` is 1-based or None; ``picked`` is the snapshot dict or None."""
    mention_id: str
    choice: Optional[int] = None
    picked: Optional[dict] = None
    parse_ok: bool = True
    note: str = ""


def parse_select(raw: str, items: list[dict]) -> dict[str, SelectResult]:
    """Map mention id → result.  Out-of-range or unknown ids are abstentions, never new codes."""
    from services.flat_extract import _json_obj
    by_id = {str(it["id"]): it for it in items}
    out: dict[str, SelectResult] = {
        mid: SelectResult(mention_id=mid, choice=None, picked=None, parse_ok=False, note="missing")
        for mid in by_id
    }
    obj = _json_obj(raw)
    if not isinstance(obj, dict):
        return out
    picks = obj.get("picks")
    if not isinstance(picks, list):
        return out
    seen: set[str] = set()
    for p in picks:
        if not isinstance(p, dict):
            continue
        mid = str(p.get("id") or "")
        if mid not in by_id or mid in seen:
            continue
        seen.add(mid)
        n = len(by_id[mid].get("candidates") or [])
        raw_choice = p.get("choice")
        choice = None
        if isinstance(raw_choice, int) and 1 <= raw_choice <= n:
            choice = raw_choice
        elif raw_choice is not None:
            out[mid] = SelectResult(mention_id=mid, parse_ok=True, note="out_of_range")
            continue
        picked = (by_id[mid]["candidates"][choice - 1] if choice else None)
        out[mid] = SelectResult(mention_id=mid, choice=choice, picked=picked, parse_ok=True,
                                note="" if choice else "abstain")
    for mid, r in out.items():
        if not r.parse_ok:
            r.parse_ok = True
            r.note = r.note or "abstain"
    return out


class OntologySelector:
    """One batched constrained call per note.  ``backend`` has ``generate_constrained`` like Med42Backend."""

    def __init__(self, backend: Any, *, max_new_tokens: int = 512):
        self.backend = backend
        self.max_new_tokens = max_new_tokens
        self.n_calls = 0

    def __call__(self, note: str, items: list[dict]) -> dict[str, SelectResult]:
        if not items:
            return {}
        from services.extract import DecodingConfig
        prompt = build_select_prompt(note, items)
        decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None,
                                  max_new_tokens=self.max_new_tokens, seed=0, constrained=False)
        try:
            raw, _ = self.backend.generate_constrained(prompt, select_answer_model(), decoding)
        except Exception:
            logger.exception("ontology selector failed; abstaining")
            return {str(it["id"]): SelectResult(mention_id=str(it["id"]), parse_ok=False, note="error")
                    for it in items}
        self.n_calls += 1
        return parse_select(raw if isinstance(raw, str) else json.dumps(raw), items)


__all__ = [
    "SELECT_ARM", "SELECT_K", "SELECT_PROMPT_VERSION", "OntologySelector", "SelectResult",
    "build_select_prompt", "parse_select", "select_answer_model", "snapshot",
]
