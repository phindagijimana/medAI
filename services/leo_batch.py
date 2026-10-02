"""Spreadsheet in, spreadsheet out: run LEO over a table of notes and append phenotype columns.

Input  (``read_table``)
    .csv, .tsv, .xlsx, .xlsm        one note per row; any other columns are kept as they are
    .jsonl                          one JSON object per line ({"id": ..., "text": ...} plus any keys)
    .txt                            one note
    a directory of .txt files       one note per file (``note_id`` = file name)
    text column: ``--text-col``, else the first of text, note, note_text, clinical_note, source_text,
    content, report.  If none matches the run stops and lists the columns: guessing which column holds
    patient text is not safe.
    optional id column (id, doc_id, note_id, document_id, visit_id, encounter_id) and date column
    (doc_date, note_date, visit_date, encounter_date, date); the date goes to the pipeline.

Output (``write_outputs``)
    csv   <out>.csv                  input columns + LEO columns (utf-8 with BOM, opens in Excel)
          <out>.claims.csv           one row per claim: value, verdict, reasons, evidence, offsets
          <out>.provenance.json      versions, settings, counts, input hash (no note text)
    xlsx  <out>.xlsx                 sheets "LEO" (as the csv), "Claims", "About" (settings and definitions)

The output holds verbatim note text (the evidence columns).  It is as sensitive as the input.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from services.leo_ask import AskResult
from services.leo_catalog import AskSpec, Phenotype
from services.leo_runtime import LeoRuntime
from services.leo_tabular import CLAIM_COLUMNS, _safe, wide_columns

TEXT_COLS = ("text", "note", "note_text", "clinical_note", "source_text", "content", "report")
ID_COLS = ("id", "doc_id", "note_id", "document_id", "visit_id", "encounter_id")
DATE_COLS = ("doc_date", "note_date", "visit_date", "encounter_date", "date")
INPUT_SUFFIXES = (".csv", ".tsv", ".xlsx", ".xlsm", ".jsonl", ".txt")


def read_table(path: str | Path, *, sheet: Optional[str] = None) -> pd.DataFrame:
    """Read any supported input into a string DataFrame (no NaN, no type guessing)."""
    p = Path(path)
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() == ".txt")
        if not files:
            raise ValueError(f"no .txt files in {p}")
        return pd.DataFrame({"note_id": [f.name for f in files],
                             "text": [f.read_text(encoding="utf-8", errors="replace") for f in files]})
    suf = p.suffix.lower()
    if suf == ".txt":
        return pd.DataFrame({"note_id": [p.name], "text": [p.read_text(encoding="utf-8", errors="replace")]})
    if suf in (".csv", ".tsv"):
        return pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig",
                           sep="\t" if suf == ".tsv" else ",")
    if suf in (".xlsx", ".xlsm"):
        df = pd.read_excel(p, sheet_name=sheet if sheet else 0, dtype=str)
        return df.fillna("")
    if suf == ".jsonl":
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        return pd.DataFrame(rows).astype(str).replace({"None": ""})
    raise ValueError(f"unsupported input {p.name!r}; use one of {', '.join(INPUT_SUFFIXES)} or a directory of .txt")


def detect_columns(df: pd.DataFrame, text_col: str = "", id_col: str = "", date_col: str = "") -> dict:
    cols = {c.lower(): c for c in df.columns}

    def pick(given: str, names: tuple[str, ...], what: str, required: bool) -> str:
        if given:
            if given not in df.columns:
                raise ValueError(f"{what} column {given!r} not found; columns are: {list(df.columns)}")
            return given
        for n in names:
            if n in cols:
                return cols[n]
        if required:
            raise ValueError(f"cannot tell which column holds the note text. Columns are: {list(df.columns)}. "
                             f"Pass --text-col NAME (looked for: {', '.join(names)}).")
        return ""

    return {"text": pick(text_col, TEXT_COLS, "text", True), "id": pick(id_col, ID_COLS, "id", False),
            "date": pick(date_col, DATE_COLS, "date", False)}


def _unique(name: str, existing: set[str]) -> str:
    while name in existing:
        name += "_leo"
    existing.add(name)
    return name


def run_table(df: pd.DataFrame, rt: LeoRuntime, *, phenotypes: list[Phenotype], asks: list[AskSpec],
              text_col: str, id_col: str = "", date_col: str = "", include_review: bool = True,
              limit: int = 0, progress: Optional[Callable[[int, int, str], None]] = None,
              cancel: Optional[Callable[[], bool]] = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Run LEO on every row; return (table with LEO columns, claims table, provenance)."""
    n_total = min(len(df), limit) if limit else len(df)
    existing = set(df.columns)
    pheno_cols = wide_columns(phenotypes)
    ask_cols: list[str] = []
    for a in asks:
        ask_cols += [a.id, f"{a.id}_status", f"{a.id}_evidence", f"{a.id}_question"]
    meta_cols = ["leo_doc_id", "leo_status", "leo_llm_used", "leo_n_chunks", "leo_n_claims", "leo_n_review"]
    rename = {c: _unique(c, existing) for c in meta_cols + pheno_cols + ask_cols}

    out_rows: list[dict] = []
    all_claims: list[dict] = []
    n_err = n_llm = 0
    t0 = datetime.now(timezone.utc)
    for i in range(n_total):
        r = df.iloc[i]
        doc_id = (str(r[id_col]).strip() if id_col else "") or f"row{i + 1}"
        res = rt.extract_note(str(r[text_col]), doc_id=doc_id, row_index=i + 1,
                              doc_date=str(r[date_col]) if date_col else "", phenotypes=phenotypes,
                              asks=asks, include_review=include_review)
        row = {rename["leo_doc_id"]: doc_id,
               rename["leo_status"]: ("error: " + res.error) if res.error else "ok",
               rename["leo_llm_used"]: res.llm_used, rename["leo_n_chunks"]: res.n_chunks,
               rename["leo_n_claims"]: res.n_claims, rename["leo_n_review"]: res.n_review}
        for c in pheno_cols:
            row[rename[c]] = res.row.get(c, "")
        by_id = {a["spec_id"]: a for a in res.asks}
        for a in asks:
            x = by_id.get(a.id)
            row[rename[a.id]] = _safe((x or {}).get("answer") or "")
            row[rename[f"{a.id}_status"]] = (x or {}).get("status", "")
            row[rename[f"{a.id}_evidence"]] = _safe((x or {}).get("quote", ""))
            row[rename[f"{a.id}_question"]] = a.question
        out_rows.append(row)
        all_claims.extend(res.claims)
        n_err += bool(res.error)
        n_llm += res.llm_used
        if progress:
            progress(i + 1, n_total, doc_id)
        if cancel and cancel():
            break
    done = len(out_rows)
    base = df.iloc[:done].reset_index(drop=True)
    leo = pd.DataFrame(out_rows, columns=[rename[c] for c in meta_cols + pheno_cols + ask_cols])
    table = pd.concat([base, leo], axis=1)
    claims = pd.DataFrame(all_claims, columns=CLAIM_COLUMNS)
    prov = {
        "tool": "LEO (MedAI-EPI)", "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "started_utc": t0.isoformat(timespec="seconds"), **rt.versions(),
        "rows_requested": n_total, "rows_processed": done, "rows_error": n_err, "rows_with_llm": n_llm,
        "include_review_values": include_review,
        "phenotypes": [p.id for p in phenotypes],
        "phenotypes_not_measured": [p.id for p in phenotypes if p.evidence != "measured"],
        "questions": [{"id": a.id, "question": a.question, "type": a.answer_type} for a in asks],
        "column_map": rename,
        "text_column": text_col, "id_column": id_col, "date_column": date_col,
        "note": ("Rules only (no LLM): nothing was cross-checked, so every value is marked needs_review."
                 if not rt.use_llm else "LLM + specialist; verdicts follow docs/LEO_ROUTING_RULES.md."),
    }
    return table, claims, prov


