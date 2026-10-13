#!/usr/bin/env python3
"""External test of EpExtra IED attributes on TUH EEG-report annotations (when the files are local).

Gold: Maldonado and Harabagiu, LREC 2020 (``writing/further_LEO.md`` G2). The TUH EEG corpus and the
SACAR annotations need a Temple data-use agreement; they are not in this repo. This script scores a
simple JSONL once you have converted a slice of those annotations:

    {"text": "...", "ieds": [{"ied_type": "sharp_wave", "localization": "temporal",
      "laterality": "right", "frequency_band": "theta", "recurrence": "frequent",
      "dispersal": "focal"}]}

Only attributes that the gold states are scored (a missing gold field is skipped). Clinic-letter
behaviour is unchanged by the section filter; this test is for EEG-report text.

    venv-medcat/bin/python scripts/score_tuh_eeg_attributes.py \
        --data data/external/tuh_eeg_reports/gold.jsonl \
        --out eval/results/tuh_eeg_attributes_epextra
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from rules.fields.eeg import IedFindingsRule  # noqa: E402
from schema.enums import DocumentType  # noqa: E402

_META = {"doc_id": "tuh", "doc_type": DocumentType.EEG_REPORT, "doc_date": None}
KEYS = ("ied_type", "localization", "laterality", "frequency_band", "recurrence", "dispersal")
DOWNLOAD_HINT = (
    "TUH EEG-report gold not found. Register at https://isip.piconepress.com/projects/nedc/html/tuh_eeg/ "
    "and obtain the LREC 2020 annotations (Maldonado and Harabagiu, ACL Anthology 2020.lrec-1.276). "
    "Convert a held-out slice to JSONL at data/external/tuh_eeg_reports/gold.jsonl. Do not change the "
    "rules after seeing that file."
)


def _plain(v):
    if v is None:
        return None
    return getattr(v, "value", v)


def _pred_ieds(text: str) -> list[dict]:
    evs = IedFindingsRule().apply([], SimpleNamespace(text=text), _META) or []
    out = []
    for ev in evs:
        v = ev.value
        out.append({k: _plain(getattr(v, k, None)) for k in KEYS})
    return out


def _match(gold: dict, pred: list[dict]) -> dict[str, tuple[int, int, int]]:
    """Greedy one-to-one on ied_type then localization; score each stated gold field."""
    used = set()
    scores = {k: [0, 0, 0] for k in KEYS}  # tp, fp, fn
    for g in gold:
        best = None
        for i, p in enumerate(pred):
            if i in used:
                continue
            if g.get("ied_type") and p.get("ied_type") != g["ied_type"]:
                continue
            best = i
            if g.get("localization") and p.get("localization") == g["localization"]:
                break
        if best is None:
            for k in KEYS:
                if g.get(k) is not None:
                    scores[k][2] += 1
            continue
        used.add(best)
        p = pred[best]
        for k in KEYS:
            if g.get(k) is None:
                continue
            if p.get(k) == g[k]:
                scores[k][0] += 1
            else:
                scores[k][1] += 1
                scores[k][2] += 1
    for i, p in enumerate(pred):
        if i not in used:
            scores["ied_type"][1] += 1
    return {k: tuple(v) for k, v in scores.items()}


def _f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/external/tuh_eeg_reports/gold.jsonl")
    ap.add_argument("--out", default="eval/results/tuh_eeg_attributes_epextra")
    args = ap.parse_args()
    path = Path(args.data)
    if not path.exists():
        print(DOWNLOAD_HINT, file=sys.stderr)
        return 2
    agg = defaultdict(lambda: [0, 0, 0])
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        n += 1
        for k, (t, f, m) in _match(row.get("ieds") or [], _pred_ieds(row["text"])).items():
            a = agg[k]
            a[0] += t
            a[1] += f
            a[2] += m
    summary = {k: dict(zip(("tp", "fp", "fn"), v), **dict(zip(("p", "r", "f1"), _f1(*v))))
               for k, v in agg.items()}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps({"n": n, "per_field": summary}, indent=2))
    L = [f"# TUH EEG-report IED attributes, rules only (n={n})", "",
         "| field | tp | fp | fn | P | R | F1 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for k, s in summary.items():
        L.append(f"| {k} | {s['tp']} | {s['fp']} | {s['fn']} | {s['p']:.3f} | {s['r']:.3f} | {s['f1']:.3f} |")
    out.with_suffix(".md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
