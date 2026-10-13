#!/usr/bin/env python3
"""External test of EpExtra's "current at visit" logic on the CASI medication-status set.

Data: Agrawal et al., EMNLP 2022 (``writing/further_LEO.md`` M2), 100 test snippets from CASI (Minnesota) with
every medication labelled active / discontinued / neither.  Hugging Face ``mitclinicalml/clinical-ie`` (gated:
accept the terms on the dataset page, then ``huggingface-cli login`` or set ``HF_TOKEN``), files
``medication_status_{dev,test}.csv``, saved under ``data/external/casi_medication_status/``.

The gold drug names are given to the rule, so this scores the context decision only (``rules.med_context.
casi_status``), not drug recognition: most CASI drugs are not anti-seizure medicines and EpExtra's linker is an
epilepsy vocabulary.  Metrics: per-label P/R/F1 and macro F1 over the three labels (the paper's metric), plus the
share of gold drugs whose name is not found verbatim in the snippet (scored as wrong).

    venv-medcat/bin/python scripts/score_casi_medication_status.py \
        --data data/external/casi_medication_status/medication_status_test.csv \
        --out eval/results/casi_medication_status_epextra
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from rules.med_context import casi_status  # noqa: E402

LABELS = ("active", "discontinued", "neither")
DOWNLOAD_HINT = ("CASI medication-status file not found. Accept the terms at "
                 "https://huggingface.co/datasets/mitclinicalml/clinical-ie, log in (huggingface-cli login or HF_TOKEN), "
                 "then download medication_status_test.csv into data/external/casi_medication_status/.")


def _parse_list(raw: str) -> list:
    raw = (raw or "").strip()
    if not raw:
        return []
    for loader in (json.loads, ast.literal_eval):
        try:
            v = loader(raw)
            return v if isinstance(v, (list, dict)) else [v]
        except Exception:
            pass
    return [x.strip() for x in raw.split(",") if x.strip()]


def _norm_label(s: str) -> str:
    s = (s or "").strip().lower()
    if s.startswith("act"):
        return "active"
    if s.startswith("disc") or "hold" in s or s.startswith("stop"):
        return "discontinued"
    return "neither"


def gold_pairs(row: dict) -> tuple[str, list[tuple[str, str]]]:
    """(snippet text, [(drug, label)]) from one CSV row, whatever the column layout."""
    cols = list(row)
    structured = {c for c in cols if (row[c] or "").strip()[:1] in ("[", "{")}
    text_col = max([c for c in cols if c not in structured] or cols, key=lambda c: len(row[c] or ""))
    by_label = {lab: c for c in cols for lab in LABELS if lab in c.lower() and c != text_col}
    pairs: list[tuple[str, str]] = []
    if by_label:
        for lab, c in by_label.items():
            for d in _parse_list(row[c]):
                name = d.get("name") or d.get("medication") if isinstance(d, dict) else d
                if name:
                    pairs.append((str(name), lab))
    else:
        for c in cols:
            if c == text_col:
                continue
            v = _parse_list(row[c])
            if isinstance(v, dict):
                for lab, names in v.items():
                    for n in (names if isinstance(names, list) else [names]):
                        pairs.append((str(n), _norm_label(lab)))
            elif v and all(isinstance(x, dict) for x in v):
                for x in v:
                    name = x.get("name") or x.get("medication") or x.get("drug")
                    lab = x.get("status") or x.get("label") or x.get("category")
                    if name and lab:
                        pairs.append((str(name), _norm_label(str(lab))))
            if pairs:
                break
    return row[text_col], pairs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/external/casi_medication_status/medication_status_test.csv")
    ap.add_argument("--out", default="eval/results/casi_medication_status_epextra")
    args = ap.parse_args()
    path = REPO / args.data
    if not path.exists():
        sys.exit(DOWNLOAD_HINT)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    conf: Counter = Counter()
    not_found = 0
    examples = []
    for i, row in enumerate(rows):
        text, pairs = gold_pairs(row)
        for name, gold in pairs:
            pred = casi_status(text, name)
            if pred is None:
                not_found += 1
                pred = "not_found"
            conf[(gold, pred)] += 1
            if pred != gold and len(examples) < 40:
                examples.append({"row": i, "drug": name, "gold": gold, "pred": pred})
    n = sum(conf.values())
    if n == 0:
        sys.exit("no gold medications parsed; check the CSV columns: " + ", ".join(rows[0]) if rows else "empty file")
    per = {}
    for lab in LABELS:
        tp = conf[(lab, lab)]
        fp = sum(v for (g, p), v in conf.items() if p == lab and g != lab)
        fn = sum(v for (g, p), v in conf.items() if g == lab and p != lab)
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        per[lab] = {"n_gold": tp + fn, "p": pr, "r": rc, "f1": 2 * pr * rc / (pr + rc) if pr + rc else 0.0}
    macro = sum(v["f1"] for v in per.values()) / len(LABELS)
    acc = sum(conf[(lab, lab)] for lab in LABELS) / n
    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps({
        "data": args.data, "snippets": len(rows), "gold_medications": n, "name_not_found": not_found,
        "accuracy": acc, "macro_f1": macro, "per_label": per,
        "confusion": {f"{g}->{p}": v for (g, p), v in sorted(conf.items())}, "errors": examples}, indent=2))
    L = ["# EpExtra medication context on CASI medication status (Agrawal et al. 2022)", "",
         f"*`scripts/score_casi_medication_status.py`, data `{args.data}`. Gold drug names given; context only.*", "",
         f"{len(rows)} snippets, {n} gold medications, {not_found} names not found verbatim (scored wrong). "
         f"Accuracy {acc:.3f}; **macro F1 {macro:.3f}**.", "",
         "| label | gold | P | R | F1 |", "|---|---:|---:|---:|---:|"]
    L += [f"| {lab} | {v['n_gold']} | {v['p']:.3f} | {v['r']:.3f} | {v['f1']:.3f} |" for lab, v in per.items()]
    L += ["", "Confusion (gold -> predicted): " + "; ".join(f"{g}->{p} {v}" for (g, p), v in sorted(conf.items()))]
    out.with_suffix(".md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
