#!/usr/bin/env python3
"""Base Med42-8B with the flat prompts (arms L0 zero-shot, L1 two-example) on
the 40 held-out F-S letters.  See ``services/flat_extract.py`` for why these
replace the per-module M-prompts for the base model.

One manifest per (letter, arm): ``prompt_id = flat_phenotype.<arm>.<version>``
(MEDAI_FLAT_PROMPT_VERSION, default v1; v2 adds an "unknown" epilepsy type).
Resumable.  Arm L2 = k retrieved F-S training letters (MEDAI_FEWSHOT_K, default 3);
the letter itself is excluded from its own examples, so development letters
(MEDAI_PIDS=EA0081,...) can be run too.  MEDAI_CORPUS=synth: US-style synthetic evaluation notes (``services.synth_eval``; manifests keyed
``synth-<visit_id>``; arms L0/L1 and their constrained forms L0C/L1C; L2 needs F-S exemplars and is
not used there); MEDAI_SHARD=i/n splits the pending work across jobs.
Env: MEDAI_ARMS (default "L0,L1"), MEDAI_MAX_NEW_TOKENS (768),
MEDAI_PIDS, MEDAI_LIMIT, MEDAI_MANIFEST_DIR.  Do NOT set MEDAI_LORA_ADAPTER_DIR:
this is the untuned model.
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
os.environ.setdefault("MEDAI_MANIFEST_DIR", str(REPO / "data" / "run_manifests_fs_test_flat"))

from services.extract import DecodingConfig  # noqa: E402
from services.flat_extract import (FLAT_PROMPT_VERSION, build_flat_prompt, flat_answer_model,
                                   parse_flat)  # noqa: E402
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


def _done(root: Path) -> set[tuple[str, str]]:
    out = set()
    for p in root.rglob("*.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("prompt_id", "").startswith("flat_phenotype."):
            out.add((m.get("source_doc_id", ""), m.get("arm", "")))
    return out


def main() -> int:
    if os.environ.get("MEDAI_LORA_ADAPTER_DIR") and os.environ.get("MEDAI_FLAT_ADAPTER_OK") != "1":
        raise SystemExit("Unset MEDAI_LORA_ADAPTER_DIR: flat arms are for the untuned model.  "
                         "(Arm H2 runs the flat contract with its own adapter: set MEDAI_FLAT_ADAPTER_OK=1 "
                         "and a separate MEDAI_MANIFEST_DIR.)")
    arms = [a for a in os.environ.get("MEDAI_ARMS", "L0,L1").split(",") if a]
    synth = os.environ.get("MEDAI_CORPUS", "fs") == "synth"
    if synth:
        from services import synth_eval
        pids = [p for p in os.environ.get("MEDAI_PIDS", "").split(",") if p] or synth_eval.eval_visits()
        if any(a.startswith("L2") for a in arms):
            raise SystemExit("L2/L2C retrieve F-S letters; not available for the synthetic corpus.")
    else:
        pids = [p for p in os.environ.get("MEDAI_PIDS", "").split(",") if p] or HELD_OUT
    prefix = "synth-" if synth else "fs-test-"
    limit = int(os.environ.get("MEDAI_LIMIT", "0") or 0)
    max_new = int(os.environ.get("MEDAI_MAX_NEW_TOKENS", "768"))

    root = Path(MANIFEST_ROOT)
    done = _done(root) if root.exists() else set()
    todo = [(p, a) for a in arms for p in pids if (f"{prefix}{p}", a) not in done]
    if os.environ.get("MEDAI_SHARD"):
        i0, n0 = (int(x) for x in os.environ["MEDAI_SHARD"].split("/"))
        todo = todo[i0::n0]
    print(f"manifests={root}\narms={arms}  {len(todo)} (letter, arm) pairs to run", flush=True)
    if limit:
        todo = todo[:limit]

    svc = Med42ModelService(_Config())
    if not svc.load_model():
        raise SystemExit(f"Failed to load Med42: {svc.load_error}")
    backend = Med42Backend(svc)
    decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None,
                              max_new_tokens=max_new, seed=0, constrained=False)

    for i, (pid, arm) in enumerate(todo, 1):
        note = (synth_eval.note_text(pid) if synth
                else (FS_TEXT_DIR / f"{pid}.txt").read_text(encoding="utf-8"))
        started = datetime.now(timezone.utc)
        t0 = time.time()
        prompt = build_flat_prompt(note, arm, exclude=pid, k=int(os.environ.get("MEDAI_FEWSHOT_K", "3")))
        if arm.endswith("C"):
            raw, n_tok = backend.generate_constrained(prompt, flat_answer_model(), decoding)
        else:
            raw, n_tok = backend.generate(prompt, decoding)
        dur = time.time() - t0
        fp = parse_flat(raw, FLAT_PROMPT_VERSION)
        RunManifest(
            run_id=f"flat-{arm}-{pid}-{started.strftime('%H%M%S')}",
            started_at=started.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(), duration_s=round(dur, 2),
            code_sha=_git_sha_short(), code_dirty=_git_dirty(), hardware=_hardware_info(),
            schema_version="v0.2.1",
            prompt_id=f"flat_phenotype.{arm}.{FLAT_PROMPT_VERSION}",
            prompt_version=FLAT_PROMPT_VERSION,
            model_name=backend.model_name, model_cache_dir=backend.model_cache_dir,
            decoding=dataclasses.asdict(decoding),
            source_doc_id=f"{prefix}{pid}", source_doc_type="progress_note",
            source_length_chars=len(note), raw_response=raw, raw_response_tokens=n_tok,
            raw_valid=fp.parse_ok, final_valid=fp.n_fields_kept > 0,
            repair_method="flat_parse", parsed_value={"fields_kept": fp.n_fields_kept,
                                                      "values_dropped": fp.n_values_dropped},
            arm=arm,
        ).write()
        print(f"[{i:3d}/{len(todo)}] {pid} {arm} tokens={n_tok} {dur:.0f}s kept={fp.n_fields_kept} "
              f"dropped={fp.n_values_dropped}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
