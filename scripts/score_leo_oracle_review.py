#!/usr/bin/env python3
"""Upper bound for LEO after review, and the review workload.  F-S letters; no GPU.

``score_leo_vs_fs_gold.py`` scores ``leo_review`` as the DRAFT a reviewer is shown (accepted and flagged values,
one value per field, nobody has corrected anything).  This script adds a perfect-reviewer oracle, so the draft can
be compared with the model's final answer:

    leo_auto      accepted values only (nothing reviewed)
    leo_review    the draft (as in the other scorer)
    oracle_pick   a PERFECT reviewer who can only choose among what the readers produced:
                  - accepted values stay as they are (they are not reviewed, so accepted errors remain);
                  - for a scalar field with no accepted value but a flagged one, the reviewer picks whichever of
                    the three candidates (LEO's shown value, the model's value, the rules' value) matches the
                    reference, else leaves the field empty;
                  - each flagged drug is kept if the reference lists it, else dropped;
                  - values neither reader produced stay missing (adding values is the deferred reviewer-added
                    value feature).
    llm           the model alone, for comparison.

Candidates are the readers' own predictions, not the claim's ``alternative`` string, and a candidate the model
produced but fusion rejected (quote not found) is not excluded, so the bound is slightly generous.

Also reports the workload: flagged claims per letter, fields to look at, and how many flagged values were
already right as shown.

    venv-medcat/bin/python scripts/score_leo_oracle_review.py \
        --llm H2=data/run_manifests_fs_stress_h2:L0C --pids EA0001,... --out eval/results/leo_oracle_review
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts import score_leo_vs_fs_gold as S  # noqa: E402
from scripts.score_llm_arms_vs_fs_gold import _load_fs_gold_for_doc  # noqa: E402

SCALARS = {
    "epilepsy_type": ("epilepsy_type",),
    "predominant_seizure_type": ("predominant_seizure_type",),
    "age_at_onset_years": ("age_at_onset_years",),
    "seizure_frequency": ("seizure_frequency.period", "seizure_frequency.count_min", "seizure_frequency.count_max"),
}
CLAIM_PATH = {
    "epilepsy_type": "clinical_seizure.epilepsy_type",
    "predominant_seizure_type": "clinical_seizure.predominant_seizure_type",
    "age_at_onset_years": "clinical_seizure.age_at_onset_years",
    "seizure_frequency": "clinical_seizure.seizure_frequency",
}


def _group_score(pred: dict, gold: dict, keys) -> tuple[int, int]:
    sc = S.score_doc(pred, gold)
    tp = sum(sc[k][0] for k in keys if k in sc)
    fp = sum(sc[k][1] for k in keys if k in sc)
    return tp, fp


def oracle(claims, llm_pred: dict, spec_pred: dict, gold: dict) -> tuple[dict, dict]:
    """Return (oracle prediction, workload counters) for one letter."""
    acc = S.native_from_claims(claims, {"accept"})
    rev = S.native_from_claims(claims, {"accept", "review"})
    out = dict(acc)
    work = Counter()
    # --- scalar groups
    for name, keys in SCALARS.items():
        path = CLAIM_PATH[name]
        accepted = any(c.field_path == path and c.validator_verdict.value == "accept" for c in claims)
        flagged = any(c.field_path == path and c.validator_verdict.value == "review" for c in claims)
        if accepted or not flagged:
            continue
        work["fields_to_review"] += 1
        cands = [{k: rev.get(k) for k in keys}, {k: llm_pred.get(k) for k in keys}, {k: spec_pred.get(k) for k in keys}]
        shown_tp, shown_fp = _group_score({**out, **cands[0]}, gold, keys)
        work["field_shown_right"] += int(shown_tp > 0 and shown_fp == 0)
        best, best_key = {k: None for k in keys}, (0, 0)
        for cand in cands:
            if all(v is None for v in cand.values()):
                continue
            tp, fp = _group_score({**out, **cand}, gold, keys)
            if (tp - fp, tp) > best_key:
                best, best_key = cand, (tp - fp, tp)
        out.update(best)                      # an empty candidate (all wrong) leaves the field empty
    # --- drugs: flagged ones kept only if the reference lists them
    gold_drugs = Counter(gold.get("current_asms") or [])
    kept = list(acc["current_asms"])
    acc_drugs = Counter(acc["current_asms"])
    flagged_drugs = Counter(rev["current_asms"]) - acc_drugs
    n_flagged = sum(flagged_drugs.values())
    work["drugs_to_review"] += n_flagged
    for d, n in flagged_drugs.items():
        ok = min(n, max(0, gold_drugs[d] - acc_drugs[d]))
        work["drugs_shown_right"] += ok
        kept += [d] * ok
    out["current_asms"] = kept
    return out, work


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="append", required=True)
    ap.add_argument("--pids", default="")
    ap.add_argument("--out", default="eval/results/leo_oracle_review")
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args()

    from services.chain_llm import ManifestLLMReasoner
    from services.chain_pipeline import ChainPipeline

    pids = [p for p in args.pids.split(",") if p] or S.HELD_OUT
    gold = {p: _load_fs_gold_for_doc(p) for p in pids}
    for g in gold.values():
        g["current_asms"] = [S.canon_drug(x) for x in g.get("current_asms") or []]
        st = g.get("predominant_seizure_type")
        g["predominant_seizure_type"] = S.GOLD_SEIZURE_TYPE_TO_ENUM.get(st, st)
    texts = {p: (S.FS_TEXT_DIR / f"{p}.txt").read_text(encoding="utf-8") for p in pids}

    base = ChainPipeline()
    base._lazy_init()
    cached = S._CachedAssembler(base._assembler)
    pipe0 = ChainPipeline(extractor=base._extractor, assembler=cached, candidate_service=base._candidate_service,
                          llm_reasoner=None)
    spec_claims = {p: pipe0.extract(texts[p], document_id=p, return_claims=True)[1] for p in pids}
    spec_pred = {p: S.native_from_claims(spec_claims[p], {"accept", "review"}, "epextra") for p in pids}

    report = {"pids": pids, "sources": {}}
    for spec in args.llm:
        label, mdir, arm = S.parse_llm(spec)
        reasoner = ManifestLLMReasoner([mdir], arm=arm)
        pipe = ChainPipeline(extractor=base._extractor, assembler=cached, candidate_service=base._candidate_service,
                             llm_reasoner=reasoner)
        pipe.cfg.ground_llm_values = True
        covered = [p for p in pids if reasoner.has(p)]
        systems = ("llm", "leo_auto", "leo_review", "oracle_pick")
        per_doc = {s: [] for s in systems}
        work_tot, flagged_per_letter = Counter(), []
        for pid in covered:
            _, claims = pipe.extract(texts[pid], document_id=pid, return_claims=True)
            llm_pred = S.native_from_module_dicts(reasoner(texts[pid], pid, "2024-01-01"))
            orc, work = oracle(claims, llm_pred, spec_pred[pid], gold[pid])
            preds = {"llm": llm_pred, "leo_auto": S.native_from_claims(claims, {"accept"}),
                     "leo_review": S.native_from_claims(claims, {"accept", "review"}), "oracle_pick": orc}
            for s in systems:
                per_doc[s].append(S.score_doc(preds[s], gold[pid]))
            work_tot.update(work)
            flagged_per_letter.append(sum(1 for c in claims if c.validator_verdict.value == "review"))
        boot = S.bootstrap(per_doc, [("oracle_pick", "llm"), ("oracle_pick", "leo_review"), ("oracle_pick", "leo_auto")],
                           n=args.bootstrap)
        block = {"arm": arm, "n_letters": len(covered), "systems": {}}
        for s in systems:
            p, r, f1 = S.micro(per_doc[s])
            block["systems"][s] = {"micro_p": p, "micro_r": r, "micro_f1": f1, "f1_ci": boot["f1_ci"][s]}
        block["paired_diff_micro_f1"] = boot["diff"]
        fl = sorted(flagged_per_letter)
        n_items = work_tot["fields_to_review"] + work_tot["drugs_to_review"]
        n_right = work_tot["field_shown_right"] + work_tot["drugs_shown_right"]
        block["workload"] = {
            "flagged_claims_per_letter_mean": round(statistics.mean(fl), 2),
            "flagged_claims_per_letter_median": statistics.median(fl),
            "flagged_claims_per_letter_p90": fl[int(0.9 * (len(fl) - 1))],
            "fields_to_review": work_tot["fields_to_review"], "drugs_to_review": work_tot["drugs_to_review"],
            "items_already_right_as_shown": n_right, "items": n_items,
            "share_already_right": round(n_right / n_items, 3) if n_items else None,
        }
        report["sources"][label] = block
        print(f"\n=== {label} ({arm}) {len(covered)} letters ===")
        print(f"{'system':<12} {'P':>6} {'R':>6} {'F1':>6}   95% CI")
        for s in systems:
            b = block["systems"][s]
            print(f"{s:<12} {b['micro_p']:>6.3f} {b['micro_r']:>6.3f} {b['micro_f1']:>6.3f}   [{b['f1_ci'][0]:.3f}, {b['f1_ci'][1]:.3f}]")
        for k, d in block["paired_diff_micro_f1"].items():
            print(f"  diff {k:<24} {d['mean']:+.3f}  CI [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]")
        print("  workload:", block["workload"])

    out = Path(args.out)
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md = ["# Perfect-reviewer upper bound and review workload (F-S letters, specialist + model; no human reviewers)\n",
          "| model feeding LEO | letters | model alone F1 | leo_auto F1 | leo_review (draft) F1 | oracle_pick F1 | oracle - model alone | flagged claims per letter (mean / median / p90) | flagged items already right |",
          "|---|---|---|---|---|---|---|---|---|"]
    for label, b in report["sources"].items():
        sy, w = b["systems"], b["workload"]
        d = b["paired_diff_micro_f1"]["oracle_pick-llm"]
        md.append(f"| {label} | {b['n_letters']} | {sy['llm']['micro_f1']:.3f} | {sy['leo_auto']['micro_f1']:.3f} | "
                  f"{sy['leo_review']['micro_f1']:.3f} | {sy['oracle_pick']['micro_f1']:.3f} | {d['mean']:+.3f} "
                  f"[{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}] | {w['flagged_claims_per_letter_mean']} / "
                  f"{w['flagged_claims_per_letter_median']} / {w['flagged_claims_per_letter_p90']} | "
                  f"{w['items_already_right_as_shown']} of {w['items']} ({w['share_already_right']}) |")
    out.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\nwrote", out.with_suffix(".json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
