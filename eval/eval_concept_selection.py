#!/usr/bin/env python3
"""Gate for Arm E: does picking from the top-5 beat lexical rank-1 on the mention gold?

CPU (default): lexical R@1 vs (a) gold-in-top-5 ceiling and (b) a token-overlap heuristic pick
among the top-5.  That is the room a selector has; it does not load the model.

GPU (``--mode gpu``): the real OntologySelector on fuzzy mentions (one batched call per letter).

    venv-medcat/bin/python eval/eval_concept_selection.py --offline
    venv-medcat/bin/python eval/eval_concept_selection.py --mode gpu --offline

Ship Arm E in the default path only if selected R@1 > lexical R@1 on scorable reachable mentions.  If the ceiling
(gold in top-5) is not above R@1, ranking — not the prompt — is the problem.  GPU 2026-10-06 first run: selected
0.335 vs lexical 0.555 (fail), but that run passed concatenated mentions instead of the letter text.  The GPU
path now uses the F-S letter.  App default remains exact hits only until a fair GPU run passes the gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from eval_concept_retrieval import GOLD_DIR, HELD_OUT, KS, SAB_TO_SYSTEM, crosswalk, load_gold  # noqa: E402
from services.onto_select import SELECT_K, snapshot  # noqa: E402

LETTER_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8381080" / "Gold1-200_corrected_spelling"
OUT_DEFAULT = "eval/results/concept_selection"


def _overlap(mention: str, label: str) -> float:
    a, b = set(re.findall(r"[a-z0-9]+", mention.lower())), set(re.findall(r"[a-z0-9]+", label.lower()))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--mode", choices=("cpu", "gpu"), default="cpu")
    args = ap.parse_args(argv)

    from services.ontology_candidates import OntologyCandidateService

    gold = load_gold()
    xw = crosswalk({g["cui"] for g in gold}, args.offline)
    svc = OntologyCandidateService()

    def is_hit(c, cui) -> bool:
        codes, names = xw.get(cui, (set(), set()))
        sys = getattr(c, "system", c.get("system") if isinstance(c, dict) else "")
        cid = getattr(c, "id", c.get("id") if isinstance(c, dict) else "")
        return (sys == "UMLS" and cid == cui) or (sys, cid) in codes

    selector = None
    if args.mode == "gpu":
        from services.leo_runtime import LeoRuntime
        from services.onto_select import OntologySelector
        rt = LeoRuntime.load(mode="gpu", arm="L1C", ext_reader=False, ontology_select=True)
        selector = OntologySelector(rt.backend)

    n = lex_hit = ceil_hit = ov_hit = sel_hit = fuzzy = exact_n = 0
    by_letter: dict[str, list] = defaultdict(list)
    for g in gold:
        by_letter[g["pid"]].append(g)

    for pid, rows in by_letter.items():
        pending = []
        local = []
        for g in rows:
            reachable = bool(xw.get(g["cui"], (set(),))[0])
            if not reachable:
                continue
            cands = svc.get_candidates(g["mention"], g["field_type"], k=10)[:SELECT_K]
            scorable = [c for c in cands if c.system in ("HPO", "SNOMED", "RxNorm", "UMLS")]
            n += 1
            if scorable and is_hit(scorable[0], g["cui"]):
                lex_hit += 1
            if any(is_hit(c, g["cui"]) for c in scorable):
                ceil_hit += 1
            if scorable:
                best = max(scorable, key=lambda c: _overlap(g["mention"], c.label))
                if is_hit(best, g["cui"]):
                    ov_hit += 1
            exact = bool(cands) and cands[0].rank_score >= 0.9 and not cands[0].is_obsolete
            if exact:
                exact_n += 1
                if is_hit(cands[0], g["cui"]):
                    sel_hit += 1
            else:
                fuzzy += 1
                local.append((g, snapshot(cands)))
                pending.append({"id": str(len(pending)), "mention": g["mention"],
                                "field_path": g["field_type"] or "", "candidates": snapshot(cands)})
        if selector and pending:
            letter = LETTER_DIR / f"{pid}.txt"
            ctx = letter.read_text(encoding="utf-8") if letter.exists() else " ".join(g["mention"] for g, _ in local)
            picks = selector(ctx, pending)
            for i, (g, _) in enumerate(local):
                r = picks.get(str(i))
                if r and r.picked and is_hit(r.picked, g["cui"]):
                    sel_hit += 1
        elif not selector:
            for g, snap in local:
                if not snap:
                    continue
                best = max(snap, key=lambda c: _overlap(g["mention"], c["label"]))
                dummy = type("C", (), best)()
                dummy.system, dummy.id = best["system"], best["id"]
                if is_hit(dummy, g["cui"]):
                    sel_hit += 1

    def rate(k):
        return round(k / n, 3) if n else None

    report = {
        "n_scorable_reachable": n, "lexical_r1": {"k": lex_hit, "rate": rate(lex_hit)},
        "gold_in_top5_ceiling": {"k": ceil_hit, "rate": rate(ceil_hit)},
        "overlap_heuristic_r1": {"k": ov_hit, "rate": rate(ov_hit)},
        "selector_or_heuristic_r1": {"k": sel_hit if args.mode == "gpu" else ov_hit,
                                     "rate": rate(sel_hit if args.mode == "gpu" else ov_hit)},
        "n_exact_lexical": exact_n, "n_fuzzy": fuzzy, "mode": args.mode, "k": SELECT_K,
        "gate": "selector_r1 > lexical_r1 (gpu) or overlap_heuristic > lexical_r1 (cpu)",
        "gate_pass": ((sel_hit if args.mode == "gpu" else ov_hit) > lex_hit) if n else False,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Path(str(out) + ".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = ["# Arm E selection vs lexical retrieval (mention gold)", "",
          f"Scorable reachable mentions: {n}. Mode: {args.mode}.", "",
          f"| method | hits | R@1 |", "|---|---:|---:|",
          f"| lexical rank-1 | {lex_hit} | {rate(lex_hit)} |",
          f"| gold in top-{SELECT_K} (ceiling) | {ceil_hit} | {rate(ceil_hit)} |",
          f"| {'Arm E selector' if args.mode == 'gpu' else 'token-overlap pick among top-' + str(SELECT_K) + ' (CPU stand-in)'} | {sel_hit if args.mode == 'gpu' else ov_hit} | {rate(sel_hit if args.mode == 'gpu' else ov_hit)} |",
          "", f"Gate (pick-from-list > lexical rank-1): **{'pass' if report['gate_pass'] else 'fail'}**.",
          "Ceiling 0.74 vs lexical 0.56 is the room Arm E has. The CPU heuristic is not the model; `--mode gpu` is the real gate.", ""]
    Path(str(out) + ".md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
