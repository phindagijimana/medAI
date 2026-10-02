"""Synthetic US-style evaluation set (synth-v3 and synth-v3-polish) for LEO.

Why this exists.  The Fonferko-Shadrach letters are UK documents (and synthetic);
the target deployment is US epilepsy-clinic notes.  The synth-v3 corpora are
GPT-written US-style notes (progress notes, consults, EEG/MRI reports, phone
follow-ups ...) with a patient-level gold phenotype.

Two facts shape how they may be used:

* The gold is **patient-level** (``targets/<patient>/target_phenotype.json``, derived from the
  semantic plan), while every patient has about five notes, each of which shows only part of it.
  Scoring one note against the whole target would charge recall for facts the note never states.
  The evaluation therefore aggregates every system's claims over all of a patient's notes and
  scores the patient (``scripts/score_leo_vs_synth_gold.py``).
* The Arm H adapter was trained on **synth-v3-polish** patients P004000-P004099 except a
  patient-level validation split (10 patients, ``finetune_lora_epi._split_by_patient`` with
  val_frac 0.1, seed 0).  Only those 10 patients are unseen by the adapter *within* polish.
  ``synth_v3`` patients P003000-P003099 are a separate generation run with their own patient
  plans; the adapter never saw them.  ``eval_patients()`` returns both strata so results are
  reported separately.

Limits to state with any result: the notes and the gold come from the same generator; the
EpExtra rules were developed against these corpora; none of this is real clinical text.
"""

from __future__ import annotations

import csv
import random
from functools import lru_cache
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent

CORPORA = {
    # corpus -> (eval_corpora dir, episynth_corpus dir)
    "synth_v3": ("synth_v3", "v3"),
    "synth_v3_polish": ("synth_v3_polish", "v3_polish"),
    # Older, simpler corpora (one progress note plus an MRI or EEG report per patient).  Used as an
    # unused validation set: no rule of leo-v0.4/v0.5 and no adapter was developed on them.
    "synth_v1": ("synth_v1_eval_100", "v1"),
    "synth_v2": ("", "v2"),
}
DOC_PREFIX = "synth-"          # source_doc_id of a run manifest is ``synth-<visit_id>``


def _v2_rows() -> tuple[dict, ...]:
    """synth-v2: the patients that have a per-document gold file (the held-out part)."""
    root = REPO / "data" / "episynth_corpus" / "v2"
    rows = []
    for g in sorted((root / "gold_v0_2_1").glob("P*_*.json")):
        pid, doc_type = g.stem.split("_", 1)
        note = root / "documents" / pid / doc_type / "output.txt"
        if note.exists():
            rows.append({"visit_id": g.stem, "patient_id": pid, "note_path": str(note),
                         "gold_path": str(g)})
    return tuple(rows)


@lru_cache(maxsize=None)
def manifest_rows(corpus: str) -> tuple[dict, ...]:
    if corpus == "synth_v2":
        return _v2_rows()
    d = REPO / "data" / "eval_corpora" / CORPORA[corpus][0]
    with (d / "manifest.csv").open(encoding="utf-8") as fh:
        rows = tuple(csv.DictReader(fh))
    if corpus == "synth_v1":     # columns: id, patient_id, doc_type, ..., source_path, gold_path
        return tuple({"visit_id": r["id"], "patient_id": r["patient_id"],
                      "note_path": f"documents/{r['id']}.txt"} for r in rows)
    return rows


@lru_cache(maxsize=None)
def _visit_index() -> dict[str, tuple[str, dict]]:
    out = {}
    for corpus in CORPORA:
        for r in manifest_rows(corpus):
            out[r["visit_id"]] = (corpus, r)
    return out


def corpus_of(visit_id: str) -> str:
    return _visit_index()[visit_id][0]


def patient_of(visit_id: str) -> str:
    return _visit_index()[visit_id][1]["patient_id"]


