#!/usr/bin/env python3
"""Fill a LEO disagreement sheet from the v4_ext plan (synthetic gold), not from a clinician.

Writes:
  * RESULT.disagreements.blind.csv     adjudicator copy (no key_A_is)
  * RESULT.disagreements.plan.csv      scored copy with key + plan truth
  * RESULT.disagreements.plan.md       per-field rates

This is plan-gold on the same generator as the rules.  It does **not** settle the
default policy (D17 / DISAGREEMENT_ADJUDICATION.md).  It tells us which reader
matched the plan when they disagreed on these notes.

    venv-medcat/bin/python eval/adjudicate_v4ext_disagreements.py \\
        data/leo_runs/v4ext_llm_x1c.disagreements.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from score_extended_phenotypes import MOTOR_STEM, NONMOTOR_STEM, PLAN_DIR, STUDY_STEM, canon  # noqa: E402
from services.leo_disagree import load, score_cases  # noqa: E402

EP_MAP = {"combined_generalized_and_focal": "combined_focal_generalized"}
SZ_MAP = {"absence_typical": "generalized_absence_typical", "myoclonic": "generalized_myoclonic"}


def _pid(doc_id: str) -> str:
    return str(doc_id).split("_")[0]


def _norm(v) -> str:
    return str(v or "").strip().lower().replace("-", "_").replace(" ", "_")


def gold_for(path: str, ref: dict):
    if path == "clinical_seizure.epilepsy_type":
        t = ref.get("EP_TYPE")
        return EP_MAP.get(t, t)
    if path == "clinical_seizure.predominant_seizure_type":
        t = ref.get("SZ_TYPE")
        if not t or str(t).startswith("unknown_onset"):
            return None
        return SZ_MAP.get(t, t)
    if path == "clinical_seizure.age_at_onset_years":
        return ref.get("AGE_AT_ONSET_YEARS")
    if path == "eeg.study_type":
        e = ref.get("EEG_STUDY") or {}
        return e.get("study_type")
    if path == "eeg.background":
        e = ref.get("EEG_STUDY") or {}
        return e.get("background")
    if path == "eeg.ied_present":
        e = ref.get("EEG_STUDY") or {}
        return None if e.get("ied_lobe") is None else True
    if path == "clinical_seizure.focal_motor_onset":
        fo = ref.get("FOCAL_ONSET") or {}
        return fo.get("motor")
    if path == "clinical_seizure.focal_nonmotor_onset":
        fo = ref.get("FOCAL_ONSET") or {}
        return fo.get("nonmotor")
    if path == "clinical_seizure.seizure_frequency":
        return ref.get("SZ_FREQ") or ref.get("SEIZURE_FREQUENCY")
    return None


def matches(path: str, reading: str, gold) -> bool:
    if gold is None or reading is None or str(reading).strip() == "":
        return False
    a, b = reading, gold
    if path == "clinical_seizure.age_at_onset_years":
        try:
            return abs(float(a) - float(b)) < 0.5
        except (TypeError, ValueError):
            return False
    if path == "eeg.study_type":
        return canon(a, STUDY_STEM) == b or _norm(a) == _norm(b)
    if path == "eeg.background":
        s = str(a).lower()
        got = "normal" if "normal" in s and "slow" not in s else ("slowing" if "slow" in s else _norm(a))
        want = "normal" if str(b) == "normal" else ("slowing" if b else None)
        return got == want or _norm(a) == _norm(b)
    if path == "eeg.ied_present":
        return str(a).strip().lower() in ("true", "1", "yes") if gold is True else str(a).strip().lower() in (
            "false", "0", "no")
    if path == "clinical_seizure.focal_motor_onset":
        return canon(a, MOTOR_STEM) == gold or _norm(a) == _norm(gold)
    if path == "clinical_seizure.focal_nonmotor_onset":
        return canon(a, NONMOTOR_STEM) == gold or _norm(a) == _norm(gold)
    if path == "clinical_seizure.seizure_frequency":
        if isinstance(gold, dict):
            q, u = gold.get("quantity"), gold.get("unit")
            blob = f"{q} {u} {q} per {u} {q}/{u}".lower()
            return str(a).lower() in blob or str(q) in str(a) and str(u or "").lower() in str(a).lower()
        return _norm(a) == _norm(b) or str(a).lower() in str(b).lower() or str(b).lower() in str(a).lower()
    return _norm(a) == _norm(b)


def decide(path: str, a: str, b: str, gold) -> tuple[str, str]:
    """truth, comment."""
    if gold is None:
        return "unclear", "no plan value for this field"
    hit_a, hit_b = matches(path, a, gold), matches(path, b, gold)
    if hit_a and hit_b:
        return "both", f"plan={gold}"
    if hit_a:
        return "A", f"plan={gold}"
    if hit_b:
        return "B", f"plan={gold}"
    return "neither", f"plan={gold}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sheet", nargs="?", default="data/leo_runs/v4ext_llm_x1c.disagreements.csv")
    args = ap.parse_args()
    src = Path(args.sheet)
    df = load(src)
    plans = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(PLAN_DIR.glob("*.json"))}
    for i, r in df.iterrows():
        pid = _pid(r["document_id"])
        plan = plans.get(pid) or {}
        ref = {a["field"]: a["value"] for a in plan.get("required_assertions") or []}
        gold = gold_for(r["field_path"], ref)
        truth, comment = decide(r["field_path"], r["reading_A"], r["reading_B"], gold)
        df.at[i, "truth"] = truth
        df.at[i, "true_value"] = "" if gold is None else str(gold)
        df.at[i, "adjudicator"] = "v4_ext_plan"
        df.at[i, "comment"] = comment
    keyed = src.with_name(src.name.replace(".csv", "") + ".plan.csv")
    blind = src.with_name(src.name.replace(".csv", "") + ".blind.csv")
    df.to_csv(keyed, index=False, encoding="utf-8-sig")
    df.drop(columns=["key_A_is"]).to_csv(blind, index=False, encoding="utf-8-sig")
    res = score_cases(df, "rules")
    lines = ["# v4_ext disagreements scored against the plan (not a clinician)", "",
             f"Sheet: `{src}`. Adjudicator: v4_ext_plan. Default shown reader: rules.", "",
             "This does **not** change the shipped disagreement policy (D17).", "",
             "| field | n | scored | rules right | model right | both | neither | unclear |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for field, r in res.items():
        rr, mm = r["rules_right"], r["model_right"]
        rrate = "n/a" if rr["rate"] is None else f"{rr['k']}/{rr['n']} ({rr['rate']:.2f})"
        mrate = "n/a" if mm["rate"] is None else f"{mm['k']}/{mm['n']} ({mm['rate']:.2f})"
        lines.append(f"| {field} | {r['n_cases']} | {r['n_scored']} | {rrate} | {mrate} | "
                     f"{r['both']} | {r['neither']} | {r['unclear']} |")
    md = src.with_name(src.name.replace(".csv", "") + ".plan.md")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {keyed}\nwrote {blind} (no key_A_is)\nwrote {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
