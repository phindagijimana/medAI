#!/usr/bin/env python3
"""Per-patient focal motor onset: plan vs rules vs model on the X1C GPU run.

    venv-medcat/bin/python eval/inspect_focal_motor.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from score_extended_phenotypes import MOTOR_STEM, PLAN_DIR, canon  # noqa: E402

RAW = REPO / "data" / "leo_runs" / "v4ext_llm_x1c.rawclaims.json"
OUT = REPO / "eval" / "results" / "focal_motor_x1c_cases.md"


def src(c):
    d = {("llm" if "llm" in x.lower() else "spec") for x in c.get("detectors") or []}
    return "+".join(sorted(d, reverse=True)) or "none"


def main() -> int:
    raw = json.loads(RAW.read_text())
    by_pid = defaultdict(list)
    for note_id, claims in raw.items():
        pid = note_id.split("_")[0]
        for c in claims:
            if c.get("field_path") == "clinical_seizure.focal_motor_onset" and c.get("verdict") != "reject":
                by_pid[pid].append(c)
    rows = []
    for p in sorted(PLAN_DIR.glob("*.json")):
        plan = json.loads(p.read_text(encoding="utf-8"))
        ref = {a["field"]: a["value"] for a in plan.get("required_assertions") or []}
        fo = (ref.get("FOCAL_ONSET") or {}).get("motor") if isinstance(ref.get("FOCAL_ONSET"), dict) else None
        if not fo:
            continue
        claims = by_pid.get(p.stem, [])
        rules, model = [], []
        for c in claims:
            dets = " ".join(str(x).lower() for x in (c.get("detectors") or []))
            if "epextra" in dets or "spec" in dets:
                rules.append(c)
            if "llm" in dets:
                model.append(c)
        rv = rules[0]["value"] if rules else None
        mv = model[0]["value"] if model else None
        rq = (rules[0].get("evidence") or "")[:80] if rules else ""
        mq = (model[0].get("evidence") or "")[:80] if model else ""
        r_ok = canon(rv, MOTOR_STEM) == fo if rv else False
        m_ok = canon(mv, MOTOR_STEM) == fo if mv else False
        status = "both_right" if r_ok and m_ok else "rules_only" if r_ok else "model_only" if m_ok else (
            "both_wrong" if rv or mv else "missing")
        rows.append({"pid": p.stem, "plan": fo, "rules": rv or "", "model": mv or "",
                     "rules_quote": rq, "model_quote": mq, "status": status})
    md = ["# Focal motor onset: plan vs X1C GPU run", "",
          f"Patients with a plan motor onset: {len(rows)}.", "",
          "| pid | plan | rules | model | status |",
          "|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['pid']} | {r['plan']} | {r['rules']} | {r['model']} | {r['status']} |")
    md += ["", "Quotes (truncated, synthetic notes):", ""]
    for r in rows:
        if r["status"] in ("both_right",):
            continue
        md.append(f"- **{r['pid']}** plan `{r['plan']}` rules `{r['rules']}` «{r['rules_quote']}» "
                  f"model `{r['model']}` «{r['model_quote']}»")
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
