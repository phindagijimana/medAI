#!/usr/bin/env python3
"""Paper extras from existing F-S L1C manifests (no GPU).

One specialist pass yields:
  - paired bootstrap CIs on micro-precision (C1) and micro-recall (C3)
  - perfect-reviewer oracle on the same 40 held-out letters as the headline
  - cohort questions (onset median, polytherapy) on gold vs model vs LEO reviewed
  - research-extract row (= agree claims)

    venv-medcat/bin/python scripts/score_leo_paper_extras.py \\
        --llm L1C=data/run_manifests_fs_test_flat_c:L1C \\
        --out eval/results/leo_paper_extras_fs40
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
from scripts.score_leo_oracle_review import oracle  # noqa: E402
from scripts.score_llm_arms_vs_fs_gold import _load_fs_gold_for_doc  # noqa: E402

PAIRS = [("leo_auto", "llm"), ("leo_auto", "specialist"), ("leo_review", "llm"),
         ("leo_review", "specialist"), ("oracle_pick", "llm")]


def _fmt_ci(pair):
    return f"[{pair[0]:+.3f}, {pair[1]:+.3f}]" if pair[0] < 0 or pair[1] < 0 else f"[{pair[0]:.3f}, {pair[1]:.3f}]"


def _cohort(preds: dict, gold: dict) -> dict:
    """Onset median among letters that state an age; polytherapy = ≥2 current ASMs."""
    onsets_g, onsets_p = [], []
    poly_g = poly_p = n_poly = 0
    for pid, g in gold.items():
        pr = preds[pid]
        if g.get("age_at_onset_years") is not None:
            onsets_g.append(float(g["age_at_onset_years"]))
            v = pr.get("age_at_onset_years")
            if v is not None:
                try:
                    onsets_p.append(float(v))
                except (TypeError, ValueError):
                    pass
        g_as = list(g.get("current_asms") or [])
        p_as = list(pr.get("current_asms") or [])
        if g_as or p_as:
            n_poly += 1
            poly_g += int(len(g_as) >= 2)
            poly_p += int(len(p_as) >= 2)
    def med(xs):
        return None if not xs else statistics.median(xs)
    return {
        "onset_n_gold": len(onsets_g), "onset_median_gold": med(onsets_g),
        "onset_n_pred": len(onsets_p), "onset_median_pred": med(onsets_p),
        "poly_n": n_poly, "poly_gold": poly_g / n_poly if n_poly else None,
        "poly_pred": poly_p / n_poly if n_poly else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="append", required=True)
    ap.add_argument("--out", default="eval/results/leo_paper_extras_fs40")
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args()

    from services.chain_llm import ManifestLLMReasoner
    from services.chain_pipeline import ChainPipeline

    pids = S.HELD_OUT
    gold = {p: _load_fs_gold_for_doc(p) for p in pids}
    for g in gold.values():
        g["current_asms"] = [S.canon_drug(x) for x in g.get("current_asms") or []]
        st = g.get("predominant_seizure_type")
        g["predominant_seizure_type"] = S.GOLD_SEIZURE_TYPE_TO_ENUM.get(st, st)
    texts = {p: (S.FS_TEXT_DIR / f"{p}.txt").read_text(encoding="utf-8") for p in pids}

    base = ChainPipeline()
    base._lazy_init()
    cached = S._CachedAssembler(base._assembler)
    pipe0 = ChainPipeline(extractor=base._extractor, assembler=cached,
                          candidate_service=base._candidate_service, llm_reasoner=None)
    spec_pred = {p: S.native_from_claims(pipe0.extract(texts[p], document_id=p, return_claims=True)[1],
                                         {"accept", "review"}, "epextra") for p in pids}

    report = {"pids": pids, "sources": {}}
    md = ["# LEO paper extras (F-S held-out 40; no new GPU)\n",
          "Paired CIs use letter-level bootstrap, 2000 resamples, seed 0. "
          "Oracle = perfect reviewer who may only pick among values the two readers produced.\n"]

    for spec in args.llm:
        label, mdir, arm = S.parse_llm(spec)
        reasoner = ManifestLLMReasoner([mdir], arm=arm)
        pipe = ChainPipeline(extractor=base._extractor, assembler=cached,
                             candidate_service=base._candidate_service, llm_reasoner=reasoner)
        pipe.cfg.ground_llm_values = True
        covered = [p for p in pids if reasoner.has(p)]
        systems = ("llm", "specialist", "leo_auto", "leo_review", "oracle_pick")
        per_doc = {s: [] for s in systems}
        preds = {s: {} for s in systems}
        work_tot, flagged = Counter(), []
        agree = Counter()
        for pid in covered:
            _, claims = pipe.extract(texts[pid], document_id=pid, return_claims=True)
            llm_pred = S.native_from_module_dicts(reasoner(texts[pid], pid, "2024-01-01"))
            orc, work = oracle(claims, llm_pred, spec_pred[pid], gold[pid])
            work_tot.update(work)
            flagged.append(sum(1 for c in claims if c.validator_verdict.value == "review"))
            cur = {
                "llm": llm_pred,
                "specialist": spec_pred[pid],
                "leo_auto": S.native_from_claims(claims, {"accept"}),
                "leo_review": S.native_from_claims(claims, {"accept", "review"}),
                "oracle_pick": orc,
            }
            for s in systems:
                preds[s][pid] = cur[s]
                per_doc[s].append(S.score_doc(cur[s], gold[pid]))
            for c in claims:
                ok = S.claim_correct(c, gold[pid])
                if ok is None:
                    continue
                cat = S.claim_category(c)
                agree[f"{cat}_scored"] += 1
                agree[f"{cat}_ok"] += int(ok)
                if cat == "agree" and c.validator_verdict.value == "accept":
                    agree["extract_scored"] += 1
                    agree["extract_ok"] += int(ok)

        boot = S.bootstrap(per_doc, PAIRS, n=args.bootstrap)
        block = {"arm": arm, "n_letters": len(covered), "systems": {},
                 "paired_diff_micro_f1": boot["diff"],
                 "paired_diff_micro_p": boot["diff_p"],
                 "paired_diff_micro_r": boot["diff_r"]}
        for s in systems:
            p, r, f1 = S.micro(per_doc[s])
            block["systems"][s] = {
                "micro_p": p, "micro_r": r, "micro_f1": f1,
                "p_ci": boot["p_ci"][s], "r_ci": boot["r_ci"][s], "f1_ci": boot["f1_ci"][s],
            }
        fl = sorted(flagged)
        n_items = work_tot["fields_to_review"] + work_tot["drugs_to_review"]
        n_right = work_tot["field_shown_right"] + work_tot["drugs_shown_right"]
        block["workload"] = {
            "flagged_claims_per_letter_mean": round(statistics.mean(fl), 2) if fl else None,
            "flagged_claims_per_letter_median": statistics.median(fl) if fl else None,
            "items": n_items, "items_already_right_as_shown": n_right,
            "share_already_right": round(n_right / n_items, 3) if n_items else None,
        }
        block["cohort"] = {s: _cohort(preds[s], {k: gold[k] for k in covered}) for s in systems}
        ext_n, ext_ok = agree["extract_scored"], agree["extract_ok"]
        block["research_extract"] = {
            "definition": "accepted claims whose detectors are specialist+llm (agree)",
            "scored": ext_n, "correct": ext_ok,
            "precision": (ext_ok / ext_n) if ext_n else None,
        }
        report["sources"][label] = block

        md += [f"## {label} (arm {arm}, {len(covered)} letters)\n",
               "| system | P | R | F1 | P 95% CI | R 95% CI | F1 95% CI |",
               "|---|---:|---:|---:|---|---|---|"]
        for s in systems:
            b = block["systems"][s]
            md.append(f"| {s} | {b['micro_p']:.3f} | {b['micro_r']:.3f} | {b['micro_f1']:.3f} | "
                      f"{_fmt_ci(b['p_ci'])} | {_fmt_ci(b['r_ci'])} | {_fmt_ci(b['f1_ci'])} |")
        md += ["", "Paired differences (letter bootstrap):",
               "| contrast | ΔP | ΔR | ΔF1 |",
               "|---|---|---|---|"]
        for k in block["paired_diff_micro_f1"]:
            dp, dr, df = block["paired_diff_micro_p"][k], block["paired_diff_micro_r"][k], block["paired_diff_micro_f1"][k]
            md.append(f"| {k} | {dp['mean']:+.3f} {_fmt_ci(dp['ci'])} | {dr['mean']:+.3f} {_fmt_ci(dr['ci'])} | "
                      f"{df['mean']:+.3f} {_fmt_ci(df['ci'])} |")
        c1a, c1b = block["paired_diff_micro_p"]["leo_auto-llm"], block["paired_diff_micro_p"]["leo_auto-specialist"]
        c3 = block["paired_diff_micro_r"]["leo_review-specialist"]
        def supported(d):
            lo, hi = d["ci"]
            return "supported" if lo > 0 else "not confirmed (CI includes ≤0)"
        md += ["",
               f"**C1 (auto-accept precision > model and > rules):** leo_auto−llm ΔP {c1a['mean']:+.3f} {_fmt_ci(c1a['ci'])} → {supported(c1a)}; "
               f"leo_auto−specialist ΔP {c1b['mean']:+.3f} {_fmt_ci(c1b['ci'])} → {supported(c1b)}.",
               f"**C3 (reviewed recall > rules):** leo_review−specialist ΔR {c3['mean']:+.3f} {_fmt_ci(c3['ci'])} → {supported(c3)}.",
               f"**Oracle** F1 {block['systems']['oracle_pick']['micro_f1']:.3f}; vs model "
               f"{block['paired_diff_micro_f1']['oracle_pick-llm']['mean']:+.3f} "
               f"{_fmt_ci(block['paired_diff_micro_f1']['oracle_pick-llm']['ci'])}. "
               f"Flagged items already right as shown: {block['workload']['items_already_right_as_shown']} of "
               f"{block['workload']['items']} ({block['workload']['share_already_right']}).",
               f"**Research extract** (accepted ∧ agree): {ext_ok}/{ext_n} = "
               f"{block['research_extract']['precision']:.3f} (same band as C2 agree precision)." if ext_n else "",
               "", "Cohort on these 40 letters (not the old M1 200-letter demo):",
               "| source | onset n / median | polytherapy rate (≥2 current ASMs) |",
               "|---|---|---|"]
        for s in ("llm", "specialist", "leo_auto", "leo_review", "oracle_pick"):
            c = block["cohort"][s]
            md.append(f"| {s} | {c['onset_n_pred']} / {c['onset_median_pred']} | {c['poly_pred']} |")
        cg = block["cohort"]["llm"]
        md.append(f"| gold | {cg['onset_n_gold']} / {cg['onset_median_gold']} | {cg['poly_gold']} |")
        md.append("")

    out = Path(args.out)
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print("wrote", out.with_suffix(".json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
