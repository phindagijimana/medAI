#!/usr/bin/env python3
"""Run DeepSeek-R1-Distill-Llama-8B M0/M1/M2 on the 60 Phase 6D.2 pilot docs.

Mirrors scripts/run_med42_on_pilot.py but uses services/deepseek_backend.py
as a second locally-deployable 8 B-tier model. Answers the paper question
"is the schema-echo behaviour Med42-specific, or characteristic of the 8 B
open-weight tier?".

Manifests write to data/run_manifests_pilot_deepseek/<date>/. Score afterwards
with scripts/score_med42_on_pilot.py --manifests-dir <that dir> --suffix deepseek.

--help / --dry-run flags supported so the script imports cleanly without
loading the model.
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

# Dedicated manifest dir.
os.environ.setdefault(
    "MEDAI_MANIFEST_DIR", str(REPO / "data" / "run_manifests_pilot_deepseek")
)

from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION  # noqa: E402
from services.extract import DecodingConfig  # noqa: E402

RUN_DIR = REPO / "data" / "episynth_pilot" / "run_001"
FREEZE_DIR = REPO / "data" / "MedAI_Phase6D1_v2_GPT_MultiGenerator_PreRun_Freeze"


def _pilot_docs():
    for arm_dir in sorted(RUN_DIR.iterdir()):
        if not arm_dir.is_dir() or arm_dir.name in ("g2", "targets"):
            continue
        if arm_dir.name == "C0":
            for p_dir in sorted(arm_dir.iterdir()):
                p = p_dir / "output.txt"
                if p.exists():
                    yield ("C0", "C0", p_dir.name, p)
        elif arm_dir.name.startswith("gpt-"):
            for cond_dir in sorted(arm_dir.iterdir()):
                for p_dir in sorted(cond_dir.iterdir()):
                    p = p_dir / "output.txt"
                    if p.exists():
                        yield (arm_dir.name, cond_dir.name, p_dir.name, p)


def _doc_type_for(pid: str) -> DocumentType:
    plan = json.loads(
        (FREEZE_DIR / "semantic_plans" / f"{pid}.json").read_text()
    )
    fam = plan.get("document_family", "epilepsy_clinic_letter")
    if fam == "eeg_report":
        return DocumentType.EEG_REPORT
    return DocumentType.PROGRESS_NOTE


def main():
    ap = argparse.ArgumentParser(description="Run DeepSeek-8B M0/M1/M2 on 60 pilot docs.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Enumerate docs but do not load the model or generate.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only process the first N documents (smoke test).")
    args = ap.parse_args()

    print("=== DeepSeek-R1-Distill-Llama-8B M0/M1/M2 on Phase 6D.2 pilot corpus ===")

    docs = list(_pilot_docs())
    if args.limit:
        docs = docs[: args.limit]
    print(f"Docs to process: {len(docs)}")

    if args.dry_run:
        for i, (arm, cond, pid, path) in enumerate(docs, 1):
            print(f"  [{i:3d}] {arm}/{cond}/{pid} -> {path.name}")
        print("--dry-run set; not loading model.")
        return

    # Deferred imports so --help / --dry-run don't require torch or a GPU.
    from services.deepseek_backend import DeepSeekBackend
    from services.router import extract_phenotype

    backend = DeepSeekBackend()
    backend.load()
    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(os.environ.get("MEDAI_MAX_NEW_TOKENS", 1024)),
        seed=0,
        constrained=os.environ.get("MEDAI_CONSTRAINED", "").lower() in ("1", "true", "yes"),
    )
    if decoding.constrained:
        print("Schema-constrained decoding: ON (lm-format-enforcer)")

    arms = ("M0", "M1", "M2")
    n_ok = n_err = 0
    for i, (arm, cond, pid, text_path) in enumerate(docs, 1):
        text = text_path.read_text(encoding="utf-8")
        doc_type = _doc_type_for(pid)
        doc = DocumentMetadata(
            doc_id=f"pilot-deepseek-{arm}-{cond}-{pid}",
            patient_id=pid,
            doc_type=doc_type,
            doc_date=date(2026, 9, 25),
        )
        for extraction_arm in arms:
            try:
                result = extract_phenotype(
                    doc=doc, source_text=text, model_backend=backend,
                    arm=extraction_arm, schema_version=SCHEMA_VERSION,
                    decoding=decoding, write_manifests=True,
                )
                n_ok += 1
                summary = result.summary()
                first = summary and list(summary.values())[0] or {}
                print(f"  [{i:3d}/{len(docs)}] {arm}/{cond}/{pid} {extraction_arm} "
                      f"raw={first.get('raw_valid')} final={first.get('final_valid')}")
            except Exception as e:
                n_err += 1
                print(f"  [{i:3d}/{len(docs)}] {arm}/{cond}/{pid} {extraction_arm} ERR: {e}",
                      file=sys.stderr)

    print(f"\nDone. ok={n_ok}, err={n_err}")


if __name__ == "__main__":
    main()
