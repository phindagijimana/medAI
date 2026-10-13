#!/usr/bin/env python3
"""Noisy-reviewer curve on stored F-S claims. CPU; no GPU; does not change extract.

oracle_pick (p=0) is the perfect reviewer in score_leo_oracle_review.py: may only choose
among values the two readers already produced. This script repeats that pick with a
reviewer who, independently on each flagged field/drug, chooses a *wrong* available
candidate with probability p. p=1 is a reviewer who never picks the gold-matching
reader when a wrong option exists.

Not a time-and-motion study. Not Loop A. Default D17 / quote-entail unchanged.

    venv-medcat/bin/python scripts/score_leo_noisy_review.py \\
        --llm L1C=data/run_manifests_fs_test_flat_c:L1C \\
        --out eval/results/leo_noisy_review_fs40
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts import score_leo_vs_fs_gold as S  # noqa: E402
from scripts.score_leo_oracle_review import (  # noqa: E402
    CLAIM_PATH, SCALARS, _group_score, oracle,
)
from scripts.score_llm_arms_vs_fs_gold import _load_fs_gold_for_doc  # noqa: E402

P_GRID = (0.0, 0.10, 0.25, 0.50, 1.0)


def _noisy(claims, llm_pred: dict, spec_pred: dict, gold: dict, rng: random.Random, p_err: float) -> dict:
    if p_err <= 0:
        out, _ = oracle(claims, llm_pred, spec_pred, gold)
        return out
    acc = S.native_from_claims(claims, {"accept"})
    rev = S.native_from_claims(claims, {"accept", "review"})
    out = dict(acc)
    for name, keys in SCALARS.items():
        path = CLAIM_PATH[name]
        accepted = any(c.field_path == path and c.validator_verdict.value == "accept" for c in claims)
        flagged = any(c.field_path == path and c.validator_verdict.value == "review" for c in claims)
        if accepted or not flagged:
            continue
        cands = [
            {k: rev.get(k) for k in keys},
            {k: llm_pred.get(k) for k in keys},
            {k: spec_pred.get(k) for k in keys},
        ]
        good, bad = [], []
        for cand in cands:
            if all(v is None for v in cand.values()):
                continue
            tp, fp = _group_score({**out, **cand}, gold, keys)
            (good if tp > 0 and fp == 0 else bad).append(cand)
        if rng.random() < p_err:
            out.update(bad[0] if bad else {k: None for k in keys})
        elif good:
            out.update(good[0])
    gold_drugs = __import__("collections").Counter(gold.get("current_asms") or [])
    kept = list(acc["current_asms"])
    acc_drugs = __import__("collections").Counter(acc["current_asms"])
    flagged_drugs = __import__("collections").Counter(rev["current_asms"]) - acc_drugs
    for d, n in flagged_drugs.items():
        in_gold = gold_drugs[d] > acc_drugs[d]
        keep = (not in_gold) if rng.random() < p_err else in_gold
        if keep:
            kept += [d] * n
    out["current_asms"] = kept
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="append", required=True)
    ap.add_argument("--pids", default="")
    ap.add_argument("--out", default="eval/results/leo_noisy_review")
    ap.add_argument("--seed", type=int, default=0)
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
    pipe0 = ChainPipeline(extractor=base._extractor, assembler=cached,
                          candidate_service=base._candidate_service, llm_reasoner=None)
    spec_claims = {p: pipe0.extract(texts[p], document_id=p, return_claims=True)[1] for p in pids}
    spec_pred = {p: S.native_from_claims(spec_claims[p], {"accept", "review"}, "epextra") for p in pids}

    report = {"pids": pids, "seed": args.seed, "p_grid": list(P_GRID), "sources": {},
              "note": "CPU curve. Not reviewer minutes. Do not retitle the paper on these F1s."}
    for spec in args.llm:
        label, mdir, arm = S.parse_llm(spec)
        reasoner = ManifestLLMReasoner([mdir], arm=arm)
        pipe = ChainPipeline(extractor=base._extractor, assembler=cached,
                             candidate_service=base._candidate_service, llm_reasoner=reasoner)
        pipe.cfg.ground_llm_values = True
        covered = [p for p in pids if reasoner.has(p)]
        extracted = {}
        for pid in covered:
            _, claims = pipe.extract(texts[pid], document_id=pid, return_claims=True)
            llm_pred = S.native_from_module_dicts(reasoner(texts[pid], pid, "2024-01-01"))
            extracted[pid] = (claims, llm_pred)
        rows = []
        for p_err in P_GRID:
            rng = random.Random(args.seed)
            per_doc = []
            for pid in covered:
                claims, llm_pred = extracted[pid]
                pred = _noisy(claims, llm_pred, spec_pred[pid], gold[pid], rng, p_err)
                per_doc.append(S.score_doc(pred, gold[pid]))
            pr, rc, f1 = S.micro(per_doc)
            rows.append({"p_error": p_err, "micro_p": pr, "micro_r": rc, "micro_f1": f1})
            print(f"{label} p={p_err:.2f}  P={pr:.3f} R={rc:.3f} F1={f1:.3f}")
        report["sources"][label] = {"arm": arm, "n_letters": len(covered), "curve": rows}

    out = Path(args.out)
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = [
        "# Noisy-reviewer curve (F-S letters; stored L1C; no GPU)\n",
        "A reviewer may only pick among values the two readers already produced. "
        "With probability *p* they pick a wrong available candidate. "
        "*p* = 0 is the oracle in `leo_oracle_review_fs40`. Not minutes. Not Loop A.\n",
        "| model | letters | p(error) | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, b in report["sources"].items():
        for row in b["curve"]:
            md.append(f"| {label} | {b['n_letters']} | {row['p_error']:.2f} | "
                      f"{row['micro_p']:.3f} | {row['micro_r']:.3f} | {row['micro_f1']:.3f} |")
    md.append("")
    out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print("wrote", out.with_suffix(".json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