def _note_file(corpus: str, row: dict) -> Path:
    if corpus == "synth_v2":
        return Path(row["note_path"])
    return REPO / "data" / "eval_corpora" / CORPORA[corpus][0] / row["note_path"]


def note_text(visit_id: str) -> str:
    corpus, row = _visit_index()[visit_id]
    return _note_file(corpus, row).read_text(encoding="utf-8")


def visits_of(corpus: str, patient_id: str) -> list[str]:
    return [r["visit_id"] for r in manifest_rows(corpus)
            if r["patient_id"] == patient_id and _note_file(corpus, r).exists()]


def target_path(corpus: str, patient_id: str) -> Path:
    if corpus == "synth_v2":    # no targets/ directory: every per-document gold file holds the patient target
        g = [r["gold_path"] for r in manifest_rows("synth_v2") if r["patient_id"] == patient_id]
        return Path(g[0])
    return (REPO / "data" / "episynth_corpus" / CORPORA[corpus][1] / "targets"
            / patient_id / "target_phenotype.json")


def polish_val_patients(val_frac: float = 0.1, seed: int = 0) -> list[str]:
    """Patients the v3-polish adapter used for validation (mirrors ``_split_by_patient``)."""
    pids = sorted({r["patient_id"] for r in manifest_rows("synth_v3_polish")
                   if target_path("synth_v3_polish", r["patient_id"]).exists()})
    rng = random.Random(seed)
    rng.shuffle(pids)
    return sorted(pids[:max(1, int(round(len(pids) * val_frac)))])


# Which patients a run covers.  MEDAI_SYNTH_SET: "eval" (default, 30 patients), "ext" (the other
# 80 synth-v3 patients, none of them looked at while the leo-v0.4/v0.5 rules were written) or
# "v1v2" (the held-out synth-v1 and synth-v2 patients) or "polish90" (the 90 polish training
# patients, base-model arms only).
STRATA_CORPUS = {"polish_val": "synth_v3_polish", "polish_train": "synth_v3_polish", "synth_v3": "synth_v3",
                 "synth_v1": "synth_v1", "synth_v2": "synth_v2"}


def eval_patients(n_unpolished: int = 20, which: Optional[str] = None) -> dict[str, list[str]]:
    """Evaluation strata: ``polish_val`` (10, same distribution as training, unseen patients)
    and ``synth_v3`` (every k-th of P003000-P003099; a different generation run)."""
    import os
    which = which or os.environ.get("MEDAI_SYNTH_SET", "eval")
    all_v3 = sorted({r["patient_id"] for r in manifest_rows("synth_v3")})
    step = max(1, len(all_v3) // n_unpolished)
    used = all_v3[::step][:n_unpolished]
    if which == "ext":
        return {"synth_v3": [p for p in all_v3 if p not in set(used)]}
    if which == "polish90":
        # The 90 polish patients the v3-polish adapter was trained on.  Only the base-model arm
        # (L1C) may be scored here; an adapter result would be a training-set result.  Used for the
        # hard-slice scores (stopped / denied / hedged / hypothetical), which need the larger n.
        val = set(polish_val_patients())
        return {"polish_train": sorted({r["patient_id"] for r in manifest_rows("synth_v3_polish")} - val)}
    if which == "v1v2":
        return {"synth_v1": sorted({r["patient_id"] for r in manifest_rows("synth_v1")}),
                "synth_v2": sorted({r["patient_id"] for r in manifest_rows("synth_v2")})}
    return {"polish_val": polish_val_patients(), "synth_v3": used}


def eval_visits(strata: Optional[dict[str, list[str]]] = None) -> list[str]:
    strata = strata or eval_patients()
    out: list[str] = []
    for name, pids in strata.items():
        for p in pids:
            out.extend(visits_of(STRATA_CORPUS[name], p))
    return out


__all__ = ["CORPORA", "DOC_PREFIX", "corpus_of", "eval_patients", "eval_visits", "manifest_rows",
           "note_text", "patient_of", "STRATA_CORPUS", "polish_val_patients", "target_path", "visits_of"]
