#!/usr/bin/env python3
"""Sweep three Med42 variants over the 60-doc pilot corpus (R4e-i).

Variants:
    (a) base_constr   → base Med42, MEDAI_CONSTRAINED=1, no LoRA adapter
    (b) tuned         → base Med42 + LoRA adapter (unconstrained)
    (c) tuned_constr  → base Med42 + LoRA adapter + MEDAI_CONSTRAINED=1

Each variant writes to a distinct manifest dir
(data/run_manifests_pilot_{base_constr,tuned,tuned_constr}/) so the extended
scorer can emit cleanly-named summaries with `--suffix`.

We load the model *once* per variant (reload is needed because the LoRA state
differs). Sequential is fine on a single L40S 24 GB slice.

Selecting variants:
    Env var MEDAI_PILOT_VARIANTS defaults to "base_constr,tuned,tuned_constr".
    Set e.g. MEDAI_PILOT_VARIANTS=tuned to run just one.

Adapter directory:
    Env var MEDAI_ADAPTER_DIR (default checkpoints/llama3-med42-8b_lora_epi).
"""

from __future__ import annotations

import gc
import json
import os
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION  # noqa: E402
from services.extract import DecodingConfig  # noqa: E402
from services.med42_backend import Med42Backend  # noqa: E402
from services.med42_model import Med42ModelService  # noqa: E402
from services.router import extract_phenotype  # noqa: E402

RUN_DIR = REPO / "data" / "episynth_pilot" / "run_001"
FREEZE_DIR = REPO / "data" / "MedAI_Phase6D1_v2_GPT_MultiGenerator_PreRun_Freeze"
DEFAULT_ADAPTER = REPO / "checkpoints" / "llama3-med42-8b_lora_epi"


class _Config:
    """Minimal duck-typed config for Med42ModelService."""

    model_name = os.environ.get("MODEL_NAME", "m42-health/Llama3-Med42-8B")
    model_cache_dir = os.environ.get(
        "MED42_MODEL_CACHE_DIR",
        str(REPO / "model_cache"),
    )
    max_concurrent_users = 1


VARIANTS = {
    # name : (lora?, constrained?)
    "base_constr": (False, True),
    "tuned": (True, False),
    "tuned_constr": (True, True),
}


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


def _run_variant(name: str, use_lora: bool, constrained: bool, adapter_dir: Path,
                 docs, arms=("M0", "M1", "M2")):
    manifest_dir = REPO / "data" / f"run_manifests_pilot_{name}"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MEDAI_MANIFEST_DIR"] = str(manifest_dir)
    if use_lora:
        os.environ["MEDAI_LORA_ADAPTER_DIR"] = str(adapter_dir)
    else:
        os.environ.pop("MEDAI_LORA_ADAPTER_DIR", None)
    os.environ["MEDAI_CONSTRAINED"] = "1" if constrained else "0"

    print(f"\n{'='*70}")
    print(f"Variant: {name}   lora={use_lora}   constrained={constrained}")
    print(f"Manifests: {manifest_dir}")
    print(f"Adapter:   {os.environ.get('MEDAI_LORA_ADAPTER_DIR', '(none)')}")
    print(f"{'='*70}\n")

    svc = Med42ModelService(_Config())
    if not svc.load_model():
        raise SystemExit(f"Failed to load Med42 for variant {name}: {svc.load_error}")
    backend = Med42Backend(svc)
    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(os.environ.get("MEDAI_MAX_NEW_TOKENS", 1024)),
        seed=0,
        constrained=constrained,
    )

    n_ok = n_err = 0
    for i, (arm, cond, pid, text_path) in enumerate(docs, 1):
        text = text_path.read_text(encoding="utf-8")
        doc_type = _doc_type_for(pid)
        doc = DocumentMetadata(
            doc_id=f"pilot-{name}-{arm}-{cond}-{pid}",
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

    print(f"\n[{name}] done. ok={n_ok}, err={n_err}\n")

    # Free GPU before loading the next variant.
    svc.unload_model()
    del svc, backend
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def main():
    selected = os.environ.get(
        "MEDAI_PILOT_VARIANTS", "base_constr,tuned,tuned_constr"
    ).split(",")
    selected = [s.strip() for s in selected if s.strip()]

    adapter_dir = Path(os.environ.get("MEDAI_ADAPTER_DIR", str(DEFAULT_ADAPTER)))
    if any(VARIANTS[v][0] for v in selected if v in VARIANTS):
        if not adapter_dir.exists():
            raise SystemExit(f"Adapter dir does not exist: {adapter_dir}")

    docs = list(_pilot_docs())
    print(f"Pilot docs: {len(docs)}")
    print(f"Variants:   {selected}")

    for v in selected:
        if v not in VARIANTS:
            print(f"Skipping unknown variant: {v}", file=sys.stderr)
            continue
        use_lora, constrained = VARIANTS[v]
        _run_variant(v, use_lora, constrained, adapter_dir, docs)

    print("All variants complete.")


if __name__ == "__main__":
    main()
