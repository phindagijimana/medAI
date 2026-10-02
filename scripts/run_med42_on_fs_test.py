#!/usr/bin/env python3
"""Run Med42-8B M0/M1/M2 on the 40 held-out F-S clinician letters.

This is the analog of `scripts/run_med42_on_pilot.py`, but iterates over
the 40 patient IDs that `_fs_pairs_train_test(seed=0)` reserves out of
the 200-doc Fonferko-Shadrach corpus. Those 40 patients (EA0161..EA0200
under our sorted-then-split contract) are NEVER seen at training time
by any v3+ adapter — so scoring on them is a genuine held-out test, not
a training-data reuse.

For each held-out pid:
  1. Read the note text from
     data/fonferko_shadrach_2024/zenodo_8381080/Gold1-200_corrected_spelling/{pid}.txt
     (same source clinician text used by score_llm_arms_vs_fs_gold.py).
  2. If a LoRA adapter is loaded (MEDAI_LORA_ADAPTER_DIR set), prepend
     `PATIENT_ID: {pid}\n\n{note}` — this mirrors the v2/v3 training-time
     augmentation contract (see finetune_lora_epi.py::_augment_pair).
  3. For each arm (M0, M1, M2), route through services.router.extract_phenotype,
     which writes manifests under data/run_manifests_fs_test/<date>/.

Scoring is done separately via scripts/score_llm_arms_vs_fs_gold.py
--held-out-only on the resulting manifest tree.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Manifests go to a dedicated dir so we don't collide with the 200-doc
# F-S sweep at data/run_manifests/ or the pilot sweeps.
os.environ.setdefault(
    "MEDAI_MANIFEST_DIR", str(REPO / "data" / "run_manifests_fs_test"),
)

from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION
from services.extract import DecodingConfig
from services.med42_backend import Med42Backend
from services.med42_model import Med42ModelService
from services.router import extract_phenotype

# Import the split helper so this runner and the training script agree on
# which 40 pids are held out (single source of truth is Task 2).
from scripts.finetune_lora_epi import _fs_pairs_train_test

FS_GOLD_TEXT_DIR = (
    REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8381080"
    / "Gold1-200_corrected_spelling"
)


class _Config:
    """Minimal duck-typed config for Med42ModelService."""
    model_name = os.environ.get("MODEL_NAME", "m42-health/Llama3-Med42-8B")
    model_cache_dir = os.environ.get(
        "MED42_MODEL_CACHE_DIR",
        str(REPO / "model_cache"),
    )
    max_concurrent_users = 1


def _held_out_pids() -> list[str]:
    """Return the sorted list of F-S patient IDs held out for test.

    Delegates to _fs_pairs_train_test so training and inference agree on
    the identity of the 40 test pids by construction.
    """
    _train_triples, test_pids = _fs_pairs_train_test(seed=0)
    return sorted(test_pids)


def _text_path_for(pid: str) -> Path:
    return FS_GOLD_TEXT_DIR / f"{pid}.txt"


def _done_arms(doc_id: str, manifest_dir: Path) -> set[str]:
    """Arms for which every applicable module already has a manifest.

    Makes the run resumable: a job that hits its wall-clock limit (the
    first Arm H attempt did, after 12 of 40 letters) can be resubmitted
    and continues instead of redoing finished letters.
    """
    import json
    from schema import modules_for
    need = len(modules_for(DocumentType.PROGRESS_NOTE))
    seen: dict[str, set[str]] = {}
    for p in manifest_dir.rglob("*.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("source_doc_id") == doc_id and m.get("arm"):
            seen.setdefault(m["arm"], set()).add(m["prompt_id"].split(".")[0])
    return {a for a, mods in seen.items() if len(mods) >= need}


def main():
    print("=== Med42-8B M0/M1/M2 on 40 held-out F-S clinician letters ===")
    pids = _held_out_pids()
    missing = [p for p in pids if not _text_path_for(p).exists()]
    if missing:
        raise SystemExit(
            f"Held-out F-S text missing for {len(missing)} pid(s): "
            f"{missing[:3]}... — expected under {FS_GOLD_TEXT_DIR}."
        )
    print(f"Held-out pids: {len(pids)} "
          f"({pids[0]}..{pids[-1]})")

    svc = Med42ModelService(_Config())
    if not svc.load_model():
        raise SystemExit(f"Failed to load Med42: {svc.load_error}")
    backend = Med42Backend(svc)
    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(os.environ.get("MEDAI_MAX_NEW_TOKENS", 4096)),
        seed=0,
        constrained=os.environ.get("MEDAI_CONSTRAINED", "").lower() in ("1", "true", "yes"),
    )
    if decoding.constrained:
        print("Schema-constrained decoding: ON (lm-format-enforcer)")

    # Mirror the v2/v3 augmentation contract from run_med42_on_pilot.py:
    # a loaded LoRA adapter was trained to copy the PATIENT_ID token from
    # the prompt into every ID field of the emitted JSON, so at inference
    # we hand it the real F-S pid and expect it to propagate.
    use_id_aug = bool(os.environ.get("MEDAI_LORA_ADAPTER_DIR"))
    if use_id_aug:
        print("LoRA adapter detected → prepending PATIENT_ID line to each note "
              "(inference contract for the v2/v3 augmentation-trained adapter).")

    # MEDAI_ARMS=M2 runs a single arm; MEDAI_RESUME=1 skips finished (letter, arm).
    arms = tuple(a.strip() for a in os.environ.get("MEDAI_ARMS", "M0,M1,M2").split(",") if a.strip())
    resume = os.environ.get("MEDAI_RESUME", "").lower() in ("1", "true", "yes")
    manifest_dir = Path(os.environ["MEDAI_MANIFEST_DIR"])
    print(f"Arms: {arms}  resume={resume}")
    n_ok = n_err = n_skip = 0
    for i, pid in enumerate(pids, 1):
        text = _text_path_for(pid).read_text(encoding="utf-8")
        if use_id_aug:
            text = f"PATIENT_ID: {pid}\n\n{text}"
        doc = DocumentMetadata(
            # Prefix keeps the manifest doc_id namespace distinct from the
            # 200-doc F-S sweep at data/run_manifests/ (which uses
            # "fs-<arm>-<pid>"), so a downstream tool can spot which set
            # produced a given manifest.
            doc_id=f"fs-test-{pid}",
            patient_id=pid,
            doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=date(2019, 1, 1),
        )
        done = _done_arms(doc.doc_id, manifest_dir) if resume else set()
        for extraction_arm in arms:
            if extraction_arm in done:
                n_skip += 1
                continue
            try:
                result = extract_phenotype(
                    doc=doc, source_text=text, model_backend=backend,
                    arm=extraction_arm, schema_version=SCHEMA_VERSION,
                    decoding=decoding, write_manifests=True,
                )
                n_ok += 1
                summary = result.summary()
                print(f"  [{i:3d}/{len(pids)}] {pid} {extraction_arm} "
                      f"raw={summary and list(summary.values())[0].get('raw_valid')} "
                      f"final={summary and list(summary.values())[0].get('final_valid')}")
            except Exception as e:
                n_err += 1
                print(f"  [{i:3d}/{len(pids)}] {pid} {extraction_arm} ERR: {e}",
                      file=sys.stderr)

    print(f"\nDone. ok={n_ok}, err={n_err}, skipped_done={n_skip}")


if __name__ == "__main__":
    main()
