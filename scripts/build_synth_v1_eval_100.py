"""Assemble the Phase 6c synth-v1 held-out evaluation corpus.

Copies documents and gold phenotype JSONs from
``data/episynth_corpus/v1/`` into
``data/eval_corpora/synth_v1_eval_100/`` for every synth-v1 patient in the
LoRA val split under the historical training seed (val_frac=0.1, seed=0),
producing:

    data/eval_corpora/synth_v1_eval_100/
        documents/<PID>_<doc_type>.txt        # one file per document
        gold_v0_2_1/<PID>_<doc_type>.json     # per-doc gold (patient-level target scoped to this doc)
        manifest.csv                          # id, patient_id, doc_type, char_count, had_lora_training
        README.md                             # provenance note

Rerun-safe: overwrites files with identical content each time.
"""

from __future__ import annotations

import csv
import json
import random
import shutil
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNTH_ROOT = REPO_ROOT / "data" / "episynth_corpus" / "v1"
SYNTH_DOCS = SYNTH_ROOT / "documents"
SYNTH_TARGETS = SYNTH_ROOT / "targets"
OUT_ROOT = REPO_ROOT / "data" / "eval_corpora" / "synth_v1_eval_100"

VAL_FRAC = 0.1
VAL_SEED = 0
SYNTH_RANGE = (500, 1000)


def _val_pids_for_corpus(n_fs: int) -> set[str]:
    """Reproduce `_split_by_patient(val_frac=0.1, seed=0)` for a corpus of
    (500 synth patients) + (first `n_fs` F-S patients).
    """
    pids = [f"P{i:06d}" for i in range(*SYNTH_RANGE)] \
         + [f"EA{i:04d}" for i in range(1, n_fs + 1)]
    pids = sorted(pids)
    rng = random.Random(VAL_SEED)
    rng.shuffle(pids)
    n_val = max(1, int(round(len(pids) * VAL_FRAC)))
    return set(pids[:n_val])


def _pick_holdout_synth_pids() -> tuple[list[str], str]:
    """Return the held-out synth patient IDs to use for Phase 7 evaluation
    of the *current* adapter (`v3_fssplit`, corpus=synth+fs80).

    Rationale
    ---------
    The Phase 7 headline number is Med42+v3_fssplit on F-S 40 held-out; that
    adapter was trained on ``synth+fs80`` (500 synth + first 160 F-S), split
    at ``val_frac=0.1, seed=0``. Under that split, 51 synth patients were
    held out from training — those 51 (102 docs) form our synth-v1 eval set.

    Older adapters (`v2`, base) used ``synth+fs`` (500 synth + all 200 F-S);
    seed=0 with a different total-pid count produces a different shuffle, so
    only 5 patients are common to both val splits. If a user needs to
    evaluate the older adapters against this held-out set, they must pass
    ``--strict-intersection`` (which reduces to that 5-patient overlap).

    Returns
    -------
    (patient_ids, rationale_note)
    """
    v_synthfs80 = _val_pids_for_corpus(160)   # v3_fssplit
    synth_v3 = sorted(p for p in v_synthfs80 if p.startswith("P0"))
    return synth_v3, (
        "val split of the corpus that trained the current LoRA adapter "
        "`v3_fssplit` (synth+fs80, val_frac=0.1, val_seed=0)"
    )


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    docs_out = OUT_ROOT / "documents"
    gold_out = OUT_ROOT / "gold_v0_2_1"
    docs_out.mkdir(exist_ok=True)
    gold_out.mkdir(exist_ok=True)

    synth_val, rationale = _pick_holdout_synth_pids()
    print(f"[build] Held-out synth patients (v3_fssplit val fold): "
          f"{len(synth_val)}")
    print(f"[build] Rationale: {rationale}")
    if len(synth_val) < 40:
        print(f"[build] FAIL: too few held-out synth patients "
              f"({len(synth_val)}), expected >= 40.", file=sys.stderr)
        return 2

    manifest_rows: list[dict[str, str]] = []
    total_docs = 0
    missing_gold = 0

    for pid in synth_val:
        pdir = SYNTH_DOCS / pid
        if not pdir.is_dir():
            print(f"[build] WARN: no docs directory for {pid}")
            continue
        # Load patient-level target once.
        tgt_path = SYNTH_TARGETS / pid / "target_phenotype.json"
        gold: dict | None = None
        if tgt_path.exists():
            gold = json.loads(tgt_path.read_text())
        else:
            missing_gold += 1

        for doc_dir in sorted(pdir.iterdir()):
            if not doc_dir.is_dir():
                continue
            doc_type = doc_dir.name
            src = doc_dir / "output.txt"
            if not src.exists():
                print(f"[build] WARN: no output.txt for {pid}/{doc_type}")
                continue
            doc_id = f"{pid}_{doc_type}"
            dst = docs_out / f"{doc_id}.txt"
            shutil.copyfile(src, dst)
            char_count = dst.stat().st_size
            total_docs += 1

            # Per-doc gold: scope the patient target to this doc's provenance.
            if gold is not None:
                per_doc_gold = _scope_gold_to_doc(gold, pid, doc_type)
                (gold_out / f"{doc_id}.json").write_text(
                    json.dumps(per_doc_gold, indent=2))

            manifest_rows.append({
                "id": doc_id,
                "patient_id": pid,
                "doc_type": doc_type,
                "char_count": str(char_count),
                "had_lora_training": "False",
                "source_path": str(src.relative_to(REPO_ROOT)),
                "gold_path": (
                    str((gold_out / f"{doc_id}.json").relative_to(REPO_ROOT))
                    if gold is not None else ""
                ),
            })

    # Manifest.
    manifest_path = OUT_ROOT / "manifest.csv"
    fields = ["id", "patient_id", "doc_type", "char_count",
              "had_lora_training", "source_path", "gold_path"]
    with manifest_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest_rows)

    # README.
    _write_readme(OUT_ROOT, len(synth_val), total_docs, missing_gold)

    print(f"[build] Wrote {total_docs} docs, {len(manifest_rows)} manifest "
          f"rows, README -> {OUT_ROOT}")
    if missing_gold:
        print(f"[build] WARN: {missing_gold} patients missing gold target")
    return 0


