#!/usr/bin/env python3
"""Score --quote-entail on stored F-S L1C manifests and list research-extract misses.

No GPU. Default fusion is unchanged (quote_entail off). This writes a side-by-side
table and the Wittlinger-style list of accepted ∧ agree cells that miss gold.

    venv-medcat/bin/python scripts/score_leo_quote_entail_fs.py \\
        --llm L1C=data/run_manifests_fs_test_flat_c:L1C \\
        --out eval/results/leo_quote_entail_fs40
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from schema.claim import ReasonCode  # noqa: E402
from scripts import score_leo_vs_fs_gold as S  # noqa: E402
from scripts.score_llm_arms_vs_fs_gold import _load_fs_gold_for_doc  # noqa: E402
from services.quote_entail import quote_entails  # noqa: E402


def _pred_text(claim) -> Any:
    val = S._plain(claim.value)
    if isinstance(val, dict):
        if val.get("generic_name"):
            return S.canon_drug(str(val["generic_name"]))
        return {k: val.get(k) for k in ("period", "count_min", "count_max", "value")
                if val.get(k) is not None}
    return val


def _gold_text(fp: str, gold: dict) -> Any:
    if S._is_current_path(fp):
        return gold.get("current_asms") or []
    if fp == "clinical_seizure.epilepsy_type":
        return gold.get("epilepsy_type")
    if fp == "clinical_seizure.predominant_seizure_type":
        return gold.get("predominant_seizure_type")
    if fp == "clinical_seizure.age_at_onset_years":
        return gold.get("age_at_onset_years")
    if fp == "clinical_seizure.seizure_frequency":
        return {k: gold.get(k) for k in ("seizure_period", "seizure_count_min", "seizure_count_max")
                if gold.get(k) is not None}
    return None


def _is_research_extract(claim) -> bool:
    return (S.claim_category(claim) == "agree"
            and claim.validator_verdict.value == "accept")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", default="L1C=data/run_manifests_fs_test_flat_c:L1C")
    ap.add_argument("--out", default="eval/results/leo_quote_entail_fs40")
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

    label, mdir, arm = S.parse_llm(args.llm)
    reasoner = ManifestLLMReasoner([mdir], arm=arm)
    covered = [p for p in pids if reasoner.has(p)]

    base = ChainPipeline()
    base._lazy_init()
    cached = S._CachedAssembler(base._assembler)
    pipe0 = ChainPipeline(extractor=base._extractor, assembler=cached,
                          candidate_service=base._candidate_service, llm_reasoner=None)
    spec_pred = {
        p: S.native_from_claims(pipe0.extract(texts[p], document_id=p, return_claims=True)[1],
                                {"accept", "review"}, "epextra")
        for p in covered
    }

    def make_pipe(entail: bool):
        pipe = ChainPipeline(extractor=base._extractor, assembler=cached,
                             candidate_service=base._candidate_service, llm_reasoner=reasoner)
        pipe.cfg.ground_llm_values = True
        pipe.cfg.quote_entail = entail
        return pipe

    def score_arm(entail: bool):
        pipe = make_pipe(entail)
        per_doc = {s: [] for s in ("llm", "specialist", "leo_auto", "leo_review")}
        extract = Counter()
        misses = []
        n_accept = n_review = n_demoted = 0
        n_accept_correct_demoted = 0
        for pid in covered:
            _, claims = pipe.extract(texts[pid], document_id=pid, return_claims=True)
            llm_pheno = reasoner(texts[pid], pid, "2024-01-01")
            preds = {
                "llm": S.native_from_module_dicts(llm_pheno),
                "specialist": spec_pred[pid],
                "leo_auto": S.native_from_claims(claims, {"accept"}),
                "leo_review": S.native_from_claims(claims, {"accept", "review"}),
            }
            for s in per_doc:
                per_doc[s].append(S.score_doc(preds[s], gold[pid]))
            for c in claims:
                v = c.validator_verdict.value
                if v == "accept":
                    n_accept += 1
                elif v == "review":
                    n_review += 1
                if any(r.value == ReasonCode.QUOTE_NOT_ENTAILED.value for r in c.reason_codes):
                    n_demoted += 1
                    ok = S.claim_correct(c, gold[pid])
                    if ok is True:
                        n_accept_correct_demoted += 1
                ok = S.claim_correct(c, gold[pid])
                if ok is None:
                    continue
                if _is_research_extract(c):
                    extract["scored"] += 1
                    extract["ok"] += int(ok)
                    if not ok:
                        extract["miss"] += 1
                        entailed = quote_entails(
                            c.field_path or "", c.value, c.mention.text, texts[pid])
                        misses.append({
                            "pid": pid,
                            "field": c.field_path,
                            "pred": _pred_text(c),
                            "gold": _gold_text(c.field_path, gold[pid]),
                            "quote": (c.mention.text or "")[:240],
                            "quote_entails": entailed,
                            "reasons": [r.value for r in c.reason_codes],
                        })
        block = {}
        for s, rows in per_doc.items():
            p, r, f1 = S.micro(rows)
            block[s] = {"micro_p": p, "micro_r": r, "micro_f1": f1}
        ext_n, ext_ok = extract["scored"], extract["ok"]
        block["research_extract"] = {
            "scored": ext_n, "correct": ext_ok, "miss": extract["miss"],
            "precision": (ext_ok / ext_n) if ext_n else None,
        }
        block["routing"] = {"accept": n_accept, "review": n_review,
                            "quote_not_entailed": n_demoted,
                            "correct_cells_demoted": n_accept_correct_demoted}
        return block, misses

    off, misses_off = score_arm(False)
    on, misses_on = score_arm(True)

    # Decision: flip default only if auto-accept precision rises and research-extract
    # precision does not fall. Conservative: stay off if the CI is not computed here.
    p_off = off["leo_auto"]["micro_p"]
    p_on = on["leo_auto"]["micro_p"]
    re_off = off["research_extract"]["precision"]
    re_on = on["research_extract"]["precision"]
    flip = (p_on is not None and p_off is not None and p_on > p_off
            and (re_on or 0) >= (re_off or 0) - 1e-9)
    decision = (
        "KEEP default off"
        if not flip else
        "Precision rose; still keep default off until a letter-bootstrap CI excludes 0 "
        "(this script does not flip D22)."
    )

    report = {
        "arm": arm, "dir": str(mdir), "n_letters": len(covered),
        "quote_entail_off": off,
        "quote_entail_on": on,
        "research_extract_misses_default": misses_off,
        "research_extract_misses_entail_on": misses_on,
        "n_misses_default": len(misses_off),
        "n_misses_caught_by_entail_check": sum(1 for m in misses_off if not m["quote_entails"]),
        "decision": decision,
        "flip_default": False,
    }

    md = [
        "# Quote-entail rematch and research-extract misses (F-S 40, L1C, no GPU)\n",
        "Default fusion is unchanged (`quote_entail` off). "
        "This is a measurement of `--quote-entail` and the Wittlinger-style list of "
        "accepted ∧ agree cells that miss gold.\n",
        f"Letters: {len(covered)}. Arm {arm} from `{mdir}`.\n",
        "## Headline systems\n",
        "| setting | auto P | auto R | auto F1 | reviewed F1 | research extract |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, b in (("default (off)", off), ("--quote-entail", on)):
        re = b["research_extract"]
        md.append(
            f"| {name} | {b['leo_auto']['micro_p']:.3f} | {b['leo_auto']['micro_r']:.3f} | "
            f"{b['leo_auto']['micro_f1']:.3f} | {b['leo_review']['micro_f1']:.3f} | "
            f"{re['correct']}/{re['scored']} = {re['precision']:.3f} |"
        )
    md += [
        "",
        f"Routing with entail on: accept {on['routing']['accept']}, "
        f"review {on['routing']['review']}, demoted `quote_not_entailed` "
        f"{on['routing']['quote_not_entailed']} "
        f"(of which {on['routing']['correct_cells_demoted']} were gold-correct).\n",
        f"**Decision.** {decision} Default stays off (D22).\n",
        f"## Research-extract misses on the default chain (n={len(misses_off)})\n",
        "These are the cells in the research extract (accepted ∧ both readers) that "
        "do not match gold. `quote_entails` is the lexical check, run on the default "
        "accept (the flag is off, so they stayed accepted).\n",
        "| letter | field | pred | gold | quote entails? | quote |",
        "|---|---|---|---|---|---|",
    ]
    for m in misses_off:
        q = (m["quote"] or "").replace("|", "/").replace("\n", " ")
        md.append(
            f"| {m['pid']} | `{m['field']}` | {m['pred']} | {m['gold']} | "
            f"{'yes' if m['quote_entails'] else '**no**'} | {q} |"
        )
    md += [
        "",
        f"Of {len(misses_off)} misses, "
        f"{sum(1 for m in misses_off if not m['quote_entails'])} have a quote that "
        "does not entail the value. Those would have gone to review if the flag were on.",
        "",
        "Not a gold-error adjudication. Epilepsy-type gold `unknown` is a diagnosis-line "
        "convention. Wittlinger-style: these rows are the place a person would look first.",
    ]

    out = Path(args.out)
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    miss_path = out.parent / "leo_research_extract_misses_fs40"
    out.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    miss_path.with_suffix(".json").write_text(
        json.dumps({"n": len(misses_off), "misses": misses_off}, indent=2, default=str),
        encoding="utf-8")
    start = next(i for i, line in enumerate(md) if line.startswith("## Research-extract misses"))
    miss_path.with_suffix(".md").write_text("\n".join(md[start:]), encoding="utf-8")
    print("wrote", out.with_suffix(".md"))
    print("wrote", miss_path.with_suffix(".md"))
    print("misses", len(misses_off), "caught_by_entail_check",
          sum(1 for m in misses_off if not m["quote_entails"]))
    print("decision:", decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
