#!/usr/bin/env python3
"""End-to-end demonstration: TUNED Med42 (+ LoRA adapter) on a Fonferko letter.

R6d refresh of scripts/demo_real_extraction.py. That script reads
pre-computed manifests from SLURM 89472 (base Med42 M1). This script
instead loads the tuned adapter live on top of Med42-8B and produces a
fresh Evidence[T]-wrapped extraction, plus a diff-vs-gold comparison.

Usage (requires GPU):
    MEDAI_LORA_ADAPTER_DIR=checkpoints/llama3-med42-8b_lora_epi \
    venv/bin/python scripts/demo_tuned_extraction.py --doc-id EA0001 --arm M2

Writes:
    eval/results/demo_tuned_extraction_<doc_id>.csv
    eval/results/demo_tuned_extraction_<doc_id>.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION  # noqa: E402
from services.extract import DecodingConfig  # noqa: E402
from services.tabular import LONG_COLUMNS, rows_to_csv_bytes, to_long_rows  # noqa: E402

FS_DOCS_DIR = REPO / "data" / "fs_corpus" / "documents"
FS_GOLD_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8356494" / "Json"
SILVER_DIR = REPO / "data" / "fonferko_shadrach_2024" / "silver_labels_v0_2_1"
OUT = REPO / "eval" / "results"


class _Config:
    model_name = os.environ.get("MODEL_NAME", "m42-health/Llama3-Med42-8B")
    model_cache_dir = os.environ.get(
        "MED42_MODEL_CACHE_DIR", str(REPO / "model_cache")
    )
    max_concurrent_users = 1


def _summarize_gold(gold_entities):
    """Extract a compact view of F-S native gold for a letter."""
    out = {"epilepsy_type": None, "predominant_seizure_type": None,
           "seizure_frequency": None, "current_asms": [], "etiology_details": None}
    for e in gold_entities:
        a = e.get("attributes", {}) or {}
        txt = (e.get("text") or "").replace("-", " ")
        if e["entity"] == "Prescription":
            out["current_asms"].append(
                f"{a.get('DrugName','?').lower()} "
                f"{a.get('DrugDose','?')} {a.get('DoseUnit','?')} "
                f"×{a.get('Frequency','?')}/day"
            )
        elif e["entity"] == "SeizureFrequency" and out["seizure_frequency"] is None:
            lo = a.get("LowerNumberOfSeizures")
            hi = a.get("UpperNumberOfSeizures")
            tp = a.get("TimePeriod")
            if lo or hi:
                out["seizure_frequency"] = f"{lo}–{hi} per {tp or '?'}"
        elif e["entity"] == "Diagnosis":
            dc = a.get("DiagCategory", "").lower()
            if dc == "epilepsy" and out["epilepsy_type"] is None:
                out["epilepsy_type"] = txt
            elif dc in ("multipleseizures", "singleseizure") and out["predominant_seizure_type"] is None:
                out["predominant_seizure_type"] = txt
        elif e["entity"] == "PatientHistory" and "haemorrhage" in txt.lower():
            out["etiology_details"] = f"{txt} ({a.get('YearDate','')})"
    return out


def _summarize_extracted(phen):
    d = {"epilepsy_type": None, "predominant_seizure_type": None,
         "seizure_frequency": None, "current_asms": [], "etiology_details": None}
    med = getattr(phen, "medication", None)
    cs = getattr(phen, "clinical_seizure", None)
    if med is not None:
        for ev in med.current_asms:
            v = ev.value
            if v is not None:
                d["current_asms"].append(f"{v.generic_name} {v.dose_text or ''}".strip())
    if cs is not None:
        for f_ in ("epilepsy_type", "predominant_seizure_type",
                   "seizure_frequency", "etiology_details_text"):
            ev = getattr(cs, f_, None)
            if ev is not None and ev.value is not None:
                key = f_ if f_ != "etiology_details_text" else "etiology_details"
                d[key] = str(ev.value)
    return d


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, list):
        return "; ".join(v) if v else "—"
    return str(v)


def _matches(g, e):
    if g is None and (e is None or e == [] or e == ""):
        return None
    if g is None or e is None or e == [] or e == "":
        return "✗"
    g_tokens = set(_fmt(g).lower().replace(",", " ").split())
    e_tokens = set(_fmt(e).lower().replace(",", " ").split())
    return "✓" if (g_tokens & e_tokens) else "✗"


def main():
    ap = argparse.ArgumentParser(description="Tuned Med42 real-note demo (R6d).")
    ap.add_argument("--doc-id", default="EA0001",
                    help="F-S letter id (default EA0001).")
    ap.add_argument("--arm", default="M2", choices=["M0", "M1", "M2"],
                    help="Prompt arm (default M2).")
    ap.add_argument("--constrained", action="store_true",
                    help="Enable lm-format-enforcer schema-constrained decoding.")
    args = ap.parse_args()

    doc_txt_path = FS_DOCS_DIR / args.doc_id / "progress_note" / "output.txt"
    if not doc_txt_path.exists():
        raise SystemExit(f"F-S letter not found: {doc_txt_path}")
    silver = json.loads((SILVER_DIR / f"{args.doc_id}.json").read_text())

    if not os.environ.get("MEDAI_LORA_ADAPTER_DIR"):
        os.environ["MEDAI_LORA_ADAPTER_DIR"] = str(
            REPO / "checkpoints" / "llama3-med42-8b_lora_epi"
        )
    adapter_dir = os.environ["MEDAI_LORA_ADAPTER_DIR"]
    if not Path(adapter_dir).exists():
        raise SystemExit(f"Adapter dir does not exist: {adapter_dir}")

    print(f"=== TUNED Med42 real-note demo (R6d) ===")
    print(f"  Letter:   {args.doc_id}  ({silver.get('doc_type')})")
    print(f"  Arm:      {args.arm}")
    print(f"  Adapter:  {adapter_dir}")
    print(f"  Constrained: {args.constrained}")

    from services.med42_backend import Med42Backend
    from services.med42_model import Med42ModelService
    from services.router import extract_phenotype

    svc = Med42ModelService(_Config())
    if not svc.load_model():
        raise SystemExit(f"Failed to load Med42+LoRA: {svc.load_error}")
    backend = Med42Backend(svc)
    print(f"  Model:    {backend.model_name}")

    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(os.environ.get("MEDAI_MAX_NEW_TOKENS", 1024)),
        seed=0, constrained=args.constrained,
    )
    doc = DocumentMetadata(
        doc_id=args.doc_id, patient_id=silver["patient_id"],
        doc_type=DocumentType(silver["doc_type"]),
        doc_date=date(2024, 1, 1),
    )
    text = doc_txt_path.read_text(encoding="utf-8")

    result = extract_phenotype(
        doc=doc, source_text=text, model_backend=backend,
        arm=args.arm, schema_version=SCHEMA_VERSION,
        decoding=decoding, write_manifests=False,
    )
    phen = result.phenotype
    long_rows = to_long_rows(phen, include_not_documented=False)
    n_content = sum(1 for r in long_rows if r["confidence"] != "not_documented")
    print(f"\n  Long-format rows (content-only): {n_content}")

    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / f"demo_tuned_extraction_{args.doc_id}.csv"
    csv_path.write_bytes(rows_to_csv_bytes(long_rows, fieldnames=LONG_COLUMNS))

    # Diff vs gold
    gold = json.loads((FS_GOLD_DIR / f"{args.doc_id}.json").read_text())
    gs = _summarize_gold(gold)
    es = _summarize_extracted(phen)

    md_lines = [
        f"## R6d tuned-Med42 demo: {args.doc_id} ({silver.get('doc_type')}), arm {args.arm}",
        "",
        f"*Generated by `scripts/demo_tuned_extraction.py`. Model: "
        f"`{backend.model_name}`. Constrained decoding: "
        f"{'yes' if args.constrained else 'no'}. Schema: v{SCHEMA_VERSION}.*",
        "",
        "### Extracted long-format rows (content-only)",
        "",
        "| module | field | value | evidence_text | confidence |",
        "|---|---|---|---|---|",
    ]
    for r in long_rows:
        v = str(r["value"])[:80]
        e = str(r["evidence_text"])[:60]
        md_lines.append(f"| {r['module']} | {r['field']} | {v} | {e} | {r['confidence']} |")

    md_lines += ["", "### Diff vs Fonferko-Shadrach native gold", "",
                 "| Field | F-S gold | Extracted (tuned) | Match |",
                 "|---|---|---|:---:|"]
    match_count = total_count = 0
    for field in ("epilepsy_type", "predominant_seizure_type",
                  "seizure_frequency", "current_asms", "etiology_details"):
        m = _matches(gs[field], es[field])
        marker = m or "n/a"
        if m is not None:
            total_count += 1
            if m == "✓":
                match_count += 1
        md_lines.append(
            f"| {field} | {_fmt(gs[field])} | {_fmt(es[field])} | {marker} |"
        )
    md_lines.append("")
    md_lines.append(
        f"**Score: {match_count}/{total_count} in-scope fields matched (lenient token-overlap).**"
    )

    md_path = OUT / f"demo_tuned_extraction_{args.doc_id}.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"\n  wrote → {csv_path}")
    print(f"  wrote → {md_path}")
    print(f"\n  Diff vs F-S gold: {match_count}/{total_count} in-scope fields matched.")


if __name__ == "__main__":
    main()