def _scope_gold_to_doc(gold: dict, pid: str, doc_type: str) -> dict:
    """Return a shallow copy of the patient-level gold with the top-level
    document block rewritten to describe THIS document (doc_id, doc_type)."""
    scoped = json.loads(json.dumps(gold))   # deep copy
    doc = scoped.get("document", {}) or {}
    doc["doc_id"] = f"{pid}_{doc_type}"
    doc["doc_type"] = doc_type
    doc["patient_id"] = pid
    scoped["document"] = doc
    return scoped


def _write_readme(out_root: Path, n_patients: int, n_docs: int,
                  n_missing_gold: int) -> None:
    lines = [
        "# Phase 6c — Synth-v1 held-out evaluation corpus",
        "",
        "## Provenance",
        "",
        "- Source: `data/episynth_corpus/v1/` (generator `gpt-5.6-sol`,",
        "  1000 documents across 500 patients P000500..P000999).",
        "- Selection: patient IDs in the LoRA val split for the CURRENT",
        "  adapter under evaluation — `v3_fssplit`, trained on",
        "  `synth+fs80` (500 synth + first 160 F-S) with",
        "  `val_frac=0.1, val_seed=0`. Split is patient-level, so every",
        "  listed patient contributed ZERO gradient updates to",
        "  `checkpoints/llama3-med42-8b_lora_epi_v3_fssplit/`.",
        "- Older adapters (`v2`, base) used `synth+fs` (500 synth + all 200",
        "  F-S). seed=0 with a different total-pid count produces a",
        "  different shuffle; only 5 synth patients are shared across both",
        "  val splits. If you need to evaluate the older adapters,",
        "  regenerate this corpus for the corpus=`synth+fs` val fold via",
        "  `scripts/build_synth_v1_eval_100.py` after editing",
        "  `_pick_holdout_synth_pids`.",
        "",
        f"- Held-out patients: **{n_patients}**",
        f"- Total documents: **{n_docs}**",
        f"- Patients missing gold target JSON: {n_missing_gold}",
        "",
        "## Layout",
        "",
        "- `documents/<PID>_<doc_type>.txt` — one plain-text note per doc.",
        "- `gold_v0_2_1/<PID>_<doc_type>.json` — patient-level target",
        "  phenotype (`data/episynth_corpus/v1/targets/<PID>/target_phenotype.json`)",
        "  with the top-level `document` block rewritten to describe THIS",
        "  doc. Per-Evidence provenance still points at the original",
        "  synthesis IDs.",
        "- `manifest.csv` — one row per document (id, patient_id, doc_type,",
        "  char_count, had_lora_training [always `False`], source_path,",
        "  gold_path).",
        "",
        "## Verification",
        "",
        "    venv-medcat/bin/python scripts/verify_synth_holdout_disjoint.py",
        "",
        "Exits 0 iff every manifest patient is in the LoRA val split of the",
        "target adapter (default `synth+fs80`, i.e. `v3_fssplit`). Reruns",
        "are reproducible under the recorded seed.",
        "",
        "## Phase 7 use",
        "",
        "Corpus-agnostic scorer will consume `documents/` for extraction and",
        "`gold_v0_2_1/` for reference labels. `had_lora_training=False`",
        "guarantees no leakage.",
    ]
    (out_root / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
