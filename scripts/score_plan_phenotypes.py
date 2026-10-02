#!/usr/bin/env python3
"""Score the specialist (rules, no LLM) on phenotypes whose reference is in the synthetic generation PLAN
or in the F-S gold, but not in the patient target files that the other scorers read.

Synthetic plans (``data/episynth_corpus/{v3,v3_polish}/patients/<pid>.json``, ``required_assertions``):

    PRIOR_ASMS            stopped drugs with a reason (polish patients only).  "inadequate seizure control" is a
                          failure in the ILAE sense (Kwan 2010); the other reasons are intolerance.
    ETIOLOGY_SPECIFICS    causative gene / variant / antibody (some v3 and polish patients).

Reference sources, prediction = specialist claims over all of one patient's notes joined (the same
documents as ``scripts/score_extra_phenotypes.py``).

F-S gold (``Json/*.json``, 200 letters; scored on the 40 held-out letters EA0161-EA0200 and on all 200,
because the rules are not trained on them):

    Prescription with Frequency "As_Required"   -> rescue medication (ExECT convention)
    Investigations EEG_Performed / EEG_Results  -> coarse EEG result normal / abnormal
    EpilepsyCause                               -> etiology details present (free text, not scored for wording)

Limits (printed in the output): synthetic strata differ in how far the rules were exposed to them; the
polish corpus is a corpus the rules were developed against; the F-S coarse EEG result is a proxy
(abnormal = interictal epileptiform discharges or non-normal background); rescue has 9 reference
prescriptions in 200 letters.

    venv-medcat/bin/python scripts/score_plan_phenotypes.py        # -> eval/results/leo_plan_phenotypes.{json,md}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PLAN_DIR = {"synth_v3": "v3", "synth_v3_polish": "v3_polish"}
FS_GOLD_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8356494" / "Json"
FS_TEXT_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8381080" / "Gold1-200_corrected_spelling"
INEFFICACY = "inadequate seizure control"


def _name(v) -> str:
    v = v.model_dump() if hasattr(v, "model_dump") else v
    return str((v or {}).get("generic_name") or "").strip().lower() if isinstance(v, dict) else str(v).strip().lower()


def _claims(claims, path):
    return [c for c in claims if c.field_path == path and c.validator_verdict.value != "reject"]


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": None if p is None else round(p, 3),
            "recall": None if r is None else round(r, 3), "f1": None if f is None else round(f, 3)}


def strata():
    """patient -> (stratum, corpus).  Strata follow services/synth_eval: eval (polish_val + 20 synth_v3), ext, polish90."""
    from services import synth_eval as se
    out = {}
    for which in ("eval", "ext", "polish90"):
        for name, pids in se.eval_patients(which=which).items():
            label = {"polish_val": "polish_val (10, held out from the adapter)", "synth_v3": "synth_v3 eval (20)",
                     "polish_train": "polish90 (90; the adapter was trained on these)"}[name]
            if which == "ext":
                label = "synth_v3 ext (80; not looked at while the v0.4/v0.5 rules were written)"
            for p in pids:
                out.setdefault(p, (label, se.STRATA_CORPUS[name]))
    return out


def synthetic(limit: int = 0):
    from services import synth_eval as se
    from services.leo_runtime import LeoRuntime
    rt = LeoRuntime(backend=None, use_llm=False)
    pats = strata()
    items = sorted(pats.items())[:limit] if limit else sorted(pats.items())
    prior_s: dict[str, Counter] = {}
    reason_s: dict[str, Counter] = {}
    etio_s: dict[str, Counter] = {}
    fa_s: dict[str, Counter] = {}
    wrong = {"prior_fp": [], "prior_fn": [], "etiology_missed": []}
    for i, (pid, (label, corpus)) in enumerate(items, 1):
        plan = json.loads((REPO / "data" / "episynth_corpus" / PLAN_DIR[corpus] / "patients" / f"{pid}.json")
                          .read_text(encoding="utf-8"))
        ref = {a["field"]: a["value"] for a in plan.get("required_assertions", [])}
        vs = se.visits_of(corpus, pid)
        text = "\n\n".join(se.note_text(v) for v in vs)
        _, claims = rt.pipeline.extract(text, document_id=pid, doc_date="2024-01-01", return_claims=True)
        pr, ec = prior_s.setdefault(label, Counter()), etio_s.setdefault(label, Counter())
        rs, fa = reason_s.setdefault(label, Counter()), fa_s.setdefault(label, Counter())
        # --- stopped drugs ----------------------------------------------------------------
        if corpus == "synth_v3_polish":
            ref_prior = {str(x["generic_name"]).lower(): x.get("reason_discontinued") for x in ref.get("PRIOR_ASMS", [])}
            cur = {_name(c.value) for c in _claims(claims, "medication.current_asms")}
            pred = {}
            for c in _claims(claims, "medication.prior_asms") + _claims(claims, "medication.failed_asms"):
                v = c.value.model_dump() if hasattr(c.value, "model_dump") else c.value
                n = _name(v)
                st = str((v or {}).get("status") or "") if isinstance(v, dict) else ""
                kind = ("inefficacy" if c.field_path.endswith("failed_asms") or "fail" in st else
                        "intolerance" if "adverse" in st else "unspecified")
                if n and (n not in pred or kind != "unspecified"):
                    pred[n] = kind
            tp = len(set(ref_prior) & set(pred))
            pr["patients"] += 1
            pr["tp"] += tp
            pr["fp"] += len(set(pred) - set(ref_prior))
            pr["fn"] += len(set(ref_prior) - set(pred))
            pr["leaked_into_current"] += len(set(ref_prior) & cur)
            pr["patients_with_reference"] += bool(ref_prior)
            if set(pred) - set(ref_prior):
                wrong["prior_fp"].append({"patient": pid, "extra": sorted(set(pred) - set(ref_prior))})
            if set(ref_prior) - set(pred):
                wrong["prior_fn"].append({"patient": pid, "missed": sorted(set(ref_prior) - set(pred))})
            # reason class on drugs found by both
            for n in set(ref_prior) & set(pred):
                truth = "inefficacy" if ref_prior[n] == INEFFICACY else "intolerance"
                rs[(truth, pred[n])] += 1
            # failed-in-the-ILAE-sense: reference = inefficacy; prediction = failed bucket or inefficacy status
            rf = {n for n, r in ref_prior.items() if r == INEFFICACY}
            pf = {n for n, k in pred.items() if k == "inefficacy"}
            fa["tp"] += len(rf & pf)
            fa["fp"] += len(pf - rf)
            fa["fn"] += len(rf - pf)
        # --- etiology specifics -------------------------------------------------------------
        spec = ref.get("ETIOLOGY_SPECIFICS")
        if spec:
            want = {k: str(v).lower().replace("anti_", "") for k, v in spec.items() if v}
            got = []
            for c in _claims(claims, "clinical_seizure.etiology_specifics"):
                v = c.value.model_dump() if hasattr(c.value, "model_dump") else c.value
                if isinstance(v, dict):
                    got.append({k: str(x).lower().replace("anti_", "") for k, x in v.items() if x})
            ec["patients"] += 1
            for k, v in want.items():
                ok = any(g.get(k) == v for g in got)
                ec[f"{k}_ref"] += 1
                ec[f"{k}_right"] += ok
                if not ok:
                    wrong["etiology_missed"].append({"patient": pid, "field": k, "reference": v,
                                                     "rules": [g.get(k) for g in got] or None})
            ec["any_specifics_claim"] += bool(got)
        # false alarms: a gene/antibody claimed for a patient whose plan names none
        elif _claims(claims, "clinical_seizure.etiology_specifics"):
            ec["false_alarm_patients"] += 1
        else:
            ec["no_reference_no_claim"] += 1
        print(f"[{i}/{len(items)}] {pid}", flush=True)
    return prior_s, reason_s, fa_s, etio_s, wrong


def fs_gold(pids: list[str]):
    """Rescue, coarse EEG and etiology-cause presence on F-S letters."""
    from services.leo_runtime import LeoRuntime
    rt = LeoRuntime(backend=None, use_llm=False)
    resc, eeg, cause = Counter(), Counter(), Counter()
    detail = {"rescue_wrong": [], "eeg_wrong": []}
    for i, pid in enumerate(pids, 1):
        gold = json.loads((FS_GOLD_DIR / f"{pid}.json").read_text(encoding="utf-8"))
        text = (FS_TEXT_DIR / f"{pid}.txt").read_text(encoding="utf-8")
        _, claims = rt.pipeline.extract(text, document_id=pid, doc_date="2024-01-01", return_claims=True)
        # rescue
        ref = {re.sub(r"[^a-z]", "", str(e["attributes"].get("DrugName") or e["text"]).lower())
               for e in gold if e["entity"] == "Prescription" and e["attributes"].get("Frequency") == "As_Required"}
        pred = {re.sub(r"[^a-z]", "", _name(c.value)) for c in _claims(claims, "medication.rescue_medication")}
        resc["tp"] += len(ref & pred)
        resc["fp"] += len(pred - ref)
        resc["fn"] += len(ref - pred)
        if ref != pred:
            detail["rescue_wrong"].append({"letter": pid, "reference": sorted(ref), "rules": sorted(pred)})
        # coarse EEG result
        res = [e["attributes"].get("EEG_Results") for e in gold if e["entity"] == "Investigations"
               and e["attributes"].get("EEG_Performed") == "Yes" and e["attributes"].get("EEG_Results") in ("Normal", "Abnormal")]
        if res:
            truth = "Abnormal" if "Abnormal" in res else "Normal"
            ied = [c.value for c in _claims(claims, "eeg.ied_present")]
            bg = [str(getattr(c.value, "value", c.value)) for c in _claims(claims, "eeg.background")]
            if any(v is True for v in ied) or any(b and b != "normal" for b in bg):
                pred_e = "Abnormal"
            elif any(v is False for v in ied) or any(b == "normal" for b in bg):
                pred_e = "Normal"
            else:
                pred_e = "none"
            eeg[(truth, pred_e)] += 1
            if pred_e != truth:
                detail["eeg_wrong"].append({"letter": pid, "reference": truth, "rules": pred_e})
        # etiology cause present
        has = any(e["entity"] == "EpilepsyCause" for e in gold)
        got = bool(_claims(claims, "clinical_seizure.etiology_details_text"))
        cause[(has, got)] += 1
        print(f"[fs {i}/{len(pids)}] {pid}", flush=True)
    return resc, eeg, cause, detail


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="eval/results/leo_plan_phenotypes")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-fs", action="store_true")
    ap.add_argument("--skip-synth", action="store_true")
    args = ap.parse_args(argv)
    res: dict = {"system": "EpExtra specialist, no LLM"}
    md = ["# Specialist on phenotypes whose reference is in the generation plan or the F-S gold (no LLM)\n"]
    if not args.skip_synth:
        prior_s, reason_s, fa_s, etio_s, wrong = synthetic(args.limit)
        res["synthetic"] = {"stopped_drugs": {}, "reason_class": {}, "failed_inefficacy": {}, "etiology_specifics": {},
                            "wrong": wrong}
        md += ["## Synthetic: stopped (prior) drugs, polish patients only (the plan has PRIOR_ASMS only there)\n",
               "| stratum | patients (with reference) | precision | recall | F1 | stopped drug listed as current |", "|---|---|---|---|---|---|"]
        for lab, c in prior_s.items():
            if not c["patients"]:
                continue
            m = prf(c["tp"], c["fp"], c["fn"])
            res["synthetic"]["stopped_drugs"][lab] = {**m, "patients": c["patients"],
                                                       "patients_with_reference": c["patients_with_reference"],
                                                       "leaked_into_current": c["leaked_into_current"]}
            md.append(f"| {lab} | {c['patients']} ({c['patients_with_reference']}) | {m['precision']} | {m['recall']} | "
                      f"{m['f1']} | {c['leaked_into_current']} |")
        md += ["", "Precision counts a stopped drug the rules list but the plan does not as wrong; the generator may have "
               "mentioned such drugs in the notes without putting them in the plan, so precision is a lower bound.", "",
               "Reason class on drugs found by both (reference inefficacy / intolerance -> rules):"]
        for lab, c in reason_s.items():
            if c:
                tbl = {f"{a} -> {b}": n for (a, b), n in c.items()}
                res["synthetic"]["reason_class"][lab] = tbl
                md.append(f"- {lab}: {tbl}")
        md += ["", "Failed drugs in the ILAE sense (reference = stopped for inadequate seizure control; rules = failed bucket or "
               "inefficacy status):", "", "| stratum | precision | recall | F1 | tp / fp / fn |", "|---|---|---|---|---|"]
        for lab, c in fa_s.items():
            if c["tp"] + c["fp"] + c["fn"]:
                m = prf(c["tp"], c["fp"], c["fn"])
                res["synthetic"]["failed_inefficacy"][lab] = m
                md.append(f"| {lab} | {m['precision']} | {m['recall']} | {m['f1']} | {m['tp']} / {m['fp']} / {m['fn']} |")
        md += ["", "## Synthetic: etiology specifics (gene, variant, antibody)\n",
               "| stratum | patients with reference | gene right | variant right | antibody right | any claim | false alarms (patients with none in plan) |",
               "|---|---|---|---|---|---|---|"]
        for lab, c in etio_s.items():
            if not (c["patients"] or c["false_alarm_patients"]):
                continue
            res["synthetic"]["etiology_specifics"][lab] = dict(c)
            def r(k):
                return f"{c[k + '_right']}/{c[k + '_ref']}" if c[k + "_ref"] else "-"
            md.append(f"| {lab} | {c['patients']} | {r('causative_gene')} | {r('causative_variant')} | {r('causative_antibody')} | "
                      f"{c['any_specifics_claim']} | {c['false_alarm_patients']} |")
        md += ["", "The synthetic specifics are few (13 v3 and 14 polish patients); intervals are wide. "
               "The polish corpus is one the rules were developed against."]
    if not args.skip_fs:
        from scripts.score_leo_vs_fs_gold import HELD_OUT
        allp = sorted(p.stem for p in FS_GOLD_DIR.glob("EA*.json"))
        out_fs = {}
        for label, pids in (("held-out letters EA0161-EA0200 (40)", HELD_OUT), ("all 200 letters", allp)):
            resc, eeg, cause, detail = fs_gold(pids if not args.limit else pids[:args.limit])
            out_fs[label] = {"rescue": prf(resc["tp"], resc["fp"], resc["fn"]),
                             "eeg_confusion": {f"{a} -> {b}": n for (a, b), n in eeg.items()},
                             "eeg_n": sum(eeg.values()), "eeg_correct": sum(n for (a, b), n in eeg.items() if a == b),
                             "cause": {f"reference {a}, rules {b}": n for (a, b), n in cause.items()}, "wrong": detail}
        res["fs"] = out_fs
        md += ["", "## F-S letters\n", "| letters | rescue (tp/fp/fn) | rescue P / R | coarse EEG result right | EEG confusion | etiology cause present: reference vs rules |",
               "|---|---|---|---|---|---|"]
        for lab, v in out_fs.items():
            r = v["rescue"]
            md.append(f"| {lab} | {r['tp']}/{r['fp']}/{r['fn']} | {r['precision']} / {r['recall']} | "
                      f"{v['eeg_correct']}/{v['eeg_n']} | {v['eeg_confusion']} | {v['cause']} |")
        md += ["", "Rescue: reference = F-S prescriptions with Frequency As_Required (9 in 200 letters). Coarse EEG: reference = "
               "EEG_Results Normal or Abnormal where an EEG was performed; rules = abnormal if interictal epileptiform "
               "discharges or a non-normal background were found, normal if they were explicitly absent or the background was "
               "normal, otherwise none. This is a proxy: an abnormal EEG can show neither. Etiology cause: presence only."]
    path = REPO / f"{args.out}.json"
    path.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (REPO / f"{args.out}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
