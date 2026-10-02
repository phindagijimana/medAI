"""LEO claims -> table rows (one row per note, plus a long table of claims).

Wide row, per selected phenotype ``<id>``:

    <id>            the value (lists: names joined with "; "; frequency: "2 per month" or "seizure free")
    <id>_status     accepted | needs_review | not_found
    <id>_evidence   the note's own words (several claims joined with " | ")
    <id>_source     which channel produced it: specialist, llm, or specialist+llm
    <id>_why        reason codes when the status is needs_review (e.g. source_disagreement, llm_only)
    <id>_detail     lists only: name (dose) per drug
    seizure_frequency also gets _count_min, _count_max, _period, _seizure_free

``accepted``  = every claim for this phenotype passed LEO's automatic checks (specialist and LLM agree, or one
source made the claim and nothing contradicted it).  It is not a guarantee: see services/leo_evidence.py for
how often accepted values were right on the test notes.  ``needs_review`` = at least one claim is
in the review queue.  With no LLM (one reader) nothing is ``accepted``: every value is ``needs_review``
with the reason ``no_second_reader``.  Rejected claims never reach the wide table; they are in the claims table.
``not_found`` = no claim.  With ``include_review=False`` values that need review are left blank.

Spreadsheet safety: text that starts with = + - @ is prefixed with an apostrophe so Excel does not
run it as a formula.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from services.leo_catalog import Phenotype

CLAIM_COLUMNS = ["document_id", "row_index", "field_path", "value", "verdict", "reason_codes", "evidence",
                 "char_start", "char_end", "section", "assertion", "experiencer", "temporality", "source",
                 "alternative"]
_MAX_CELL = 2000


def _safe(s: Any) -> Any:
    if isinstance(s, str):
        s = s.replace("\r", " ")
        if len(s) > _MAX_CELL:
            s = s[:_MAX_CELL - 1] + "…"
        if s[:1] in ("=", "+", "-", "@"):
            return "'" + s
    return s


def display_drug(name: str) -> str:
    """Readable generic name: lexicon label for a salt, brand or alias; otherwise the name as given."""
    n = (name or "").strip().lower().replace(" ", "")
    try:
        from rules.asm_lexicon import ASM_LEXICON
        for key, e in ASM_LEXICON.items():
            group = {key.lower().replace(" ", ""), (e.get("label") or "").lower().replace(" ", ""),
                     *[x.lower().replace(" ", "") for x in e.get("salts", [])],
                     *[x.lower().replace(" ", "") for x in e.get("brands", [])],
                     *[x.lower().replace(" ", "") for x in e.get("other_names", [])]}
            if n in group:
                return e.get("label") or key
    except Exception:
        pass
    return (name or "").strip()


def _sources(c: Any) -> str:
    d = {x.lower() for x in (c.detectors or [])}
    ch = []
    if any("specialist" in x or "epextra" in x or "medcat" in x for x in d):
        ch.append("specialist")
    if any("llm" in x for x in d):
        ch.append("llm")
    return "+".join(ch) or "+".join(sorted(d))


def _freq_text(v: dict) -> str:
    if v.get("seizure_free"):
        return "seizure free"
    lo, hi, per = v.get("count_min"), v.get("count_max"), v.get("period")
    if lo is None and hi is None:
        return v.get("raw_text") or ""
    fmt = lambda x: str(int(x)) if float(x).is_integer() else f"{x:g}"
    cnt = fmt(lo) if hi is None or lo == hi else f"{fmt(lo)}-{fmt(hi)}"
    return f"{cnt} per {per}" if per and per != "unspecified" else cnt


def _value_text(ph: Phenotype, v: Any) -> str:
    if v is None:
        return ""
    if ph.kind == "frequency" and isinstance(v, dict):
        return _freq_text(v)
    if isinstance(v, dict):
        if "generic_name" in v:
            return display_drug(v.get("generic_name") or "")
        # surgery and similar objects: the readable parts only
        parts = [str(x) for k, x in v.items() if x not in (None, "", False) and k in
                 ("surgery_type", "target", "laterality", "year", "therapy_type", "lobe")]
        return " ".join(parts) or "; ".join(f"{k}={x}" for k, x in v.items() if x not in (None, ""))
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(getattr(v, "value", v))


def _detail(v: Any) -> str:
    if isinstance(v, dict) and "generic_name" in v:
        name = display_drug(v.get("generic_name") or "")
        return f"{name} ({v['dose_text']})" if v.get("dose_text") else name
    return ""


def claim_rows(claims: Iterable[Any], document_id: str, row_index: int, *, single_reader: bool = False) -> list[dict]:
    out = []
    for c in claims:
        v = c.value
        verdict = c.validator_verdict.value
        reasons = [r.value for r in c.reason_codes]
        if single_reader and verdict == "accept":          # nothing was cross-checked
            verdict, reasons = "review", reasons + ["no_second_reader"]
        out.append({
            "document_id": document_id, "row_index": row_index, "field_path": c.field_path or "",
            "value": _safe(v if isinstance(v, (str, int, float, bool)) or v is None else
                           _value_text(_GENERIC, v)),
            "verdict": verdict,
            "reason_codes": ";".join(reasons),
            "evidence": _safe(c.mention.text), "char_start": c.mention.start, "char_end": c.mention.end,
            "section": c.section, "assertion": c.assertion.value, "experiencer": c.experiencer.value,
            "temporality": c.temporality.status.value, "source": _sources(c), "alternative": _safe(c.alternative or ""),
        })
    return out


def wide_columns(phenotypes: list[Phenotype]) -> list[str]:
    cols: list[str] = []
    for p in phenotypes:
        cols += [p.id, f"{p.id}_status", f"{p.id}_evidence", f"{p.id}_source", f"{p.id}_why"]
        if p.kind == "list":
            cols.append(f"{p.id}_detail")
        if p.kind == "frequency":
            cols += [f"{p.id}_count_min", f"{p.id}_count_max", f"{p.id}_period", f"{p.id}_seizure_free"]
    return cols


def wide_row(claims: list[Any], phenotypes: list[Phenotype], *, include_review: bool = True,
             single_reader: bool = False) -> dict:
    """One row of phenotype columns from the claims of one note.

    ``single_reader=True`` (no LLM ran) turns every ``accepted`` into ``needs_review`` with the reason
    ``no_second_reader``.  With the LLM present, ACCEPT means the two sources were compared; without it nothing
    was cross-checked, and specialist-only claims were right only 25% of the time on the F-S letters.
    """
    def ok(c: Any) -> bool:
        return (not single_reader) and c.validator_verdict.value == "accept"

    row: dict = {}
    for p in phenotypes:
        mine = [c for c in claims if c.field_path in p.field_paths and c.validator_verdict.value != "reject"]
        mine.sort(key=lambda c: 0 if ok(c) else 1)
        row.update({p.id: "", f"{p.id}_status": "not_found", f"{p.id}_evidence": "", f"{p.id}_source": "",
                    f"{p.id}_why": ""})
        if p.kind == "list":
            row[f"{p.id}_detail"] = ""
        if p.kind == "frequency":
            row.update({f"{p.id}_count_min": "", f"{p.id}_count_max": "", f"{p.id}_period": "",
                        f"{p.id}_seizure_free": ""})
        if not mine:
            continue
        all_ok = all(ok(c) for c in mine)
        why = sorted({r.value for c in mine if not ok(c) for r in c.reason_codes})
        if single_reader:
            why = sorted(set(why) | {"no_second_reader"})
        if p.kind == "list":
            seen, vals, details, ev, src = set(), [], [], [], set()
            for c in mine:
                if not include_review and not ok(c):
                    continue
                t = _value_text(p, c.value)
                if t and t.lower() not in seen:
                    seen.add(t.lower())
                    vals.append(t)
                    details.append(_detail(c.value) or t)
                    ev.append(c.mention.text)
                    src.add(_sources(c))
            row[p.id] = _safe("; ".join(vals))
            row[f"{p.id}_detail"] = _safe("; ".join(details))
            row[f"{p.id}_evidence"] = _safe(" | ".join(ev))
            row[f"{p.id}_source"] = "; ".join(sorted(src))
        else:
            best = mine[0]
            distinct = {_value_text(p, c.value) for c in mine}
            if len(distinct) > 1:
                why = sorted(set(why) | {"conflicting_values"})
                all_ok = False
            if include_review or ok(best):
                row[p.id] = _safe(_value_text(p, best.value))
                row[f"{p.id}_evidence"] = _safe(best.mention.text)
                row[f"{p.id}_source"] = _sources(best)
                if p.kind == "frequency" and isinstance(best.value, dict):
                    v = best.value
                    row[f"{p.id}_count_min"] = "" if v.get("count_min") is None else v["count_min"]
                    row[f"{p.id}_count_max"] = "" if v.get("count_max") is None else v["count_max"]
                    per = v.get("period")
                    row[f"{p.id}_period"] = "" if per in (None, "unspecified") else per
                    row[f"{p.id}_seizure_free"] = bool(v.get("seizure_free"))
        row[f"{p.id}_status"] = "accepted" if all_ok else "needs_review"
        row[f"{p.id}_why"] = ";".join(why)
    return row


class _Generic:
    kind = "scalar"


_GENERIC: Any = _Generic()

__all__ = ["CLAIM_COLUMNS", "claim_rows", "wide_columns", "wide_row", "display_drug"]
