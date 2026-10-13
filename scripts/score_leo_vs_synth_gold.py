#!/usr/bin/env python3
"""Score LEO (LLM + EpExtra + ontology) on the US-style synthetic evaluation notes, patient level.

Same four systems, seven fields, micro-F1, paired bootstrap, claim precision by agreement and
safety counters as ``scripts/score_leo_vs_fs_gold.py`` (whose primitives this imports), with
three differences that follow from the data (see ``services/synth_eval.py``):

* **Patient-level gold.**  ``targets/<patient>/target_phenotype.json`` describes the patient; each
  note shows part of it.  Every system's per-note predictions are therefore aggregated over the
  patient's notes (``current_asms`` = union; scalars = majority vote, ties to the later note;
  seizure frequency = majority vote over the whole (period, min, max) triple) and the patient is the
  unit of scoring and of bootstrap resampling.  The same aggregation is applied to every system.
* **Seizure-free is count 0.**  The gold writes "seizure-free" as count 0 with no period; a
  prediction with ``seizure_free=true`` and no counts reads as count 0 (``SEIZURE_FREE_AS_ZERO``);
  the period is then not scored.  This is applied to every system alike.
* **Strata.**  ``polish_val``: the 10 synth-v3-polish patients the adapter did not train on;
  ``synth_v3``: 20 patients of the separate synth-v3 generation run.  Results are reported for the
  pool and for each stratum.

Run (no GPU; needs medcat, hence venv-medcat)::

    venv-medcat/bin/python scripts/score_leo_vs_synth_gold.py \\
        --llm armH=data/run_manifests_synth_eval_ft:FT \\
        --llm L1C=data/run_manifests_synth_eval_flat:L1C \\
        --out eval/results/leo_vs_synth_gold
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import scripts.score_leo_vs_fs_gold as fs  # noqa: E402
from services import synth_eval  # noqa: E402

fs.SEIZURE_FREE_AS_ZERO = True
fs.RESCUE_AS_CURRENT = False      # synthetic gold lists the maintenance regimen only
SYSTEMS, FIELDS = fs.SYSTEMS, fs.FIELDS


SLICE_TAGS = {"prior_asms": "PRIOR_ASMS", "denied": "DENIED_FINDINGS",
              "hedged": "HEDGED_FINDINGS", "hypothetical": "HYPOTHETICAL_TRIGGERS"}


def plan_for(corpus: str, patient: str) -> Optional[dict]:
    """Generation plan of a patient (which distractor assertions the notes carry), or None."""
    p = REPO / "data" / "episynth_corpus" / synth_eval.CORPORA[corpus][1] / "patients" / f"{patient}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if "required_assertions" in d else None


def plan_tags(plan: Optional[dict]) -> dict:
    """{slice: True/False} and the stopped drugs the plan lists."""
    fields = {a.get("field"): a.get("value") for a in (plan or {}).get("required_assertions", [])}
    tags = {name: tag in fields for name, tag in SLICE_TAGS.items()}
    tags["any_distractor"] = any(tags.values())
    prior = [str(x.get("generic_name")) for x in (fields.get("PRIOR_ASMS") or []) if isinstance(x, dict)]
    return {"tags": tags, "prior_drugs": [fs.canon_drug(x) for x in prior if x]}


def gold_for(corpus: str, patient: str) -> dict:
    t = json.loads(synth_eval.target_path(corpus, patient).read_text(encoding="utf-8"))
    n = fs.native_from_module_dicts({"clinical_seizure": t["clinical_seizure"],
                                     "medication": t["medication"]})
    return {
        "current_asms": n["current_asms"],
        "seizure_period": n["seizure_frequency.period"],
        "seizure_count_min": n["seizure_frequency.count_min"],
        "seizure_count_max": n["seizure_frequency.count_max"],
        "epilepsy_type": n["epilepsy_type"],
        "predominant_seizure_type": n["predominant_seizure_type"],
        "age_at_onset_years": n["age_at_onset_years"],
    }


def _vote(values: list):
    """Most common non-null value; ties go to the later note."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    cnt = Counter(map(repr, vals))
    best = max(cnt.values())
    for v in reversed(vals):
        if cnt[repr(v)] == best:
            return v
    return None


