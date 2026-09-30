#!/usr/bin/env python3
"""Audit MetaCAT-training-signal coverage in a synth corpus.

Reads a manifest.csv + documents/ and reports what fraction of docs
contain evidence of each of the 5 ExECT-V2 attribute dimensions:

    1. Presence / Negation
    2. Experiencer (family)
    3. Temporality (past AEDs)
    4. Certainty (hedged assertions)
    5. Hypothetical (if / should triggers)

Also reports the realism markers (physician shorthand, device brand names,
exam fragments).

Usage:
    venv-medcat/bin/python scripts/audit_metacat_coverage.py \\
        --corpus-dir data/eval_corpora/synth_v3_polish \\
        [--compare-with data/eval_corpora/synth_v3]
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


DIMENSIONS = {
    # ExECT-V2 5-dimension MetaCAT attribute set
    "negation":     re.compile(r"\b(denies|denied|no\s+(?:history\s+of|reports\s+of)|"
                               r"without|absent|no\s+known|no\s+evidence\s+of|"
                               r"no\s+family\s+history|NKDA)\b", re.I),
    "family_hx":    re.compile(r"\b(?:family\s+history|father|mother|brother|sister|"
                               r"maternal|paternal|sibling|grandmother|grandfather)"
                               r"[^.]{0,60}\b(?:epilep|seizur|febrile|neurologic|"
                               r"stroke|migraine)", re.I),
    "past_aed":     re.compile(r"\b(?:previously\s+(?:trialed|tried|took|on)|"
                               r"failed\s+(?:trial|adequate|prior)|"
                               r"prior(?:ly)?\s+(?:on|took|treated)|"
                               r"was\s+(?:on|taking|started\s+on)|"
                               r"discontinued\s+due\s+to)\b", re.I),
    "certainty_hedged": re.compile(r"\b(?:possibly|likely|probable|probably|"
                                   r"cannot\s+exclude|consistent\s+with|"
                                   r"suggestive\s+of|suspected|c/w|may\s+be|"
                                   r"could\s+represent|r/o)\b", re.I),
    "hypothetical": re.compile(r"\b(?:if\s+(?:she|he|they|another|breakthrough)|"
                               r"should\s+(?:she|he|they|recurrence|another)|"
                               r"in\s+the\s+event\s+of|would\s+recommend\s+"
                               r"(?:if|should))\b", re.I),
}

REALISM = {
    "sp_shorthand":  re.compile(r"\bs/p\b"),
    "hx_shorthand":  re.compile(r"\b(?:hx\s+of|h/o)\b", re.I),
    "ro_shorthand":  re.compile(r"\br/o\b", re.I),
    "device_brand":  re.compile(r"\b(?:NeuroPace|Medtronic\s+DBS|LivaNova\s+VNS|"
                                r"Percept|SenTiva)\b", re.I),
    "exam_fragment": re.compile(r"(?:^|\.\s+)(?:Alert,\s+oriented|"
                                r"CN\s+II-XII\s+intact|Motor\s+5/5|"
                                r"DTRs\s+2\+|In\s+NAD)", re.I | re.M),
    "brand_generic": re.compile(r"\b(?:Keppra|Lamictal|Dilantin|Tegretol|Trileptal|"
                                r"Vimpat|Topamax|Depakote|Depakene)\s*\("),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--compare-with", default=None,
                    help="Second corpus dir to compare against (optional)")
    args = ap.parse_args()

    def survey(corpus_dir: str) -> dict:
        base = Path(corpus_dir)
        manifest = base / "manifest.csv"
        docs = base / "documents"
        if not manifest.exists():
            return {}
        rows = list(csv.DictReader(manifest.open()))
        n = 0
        dim_hits = {k: 0 for k in DIMENSIONS}
        real_hits = {k: 0 for k in REALISM}
        for r in rows:
            p = base / r["note_path"]
            if not p.exists():
                continue
            n += 1
            text = p.read_text()
            for k, pat in DIMENSIONS.items():
                if pat.search(text):
                    dim_hits[k] += 1
            for k, pat in REALISM.items():
                if pat.search(text):
                    real_hits[k] += 1
        return {"n": n, "dim": dim_hits, "real": real_hits}

    a = survey(args.corpus_dir)
    b = survey(args.compare_with) if args.compare_with else None

    def _fmt(v, n): return f"{100*v/max(n,1):5.1f}% ({v:3d}/{n})"

    print(f"Corpus A: {args.corpus_dir}  n={a['n']} docs")
    if b:
        print(f"Corpus B: {args.compare_with}  n={b['n']} docs")
    print()
    print("─── MetaCAT ambiguation dimensions ─────────────────────────")
    print(f"{'dimension':<20}  {'corpus A':>18}", end="")
    if b: print(f"  {'corpus B':>18}  Δ")
    else: print()
    for k in DIMENSIONS:
        line = f"{k:<20}  {_fmt(a['dim'][k], a['n']):>18}"
        if b:
            delta = (a['dim'][k]/max(a['n'],1) - b['dim'][k]/max(b['n'],1)) * 100
            line += f"  {_fmt(b['dim'][k], b['n']):>18}  {delta:+5.1f}pp"
        print(line)

    print()
    print("─── Realism markers ─────────────────────────────────────────")
    print(f"{'marker':<20}  {'corpus A':>18}", end="")
    if b: print(f"  {'corpus B':>18}  Δ")
    else: print()
    for k in REALISM:
        line = f"{k:<20}  {_fmt(a['real'][k], a['n']):>18}"
        if b:
            delta = (a['real'][k]/max(a['n'],1) - b['real'][k]/max(b['n'],1)) * 100
            line += f"  {_fmt(b['real'][k], b['n']):>18}  {delta:+5.1f}pp"
        print(line)


if __name__ == "__main__":
    main()
