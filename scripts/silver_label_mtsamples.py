"""MTSamples silver-label generator — schema-injected M2-style prompt.

Extracts v0.2.1 EpilepsyPhenotype JSON from raw MTSamples neurology notes
via a held-out extractor tier (gpt-5.6-terra) with the full Pydantic schema
in the prompt for shape conformance.

v1 of this script used a stripped-down prompt that produced flat, non-v0.2.1
output. v2 injects the full `EpilepsyPhenotype.model_json_schema()` so the
LLM emits nested `clinical_seizure.*`, `medication.*`, etc.

Held-out constraint (project memory): gpt-5.6-terra is our EVAL extractor
tier (never a generator for training data). Silver labelling IS an
extractor role, so terra is the correct model.

Usage:
    OPENAI_API_KEY=... venv-medcat/bin/python scripts/silver_label_mtsamples.py --n 10
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
CORPUS_ROOT = REPO_ROOT / "data" / "eval_corpora" / "mtsamples_neuro"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _build_prompt(note: str, schema_json: str) -> str:
    """M2-style schema-injected prompt for v0.2.1 EpilepsyPhenotype extraction."""
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


def _check_prereqs() -> tuple[bool, str]:
    try:
        import openai  # noqa: F401
    except ImportError:
        return False, "openai package not installed in venv-medcat"
    if not os.environ.get("OPENAI_API_KEY"):
        return False, "OPENAI_API_KEY not set in environment"
    return True, ""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--model", default="gpt-5.6-terra")
    p.add_argument("--out-suffix", default="v2")
    args = p.parse_args(argv)

    ok, reason = _check_prereqs()
    if not ok:
        print(f"[silver] PENDING: {reason}")
        return 10

    manifest_path = CORPUS_ROOT / "manifest.csv"
    if not manifest_path.exists():
        print(f"[silver] FAIL: no manifest at {manifest_path}. Run "
              "scripts/fetch_mtsamples_neuro.py first.")
        return 2

    # Load schema once
    from schema.ontology import EpilepsyPhenotype
    schema_dict = EpilepsyPhenotype.model_json_schema()
    schema_json = json.dumps(schema_dict, indent=2)
    print(f"[silver] Schema size: {len(schema_json)} chars")

    with manifest_path.open() as fh:
        rows = list(csv.DictReader(fh))[:args.n]
    print(f"[silver] Labelling {len(rows)} notes with {args.model}")

    from openai import OpenAI       # type: ignore
    client = OpenAI()

    labels = []
    for row in rows:
        note = (CORPUS_ROOT / row["id"] / "note.txt").read_text()
        prompt = _build_prompt(note, schema_json)

        resp = client.responses.create(
            model=args.model,
            input=prompt,
        )
        raw = resp.output_text.strip()
        # Strip potential markdown fence.
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json\n"):
                raw = raw[5:]
            raw = raw.rsplit("```", 1)[0].strip()
        try:
            pheno = json.loads(raw)
        except Exception as e:
            print(f"[silver] {row['id']}: JSON parse fail: {e}")
            pheno = {"raw_output": raw, "parse_error": str(e)}
        labels.append({
            "doc_id": row["id"],
            "source_url": row["source_url"],
            "silver_model": args.model,
            "labelled_at": datetime.now(timezone.utc).isoformat(),
            "phenotype": pheno,
        })
        # Check for v0.2.1 shape conformance
        conformant = isinstance(pheno, dict) and "clinical_seizure" in pheno
        print(f"[silver] {'OK' if conformant else 'SHAPE?'} {row['id']} "
              f"({len(raw)} chars raw, v021_shape={conformant})")

    out = CORPUS_ROOT / f"silver_gold_{args.n}_{args.out_suffix}.json"
    out.write_text(json.dumps(labels, indent=2))
    print(f"[silver] Wrote {out}")

    # Also split into per-doc for scoring
    per_doc_dir = CORPUS_ROOT / f"silver_per_doc_{args.out_suffix}"
    per_doc_dir.mkdir(exist_ok=True)
    n_conformant = 0
    for label in labels:
        p_data = label["phenotype"]
        if isinstance(p_data, dict) and "clinical_seizure" in p_data:
            (per_doc_dir / f"{label['doc_id']}.json").write_text(
                json.dumps(p_data, indent=2)
            )
            n_conformant += 1
    print(f"[silver] Split {n_conformant} v0.2.1-conformant labels to {per_doc_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