def aggregate(preds: list[dict]) -> dict:
    """Patient prediction from per-note predictions given in visit order."""
    out: dict = {"current_asms": sorted({d for p in preds for d in p.get("current_asms") or []})}
    for k in ("epilepsy_type", "predominant_seizure_type", "seizure_onset_class", "age_at_onset_years"):
        out[k] = _vote([p.get(k) for p in preds])
    freq_keys = ("seizure_frequency.period", "seizure_frequency.count_min", "seizure_frequency.count_max")
    triples = [tuple(p.get(k) for k in freq_keys) for p in preds]
    best = _vote([t for t in triples if any(x is not None for x in t)])
    for k, v in zip(freq_keys, best or (None, None, None)):
        out[k] = v
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="append", required=True, help="label=manifest_dir:ARM (repeatable)")
    ap.add_argument("--out", default="eval/results/leo_vs_synth_gold")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--disagree-llm", default="")
    ap.add_argument("--no-ground", action="store_true")
    ap.add_argument("--slices", action="store_true",
                    help="also score subsets of patients whose notes carry stopped drugs, denied, hedged or "
                         "hypothetical statements (from the generation plan), and stopped-drug leakage")
    ap.add_argument("--rescue-as-current", action="store_true",
                    help="count rescue drugs as current ASMs (default here: maintenance only)")
    args = ap.parse_args(argv)
    fs.RESCUE_AS_CURRENT = bool(args.rescue_as_current)

    from services.chain_llm import ManifestLLMReasoner
    from services.chain_pipeline import ChainPipeline
    from services.ft_extract import is_degenerate

    strata = synth_eval.eval_patients()
    corpus_of_patient = {p: synth_eval.STRATA_CORPUS[st] for st, ps in strata.items() for p in ps}
    stratum_of = {p: s for s, ps in strata.items() for p in ps}
    visits = synth_eval.eval_visits(strata)
    patients = sorted(corpus_of_patient)
    gold = {p: gold_for(corpus_of_patient[p], p) for p in patients}
    texts = {v: synth_eval.note_text(v) for v in visits}
    by_patient = defaultdict(list)
    for v in visits:
        by_patient[synth_eval.patient_of(v)].append(v)

    base = ChainPipeline()
    base._lazy_init()
    cached = fs._CachedAssembler(base._assembler)
    pipe0 = ChainPipeline(extractor=base._extractor, assembler=cached,
                          candidate_service=base._candidate_service, llm_reasoner=None)
    spec_claims = {v: pipe0.extract(texts[v], document_id=v, return_claims=True)[1] for v in visits}

    plans = {p: plan_tags(plan_for(corpus_of_patient[p], p)) for p in patients}

    # claim_correct is looked up at module level inside the fs bootstrap helpers
    report: dict = {"strata": {k: v for k, v in strata.items()}, "rescue_as_current": fs.RESCUE_AS_CURRENT,
                    "sources": {}}
    for spec in args.llm:
        label, mdir, arm = fs.parse_llm(spec)
        reasoner = ManifestLLMReasoner([mdir], arm=arm, doc_id_map=lambda d: f"synth-{d}")
        covered = [v for v in visits if reasoner.has(v)]
        print(f"\n=== {label}: {arm} from {mdir} covers {len(covered)}/{len(visits)} notes ===", flush=True)
        if not covered:
            continue
        pipe = ChainPipeline(extractor=base._extractor, assembler=cached,
                             candidate_service=base._candidate_service, llm_reasoner=reasoner)
        pipe.cfg.ground_llm_values = not args.no_ground
        pipe.cfg.disagree_primary = {fs._CLAIM_PATH.get(f, f): "llm"
                                     for f in args.disagree_llm.split(",") if f}
        note_preds: dict[str, dict[str, dict]] = {}
        note_claims: dict[str, list] = {}
        note_stats: dict[str, Any] = {}
        n_valid = n_populated = 0
        for v in covered:
            stats, claims = pipe.extract(texts[v], document_id=v, return_claims=True)
            pheno = reasoner(texts[v], v, "2024-01-01")
            n_valid += pheno is not None
            n_populated += pheno is not None and not is_degenerate(pheno)
            note_preds[v] = {
                "llm": fs.native_from_module_dicts(pheno),
                "specialist": fs.native_from_claims(spec_claims[v], {"accept", "review"}, "epextra"),
                "leo_auto": fs.native_from_claims(claims, {"accept"}),
                "leo_review": fs.native_from_claims(claims, {"accept", "review"}),
            }
            note_claims[v], note_stats[v] = claims, stats

        covered_patients = [p for p in patients if any(v in note_preds for v in by_patient[p])]
        patient_pred = {
            p: {s: aggregate([note_preds[v][s] for v in by_patient[p] if v in note_preds])
                for s in SYSTEMS}
            for p in covered_patients}

        def block_for(subset: list[str]) -> dict:
            per_doc = {s: [fs.score_doc(patient_pred[p][s], gold[p]) for p in subset] for s in SYSTEMS}
            claims_all = [(synth_eval.patient_of(v), c) for p in subset for v in by_patient[p]
                          if v in note_claims for c in note_claims[v]]
            totals = Counter()
            for p in subset:
                for v in by_patient[p]:
                    if v in note_stats:
                        st = note_stats[v]
                        totals.update({
                            "claims": st.n_claims_emitted, "accept": st.n_accepted,
                            "review": st.n_review, "reject": st.n_rejected,
                            "llm_agree": st.n_llm_agree, "llm_disagree": st.n_llm_disagree,
                            "specialist_only": st.n_specialist_only, "llm_only": st.n_llm_only,
                            "llm_unsupported": st.n_llm_unsupported})
            pairs = [("leo_auto", "llm"), ("leo_review", "llm"), ("leo_review", "specialist"),
                     ("leo_auto", "specialist")]
            boot = fs.bootstrap(per_doc, pairs, n=args.bootstrap)
            blk: dict = {"arm": arm, "dir": str(mdir), "n_letters": len(subset),
                         "n_notes": sum(1 for p in subset for v in by_patient[p] if v in note_preds),
                         "n_llm_phenotype_valid": n_valid, "n_llm_phenotype_populated": n_populated,
                         "systems": {}}
            for s in SYSTEMS:
                p_, r_, f1_ = fs.micro(per_doc[s])
                blk["systems"][s] = {"micro_p": p_, "micro_r": r_, "micro_f1": f1_,
                                     "f1_ci": boot["f1_ci"][s], "per_field": fs.per_field(per_doc[s])}
            blk["paired_diff_micro_f1"] = boot["diff"]
            # Stopped-drug leakage: drugs the plan lists as prior that a system reports as current.
            prior_total = sum(len(plans[p]["prior_drugs"]) for p in subset)
            blk["prior_drugs_in_plan"] = prior_total
            for s_ in SYSTEMS:
                leaked = sum(len(set(plans[p]["prior_drugs"]) & set(patient_pred[p][s_]["current_asms"]))
                             for p in subset)
                blk["systems"][s_]["prior_leak"] = {"leaked": leaked, "prior_drugs": prior_total,
                                                    "rate": (leaked / prior_total) if prior_total else None}
            cat: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
            for p, c in claims_all:
                k = fs.claim_category(c)
                cat[k][2] += 1
                ok = fs.claim_correct(c, gold[p])
                if ok is not None:
                    cat[k][1] += 1
                    cat[k][0] += int(ok)
            blk["claim_precision_ci"] = fs.claim_bootstrap(claims_all, gold, n=args.bootstrap)
            blk["claim_precision_by_category"] = {
                k: {"correct": v[0], "scored": v[1], "total": v[2],
                    "precision": (v[0] / v[1]) if v[1] else None} for k, v in sorted(cat.items())}
            n_claims = totals["claims"]
            unmatched = totals["llm_only"] + totals["llm_unsupported"]
            grounded = sum(1 for _, c in claims_all if c.concept.system != "MEDAI-ENUM")
            blk["safety"] = {
                "claims": n_claims,
                "accept_rate": totals["accept"] / n_claims if n_claims else None,
                "review_rate": totals["review"] / n_claims if n_claims else None,
                "reject_rate": totals["reject"] / n_claims if n_claims else None,
                "ontology_grounded_rate": grounded / n_claims if n_claims else None,
                "llm_proposed_unmatched": unmatched, "llm_unsupported_quote": totals["llm_unsupported"],
                "llm_unsupported_rate_of_unmatched": totals["llm_unsupported"] / unmatched if unmatched else None,
                "counts": dict(totals)}
            return blk, per_doc

        groups = {"all": covered_patients}
        for sname, plist in strata.items():
            groups[sname] = [p for p in covered_patients if p in set(plist)]
        if args.slices:
            for name in list(SLICE_TAGS) + ["any_distractor"]:
                groups[f"slice:{name}"] = [p for p in covered_patients if plans[p]["tags"].get(name)]
            groups["slice:no_distractor"] = [p for p in covered_patients
                                             if plans[p]["tags"] and not plans[p]["tags"]["any_distractor"]]
        for gname, subset in groups.items():
            if len(subset) < 3:
                continue
            blk, per_doc = block_for(subset)
            key = label if gname == "all" else f"{label} [{gname}]"
            report["sources"][key] = blk
            print(f"\n--- {key}: {len(subset)} patients, {blk['n_notes']} notes ---")
            for s in SYSTEMS:
                b = blk["systems"][s]
                leak = b.get("prior_leak") or {}
                extra = (f"  stopped-drug leak {leak['leaked']}/{leak['prior_drugs']}"
                         if leak.get("prior_drugs") else "")
                print(f"{s:<12} P {b['micro_p']:.3f} R {b['micro_r']:.3f} F1 {b['micro_f1']:.3f} "
                      f"CI [{b['f1_ci'][0]:.3f}, {b['f1_ci'][1]:.3f}]{extra}")
            for k, d in blk["paired_diff_micro_f1"].items():
                print(f"  Δ {k:<22} {d['mean']:+.3f} CI [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]")
            print("  claim precision:", {k: (round(v['precision'], 3) if v['precision'] is not None else None,
                                             v['scored']) for k, v in blk["claim_precision_by_category"].items()})

    out = Path(args.out)
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    fs._write_md(report, out.with_suffix(".md"))
    md = out.with_suffix(".md")
    txt = md.read_text(encoding="utf-8")
    txt = txt.replace("# LEO vs Fonferko-Shadrach native gold", "# LEO vs synthetic US-style gold (patient level)", 1)
    txt = txt.replace("Generated by `scripts/score_leo_vs_fs_gold.py`.  Held-out letters EA0161-EA0200; "
                      "seven native-gold fields (see script docstring).",
                      "Generated by `scripts/score_leo_vs_synth_gold.py`.  Unit = patient (notes aggregated); "
                      f"{len(patients)} patients ({', '.join(f'{k} {len(v)}' for k, v in strata.items())}); seven fields.")
    txt = txt.replace("letters", "patients")
    md.write_text(txt, encoding="utf-8")
    print(f"\nwrote {out.with_suffix('.json')} and {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
