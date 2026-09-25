#!/usr/bin/env python3
"""Run Med42-8B M0/M1/M2 on the 60 Phase 6D.2 pilot documents.

For every (rendered_pilot_document × arm), we call the standard
`services.router.extract_phenotype` pipeline, log a run manifest to
`data/run_manifests_pilot/<date>/`, and use the same v0.2.1 schema
and prompt registry as the Fonferko-Shadrach baseline.

The pilot corpus has only two applicable modules per document
(clinical_seizure for P001–P004 clinic letters, eeg for P005–P006 EEG
reports), so total work is ~360 extractions × ~5–20 s each ≈ 30–90 min
on an L40S 24 GB slice.

Requires GPU. Uses the same Med42Backend + DecodingConfig(seed=0,
do_sample=False) as the paper sweep — deterministic, reproducible.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Route manifests to a dedicated dir so we don't collide with the F-S sweep.
os.environ.setdefault("MEDAI_MANIFEST_DIR", str(REPO / "data" / "run_manifests_pilot"))

from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION
from services.extract import DecodingConfig
from services.med42_backend import Med42Backend
from services.med42_model import Med42ModelService
from services.router import extract_phenotype

RUN_DIR = REPO / "data" / "episynth_pilot" / "run_001"
FREEZE_DIR = Path(
    "/tmp/phase6d1v2/MedAI_Phase6D1_v2_GPT_MultiGenerator_PreRun_Freeze"
)


class _Config:
    """Minimal duck-typed config for Med42ModelService."""
    model_name = os.environ.get("MODEL_NAME", "m42-health/Llama3-Med42-8B")
    model_cache_dir = os.environ.get(
        "MED42_MODEL_CACHE_DIR",
        str(REPO / "model_cache"),
    )
    max_concurrent_users = 1


def _pilot_docs():
    """(arm, cond, patient_id, doc_type, path) tuples for all 60 renders."""
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
    """P001–P004 are clinic letters; P005–P006 are EEG reports."""
    plan = json.loads(
        (FREEZE_DIR / "semantic_plans" / f"{pid}.json").read_text()
    )
    fam = plan.get("document_family", "epilepsy_clinic_letter")
    if fam == "eeg_report":
        return DocumentType.EEG_REPORT
    return DocumentType.PROGRESS_NOTE


def main():
    print("=== Med42-8B M0/M1/M2 on Phase 6D.2 pilot corpus ===")
    svc = Med42ModelService(_Config())
    if not svc.load_model():
        raise SystemExit(f"Failed to load Med42: {svc.load_error}")
    backend = Med42Backend(svc)
    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(os.environ.get("MEDAI_MAX_NEW_TOKENS", 1024)),
        seed=0,
    )

    docs = list(_pilot_docs())
    print(f"Docs to process: {len(docs)}")
    arms = ("M0", "M1", "M2")

    n_ok = n_err = 0
    for i, (arm, cond, pid, text_path) in enumerate(docs, 1):
        text = text_path.read_text(encoding="utf-8")
        doc_type = _doc_type_for(pid)
        doc = DocumentMetadata(
            doc_id=f"pilot-{arm}-{cond}-{pid}",
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
                print(f"  [{i:3d}/{len(docs)}] {arm}/{cond}/{pid} {extraction_arm} "
                      f"raw={summary and list(summary.values())[0].get('raw_valid')} "
                      f"final={summary and list(summary.values())[0].get('final_valid')}")
            except Exception as e:
                n_err += 1
                print(f"  [{i:3d}/{len(docs)}] {arm}/{cond}/{pid} {extraction_arm} ERR: {e}",
                      file=sys.stderr)

    print(f"\nDone. ok={n_ok}, err={n_err}")


if __name__ == "__main__":
    main()