def input_hash(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    if p.is_dir():
        for f in sorted(p.iterdir()):
            if f.is_file():
                h.update(f.name.encode())
                h.update(f.read_bytes())
    else:
        h.update(p.read_bytes())
    return h.hexdigest()


def default_output(inp: str | Path, fmt: str) -> Path:
    p = Path(inp)
    stem = p.stem if p.is_file() else p.name
    d = p.parent if p.is_file() else p.parent
    return d / f"{stem}_leo.{fmt}"


def _about_rows(prov: dict, phenotypes: list[Phenotype]) -> list[list[str]]:
    rows = [["LEO output", ""]]
    rows += [[k, json.dumps(v) if isinstance(v, (list, dict)) else str(v)] for k, v in prov.items()]
    rows += [["", ""], ["Phenotype", "Definition and what has been measured"]]
    rows += [[p.id, f"{p.definition}  [accuracy: {p.evidence}]" + (f"  {p.note}" if p.note else "")] for p in phenotypes]
    rows += [["", ""], ["Evidence",
              "Accuracy was tested on synthetic notes only (40 UK-style letters, 30 synthetic US-style patients), never on real "
              "clinical notes. Figures: docs/EVAL_PROTOCOL_LEO.md and the Evidence page of the app. 'measured' = accuracy tested "
              "against reference annotations; 'rules_only' = the specialist alone was scored on synthetic notes, no LLM; 'indirect' = only its effect on another field was tested; 'none' = not tested."]]
    rows += [["", ""], ["Column suffixes", "_status: accepted | needs_review | not_found.  _evidence: the note's own words.  "
             "_source: specialist, llm.  _why: reason codes when review is needed."],
             ["Warning", "Evidence columns contain note text. Treat this file like the input notes."]]
    return rows


def write_outputs(table: pd.DataFrame, claims: pd.DataFrame, prov: dict, out: str | Path, fmt: str,
                  phenotypes: list[Phenotype]) -> list[Path]:
    """Write the result; return the paths written."""
    out = Path(out)
    fmt = fmt.lower()
    base = out.with_suffix("")
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "xlsx":
        path = base.with_suffix(".xlsx")
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            table.to_excel(xw, sheet_name="LEO", index=False)
            claims.to_excel(xw, sheet_name="Claims", index=False)
            pd.DataFrame(_about_rows(prov, phenotypes)).to_excel(xw, sheet_name="About", index=False, header=False)
            for ws in xw.book.worksheets:
                ws.freeze_panes = "A2"
        return [path]
    if fmt != "csv":
        raise ValueError("format must be csv or xlsx")
    p1, p2, p3 = base.with_suffix(".csv"), Path(str(base) + ".claims.csv"), Path(str(base) + ".provenance.json")
    table.to_csv(p1, index=False, encoding="utf-8-sig")
    claims.to_csv(p2, index=False, encoding="utf-8-sig")
    p3.write_text(json.dumps(prov, indent=2), encoding="utf-8")
    return [p1, p2, p3]


__all__ = ["read_table", "detect_columns", "run_table", "write_outputs", "default_output", "input_hash",
           "INPUT_SUFFIXES", "TEXT_COLS", "ID_COLS", "DATE_COLS"]
