"""Collect and score the cases where the model and the rules disagree (the data a per-field policy needs).

LEO shows one value and keeps the other reader's value as the claim's ``alternative``.  Which reader is
right per field is not known for real notes, so a pilot should collect the disagreements, have an
adjudicator decide each one *without knowing which reader said what*, and then score the readers.

``export_cases(claims_csv)``  -> one row per disagreement, readings A and B in a random but reproducible
                                 order (the key to the order is in the last column; hide it from the adjudicator)
``score_cases(adjudicated)``  -> per field: how often the rules were right, the model was right, both, neither,
                                 with Wilson 95% intervals.

Protocol: docs/DISAGREEMENT_ADJUDICATION.md.  Files contain note text (the evidence quote): treat as PHI.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Optional

import pandas as pd

TRUTH_CHOICES = ("A", "B", "both", "neither", "unclear")

CASE_COLUMNS = ["case_id", "document_id", "row_index", "field_path", "reading_A", "reading_B", "evidence_shown",
                "truth", "true_value", "adjudicator", "comment", "key_A_is"]


def _a_is_shown(case_id: str) -> bool:
    """Reproducible coin flip from the case id (not random.random, so a re-export gives the same sheet)."""
    return int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % 2 == 0


def export_cases(claims: pd.DataFrame) -> pd.DataFrame:
    """Disagreement cases from a ``<out>.claims.csv`` table.

    ``reading_A``/``reading_B`` are the two readers' values in a hidden order.  ``key_A_is`` says which
    reader reading_A is: ``shown`` = the value LEO displayed (the rules' value under the default policy),
    ``other`` = the alternative.  Remove that column before the sheet goes to an adjudicator.
    """
    need = {"document_id", "row_index", "field_path", "value", "reason_codes", "alternative", "evidence"}
    missing = need - set(claims.columns)
    if missing:
        raise ValueError(f"not a LEO claims table, missing columns: {sorted(missing)}")
    df = claims.fillna("")
    mask = df["reason_codes"].astype(str).str.contains("source_disagreement", regex=False)
    mask &= df["alternative"].astype(str).str.strip() != ""
    rows = []
    for _, r in df[mask].iterrows():
        cid = f"{r['document_id']}|{r['row_index']}|{r['field_path']}"
        shown, other = str(r["value"]), str(r["alternative"])
        a_shown = _a_is_shown(cid)
        rows.append({"case_id": cid, "document_id": r["document_id"], "row_index": r["row_index"],
                     "field_path": r["field_path"],
                     "reading_A": shown if a_shown else other, "reading_B": other if a_shown else shown,
                     "evidence_shown": r["evidence"], "truth": "", "true_value": "", "adjudicator": "",
                     "comment": "", "key_A_is": "shown" if a_shown else "other"})
    return pd.DataFrame(rows, columns=CASE_COLUMNS)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def score_cases(sheet: pd.DataFrame, shown_reader: str = "rules") -> dict:
    """Per-field tally of an adjudicated sheet (must still carry ``key_A_is``).

    ``shown_reader`` names who produced the value LEO displayed (``rules`` under the default policy,
    ``model`` for fields on the candidate policy).  Cases with truth ``unclear`` or blank are counted
    separately and left out of the rates.
    """
    if shown_reader not in ("rules", "model"):
        raise ValueError("shown_reader must be rules or model")
    df = sheet.fillna("")
    if "key_A_is" not in df.columns:
        raise ValueError("the sheet has no key_A_is column; score it with the key still attached")
    out: dict[str, dict] = {}
    other_reader = "model" if shown_reader == "rules" else "rules"
    for field, g in df.groupby("field_path"):
        t = {"rules": 0, "model": 0, "both": 0, "neither": 0, "unclear": 0, "unadjudicated": 0}
        for _, r in g.iterrows():
            truth = str(r["truth"]).strip()
            if truth == "":
                t["unadjudicated"] += 1
            elif truth in ("both", "neither", "unclear"):
                t[truth] += 1
            elif truth in ("A", "B"):
                a_is_shown = r["key_A_is"] == "shown"
                picked_shown = (truth == "A") == a_is_shown
                t[shown_reader if picked_shown else other_reader] += 1
            else:
                raise ValueError(f"truth must be one of {TRUTH_CHOICES}, got {truth!r} ({r['case_id']})")
        n = t["rules"] + t["model"] + t["both"] + t["neither"]
        res = {"n_cases": int(len(g)), "n_scored": n, **t}
        for reader in ("rules", "model"):
            k = t[reader] + t["both"]
            lo, hi = wilson(k, n)
            res[f"{reader}_right"] = {"k": k, "n": n, "rate": round(k / n, 3) if n else None,
                                     "ci95": [round(lo, 3), round(hi, 3)]}
        out[field] = res
    return out


def load(path: Path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        return pd.read_excel(p, dtype=str)
    return pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig")


ACCEPTED_COLUMNS = ["case_id", "document_id", "row_index", "field_path", "value", "evidence_shown",
                    "truth", "true_value", "adjudicator", "comment"]
CODE_COLUMNS = ["case_id", "document_id", "row_index", "field_path", "mention", "selected_system",
                "selected_id", "selected_label", "ontology_match", "code_accepted", "candidates",
                "truth", "true_system", "true_id", "adjudicator", "comment"]


def export_accepted_sample(claims: pd.DataFrame, n: int = 50, seed: str = "leo-accepted") -> pd.DataFrame:
    """A reproducible sample of accepted *values* (the protocol's check that disagreements miss 'both wrong')."""
    need = {"document_id", "row_index", "field_path", "value", "verdict", "evidence"}
    missing = need - set(claims.columns)
    if missing:
        raise ValueError(f"not a LEO claims table, missing columns: {sorted(missing)}")
    df = claims.fillna("")
    acc = df[df["verdict"].astype(str).str.lower().eq("accept")].copy()
    if acc.empty:
        return pd.DataFrame(columns=ACCEPTED_COLUMNS)
    acc["_k"] = acc.apply(lambda r: int(hashlib.sha256(
        f"{seed}|{r['document_id']}|{r['row_index']}|{r['field_path']}|{r['value']}".encode()).hexdigest(), 16), axis=1)
    acc = acc.sort_values("_k").head(int(n))
    rows = []
    for _, r in acc.iterrows():
        cid = f"{r['document_id']}|{r['row_index']}|{r['field_path']}|accepted"
        rows.append({"case_id": cid, "document_id": r["document_id"], "row_index": r["row_index"],
                     "field_path": r["field_path"], "value": r["value"], "evidence_shown": r["evidence"],
                     "truth": "", "true_value": "", "adjudicator": "", "comment": ""})
    return pd.DataFrame(rows, columns=ACCEPTED_COLUMNS)


def export_code_cases(claims: pd.DataFrame) -> pd.DataFrame:
    """One row per claim that has candidates: quote, selected id, list. Adjudicator marks correct/wrong/abstain-ok."""
    need = {"document_id", "row_index", "field_path", "evidence"}
    missing = need - set(claims.columns)
    if missing:
        raise ValueError(f"not a LEO claims table, missing columns: {sorted(missing)}")
    df = claims.fillna("")
    if "ontology_candidates" not in df.columns:
        return pd.DataFrame(columns=CODE_COLUMNS)
    rows = []
    for _, r in df.iterrows():
        cands = str(r.get("ontology_candidates") or "").strip()
        if not cands:
            continue
        cid = f"{r['document_id']}|{r['row_index']}|{r['field_path']}|code"
        rows.append({
            "case_id": cid, "document_id": r["document_id"], "row_index": r["row_index"],
            "field_path": r["field_path"], "mention": r["evidence"],
            "selected_system": r.get("concept_system", ""), "selected_id": r.get("concept_id", ""),
            "selected_label": r.get("concept_label", ""), "ontology_match": r.get("ontology_match", ""),
            "code_accepted": r.get("code_accepted", ""), "candidates": cands,
            "truth": "", "true_system": "", "true_id": "", "adjudicator": "", "comment": "",
        })
    return pd.DataFrame(rows, columns=CODE_COLUMNS)


def score_code_cases(sheet: pd.DataFrame) -> dict:
    """truth = correct | wrong | abstain_ok | unclear | blank."""
    df = sheet.fillna("")
    t = {"correct": 0, "wrong": 0, "abstain_ok": 0, "unclear": 0, "unadjudicated": 0}
    for _, r in df.iterrows():
        truth = str(r.get("truth") or "").strip().lower()
        if truth == "":
            t["unadjudicated"] += 1
        elif truth in t:
            t[truth] += 1
        else:
            raise ValueError(f"code-sheet truth must be correct, wrong, abstain_ok or unclear, got {truth!r}")
    n = t["correct"] + t["wrong"] + t["abstain_ok"]
    k = t["correct"] + t["abstain_ok"]
    lo, hi = wilson(k, n)
    return {"n_cases": int(len(df)), "n_scored": n, **t,
            "selector_ok": {"k": k, "n": n, "rate": round(k / n, 3) if n else None,
                            "ci95": [round(lo, 3), round(hi, 3)]}}
