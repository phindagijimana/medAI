#!/usr/bin/env python3
"""GPU runner: full Fonferko-Shadrach M0/M1/M2 sweep for the Shape-A paper.

Iterates over the 200 silver-labeled Fonferko-Shadrach letters and runs each
applicable module (clinical_seizure + medication) through each Med42 arm
(M0, M1, M2). Writes run manifests to `data/run_manifests/<date>/` — the same
directory the eval aggregator reads.

Resumable: if a manifest already exists whose (source_doc_id, module, arm,
prompt_version) tuple matches, that combination is skipped. Safe to rerun
after a wall-clock timeout.

Runtime estimate: ~5–10 h on an L40S for 200 × 3 × 2 = 1,200 inferences.

Usage (typically via SLURM wrapper scripts/slurm_open_benchmark.sh):
    python scripts/run_open_benchmark_gpu.py --n-docs 200 --arms M0,M1,M2 \
        --modules clinical_seizure,medication
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Med42Config
from schema import (
    ClinicalSeizureModule,
    DocumentMetadata,
    DocumentType,
    MedicationModule,
    SCHEMA_VERSION,
)
from services.extract import DecodingConfig, extract_module
from services.med42_backend import Med42Backend
from services.med42_model import Med42ModelService
from services.prompt_registry import resolve
from services.run_manifest import MANIFEST_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("open_benchmark_gpu")


REPO = Path(__file__).resolve().parent.parent
SILVER_DIR = REPO / "data" / "fonferko_shadrach_2024" / "silver_labels_v0_2_1"

MODULE_CLASSES = {
    "clinical_seizure": ClinicalSeizureModule,
    "medication": MedicationModule,
}


def _load_letters(n_docs: int | None) -> list[dict]:
    """Return a list of {doc_id, text, gold_phenotype} dicts sorted by doc_id."""
    files = sorted(SILVER_DIR.glob("EA*.json"))
    if n_docs:
        files = files[:n_docs]
    records: list[dict] = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        src_path = REPO / data["source_text_path"]
        if not src_path.exists():
            log.warning("missing source text for %s", data["doc_id"])
            continue
        records.append({
            "doc_id": data["doc_id"],
            "text": src_path.read_text(encoding="utf-8"),
            "gold_phenotype": data["phenotype"],
        })
    return records


def _index_existing_manifests(root: Path) -> set[tuple[str, str, str, str]]:
    """Return the set of (doc_id, module, arm, prompt_version) tuples that
    already have a manifest on disk. Used for resumability."""
    seen: set[tuple[str, str, str, str]] = set()
    if not root.exists():
        return seen
    for f in root.rglob("*.json"):
        try:
            mf = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Try to infer module from prompt_id (e.g. "medication.M2.v1")
        pid = mf.get("prompt_id") or ""
        parts = pid.split(".")
        if len(parts) != 3:
            continue
        module, arm, version = parts
        key = (mf.get("source_doc_id", ""), module, arm, version)
        seen.add(key)
    return seen


def _run_one(
    doc: DocumentMetadata,
    source_text: str,
    module_name: str,
    module_cls,
    arm: str,
    version: str,
    backend: Med42Backend,
    decoding: DecodingConfig,
) -> dict:
    prompt = resolve(module_name, arm, version)
    result = extract_module(
        module_cls=module_cls,
        prompt=prompt,
        source_text=source_text,
        source_doc_meta=doc,
        model_backend=backend,
        decoding=decoding,
        schema_version=SCHEMA_VERSION,
    )
    result.manifest.write()
    m = result.manifest
    return {
        "doc_id": doc.doc_id, "arm": arm, "module": module_name,
        "prompt_version": version,
        "raw_valid": m.raw_valid, "final_valid": m.final_valid,
        "repair_method": m.repair_method,
        "tokens": m.raw_response_tokens,
        "duration_s": m.duration_s,
        "run_id": m.run_id,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-docs", type=int, default=None,
                    help="Limit to first N letters (for smoke testing)")
    ap.add_argument("--arms", type=str, default="M0,M1,M2",
                    help="Comma-separated arms")
    ap.add_argument("--modules", type=str, default="clinical_seizure,medication",
                    help="Comma-separated modules (must be in MODULE_CLASSES)")
    ap.add_argument("--prompt-version", type=str, default="v1",
                    help="Prompt template version to use. v2 exists for "
                         "medication + clinical_seizure with Fonferko-adapted "
                         "few-shot; use --prompt-version v2 to include those.")
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't load Med42; just list the work")
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    modules = [m.strip() for m in args.modules.split(",") if m.strip()]
    for m in modules:
        if m not in MODULE_CLASSES:
            log.error("unknown module %r; allowed: %s", m, list(MODULE_CLASSES))
            return 2

    letters = _load_letters(args.n_docs)
    log.info("Loaded %d letters. Arms=%s modules=%s version=%s",
             len(letters), arms, modules, args.prompt_version)

    existing = _index_existing_manifests(MANIFEST_ROOT)
    total_planned = len(letters) * len(arms) * len(modules)
    already_done = sum(
        1 for l in letters for a in arms for m in modules
        if (l["doc_id"], m, a, args.prompt_version) in existing
    )
    to_do = total_planned - already_done
    log.info("Total planned: %d  already-done: %d  to-do: %d",
             total_planned, already_done, to_do)

    if args.dry_run:
        return 0

    # Load Med42 once
    config = Med42Config()
    log.info("Loading Med42: %s (cache=%s)", config.model_name, config.model_cache_dir)
    t_load = time.time()
    svc = Med42ModelService(config)
    if not svc.load_model():
        log.error("Med42 load failed: %s", svc.load_error)
        return 2
    log.info("Med42 loaded on %s in %.1fs", svc.device, time.time() - t_load)
    backend = Med42Backend(svc)

    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=args.max_new_tokens, seed=args.seed,
    )

    stats: dict[str, dict[str, int]] = {}  # arm -> {n, raw_valid, final_valid}
    t_start = time.time()
    completed = 0

    for letter in letters:
        text = letter["text"]
        doc = DocumentMetadata(
            doc_id=letter["doc_id"], doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=date(2024, 1, 1), patient_id=letter["doc_id"],
        )
        for arm in arms:
            for module_name in modules:
                key = (doc.doc_id, module_name, arm, args.prompt_version)
                if key in existing:
                    continue
                try:
                    r = _run_one(doc, text, module_name,
                                 MODULE_CLASSES[module_name],
                                 arm, args.prompt_version, backend, decoding)
                except Exception as e:
                    log.exception("failed on %s / %s / %s: %s",
                                  doc.doc_id, module_name, arm, e)
                    continue
                completed += 1
                arm_stats = stats.setdefault(arm, {"n": 0, "raw_valid": 0,
                                                   "final_valid": 0,
                                                   "duration_s": 0.0})
                arm_stats["n"] += 1
                if r["raw_valid"]:
                    arm_stats["raw_valid"] += 1
                if r["final_valid"]:
                    arm_stats["final_valid"] += 1
                arm_stats["duration_s"] += r["duration_s"] or 0.0

                if completed % 20 == 0:
                    elapsed = time.time() - t_start
                    eta = (elapsed / completed) * (to_do - completed) if completed else 0
                    log.info(
                        "progress: %d/%d complete, elapsed=%.1fs, eta≈%.1fs (%.1f min)",
                        completed, to_do, elapsed, eta, eta / 60,
                    )

    total_elapsed = time.time() - t_start
    log.info("=" * 60)
    log.info("Run complete. Total elapsed: %.1fs (%.2f h) — %d inferences",
             total_elapsed, total_elapsed / 3600, completed)
    for arm, s in stats.items():
        raw_rate = s["raw_valid"] / s["n"] if s["n"] else 0
        final_rate = s["final_valid"] / s["n"] if s["n"] else 0
        avg_dur = s["duration_s"] / s["n"] if s["n"] else 0
        log.info(
            "arm=%s n=%d raw_valid=%.3f final_valid=%.3f avg_duration=%.2fs",
            arm, s["n"], raw_rate, final_rate, avg_dur,
        )

    # Snapshot summary next to the manifests for easy retrieval
    summary_path = MANIFEST_ROOT / datetime.now(timezone.utc).strftime("%Y-%m-%d") \
        / f"open_benchmark_run_{int(time.time())}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arms": arms, "modules": modules,
        "prompt_version": args.prompt_version,
        "n_letters": len(letters),
        "total_completed": completed,
        "total_elapsed_s": round(total_elapsed, 1),
        "per_arm": stats,
    }, indent=2), encoding="utf-8")
    log.info("summary → %s", summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
