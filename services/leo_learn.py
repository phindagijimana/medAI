"""Versioned learning from Validator files. Does not change extract.

Clicks are labels. ``leo learn`` reads ``reviewed.csv`` (or the opt-in training archive)
and prints Loop A (routing) and Loop B (accept thresholds). It writes a policy JSON only
when the ≥100/field CI gate passes. It never retrains Med42, never rewrites few-shot,
and never hot-reloads the next extract. Apply a policy on a new ``leo-v0.x`` with
``--disagree-llm policy:FILE``. Loop C (few-shot / LoRA / BIO) is paused.

Protocol: ``docs/ACTIVE_LEARNING_PLAN.md``, ``docs/DISAGREEMENT_ADJUDICATION.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from services.leo_disagree import policy_from_scores, wilson
from services.leo_review import DECISIONS, READER_PREFERRED

MIN_N = 100
PAUSED_C = ("Loop C (few-shot / LoRA / BIO) is paused until IRB notes exist and a "
            "frozen test set is held out. Doctor clicks are labels, not completions. "
            "See docs/ACTIVE_LEARNING_PLAN.md.")
APPLY_REFUSED = ("leo learn does not change extract. If a policy JSON meets the "
                 "≥100/field CI gate, apply it on a new leo-v0.x with "
                 "--disagree-llm policy:FILE. D17 stays until then.")


def claim_path(field: str) -> str:
    """Phenotype id or short name → Claim.field_path (what --disagree-llm policy:FILE uses)."""
    f = (field or "").strip()
    if not f:
        return f
    from services.leo_runtime import _SHORT_PATH
    if f in _SHORT_PATH:
        return _SHORT_PATH[f]
    try:
        from services.leo_catalog import get
        p = get(f)
        if p.field_paths:
            return p.field_paths[0]
    except KeyError:
        pass
    return f


def archive_reviewed_paths() -> list[Path]:
    """Permitted copies in data/leo_training/<job>/reviewed.csv (not the 24-hour job folder)."""
    from services.leo_training_archive import archive_root
    root = archive_root()
    out = []
    for p in sorted(root.glob("*/reviewed.csv")):
        if (p.parent / "consent.json").is_file():
            out.append(p)
    return out


def load_reviews(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Latest decision per (doc_id, row, field) across one or more reviewed.csv files."""
    frames = []
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.is_file():
            raise FileNotFoundError(str(p))
        df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if "decision" not in df.columns or "field" not in df.columns:
            raise ValueError(f"{p.name} is not a reviewed.csv")
        df = df.copy()
        df["_src"] = str(p)
        frames.append(df)
    if not frames:
        raise ValueError("no reviewed.csv files")
    df = pd.concat(frames, ignore_index=True)
    df["decision"] = df["decision"].astype(str).str.strip().str.lower()
    df = df[df["decision"].isin(DECISIONS)].copy()
    if df.empty:
        return df
    if "reviewed_utc" in df.columns:
        df = df.sort_values("reviewed_utc", kind="mergesort")
    keys = [c for c in ("doc_id", "row", "field") if c in df.columns]
    if len(keys) == 3:
        ident = df["doc_id"].astype(str).str.strip() + "|" + df["row"].astype(str).str.strip()
        has_id = ident.str.strip("|") != ""
        df = pd.concat([df.loc[~has_id], df.loc[has_id].drop_duplicates(keys, keep="last")],
                       ignore_index=True)
    return df.reset_index(drop=True)


def scores_from_reviews(df: pd.DataFrame) -> dict[str, dict]:
    """Loop A: per-field reader votes from ``reader_preferred`` (disagreements only)."""
    if df.empty or "reader_preferred" not in df.columns:
        return {}
    rp = df.copy()
    rp["reader_preferred"] = rp["reader_preferred"].astype(str).str.strip().str.lower()
    rp = rp[rp["reader_preferred"].isin(READER_PREFERRED)]
    out: dict[str, dict] = {}
    for field, g in rp.groupby(rp["field"].astype(str).str.strip(), sort=True):
        t = {"rules": 0, "model": 0, "both": 0, "neither": 0, "unclear": 0, "unadjudicated": 0}
        for v in g["reader_preferred"]:
            t[v] += 1
        n = t["rules"] + t["model"] + t["both"] + t["neither"]
        res: dict[str, Any] = {"n_cases": int(len(g)), "n_scored": n, **t,
                               "claim_path": claim_path(str(field))}
        for reader in ("rules", "model"):
            k = t[reader] + t["both"]
            lo, hi = wilson(k, n)
            res[f"{reader}_right"] = {"k": k, "n": n, "rate": round(k / n, 3) if n else None,
                                     "ci95": [round(lo, 3), round(hi, 3)]}
        out[str(field)] = res
    return out


