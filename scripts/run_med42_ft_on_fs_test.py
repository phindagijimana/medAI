#!/usr/bin/env python3
"""Arm H, in contract: tuned Med42-8B on the 40 held-out F-S letters.

Uses the training prompt (``services.ft_extract``) - one full-phenotype
generation per letter - instead of the per-module M0/M1/M2 prompts.  Writes
one run manifest per letter (``prompt_id = epilepsy_phenotype.FT.v1``,
``arm = FT``) that ``services.chain_llm.ManifestLLMReasoner`` and
``scripts/score_leo_vs_fs_gold.py`` read.

Resumable: letters that already have a manifest in MEDAI_MANIFEST_DIR are
skipped, so a job that hits its wall-clock limit can simply be resubmitted.

    MEDAI_LORA_ADAPTER_DIR=checkpoints/llama3-med42-8b_lora_epi_v3_polish \\
    MEDAI_MANIFEST_DIR=data/run_manifests_fs_test_ft_v3_polish \\
    venv/bin/python scripts/run_med42_ft_on_fs_test.py

Env: MEDAI_MAX_NEW_TOKENS (default 4096), MEDAI_PIDS (comma list, default the
40 held-out letters), MEDAI_LIMIT (stop after N new letters, for smoke runs).

MEDAI_CORPUS=synth runs the US-style synthetic evaluation notes instead of the F-S letters
(``services.synth_eval``: visit ids, default = the 143 evaluation visits).  Manifests are then
keyed ``synth-<visit_id>`` and the PATIENT_ID line carries the patient id.  MEDAI_SHARD=i/n runs
every n-th pending note starting at i, so several GPU jobs can share one manifest directory.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("MEDAI_MANIFEST_DIR", str(REPO / "data" / "run_manifests_fs_test_ft"))

from services.extract import DecodingConfig  # noqa: E402
from services.ft_extract import (  # noqa: E402
    FT_ARM, FT_PROMPT_ID, build_ft_prompt, is_degenerate, split_phenotype,
)
from services.med42_backend import Med42Backend  # noqa: E402
from services.med42_model import Med42ModelService  # noqa: E402
from services.run_manifest import MANIFEST_ROOT, RunManifest, _git_dirty, _git_sha_short, _hardware_info  # noqa: E402

FS_TEXT_DIR = (REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8381080"
               / "Gold1-200_corrected_spelling")
HELD_OUT = [f"EA{i:04d}" for i in range(161, 201)]


class _Config:
    model_name = os.environ.get("MODEL_NAME", "m42-health/Llama3-Med42-8B")
    model_cache_dir = os.environ.get("MED42_MODEL_CACHE_DIR", str(REPO / "model_cache"))
    max_concurrent_users = 1


def _done(manifest_dir: Path) -> set[str]:
    out = set()
    for p in manifest_dir.rglob("*.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("prompt_id") == FT_PROMPT_ID:
            out.add(m.get("source_doc_id", ""))
    return out


def main() -> int:
    adapter = os.environ.get("MEDAI_LORA_ADAPTER_DIR", "")
    if not adapter:
        raise SystemExit("MEDAI_LORA_ADAPTER_DIR is required (this is the tuned-adapter contract).")
    synth = os.environ.get("MEDAI_CORPUS", "fs") == "synth"
    if synth:
        from services import synth_eval
        pids = [p for p in os.environ.get("MEDAI_PIDS", "").split(",") if p] or synth_eval.eval_visits()
    else:
        pids = [p for p in os.environ.get("MEDAI_PIDS", "").split(",") if p] or HELD_OUT
    prefix = "synth-" if synth else "fs-test-"
    limit = int(os.environ.get("MEDAI_LIMIT", "0") or 0)
    max_new = int(os.environ.get("MEDAI_MAX_NEW_TOKENS", "4096"))

    done = _done(Path(MANIFEST_ROOT)) if Path(MANIFEST_ROOT).exists() else set()
    todo = [p for p in pids if f"{prefix}{p}" not in done]
    if os.environ.get("MEDAI_SHARD"):
        i0, n0 = (int(x) for x in os.environ["MEDAI_SHARD"].split("/"))
        todo = todo[i0::n0]
    print(f"adapter={adapter}\nmanifests={MANIFEST_ROOT}\nletters: {len(pids)} total, "
          f"{len(pids) - len(todo)} already done, {len(todo)} to run", flush=True)
    if limit:
        todo = todo[:limit]

    svc = Med42ModelService(_Config())
    if not svc.load_model():
        raise SystemExit(f"Failed to load Med42: {svc.load_error}")
    backend = Med42Backend(svc)
    decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None,
                              max_new_tokens=max_new, seed=0, constrained=False)

    n_pop = 0
    for i, pid in enumerate(todo, 1):
        note = (synth_eval.note_text(pid) if synth
                else (FS_TEXT_DIR / f"{pid}.txt").read_text(encoding="utf-8"))
        patient = synth_eval.patient_of(pid) if synth else pid
        started = datetime.now(timezone.utc)
        t0 = time.time()
        raw, n_tok = backend.generate(build_ft_prompt(note, patient), decoding)
        dur = time.time() - t0
        modules = split_phenotype(raw, doc_id=pid)
        degenerate = is_degenerate(modules)
        n_pop += (not degenerate)
        m = RunManifest(
            run_id=f"ft-{pid}-{started.strftime('%H%M%S')}",
            started_at=started.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_s=round(dur, 2),
            code_sha=_git_sha_short(), code_dirty=_git_dirty(),
            hardware=_hardware_info(),
            schema_version="v0.2.1",
            prompt_id=FT_PROMPT_ID, prompt_version="v1",
            model_name=backend.model_name, model_cache_dir=backend.model_cache_dir,
            decoding=dataclasses.asdict(decoding),
            source_doc_id=f"{prefix}{pid}", source_doc_type="progress_note",
            source_length_chars=len(note),
            raw_response=raw, raw_response_tokens=n_tok,
            raw_valid=bool(modules), final_valid=bool(modules) and not degenerate,
            repair_method="per_module_smart_repair",
            parsed_value={k: True for k in modules},
            arm=FT_ARM,
        )
        m.write()
        print(f"[{i:3d}/{len(todo)}] {pid} tokens={n_tok} {dur:.0f}s modules={sorted(modules)} "
              f"{'DEGENERATE' if degenerate else 'ok'}", flush=True)

    print(f"\nDone. new letters={len(todo)} populated={n_pop}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
