"""What has actually been measured for LEO, read from the result files at run time.

Nothing here is typed in by hand except the mapping from a catalogue phenotype to the scorer's field
names and the plain-language caveats.  Every number comes from a scorer output in ``eval/results``
(produced by ``scripts/score_leo_vs_fs_gold.py`` and ``scripts/score_leo_vs_synth_gold.py``), and the
file and system it came from are returned with it.  If a file is missing the phenotype is reported as
"no evidence file", never as a guess.

The numbers printed here come from the frozen L1C D17 files (``leo_vs_fs_gold_v08``,
``leo_vs_synth_gold_v07_maint``). Live runtime is ``leo-v0.9`` (unknown+silent REVIEW; cluster-if
not current). Headline extras stay frozen. A test checks that the files exist and that the arm is L1C.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

RESULTS = Path(__file__).resolve().parent.parent / "eval" / "results"

DATASETS: dict[str, dict[str, Any]] = {
    "fs": {
        "file": "leo_vs_fs_gold_v08.json", "source": "L1C",
        "label": "40 held-out clinic letters (Fonferko-Shadrach, UK style)",
        "unit": "letters", "text": "synthetic",
        "gold": "clinician-adjudicated annotations from the ExECT corpus (the epilepsy type in the gold is a keyword "
                "rule over the diagnosis text)",
        "convention": "a rescue drug counts as a current ASM (the F-S gold convention)",
        "protocol": "docs/EVAL_PROTOCOL_LEO.md 10.1-10.7; scored with the shipped configuration (no override), "
                    "sections 10.9 and 10.41",
    },
    "synth": {
        "file": "leo_vs_synth_gold_v07_maint.json", "source": "L1C",
        "label": "30 synthetic US-style patients (143 notes)",
        "unit": "patients", "text": "synthetic",
        "gold": "the generator's own ground truth, aggregated over each patient's notes",
        "convention": "rescue drugs do not count as current ASMs",
        "protocol": "docs/EVAL_PROTOCOL_LEO.md 10.4, 10.7, 10.41",
    },
}

# catalogue phenotype -> [(scorer key, label, note)]
FIELD_MAP: dict[str, list[tuple[str, str, str]]] = {
    "epilepsy_type": [("epilepsy_type", "all records", ""),
                      ("epilepsy_type|typed", "only where the reference names a type",
                       "Records whose reference is 'unknown' are left out; a predicted 'unknown' counts as no answer.")],
    "seizure_type": [("predominant_seizure_type", "predominant seizure type", "")],
    "seizure_onset_class": [("predominant_seizure_type|class", "focal / generalized / unknown onset", "")],
    "age_at_onset": [("age_at_onset_years", "within 1 year", "")],
    "seizure_frequency": [("seizure_frequency.period", "period", ""),
                          ("seizure_frequency.count_min", "count, lower bound", ""),
                          ("seizure_frequency.count_max", "count, upper bound", "")],
    "current_asms": [("current_asms", "drug names", "")],
    "seizure_free": [("seizure_free", "seizure free now (yes / no)", "")],
    "date_of_last_seizure": [("date_of_last_seizure", "date at the reference's precision",
                              "Any of the reference's per-seizure-type dates counts as a match.")],
}

CAVEATS = [
    "Every test note here is synthetic text. No real clinical note has been scored, so these numbers say nothing "
    "yet about real notes.",
    "The F-S letters are UK-style letters; the synthetic US-style notes were written from the same plan as their gold "
    "and state the facts plainly, so they are close to saturated and cannot rank methods.",
    "The EpExtra rules and the LEO routing were developed against these corpora; a clinician-annotated US set is "
    "still needed.",
    "Samples are small. Read the n beside each number: an F1 of 1.00 on 4 letters is not strong evidence.",
    "LLM-only answers are never auto-accepted. Questions (free text) have no accuracy measurement at all.",
]


def _load(name: str) -> Optional[dict]:
    try:
        return json.loads((RESULTS / name).read_text())
    except Exception:
        return None


def _pf(src: dict, system: str, key: str) -> Optional[dict]:
    d = (src.get("systems", {}).get(system, {}).get("per_field", {}) or {}).get(key)
    if not d:
        return None
    return {"n": d["n"], "p": round(d["p"], 3), "r": round(d["r"], 3), "f1": round(d["f1"], 3)}


def evidence() -> dict:
    """The full evidence object for the UI and ``GET /leo/evidence``."""
    out: dict[str, Any] = {"datasets": [], "fields": {}, "claim_precision": {}, "caveats": CAVEATS,
                           "config": "runtime leo-v0.9; scored files L1C D17 (frozen v08/v07). Rules shown on disagreement; model kept as alternative"}
    srcs: dict[str, Optional[dict]] = {}
    for did, d in DATASETS.items():
        raw = _load(d["file"])
        src = (raw or {}).get("sources", {}).get(d["source"])
        srcs[did] = src
        item = {"id": did, **{k: d[k] for k in ("label", "unit", "text", "gold", "convention", "protocol", "file")},
                "available": src is not None}
        if src:
            item["n"] = src["n_letters"]
            item["arm"] = src.get("arm")
            item["systems"] = {s: {"micro_p": round(v["micro_p"], 3), "micro_r": round(v["micro_r"], 3),
                                   "micro_f1": round(v["micro_f1"], 3),
                                   "ci": [round(x, 3) for x in v["f1_ci"]] if v.get("f1_ci") else None}
                               for s, v in src["systems"].items()}
            out["claim_precision"][did] = {k: {"correct": v["correct"], "scored": v["scored"],
                                               "precision": None if v["precision"] is None else round(v["precision"], 3)}
                                           for k, v in src.get("claim_precision_by_category", {}).items()}
        out["datasets"].append(item)
    for pid, rows in FIELD_MAP.items():
        entries = []
        for key, label, note in rows:
            e: dict[str, Any] = {"metric": label, "note": note}
            for did, src in srcs.items():
                e[did] = None if src is None else {
                    "reviewed": _pf(src, "leo_review", key), "auto": _pf(src, "leo_auto", key),
                    "llm_alone": _pf(src, "llm", key), "specialist_alone": _pf(src, "specialist", key)}
            entries.append(e)
        out["fields"][pid] = entries
    return out


__all__ = ["evidence", "DATASETS", "FIELD_MAP", "CAVEATS"]