def policy_from_reviews(scores: dict, *, min_n: int = MIN_N) -> dict[str, str]:
    """Same CI gate as ``leo disagreements --emit-policy``. Keys are claim paths."""
    mapped = {}
    for field, res in (scores or {}).items():
        mapped[res.get("claim_path") or claim_path(field)] = res
    return policy_from_scores(mapped, min_n=min_n)


def loop_b(df: pd.DataFrame) -> dict[str, Any]:
    """Accept vs Correct vs Deny, split flagged vs accepted audit. Recommendations only."""
    if df.empty:
        return {"fields": {}, "why": {}, "audit": {}, "flagged": {}, "recommendations": []}
    why_col = df["why_tag"].astype(str).str.strip().str.lower() if "why_tag" in df.columns else pd.Series([""] * len(df))
    status = (df["proposed_status"].astype(str).str.strip().str.lower()
              if "proposed_status" in df.columns else pd.Series([""] * len(df)))
    quote = (df["quote_ok"].astype(str).str.strip().str.lower()
             if "quote_ok" in df.columns else pd.Series([""] * len(df)))
    fields: dict[str, dict] = {}
    for field, g in df.groupby(df["field"].astype(str).str.strip(), sort=True):
        d = g["decision"]
        idx = g.index
        st = status.loc[idx]
        fields[str(field)] = {
            "n": int(len(g)),
            "accept": int((d == "accept").sum()),
            "correct": int((d == "correct").sum()),
            "reject": int((d == "reject").sum()),
            "add": int((d == "add").sum()),
            "n_audit": int((st == "accepted").sum()),
            "n_flagged": int(st.isin(("needs_review", "rejected")).sum()),
        }
    why = {str(k): int(v) for k, v in why_col[why_col != ""].value_counts().items()}
    audit_idx = status == "accepted"
    flagged_idx = status.isin(("needs_review", "rejected"))

    def _rates(mask) -> dict:
        sub = df.loc[mask]
        n = int(len(sub))
        if n == 0:
            return {"n": 0, "kept": 0, "changed": 0, "precision": None}
        kept = int((sub["decision"] == "accept").sum())
        changed = int(sub["decision"].isin(("correct", "reject")).sum())
        prec = round(kept / n, 3) if n else None
        return {"n": n, "kept": kept, "changed": changed, "precision": prec}

    audit, flagged = _rates(audit_idx), _rates(flagged_idx)
    recs = []
    n_quote = int(why.get("quote_does_not_support", 0)) + int((quote == "no").sum())
    n_status = int(why.get("wrong_status", 0))
    n_value = int(why.get("wrong_value", 0))
    if audit["n"] >= 10 and audit["precision"] is not None and audit["precision"] < 0.90:
        recs.append("Loop B: accepted-cell audit precision is below 0.90. Tighten fusion "
                    "(quote-entailment; stop auto-accepting surgery/plans) on a new leo-v0.x. "
                    "Do not tune on the reported test set.")
    elif audit["n"] < 10:
        recs.append("Loop B: fewer than 10 accepted-audit clicks. Switch the Validator to "
                    "Accepted sample (10% audit) so silent errors are measured.")
    if n_quote >= 5:
        recs.append("Loop B: quote_does_not_support is repeating. Score --quote-entail on "
                    "held-out notes before shipping it as default.")
    if n_status >= 5:
        recs.append("Loop B: wrong_status is repeating (medication role / ConText / later-stop-wins). "
                    "Fix as a versioned rule, not LoRA.")
    if n_value >= 5 and n_quote < 5 and n_status < 5:
        recs.append("Loop B: wrong_value without a status/quote cluster. Use Loop A routing first; "
                    "do not turn one comment into a gazetteer.")
    enough = any(v["n"] >= MIN_N for v in fields.values())
    if not enough:
        recs.append(f"Loop B gate: no field has ≥{MIN_N} reviewed cells. Report rates; do not "
                    "change auto-accept thresholds yet.")
    if not recs:
        recs.append("Loop B: no threshold change indicated. Keep D17 and current ACCEPT rules.")
    recs.append("Recommendations are not applied. A threshold change is a new pipeline version "
                "after a held-out re-score.")
    return {"fields": fields, "why": why, "audit": audit, "flagged": flagged,
            "recommendations": recs}


