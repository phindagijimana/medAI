#!/usr/bin/env python3
"""Where do wrong LEO claims come from on the synthetic notes?  (diagnostic, no GPU)

For every claim that has a gold reference and is wrong, report the detector category and, for
drug claims, whether the drug is in the patient's gold *prior* list (a stopped drug read as
current), so that the fix can target the real failure instead of guessing.

    venv-medcat/bin/python scripts/diag_synth_claim_errors.py \\
        armH=data/run_manifests_synth_eval_ft:FT L1C=data/run_manifests_synth_eval_flat:L1C
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import scripts.score_leo_vs_fs_gold as fs  # noqa: E402
import scripts.score_leo_vs_synth_gold as sg  # noqa: E402
from services import synth_eval  # noqa: E402


def prior_and_denied(corpus: str, patient: str) -> tuple[set[str], list[str]]:
    plan = REPO / "data" / "episynth_corpus" / synth_eval.CORPORA[corpus][1] / "patients" / f"{patient}.json"
    d = json.loads(plan.read_text(encoding="utf-8"))
    prior, denied = set(), []
    for a in d.get("required_assertions", []):
        if a["field"] == "PRIOR_ASMS":
            prior |= {fs.canon_drug(x["generic_name"]) for x in a["value"]}
        elif a["field"] == "DENIED_FINDINGS":
            denied += list(a["value"])
    return prior, denied


def main() -> int:
    from services.chain_llm import ManifestLLMReasoner
    from services.chain_pipeline import ChainPipeline

    fs.SEIZURE_FREE_AS_ZERO = True
    strata = synth_eval.eval_patients()
    corpus_of = {p: c for c, ps in (("synth_v3_polish", strata["polish_val"]),
                                    ("synth_v3", strata["synth_v3"])) for p in ps}
    gold = {p: sg.gold_for(c, p) for p, c in corpus_of.items()}
    extra = {p: prior_and_denied(c, p) for p, c in corpus_of.items()}
    visits = synth_eval.eval_visits(strata)

    base = ChainPipeline()
    base._lazy_init()
    for spec in sys.argv[1:]:
        label, mdir, arm = fs.parse_llm(spec)
        reasoner = ManifestLLMReasoner([mdir], arm=arm, doc_id_map=lambda d: f"synth-{d}")
        pipe = ChainPipeline(extractor=base._extractor, assembler=base._assembler,
                             candidate_service=base._candidate_service, llm_reasoner=reasoner)
        wrong: Counter = Counter()
        total: Counter = Counter()
        drug_wrong_reason: Counter = Counter()
        examples = defaultdict(list)
        for v in visits:
            if not reasoner.has(v):
                continue
            p = synth_eval.patient_of(v)
            _, claims = pipe.extract(synth_eval.note_text(v), document_id=v, return_claims=True)
            for c in claims:
                ok = fs.claim_correct(c, gold[p])
                if ok is None:
                    continue
                key = (fs.claim_category(c), (c.field_path or "").split(".")[-1])
                total[key] += 1
                if ok:
                    continue
                wrong[key] += 1
                if c.field_path == "medication.current_asms":
                    val = fs._plain(c.value) or {}
                    name = fs.canon_drug(str((val or {}).get("generic_name") or ""))
                    why = "stopped drug (gold prior)" if name in extra[p][0] else "not a gold drug"
                    drug_wrong_reason[(key[0], why)] += 1
                    if len(examples[why]) < 4:
                        examples[why].append((v, name))
        print(f"\n=== {label} ({arm}) wrong claims by (category, field): wrong / scored")
        for k in sorted(wrong, key=lambda k: -wrong[k]):
            print(f"  {k[0]:<16} {k[1]:<26} {wrong[k]:>4} / {total[k]:<4}")
        print("  drug claims, why wrong:", dict(drug_wrong_reason))
        for why, ex in examples.items():
            print(f"  e.g. {why}:", ex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
