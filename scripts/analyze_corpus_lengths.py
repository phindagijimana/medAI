#!/usr/bin/env python3
"""Corpus length distribution — chars, whitespace tokens, LLaMA tokens.

Produces eval/results/corpus_lengths_summary.md with a table like:

    | corpus      |    n | chars (median [IQR])   | tokens (median [IQR])  |
    | pilot       |   60 | ...                    | ...                    |
    | synth-v1    | 1000 | ...                    | ...                    |
    | fonferko-fs |  200 | ...                    | ...                    |

Feeds §Corpus characterization in the manuscript.

Tokenizer is the Med42/Llama family; we use hf-internal-testing/llama-tokenizer
so this runs without pulling the full Med42 model — tokens produced are
byte-identical because they share the same base BPE.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "eval" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _iter_notes(kind: str):
    """Yield note text strings by corpus kind."""
    if kind == "pilot":
        base = REPO / "data" / "episynth_pilot" / "run_001"
        for arm_dir in base.iterdir():
            if not arm_dir.is_dir() or arm_dir.name in ("g2", "targets"):
                continue
            if arm_dir.name == "C0":
                for p in arm_dir.iterdir():
                    f = p / "output.txt"
                    if f.exists(): yield f.read_text(encoding="utf-8")
            else:
                for cond in arm_dir.iterdir():
                    if not cond.is_dir(): continue
                    for p in cond.iterdir():
                        f = p / "output.txt"
                        if f.exists(): yield f.read_text(encoding="utf-8")
    elif kind == "synth-v1":
        base = REPO / "data" / "episynth_corpus" / "v1" / "documents"
        for pid in sorted(base.iterdir()):
            if not pid.is_dir(): continue
            for dt in pid.iterdir():
                if not dt.is_dir(): continue
                f = dt / "output.txt"
                if f.exists():
                    yield f.read_text(encoding="utf-8")
    elif kind == "fonferko-fs":
        base = REPO / "data" / "fs_corpus" / "documents"
        for pid in sorted(base.iterdir()):
            if not pid.is_dir(): continue
            for dt in pid.iterdir():
                if not dt.is_dir(): continue
                f = dt / "output.txt"
                if f.exists():
                    yield f.read_text(encoding="utf-8")


def _quartiles(xs):
    xs = sorted(xs)
    n = len(xs)
    if n < 4:
        return xs[0], statistics.median(xs), xs[-1]
    q1 = xs[n // 4]
    q3 = xs[3 * n // 4]
    return q1, statistics.median(xs), q3


def main() -> None:
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("hf-internal-testing/llama-tokenizer")

    rows = []
    for kind in ("pilot", "synth-v1", "fonferko-fs"):
        chars = []
        wtoks = []
        ltoks = []
        for text in _iter_notes(kind):
            if not text.strip():
                continue
            chars.append(len(text))
            wtoks.append(len(text.split()))
            ltoks.append(len(tok(text, add_special_tokens=False)["input_ids"]))
        n = len(chars)
        c_q = _quartiles(chars)
        w_q = _quartiles(wtoks)
        l_q = _quartiles(ltoks)
        rows.append({
            "corpus": kind,
            "n_docs": n,
            "char_q1": c_q[0], "char_median": c_q[1], "char_q3": c_q[2],
            "wtok_q1": w_q[0], "wtok_median": w_q[1], "wtok_q3": w_q[2],
            "ltok_q1": l_q[0], "ltok_median": l_q[1], "ltok_q3": l_q[2],
        })
        print(f"{kind:<14} n={n:>4}  chars {c_q[0]}/{c_q[1]}/{c_q[2]}  "
              f"wtoks {w_q[0]}/{w_q[1]}/{w_q[2]}  ltoks {l_q[0]}/{l_q[1]}/{l_q[2]}")

    # CSV
    with (OUT_DIR / "corpus_lengths.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows: w.writerow(r)

    # Markdown for the manuscript §Corpus characterization
    md = [
        "## Corpus length distribution (Table S1 candidate)\n",
        "*Note text after semantic-plan rendering (pilot, synth-v1) or "
        "after F-S de-identification (fonferko-fs). Tokens counted with "
        "the LLaMA/Med42-family BPE tokenizer, no special tokens.*\n",
        "| corpus | n docs | chars (Q1/median/Q3) | whitespace tokens | LLaMA tokens |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        md.append(
            f"| {r['corpus']} | {r['n_docs']} | "
            f"{r['char_q1']}/{r['char_median']}/{r['char_q3']} | "
            f"{r['wtok_q1']}/{r['wtok_median']}/{r['wtok_q3']} | "
            f"{r['ltok_q1']}/{r['ltok_median']}/{r['ltok_q3']} |"
        )
    (OUT_DIR / "corpus_lengths_summary.md").write_text("\n".join(md) + "\n")
    print(f"\nwrote {OUT_DIR/'corpus_lengths_summary.md'}")


if __name__ == "__main__":
    main()