def run(paths: Iterable[str | Path], *, min_n: int = MIN_N, loops: str = "all") -> tuple[str, dict]:
    """Run Loop A and/or B. Returns (markdown report, result dict). Does not write extract."""
    loops = (loops or "all").strip().lower()
    if loops in ("c", "lora", "few-shot", "fewshot", "bio"):
        raise ValueError(PAUSED_C)
    if loops not in ("a", "b", "all"):
        raise ValueError("loops must be a, b, or all")
    files = [Path(p) for p in paths]
    df = load_reviews(files)
    result: dict[str, Any] = {
        "n_files": len(files), "n_rows": int(len(df)), "min_n": int(min_n),
        "applied": False, "policy": {}, "loop_a": {}, "loop_b": {},
        "paused": "few-shot and LoRA/BIO (Loop C)",
    }
    lines = ["# LEO learn (labels only; extract unchanged)", "",
             f"Files: {result['n_files']}. Decisions: {result['n_rows']}. "
             f"Gate: ≥{min_n} scored cases/field. D17 stays until a new leo-v0.x.",
             "", APPLY_REFUSED, "", PAUSED_C, ""]
    if loops in ("a", "all"):
        scores = scores_from_reviews(df)
        pol = policy_from_reviews(scores, min_n=min_n)
        result["loop_a"] = {"scores": scores, "policy": pol}
        result["policy"] = pol
        lines += ["## Loop A — routing (which reader to show)", ""]
        if not scores:
            lines.append("No `reader_preferred` votes yet. On a disagreement the Validator "
                         "requires rules / model / both / neither.")
        else:
            lines += ["| field | path | n_scored | rules right | model right | gate |",
                      "|---|---|---:|---|---|---|"]
            for field, res in scores.items():
                rr, mr = res["rules_right"], res["model_right"]
                n = res["n_scored"]
                gate = "show model" if claim_path(field) in pol else (
                    "keep rules (n below gate)" if n < min_n else "keep rules (CI gate)")
                rtxt = "n/a" if rr["rate"] is None else f"{rr['k']}/{rr['n']} {rr['rate']:.2f} {rr['ci95']}"
                mtxt = "n/a" if mr["rate"] is None else f"{mr['k']}/{mr['n']} {mr['rate']:.2f} {mr['ci95']}"
                lines.append(f"| `{field}` | `{res['claim_path']}` | {n} | {rtxt} | {mtxt} | {gate} |")
            lines.append("")
            if pol:
                lines.append(f"Policy that meets the gate ({len(pol)} field(s) → model): "
                             f"`{pol}`. Write it with `--emit-policy` and apply only as "
                             "`--disagree-llm policy:FILE` on a new pipeline version.")
            else:
                lines.append("No field meets the CI gate. Empty policy (D17: rules everywhere).")
        lines.append("")
    if loops in ("b", "all"):
        b = loop_b(df)
        result["loop_b"] = b
        lines += ["## Loop B — accept thresholds (still rules)", ""]
        if b["fields"]:
            lines += ["| field | n | accept | correct | deny | add | audit n | flagged n |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|"]
            for field, r in b["fields"].items():
                lines.append(f"| `{field}` | {r['n']} | {r['accept']} | {r['correct']} | "
                             f"{r['reject']} | {r['add']} | {r['n_audit']} | {r['n_flagged']} |")
            lines.append("")
        a, f = b["audit"], b["flagged"]
        ap = "n/a" if a["precision"] is None else f"{a['precision']:.2f}"
        fp = "n/a" if f["precision"] is None else f"{f['precision']:.2f}"
        lines.append(f"Accepted audit (proposed_status=accepted): n={a['n']} kept={a['kept']} "
                     f"changed={a['changed']} precision={ap}. "
                     f"Flagged queue: n={f['n']} kept={f['kept']} changed={f['changed']} precision={fp}.")
        lines.append("Flagged-only rates are biased; the 10% accepted sample is the silent-error check.")
        if b["why"]:
            lines.append("Why tags: " + ", ".join(f"`{k}` {v}" for k, v in b["why"].items()) + ".")
        lines.append("")
        lines.append("Recommendations (not applied):")
        for rec in b["recommendations"]:
            lines.append(f"- {rec}")
        lines.append("")
    lines += ["## Loop C — paused", "", PAUSED_C, ""]
    return "\n".join(lines) + "\n", result


def write_policy(path: str | Path, policy: dict[str, str]) -> Path:
    import json
    dest = Path(path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    return dest


__all__ = ["run", "load_reviews", "scores_from_reviews", "policy_from_reviews", "loop_b",
           "claim_path", "archive_reviewed_paths", "write_policy", "MIN_N", "PAUSED_C", "APPLY_REFUSED"]
