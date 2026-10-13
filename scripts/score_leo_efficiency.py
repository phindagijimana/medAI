#!/usr/bin/env python3
"""Wall-clock and token stats from existing L1C F-S manifests (no model load).

    python3 scripts/score_leo_efficiency.py \
        --glob 'data/run_manifests_fs_test_flat_c/**/flat-L1C-*.json' \
        --out eval/results/leo_efficiency_fs40
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--glob", default="data/run_manifests_fs_test_flat_c/**/flat-L1C-*.json")
    ap.add_argument("--out", default="eval/results/leo_efficiency_fs40")
    args = ap.parse_args()
    files = sorted(REPO.glob(args.glob))
    rows = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        rows.append({
            "id": d.get("source_doc_id") or f.stem,
            "duration_s": d.get("duration_s"),
            "chars": d.get("source_length_chars"),
            "tokens": d.get("raw_response_tokens"),
            "gpu": (d.get("hardware") or {}).get("gpu_name"),
            "torch": (d.get("hardware") or {}).get("torch"),
            "model": d.get("model_name"),
            "arm": d.get("arm"),
            "prompt_id": d.get("prompt_id"),
            "max_new_tokens": (d.get("decoding") or {}).get("max_new_tokens"),
            "seed": (d.get("decoding") or {}).get("seed"),
        })
    durs = [r["duration_s"] for r in rows if r["duration_s"] is not None]
    toks = [r["tokens"] for r in rows if r["tokens"] is not None]
    chars = [r["chars"] for r in rows if r["chars"] is not None]
    summary = {
        "n": len(rows),
        "model": rows[0]["model"] if rows else None,
        "arm": rows[0]["arm"] if rows else None,
        "gpu": rows[0]["gpu"] if rows else None,
        "duration_s": {
            "mean": statistics.mean(durs) if durs else None,
            "median": statistics.median(durs) if durs else None,
            "min": min(durs) if durs else None,
            "max": max(durs) if durs else None,
            "sum": sum(durs) if durs else None,
        },
        "raw_response_tokens": {
            "mean": statistics.mean(toks) if toks else None,
            "median": statistics.median(toks) if toks else None,
            "max": max(toks) if toks else None,
        },
        "source_chars": {
            "mean": statistics.mean(chars) if chars else None,
            "median": statistics.median(chars) if chars else None,
            "max": max(chars) if chars else None,
        },
        "rows": rows,
    }
    out = Path(args.out)
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    ds, ts, cs = summary["duration_s"], summary["raw_response_tokens"], summary["source_chars"]
    md = [
        "# LEO L1C efficiency (F-S held-out manifests; no re-run)\n",
        f"n={summary['n']}  model=`{summary['model']}`  arm=`{summary['arm']}`  gpu=`{summary['gpu']}`",
        "",
        "| | mean | median | min | max | sum |",
        "|---|---:|---:|---:|---:|---:|",
        f"| duration (s) | {ds['mean']:.2f} | {ds['median']:.2f} | {ds['min']:.2f} | {ds['max']:.2f} | {ds['sum']:.1f} |",
        f"| completion tokens | {ts['mean']:.1f} | {ts['median']:.1f} | — | {ts['max']} | — |",
        f"| note characters | {cs['mean']:.0f} | {cs['median']:.0f} | — | {cs['max']} | — |",
        "",
        "These are **model generate() times** from the stored manifests, not end-to-end LEO "
        "(specialist + fusion + extra readers). Specialist-only CPU on the same 40 letters is a separate pass.",
        "",
    ]
    out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print(out.with_suffix(".md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
