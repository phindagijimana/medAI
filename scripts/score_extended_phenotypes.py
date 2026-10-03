#!/usr/bin/env python3
"""Score the specialist (rules, no LLM) on the extended synthetic set (v4_ext): EEG findings, semiology, focal
onset features, rescue drugs and surgery history.

Reference = the plan (`data/episynth_corpus/v4_ext/patients/<pid>.json`, fields EEG_STUDY, SEMIOLOGY, FOCAL_ONSET,
RESCUE_MEDS, SURGERY_HISTORY; see scripts/synth_extended_plan.py).  Document = all of one patient's generated notes
joined (`data/eval_corpora/synth_v4_ext`).  Prediction = specialist claims.

Because the notes are written by an LLM from the plan, a short note type may leave a plan value out.  Every item
is therefore scored two ways: against the whole plan ("all") and only on items whose key words really appear in the
joined text ("in text").  The second is what the rules can be fairly held to.

    venv-medcat/bin/python scripts/score_extended_phenotypes.py   # -> eval/results/leo_extended_phenotypes.{json,md}

Synthetic LLM-written notes only; these figures say nothing about real clinic notes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PLAN_DIR = REPO / "data" / "episynth_corpus" / "v4_ext" / "patients"
CORPUS = REPO / "data" / "eval_corpora" / "synth_v4_ext"

STUDY_STEM = {"routine_eeg": "routine", "prolonged_eeg": "prolong|long.term|ltm|24.hour|48.hour|72.hour",
              "ambulatory_eeg": "ambulatory", "video_eeg_monitoring": "video|emu|monitoring"}
MOTOR_STEM = {"automatisms": "automat", "clonic jerking": "clonic|jerk", "tonic posturing": "tonic|postur|stiffen",
              "versive head turning": "versive|head turn|version", "epileptic spasms": "spasm",
              "hyperkinetic movements": "hyperkinetic"}
NONMOTOR_STEM = {"behavior arrest": "arrest|staring|stare", "autonomic": "autonomic", "cognitive": "cognitive",
                 "emotional": "emotional|fear", "sensory": "sensory|tingl"}
AURA_STEM = {"epigastric rising sensation": "epigastric|rising", "deja vu": "d[eé]j[aà]", "fear": "fear",
             "visual phenomena": "visual", "olfactory (burning smell)": "olfactory|smell|burning",
             "tingling of the hand": "tingl|paresthes"}
SURG_STEM = {"anterior temporal lobectomy": "lobectomy|temporal resection",
             "laser interstitial thermal therapy": "laser|litt|thermal",
             "lesionectomy": "lesionectomy|resection", "vagus nerve stimulator implantation": "vagus|vns",
             "responsive neurostimulation implantation": "responsive|rns|neuropace"}
RESCUE_STEM = {"diazepam": "diazepam|diastat", "midazolam": "midazolam|nayzilam", "lorazepam": "lorazepam|ativan",
               "clonazepam": "clonazepam|klonopin"}


def has(text: str, stem: str) -> bool:
    return re.search(stem, text, re.I) is not None


def canon(value, table: dict[str, str]):
    """Map a rules value to a reference label by stem (first label whose stem is found)."""
    s = str(value or "").lower()
    for label, stem in table.items():
        if has(s, stem):
            return label
    return None


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    rd = lambda x: None if x is None else round(x, 3)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": rd(p), "recall": rd(r), "f1": rd(f)}


def dump(v):
    return v.model_dump() if hasattr(v, "model_dump") else v


def claims_of(claims, path):
    return [c for c in claims if c.field_path == path and c.validator_verdict.value != "reject"]


class Acc:
    """accuracy on reference items: answered / right, split into all vs in-text."""

    def __init__(self):
        self.n = Counter()

    def add(self, key, in_text, answered, right):
        for scope in ("all",) + (("in_text",) if in_text else ()):
            self.n[(key, scope, "n")] += 1
            self.n[(key, scope, "answered")] += int(answered)
            self.n[(key, scope, "right")] += int(right)

    def row(self, key, scope):
        n, a, r = (self.n[(key, scope, k)] for k in ("n", "answered", "right"))
        return {"n": n, "answered": a, "right": r, "accuracy": round(r / n, 3) if n else None,
                "accuracy_when_answered": round(r / a, 3) if a else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/results/leo_extended_phenotypes")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from services.leo_runtime import LeoRuntime
    rt = LeoRuntime(backend=None, use_llm=False)

    rows = list(csv.DictReader((CORPUS / "manifest.csv").open(encoding="utf-8")))
    notes = defaultdict(list)
    for r in rows:
        notes[r["patient_id"]].append((CORPUS / r["note_path"]).read_text(encoding="utf-8"))
    pids = sorted(notes)[: args.limit or None]

    acc = Acc()
    rescue = {"all": Counter(), "in_text": Counter()}
    rescue_fa = Counter()
    rescue_fp_kind = Counter()
    surg = {"all": Counter(), "in_text": Counter()}
    surg_fa = Counter()
    sem_motor, sem_aura = Counter(), Counter()
    false_alarm = Counter()
    ex = defaultdict(list)

    for i, pid in enumerate(pids, 1):
        print(f"[{i}/{len(pids)}] {pid}", file=sys.stderr)
        plan = json.loads((PLAN_DIR / f"{pid}.json").read_text(encoding="utf-8"))
        ref = {a["field"]: a["value"] for a in plan["required_assertions"]}
        text = "\n\n".join(notes[pid])
        _, claims = rt.pipeline.extract(text, document_id=pid, doc_date="2024-01-01", return_claims=True)
        val = lambda path: [dump(c.value) for c in claims_of(claims, path)]

        # ---- EEG -------------------------------------------------------------------------
        e = ref.get("EEG_STUDY") or {}
        got = val("eeg.study_type")
        label = canon(got[0], STUDY_STEM) if got else None
        acc.add("eeg_study_type", has(text, STUDY_STEM[e["study_type"]]), bool(got), label == e["study_type"])
        if got and label != e["study_type"]:
            ex["study_type"].append((pid, e["study_type"], got[0]))

        bg = val("eeg.background")
        ref_bg = "normal" if e["background"] == "normal" else "slowing"
        got_bg = None
        if bg:
            s = str(bg[0]).lower()
            got_bg = "normal" if has(s, "normal") and not has(s, "slow") else ("slowing" if has(s, "slow") else None)
        bg_in_text = has(text, "normal background|background.*normal|normal.*background") if ref_bg == "normal" \
            else has(text, "slow")
        acc.add("eeg_background_normal_vs_slowing", bg_in_text, got_bg is not None, got_bg == ref_bg)

        ied_ref = e.get("ied_lobe") is not None
        ied_got = val("eeg.ied_present")
        ied_found = bool(ied_got) and ied_got[0] is True
        loc = [x for x in val("eeg.ied_findings") if isinstance(x, dict)]
        if ied_ref:
            in_text = has(text, e["ied_lobe"]) and has(text, "sharp|spike|epileptiform|discharge")
            acc.add("eeg_ied_found", in_text, True, ied_found)
            if ied_found and loc and e["ied_lobe"] != "generalized":
                lob = str(loc[0].get("localization") or "").lower()
                sd = str(loc[0].get("laterality") or "").lower()
                acc.add("eeg_ied_lobe", in_text, bool(lob), e["ied_lobe"] in lob)
                acc.add("eeg_ied_side", in_text and has(text, e["ied_laterality"]), bool(sd), e["ied_laterality"] in sd)
        elif ied_found:
            false_alarm["ied_reported_but_none"] += 1
            ex["ied_false_alarm"].append(pid)

        lobe, side = val("eeg.ictal_onset_lobe"), val("eeg.ictal_onset_laterality")
        if e.get("ictal_onset_lobe"):
            it = has(text, "onset") and has(text, e["ictal_onset_lobe"])
            acc.add("eeg_ictal_lobe", it, bool(lobe), bool(lobe) and e["ictal_onset_lobe"] in str(lobe[0]).lower())
            acc.add("eeg_ictal_side", it and has(text, e["ictal_onset_laterality"]), bool(side),
                    bool(side) and e["ictal_onset_laterality"] in str(side[0]).lower())
        elif lobe or side:
            false_alarm["ictal_onset_reported_but_none"] += 1
            ex["ictal_false_alarm"].append((pid, e["study_type"], lobe[:1]))

        # ---- focal onset features -----------------------------------------------------------
        fo = ref.get("FOCAL_ONSET")
        for kind, path, table in (("motor", "clinical_seizure.focal_motor_onset", MOTOR_STEM),
                                  ("nonmotor", "clinical_seizure.focal_nonmotor_onset", NONMOTOR_STEM)):
            g = val(path)
            if fo and fo.get(kind):
                it = has(text, table[fo[kind]])
                lab = canon(g[0], table) if g else None
                acc.add(f"focal_{kind}_onset", it, bool(g), lab == fo[kind])
                if g and lab != fo[kind]:
                    ex[f"focal_{kind}"].append((pid, fo[kind], g[0]))
            elif g:
                # the plan leaves the onset field empty but may still describe the feature as semiology
                sem0 = ref.get("SEMIOLOGY") or {}
                support = " ".join([str(m) for m in sem0.get("motor_features", [])] + [str(sem0.get("aura") or "")])
                lab = canon(g[0], table)
                if lab and has(support, table[lab]) or (kind == "nonmotor" and lab == "emotional" and has(support, "fear")):
                    false_alarm[f"focal_{kind}_in_semiology_not_onset"] += 1
                else:
                    false_alarm[f"focal_{kind}_reported_but_unsupported"] += 1
                    ex[f"focal_{kind}_false_alarm"].append((pid, g[0]))

        # ---- semiology (lenient: reference feature mentioned in the semiology text) ------------
        sem = ref.get("SEMIOLOGY") or {}
        stext = " ".join(str(x) for x in val("clinical_seizure.semiology_text"))
        for m in sem.get("motor_features", []):
            stem = MOTOR_STEM.get(m)
            if not stem:
                continue
            sem_motor["all"] += 1
            if has(text, stem):
                sem_motor["in_text"] += 1
                sem_motor["found"] += has(stext, stem)
        if sem.get("aura"):
            sem_aura["all"] += 1
            if has(text, AURA_STEM[sem["aura"]]):
                sem_aura["in_text"] += 1
                sem_aura["found"] += has(stext, AURA_STEM[sem["aura"]])

        # ---- rescue ----------------------------------------------------------------------
        rr = [d["generic_name"] for d in ref.get("RESCUE_MEDS", [])]
        raw = [x.get("generic_name") if isinstance(x, dict) else x for x in val("medication.rescue_medication")]
        gr = {canon(n, RESCUE_STEM) or str(n).lower() for n in raw if n}
        for scope in ("all", "in_text"):
            for name in rr:
                if scope == "in_text" and not has(text, RESCUE_STEM[name]):
                    continue
                rescue[scope]["tp" if name in gr else "fn"] += 1
        for g in gr - set(rr):
            rescue["all"]["fp"] += 1
            rescue["in_text"]["fp"] += 1
            sents = [m.group(0) for m in re.finditer(r"[^.\n]*(?:%s)[^.\n]*" % RESCUE_STEM.get(g, re.escape(g)), text, re.I)]
            hyp = [bool(re.search(r"\bshould\b|\bif\b|\bin case\b|\bwhen\b.*cluster", t, re.I)) for t in sents]
            inp = [bool(re.search(r"EMU|inpatient|IV\b|protocol|admission|hospital", t, re.I)) for t in sents]
            kind = "hypothetical_instruction" if sents and all(hyp) else \
                   "inpatient_or_protocol_order" if sents and all(i or h for i, h in zip(inp, hyp)) else "other"
            rescue_fp_kind[kind] += 1
            ex["rescue_fp"].append((pid, g, rr, kind))
        if not rr:
            rescue_fa["patients_without_reference"] += 1
            rescue_fa["with_rescue_reported"] += int(bool(gr))

        # ---- surgery ---------------------------------------------------------------------
        sr = [d["procedure"] for d in ref.get("SURGERY_HISTORY", [])]
        gs_raw = val("medication.surgery_history")
        gs = {canon(json.dumps(x, default=str), SURG_STEM) for x in gs_raw}
        gs.discard(None)
        for scope in ("all", "in_text"):
            for p in sr:
                if scope == "in_text" and not has(text, SURG_STEM[p]):
                    continue
                surg[scope]["tp" if p in gs else "fn"] += 1
                if scope == "all" and p not in gs:
                    ex["surgery_missed"].append((pid, p, [str(x)[:80] for x in gs_raw]))
        for g in gs - set(sr):
            surg["all"]["fp"] += 1
            surg["in_text"]["fp"] += 1
            ex["surgery_fp"].append((pid, g, sr))
        if not sr:
            surg_fa["patients_without_reference"] += 1
            surg_fa["with_surgery_reported"] += int(bool(gs_raw))

    keys = sorted({k[0] for k in acc.n})
    res = {"patients": len(pids), "notes": sum(len(notes[p]) for p in pids),
           "accuracy": {k: {"all": acc.row(k, "all"), "in_text": acc.row(k, "in_text")} for k in keys},
           "false_alarms": dict(false_alarm),
           "semiology_motor_recall": dict(sem_motor), "semiology_aura_recall": dict(sem_aura),
           "rescue": {s: prf(rescue[s]["tp"], rescue[s]["fp"], rescue[s]["fn"]) for s in rescue},
           "rescue_false_alarm_patients": dict(rescue_fa),
           "rescue_false_positive_context": dict(rescue_fp_kind),
           "surgery": {s: prf(surg[s]["tp"], surg[s]["fp"], surg[s]["fn"]) for s in surg},
           "surgery_false_alarm_patients": dict(surg_fa),
           "examples": {k: v[:12] for k, v in ex.items()}}
    path = REPO / f"{args.out}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    md = [f"# Specialist on the extended synthetic set (v4_ext; {res['patients']} patients, {res['notes']} notes joined "
          f"per patient; no LLM)\n",
          "Reference = plan. \"in text\" = only items whose key words appear in the generated text.\n",
          "| item | n (all) | answered | right | accuracy (all) | when answered | n (in text) | right (in text) | "
          "accuracy (in text) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k in keys:
        a, t = res["accuracy"][k]["all"], res["accuracy"][k]["in_text"]
        md.append(f"| {k} | {a['n']} | {a['answered']} | {a['right']} | {a['accuracy']} | {a['accuracy_when_answered']} | "
                  f"{t['n']} | {t['right']} | {t['accuracy']} |")
    md += ["", f"Rules gave a value where the plan has none: {res['false_alarms']}", "",
           f"Semiology motor features found in the semiology text: {sem_motor['found']} of {sem_motor['in_text']} in text "
           f"({sem_motor['all']} in plan); aura: {sem_aura['found']} of {sem_aura['in_text']} in text "
           f"({sem_aura['all']} in plan). Lenient key-word match.", "",
           "| list | scope | tp / fp / fn | precision | recall | F1 |", "|---|---|---|---|---|---|"]
    for name in ("rescue", "surgery"):
        for s, v in res[name].items():
            md.append(f"| {name} | {s} | {v['tp']} / {v['fp']} / {v['fn']} | {v['precision']} | {v['recall']} | {v['f1']} |")
    md += ["", f"Rescue false positives by what the sentence says: {dict(rescue_fp_kind)} (hypothetical_instruction = "
           "\"should he have a cluster, use nasal midazolam\", written from the plan's hypothetical triggers; "
           "inpatient_or_protocol_order = an EMU / hospital PRN order)."]
    md += ["", f"Patients with no reference rescue drug: {dict(rescue_fa)}; no reference surgery: {dict(surg_fa)}."]
    (REPO / f"{args.out}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
