#!/usr/bin/env python3
"""Score LEO output (rules-only and LLM+rules) on the v4_ext synthetic set against the plan.

Standalone: it keeps the matching rules of scripts/score_extended_phenotypes.py (stem tables, `has`, `canon`, the
"in text" key-word tests, the scorer's conditions for the lobe/side items) by importing them, but reads LEO's per-note
raw claims (written by eval/leo_v4ext_run.py) instead of running the specialist on the patient's joined notes.

Aggregation per patient (the same for every arm): claims of all the patient's notes, rejected claims dropped.
  * scalar items (study type, background, ictal lobe/side, focal onset, IED lobe/side, epilepsy type, seizure type,
    onset age): the most frequent label over the claims, ties to the earlier note (accepted claims first);
  * "found" items (IED present) and lists (rescue, surgery, current ASMs): any claim / union.
Views of one arm: `all` = every non-rejected claim (what LEO shows a reviewer, "leo_review");
`accepted` = only claims whose verdict is accept ("leo_auto").  A note with no LLM reading (rules-only arm or a failed
LLM call) has every accept turned into review, as LEO itself does (single_reader).

Per item the outcome is one of: correct, wrong (answered, differs from the plan), missing (not answered although the
plan item's key words are in the notes), not_reported (not answered and the notes never state it).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import score_extended_phenotypes as S  # noqa: E402  (helpers only; main() is not run)

PLAN_DIR = S.PLAN_DIR
CORPUS = S.CORPUS
EP_MAP = {"combined_generalized_and_focal": "combined_focal_generalized"}
SZ_MAP = {"absence_typical": "generalized_absence_typical", "myoclonic": "generalized_myoclonic"}


def load_arm(prefix: str, force_single_reader: bool):
    raw = json.loads(Path(prefix + ".rawclaims.json").read_text())
    stats = json.loads(Path(prefix + ".stats.json").read_text())
    llm_note = {n["note_id"]: bool(n["llm_used"]) for n in stats["per_note"]}
    out = []                                         # (patient, note order, effective verdict, claim)
    for note_id, claims in raw.items():
        pid = note_id.split("_")[0]
        single = force_single_reader or not llm_note.get(note_id, False)
        for c in claims:
            v = c["verdict"]
            if single and v == "accept":
                v = "review"
            out.append((pid, note_id, v, c))
    out.sort(key=lambda t: (t[0], t[1]))
    return out, stats


def src_of(c):
    d = {("llm" if "llm" in x.lower() else "spec") for x in c["detectors"]}
    return "+".join(sorted(d, reverse=True)) or "none"           # llm / spec / spec+llm -> normalised below


def vote(labels):
    labels = [x for x in labels if x is not None]
    if not labels:
        return None
    c = Counter(labels)
    best = max(c.values())
    return next(x for x in labels if c[x] == best)


class Outcome:
    def __init__(self):
        self.n = defaultdict(Counter)          # item -> Counter(correct, wrong, missing, not_reported)
        self.spurious = Counter()              # item -> count (value where the plan has none)

    def add(self, item, in_text, answered, right):
        k = "correct" if answered and right else "wrong" if answered else ("missing" if in_text else "not_reported")
        self.n[item][k] += 1
        self.n[item]["n"] += 1


def claim_correct(path, v, plan):
    """True / False / None (not scorable) for one claim against the plan of its patient."""
    ref = plan["ref"]
    e = ref.get("EEG_STUDY") or {}
    fo = ref.get("FOCAL_ONSET")
    text = plan["text"]
    sem = ref.get("SEMIOLOGY") or {}
    if path == "eeg.study_type":
        return S.canon(v, S.STUDY_STEM) == e["study_type"]
    if path == "eeg.background":
        s = str(v).lower()
        g = "normal" if S.has(s, "normal") and not S.has(s, "slow") else ("slowing" if S.has(s, "slow") else None)
        return g == ("normal" if e["background"] == "normal" else "slowing")
    if path == "eeg.ied_present":
        return bool(v) == (e.get("ied_lobe") is not None)
    if path == "eeg.ied_findings":
        if e.get("ied_lobe") is None:
            return False
        if not isinstance(v, dict):
            return None
        lob, sd = str(v.get("localization") or "").lower(), str(v.get("laterality") or "").lower()
        if e["ied_lobe"] == "generalized":
            return "general" in lob or lob == ""
        return (e["ied_lobe"] in lob) and (not sd or e["ied_laterality"] in sd)
    if path in ("eeg.ictal_onset_lobe", "eeg.ictal_onset_laterality"):
        key = "ictal_onset_lobe" if path.endswith("lobe") else "ictal_onset_laterality"
        return bool(e.get(key)) and e[key] in str(v).lower()
    if path in ("clinical_seizure.focal_motor_onset", "clinical_seizure.focal_nonmotor_onset"):
        kind, table = ("motor", S.MOTOR_STEM) if "nonmotor" not in path else ("nonmotor", S.NONMOTOR_STEM)
        lab = S.canon(v, table)
        if fo and fo.get(kind):
            return lab == fo[kind]
        support = " ".join([str(m) for m in sem.get("motor_features", [])] + [str(sem.get("aura") or "")])
        if lab and (S.has(support, table[lab]) or (kind == "nonmotor" and lab == "emotional" and S.has(support, "fear"))):
            return None                      # plan lists it as semiology, not onset: not scorable as onset
        return False
    if path == "medication.rescue_medication":
        name = v.get("generic_name") if isinstance(v, dict) else v
        return (S.canon(name, S.RESCUE_STEM) or str(name).lower()) in {d["generic_name"] for d in ref.get("RESCUE_MEDS", [])}
    if path == "medication.surgery_history":
        return S.canon(json.dumps(v, default=str), S.SURG_STEM) in {d["procedure"] for d in ref.get("SURGERY_HISTORY", [])}
    if path == "clinical_seizure.epilepsy_type":
        return str(v) == EP_MAP.get(ref["EP_TYPE"], ref["EP_TYPE"])
    if path == "clinical_seizure.predominant_seizure_type":
        t = ref["SZ_TYPE"]
        if t.startswith("unknown_onset"):
            return None
        return str(v) == SZ_MAP.get(t, t)
    if path == "clinical_seizure.age_at_onset_years":
        try:
            return abs(float(v) - float(ref["AGE_AT_ONSET_YEARS"])) < 0.5
        except Exception:
            return False
    if path == "medication.current_asms":
        name = (v.get("generic_name") if isinstance(v, dict) else str(v)).lower()
        return name in {d["generic_name"].lower() for d in ref.get("CURRENT_ASMS", [])}
    return None


SCORED_PATHS = ["eeg.study_type", "eeg.background", "eeg.ied_present", "eeg.ied_findings", "eeg.ictal_onset_lobe",
                "eeg.ictal_onset_laterality", "clinical_seizure.focal_motor_onset", "clinical_seizure.focal_nonmotor_onset",
                "medication.rescue_medication", "medication.surgery_history", "clinical_seizure.epilepsy_type",
                "clinical_seizure.predominant_seizure_type", "clinical_seizure.age_at_onset_years",
                "medication.current_asms"]


def score_view(claims, plans, view):
    """claims: list of (pid, note, verdict, claim) of one arm; view 'all' or 'accepted'."""
    by = defaultdict(list)
    for pid, note, v, c in claims:
        if v == "reject":
            continue
        if view == "accepted" and v != "accept":
            continue
        if view == "crosschecked" and not (v == "accept" and "llm" in src_of(c) and "spec" in src_of(c)):
            continue                      # accepted AND both readers produced it
        if view == "model" and "llm" not in src_of(c):
            continue                      # whatever the model itself produced (any verdict but reject)
        by[pid].append((v, c))
    O = Outcome()
    rescue = {"all": Counter(), "in_text": Counter()}
    surg = {"all": Counter(), "in_text": Counter()}
    sem_motor, sem_aura = Counter(), Counter()
    asm = Counter()
    for pid, plan in plans.items():
        ref, text = plan["ref"], plan["text"]
        cl = sorted(by.get(pid, []), key=lambda t: 0 if t[0] == "accept" else 1)
        val = lambda path: [c["value"] for v, c in cl if c["field_path"] == path]
        e = ref["EEG_STUDY"]
        # study type
        labs = [S.canon(x, S.STUDY_STEM) for x in val("eeg.study_type")]
        lab = vote(labs) if labs else None
        O.add("eeg_study_type", S.has(text, S.STUDY_STEM[e["study_type"]]), bool(labs), lab == e["study_type"])
        # background
        bgl = []
        for x in val("eeg.background"):
            s = str(x).lower()
            bgl.append("normal" if S.has(s, "normal") and not S.has(s, "slow") else ("slowing" if S.has(s, "slow") else None))
        g = vote(bgl)
        ref_bg = "normal" if e["background"] == "normal" else "slowing"
        bg_in = S.has(text, "normal background|background.*normal|normal.*background") if ref_bg == "normal" else S.has(text, "slow")
        O.add("eeg_background_normal_vs_slowing", bg_in, g is not None, g == ref_bg)
        # IED
        ied_found = any(x is True for x in val("eeg.ied_present"))
        loc = [x for x in val("eeg.ied_findings") if isinstance(x, dict)]
        if e.get("ied_lobe") is not None:
            in_text = S.has(text, e["ied_lobe"]) and S.has(text, "sharp|spike|epileptiform|discharge")
            O.add("eeg_ied_found", in_text, ied_found, True)      # not found = missing (scorer: wrong)
            if ied_found and loc and e["ied_lobe"] != "generalized":
                lob = vote([str(x.get("localization") or "").lower() or None for x in loc]) or ""
                sd = vote([str(x.get("laterality") or "").lower() or None for x in loc]) or ""
                O.add("eeg_ied_lobe", in_text, bool(lob), e["ied_lobe"] in lob)
                O.add("eeg_ied_side", in_text and S.has(text, e["ied_laterality"]), bool(sd), e["ied_laterality"] in sd)
        elif ied_found:
            O.spurious["eeg_ied_reported_but_none"] += 1
        # ictal onset
        lobe = vote([str(x).lower() for x in val("eeg.ictal_onset_lobe")])
        side = vote([str(x).lower() for x in val("eeg.ictal_onset_laterality")])
        if e.get("ictal_onset_lobe"):
            it = S.has(text, "onset") and S.has(text, e["ictal_onset_lobe"])
            O.add("eeg_ictal_lobe", it, bool(lobe), bool(lobe) and e["ictal_onset_lobe"] in lobe)
            O.add("eeg_ictal_side", it and S.has(text, e["ictal_onset_laterality"]), bool(side),
                  bool(side) and e["ictal_onset_laterality"] in side)
        elif lobe or side:
            O.spurious["eeg_ictal_onset_reported_but_none"] += 1
        # focal onset
        fo = ref.get("FOCAL_ONSET")
        for kind, path, table in (("motor", "clinical_seizure.focal_motor_onset", S.MOTOR_STEM),
                                  ("nonmotor", "clinical_seizure.focal_nonmotor_onset", S.NONMOTOR_STEM)):
            gl = [S.canon(x, table) for x in val(path)]
            gv = val(path)
            if fo and fo.get(kind):
                lab = vote(gl) if gv else None
                O.add(f"focal_{kind}_onset", S.has(text, table[fo[kind]]), bool(gv), lab == fo[kind])
            elif gv:
                sem0 = ref.get("SEMIOLOGY") or {}
                support = " ".join([str(m) for m in sem0.get("motor_features", [])] + [str(sem0.get("aura") or "")])
                lab = vote(gl)
                if lab and S.has(support, table[lab]) or (kind == "nonmotor" and lab == "emotional" and S.has(support, "fear")):
                    O.spurious[f"focal_{kind}_in_semiology_not_onset (not an error)"] += 1
                else:
                    O.spurious[f"focal_{kind}_reported_but_unsupported"] += 1
        # semiology (lenient)
        sem = ref.get("SEMIOLOGY") or {}
        stext = " ".join(str(x) for x in val("clinical_seizure.semiology_text"))
        for m in sem.get("motor_features", []):
            stem = S.MOTOR_STEM.get(m)
            if stem:
                O.add("semiology_motor_feature_in_text", S.has(text, stem), S.has(stext, stem), True)
        if sem.get("aura"):
            O.add("semiology_aura_in_text", S.has(text, S.AURA_STEM[sem["aura"]]), S.has(stext, S.AURA_STEM[sem["aura"]]), True)
        # rescue
        rr = [d["generic_name"] for d in ref.get("RESCUE_MEDS", [])]
        raw = [x.get("generic_name") if isinstance(x, dict) else x for x in val("medication.rescue_medication")]
        gr = {S.canon(n, S.RESCUE_STEM) or str(n).lower() for n in raw if n}
        for scope in ("all", "in_text"):
            for name in rr:
                if scope == "in_text" and not S.has(text, S.RESCUE_STEM[name]):
                    continue
                rescue[scope]["tp" if name in gr else "fn"] += 1
        for _ in gr - set(rr):
            rescue["all"]["fp"] += 1
            rescue["in_text"]["fp"] += 1
        for name in rr:
            O.add("rescue_drug", S.has(text, S.RESCUE_STEM[name]), name in gr, True)
        # surgery
        sr = [d["procedure"] for d in ref.get("SURGERY_HISTORY", [])]
        gs = {S.canon(json.dumps(x, default=str), S.SURG_STEM) for x in val("medication.surgery_history")}
        gs.discard(None)
        for scope in ("all", "in_text"):
            for p in sr:
                if scope == "in_text" and not S.has(text, S.SURG_STEM[p]):
                    continue
                surg[scope]["tp" if p in gs else "fn"] += 1
        for _ in gs - set(sr):
            surg["all"]["fp"] += 1
            surg["in_text"]["fp"] += 1
        for p in sr:
            O.add("surgery_procedure", S.has(text, S.SURG_STEM[p]), p in gs, True)
        # core
        ept = [str(x) for x in val("clinical_seizure.epilepsy_type")]
        O.add("core_epilepsy_type", True, bool(ept), vote(ept) == EP_MAP.get(ref["EP_TYPE"], ref["EP_TYPE"]))
        szt = ref["SZ_TYPE"]
        if not szt.startswith("unknown_onset"):
            sz = [str(x) for x in val("clinical_seizure.predominant_seizure_type")]
            O.add("core_seizure_type", True, bool(sz), vote(sz) == SZ_MAP.get(szt, szt))
        ao = []
        for x in val("clinical_seizure.age_at_onset_years"):
            try:
                ao.append(round(float(x), 1))
            except Exception:
                pass
        O.add("core_age_at_onset", True, bool(ao), bool(ao) and abs(vote(ao) - float(ref["AGE_AT_ONSET_YEARS"])) < 0.5)
        ref_asm = {d["generic_name"].lower() for d in ref.get("CURRENT_ASMS", [])}
        got_asm = {(x.get("generic_name") if isinstance(x, dict) else str(x)).lower() for x in val("medication.current_asms")}
        asm["tp"] += len(ref_asm & got_asm)
        asm["fp"] += len(got_asm - ref_asm)
        asm["fn"] += len(ref_asm - got_asm)
    res = {"outcomes": {k: dict(v) for k, v in sorted(O.n.items())}, "spurious": dict(O.spurious),
           "rescue": {s: S.prf(rescue[s]["tp"], rescue[s]["fp"], rescue[s]["fn"]) for s in rescue},
           "surgery": {s: S.prf(surg[s]["tp"], surg[s]["fp"], surg[s]["fn"]) for s in surg},
           "current_asms_patient_union": S.prf(asm["tp"], asm["fp"], asm["fn"])}
    return res


def claim_stats(claims, plans):
    """Shares of verdicts and claim-level precision (per scored path), after the single-reader rule."""
    allv = Counter(v for _, _, v, _ in claims)
    scored_v = Counter()
    per = defaultdict(lambda: defaultdict(Counter))      # verdict[/source] -> path -> correct/wrong/unscorable
    uniq = defaultdict(set)
    for pid, note, v, c in claims:
        p = c["field_path"]
        if p not in SCORED_PATHS:
            continue
        scored_v[v] += 1
        sc = src_of(c)
        sc = "both" if ("llm" in sc and "spec" in sc) else ("model_only" if "llm" in sc else "specialist_only")
        for key in (v, f"{v}|{sc}"):
            ok0 = claim_correct(p, c["value"], plans[pid])
            per[key][p]["unscorable" if ok0 is None else ("correct" if ok0 else "wrong")] += 1
            if ok0 is not None:
                uniq[(key, p)].add((pid, json.dumps(c["value"], sort_keys=True, default=str), ok0))
    out = {"all_claims_by_verdict": dict(allv), "scored_path_claims_by_verdict": dict(scored_v), "claim_level": {}}
    for v in per:
        tot = Counter()
        rows = {}
        for p, cnt in per[v].items():
            rows[p] = dict(cnt)
            tot.update(cnt)
        u = Counter(ok for (vv, _), s in uniq.items() if vv == v for (_, _, ok) in s)
        out["claim_level"][v] = {
            "by_path": rows, "correct": tot["correct"], "wrong": tot["wrong"], "unscorable": tot["unscorable"],
            "precision": round(tot["correct"] / (tot["correct"] + tot["wrong"]), 3) if tot["correct"] + tot["wrong"] else None,
            "distinct_patient_path_value": {"correct": u[True], "wrong": u[False],
                                            "precision": round(u[True] / (u[True] + u[False]), 3) if u[True] + u[False] else None}}
    return out


ITEMS = [("core_epilepsy_type", "epilepsy type (core)"), ("core_seizure_type", "seizure type (core)"),
         ("core_age_at_onset", "age at onset (core)"),
         ("eeg_study_type", "EEG study type"), ("eeg_background_normal_vs_slowing", "EEG background"),
         ("eeg_ied_found", "interictal discharges found"), ("eeg_ied_lobe", "IED lobe"), ("eeg_ied_side", "IED side"),
         ("eeg_ictal_lobe", "ictal onset lobe"), ("eeg_ictal_side", "ictal onset side"),
         ("focal_motor_onset", "focal motor onset"), ("focal_nonmotor_onset", "focal non-motor onset"),
         ("semiology_motor_feature_in_text", "semiology: motor feature (lenient)"),
         ("semiology_aura_in_text", "semiology: aura (lenient)"),
         ("rescue_drug", "rescue drug"), ("surgery_procedure", "surgery procedure")]


def cell(o):
    if not o:
        return "-"
    g = lambda k: o.get(k, 0)
    return f"{g('correct')} / {g('wrong')} / {g('missing')} / {g('not_reported')}"


def tables(res):
    A = res["arms"]
    views = [("rules-only (all claims, all needs_review)", "rules_only", "all"),
             ("LEO+model, all claims (reviewer view)", "leo_llm", "all"),
             ("LEO+model, accepted claims only", "leo_llm", "accepted"),
             ("LEO+model, accepted AND both readers", "leo_llm", "crosschecked"),
             ("model's own claims only", "leo_llm", "model")]
    md = ["Per item: correct / wrong / missing / not_reported (n = plan items). Plan items scored as in "
          "scripts/score_extended_phenotypes.py; core items added.\n",
          "| item | n | " + " | ".join(v[0] for v in views) + " |", "|---|---|" + "---|" * len(views)]
    for key, label in ITEMS:
        n = A["rules_only"]["views"]["all"]["outcomes"].get(key, {}).get("n", "-")
        md.append(f"| {label} | {n} | " + " | ".join(cell(A[a]["views"][v]["outcomes"].get(key)) for _, a, v in views) + " |")
    md += ["", "Where the plan has no value but a value was reported (patients; ideal 0):", "",
           "| item | " + " | ".join(v[0] for v in views) + " |", "|---|" + "---|" * len(views)]
    keys = sorted({k for _, a, v in views for k in A[a]["views"][v]["spurious"]})
    for k in keys:
        md.append(f"| {k} | " + " | ".join(str(A[a]["views"][v]["spurious"].get(k, 0)) for _, a, v in views) + " |")
    md += ["", "Lists, tp / fp / fn (precision, recall):", "",
           "| list | " + " | ".join(v[0] for v in views) + " |", "|---|" + "---|" * len(views)]
    for nm, key in (("rescue drugs", "rescue"), ("surgery procedures", "surgery")):
        md.append(f"| {nm} | " + " | ".join(
            "{tp} / {fp} / {fn} ({precision}, {recall})".format(**A[a]["views"][v][key]["all"]) for _, a, v in views) + " |")
    md.append("| current ASMs (patient-level union) | " + " | ".join(
        "{tp} / {fp} / {fn} ({precision}, {recall})".format(**A[a]["views"][v]["current_asms_patient_union"]) for _, a, v in views) + " |")
    md += ["", "Claim level (scored field paths only; each claim judged against the plan of its patient):", "",
           "| arm | verdict / source | correct | wrong | not scorable | precision | distinct (patient, field, value) precision |",
           "|---|---|---|---|---|---|---|"]
    for a in ("rules_only", "leo_llm"):
        cl = A[a]["claim_stats"]["claim_level"]
        for k in sorted(cl):
            x = cl[k]
            md.append(f"| {a} | {k} | {x['correct']} | {x['wrong']} | {x['unscorable']} | {x['precision']} | "
                      f"{x['distinct_patient_path_value']['precision']} ({x['distinct_patient_path_value']['correct']}/"
                      f"{x['distinct_patient_path_value']['correct'] + x['distinct_patient_path_value']['wrong']}) |")
    md += ["", "Verdict shares (all claims, all field paths; reject = dropped):", ""]
    for a in ("rules_only", "leo_llm"):
        c = A[a]["claim_stats"]["all_claims_by_verdict"]
        t = sum(v for k, v in c.items() if k != "reject")
        md.append(f"- {a}: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())) +
                  f"; of {t} shown claims: " + ", ".join(f"{k} {100 * v / t:.1f}%" for k, v in sorted(c.items()) if k != "reject"))
        c = A[a]["claim_stats"]["scored_path_claims_by_verdict"]
        t = sum(v for k, v in c.items() if k != "reject")
        md.append(f"  - on the scored field paths: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())) +
                  f"; " + ", ".join(f"{k} {100 * v / t:.1f}%" for k, v in sorted(c.items()) if k != "reject"))
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", default="data/leo_runs/v4ext_rules")
    ap.add_argument("--llm", default="data/leo_runs/v4ext_llm")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import csv
    rows = list(csv.DictReader((CORPUS / "manifest.csv").open(encoding="utf-8")))
    notes = defaultdict(list)
    for r in rows:
        notes[r["patient_id"]].append((CORPUS / r["note_path"]).read_text(encoding="utf-8"))
    plans = {}
    for pid in sorted(notes):
        pl = json.loads((PLAN_DIR / f"{pid}.json").read_text())
        plans[pid] = {"ref": {x["field"]: x["value"] for x in pl["required_assertions"]}, "text": "\n\n".join(notes[pid])}

    result = {"patients": len(plans), "notes": sum(len(v) for v in notes.values()), "arms": {}}
    for name, prefix, force in (("rules_only", a.rules, True), ("leo_llm", a.llm, False)):
        if not Path(prefix + ".rawclaims.json").exists():
            continue
        claims, stats = load_arm(prefix, force)
        arm = {"stats": {k: v for k, v in stats.items() if k not in ("per_note", "gpu_samples")},
               "claim_stats": claim_stats(claims, plans), "views": {}}
        arm["views"]["all"] = score_view(claims, plans, "all")
        if name != "rules_only":
            arm["views"]["accepted"] = score_view(claims, plans, "accepted")
            arm["views"]["crosschecked"] = score_view(claims, plans, "crosschecked")
            arm["views"]["model"] = score_view(claims, plans, "model")
        pn = stats["per_note"]
        arm["timing"] = {"mean_s": round(sum(x["seconds"] for x in pn) / len(pn), 2), "max_s": max(x["seconds"] for x in pn),
                         "min_s": min(x["seconds"] for x in pn), "notes": len(pn),
                         "total_note_seconds": round(sum(x["seconds"] for x in pn), 1),
                         "errors": [{"note_id": x["note_id"], "error": x["error"]} for x in pn if x["error"]],
                         "llm_used_notes": sum(1 for x in pn if x["llm_used"])}
        result["arms"][name] = arm
    out = REPO / f"{a.out}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, default=str))
    (REPO / f"{a.out}.tables.md").write_text(tables(result))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
