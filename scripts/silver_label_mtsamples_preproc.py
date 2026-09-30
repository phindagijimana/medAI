#!/usr/bin/env python3
"""Silver-label the 18 preprocessed MTSamples notes via gpt-5.6-terra.

Uses the held-out GPT tier (per project memory: `feedback_gpt_research_holdout`).
Emits per-doc silver JSON aligned with the preprocessed text — char offsets
and evidence spans will refer to the preprocessed text, not the raw MTSamples.

Output:
    data/eval_corpora/mtsamples_neuro_preprocessed/silver_per_doc/
        MT_V####.json

Usage:
    set -a; source .env; set +a
    venv-medcat/bin/python scripts/silver_label_mtsamples_preproc.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "data" / "eval_corpora" / "mtsamples_neuro_preprocessed"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _build_prompt(note: str, schema_json: str) -> str:
    return (
        "You are a clinical NLP extractor. Read the US neurology note "
        "below and produce a MedAI-EPI v0.2.1 EpilepsyPhenotype JSON that "
        "STRICTLY conforms to the schema below.\n\n"
        "Rules:\n"
        "- Nest fields as shown in the schema (clinical_seizure.predominant_seizure_type "
        "is nested inside clinical_seizure; do NOT flatten to top level).\n"
        "- Every Evidence[T] field has this shape: "
        "{\"value\": <value or null>, \"certainty\": one of definite|probable|possible|not_documented, "
        "\"temporal_status\": one of current|past|hypothetical|not_documented, "
        "\"evidence_text\": <short verbatim quote or null>, "
        "\"source_doc_id\": <doc id or null>, \"char_start\": null, \"char_end\": null}\n"
        "- If a field is not documented in the note, set value=null and "
        "certainty=\"not_documented\".\n"
        "- Use enum values EXACTLY as shown in the schema (e.g., focal_aware, "
        "generalized_tonic_clonic, NOT \"Focal aware\" or \"GTC\").\n"
        "- schema_version must be \"v0.2.1\".\n"
        "- Do NOT hallucinate — only include phenotype elements the note actually documents.\n"
        "- Return ONLY the JSON object, no prose, no markdown fences.\n\n"
        "Schema (v0.2.1 EpilepsyPhenotype):\n"
        f"{schema_json}\n\n"
        "Clinical note:\n"
        '"""\n'
        f"{note}\n"
        '"""\n\n'
        "Phenotype JSON:"
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="gpt-5.6-terra")
    p.add_argument("--limit", type=int, default=None,
                   help="Optional cap on number of notes to label (smoke test)")
    args = p.parse_args(argv)

    if not os.environ.get("OPENAI_API_KEY"):
        print("[silver] OPENAI_API_KEY not set. `set -a; source .env; set +a` first.")
        return 10

    manifest_path = CORPUS_ROOT / "manifest.csv"
    if not manifest_path.exists():
        print(f"[silver] FAIL: {manifest_path} missing")
        return 2

    from schema.ontology import EpilepsyPhenotype
    schema_dict = EpilepsyPhenotype.model_json_schema()
    schema_json = json.dumps(schema_dict, indent=2)
    print(f"[silver] Schema size: {len(schema_json)} chars")

    with manifest_path.open() as fh:
        rows = list(csv.DictReader(fh))
    if args.limit:
        rows = rows[: args.limit]

    out_dir = CORPUS_ROOT / "silver_per_doc"
    out_dir.mkdir(exist_ok=True)

    from openai import OpenAI  # type: ignore
    client = OpenAI()

    n_ok = n_fail = 0
    for i, row in enumerate(rows, 1):
        visit_id = row["visit_id"]
        note_path = CORPUS_ROOT / row["note_path"]
        if not note_path.exists():
            print(f"[silver] SKIP {visit_id}: {note_path} missing")
            continue

        out_path = out_dir / f"{visit_id}.json"
        if out_path.exists():
            n_ok += 1
            print(f"[silver] SKIP {visit_id}: already labelled")
            continue

        note = note_path.read_text()
        prompt = _build_prompt(note, schema_json)

        try:
            resp = client.responses.create(model=args.model, input=prompt)
            raw = (resp.output_text or "").strip()
        except Exception as e:
            print(f"[silver] ERR {visit_id}: {e}")
            n_fail += 1
            continue

        # Strip potential markdown fence
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json\n"):
                raw = raw[5:]
            raw = raw.rsplit("```", 1)[0].strip()

        try:
            pheno = json.loads(raw)
        except Exception as e:
            print(f"[silver] PARSE-FAIL {visit_id}: {e}")
            (out_dir / f"{visit_id}.raw").write_text(raw)
            n_fail += 1
            continue

        out_path.write_text(json.dumps(pheno, indent=2))
        conformant = isinstance(pheno, dict) and "clinical_seizure" in pheno
        print(f"[silver] {'OK' if conformant else 'SHAPE?'} {visit_id} "
              f"({len(raw)} chars, conformant={conformant}) [{i}/{len(rows)}]")
        if conformant:
            n_ok += 1
        else:
            n_fail += 1

    # Emit run metadata
    (CORPUS_ROOT / "silver_run_metadata.json").write_text(json.dumps({
        "labeller_model": args.model,
        "n_labelled": n_ok,
        "n_failed": n_fail,
        "text_variant": "preprocessed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "silver_label_mtsamples_preproc.py v1.0",
    }, indent=2))

    print(f"\n[silver] Done. OK={n_ok}  FAIL={n_fail}")
    print(f"[silver] Silver dir: {out_dir}")
    return 0 if n_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
