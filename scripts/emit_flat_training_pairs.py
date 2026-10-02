#!/usr/bin/env python3
"""Training pairs for "Arm H2": the flat contract, with verbatim evidence spans.

Why a second adapter.  The first adapter (Arm H, ``emit_synth_v3_training_pairs.py``) was trained to
write the whole EpilepsyPhenotype JSON for every visit, using the *patient-level* gold as the
target.  Two problems follow:

* The target carries facts the visit's note may not state, and its evidence strings are templated
  ("lacosamide current", "age at onset 11"), so the adapter never learned to copy a span of the
  note.  The pipeline works around this with ``ground_value`` (it finds the span itself).
* Most target tokens are schema boilerplate and copied IDs, so the validation loss is about zero
  whether or not the clinical values are right; it says almost nothing about extraction quality.

H2 trains on the small ``FlatAnswer`` contract that LEO already uses with constrained decoding
(arm L2C), one note at a time:

* a gold field is kept only if ``services.chain_llm.ground_value`` can find supporting words in
  *this note*; those words become the ``quote`` (verbatim, so the model learns to copy);
* a gold field that cannot be found in this note becomes ``null`` (the note does not state it) and is
  counted, so the false-null risk of an imperfect grounder is visible;
* the drug list holds only gold *current* ASMs found in the note, so stopped, planned and
  hypothetical drugs in the note are negatives.

Same patients, same patient-level split (seed 0, 10 %) as the Arm H data, so the held-out ``polish_val``
patients stay unseen and the comparison with Arm H and with the untuned L1C/L2C is like for like.

Usage:
    venv-medcat/bin/python scripts/emit_flat_training_pairs.py            # writes the two files
    venv-medcat/bin/python scripts/emit_flat_training_pairs.py --dry-run --n 3
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import re                                                    # noqa: E402

from services.chain_llm import _NUM_RX, _to_num, ground_value  # noqa: E402
from services.flat_extract import build_flat_prompt        # noqa: E402

CORPUS = REPO / "data" / "eval_corpora" / "synth_v3_polish"
TARGETS = REPO / "data" / "episynth_corpus" / "v3_polish" / "targets"
FIELDS = ("epilepsy_type", "predominant_seizure_type", "age_at_onset_years", "seizure_frequency", "current_asms")


# The pipeline grounder (ground_value) misses frequencies that put a hyphenated word between the count
# and "per" ("2 focal impaired-awareness seizures per year") and "once monthly".  For training data a
# missed span would teach a false null, so use a looser matcher here and skip what is still unclear.
_UNIT = r"(?:day|week|month|year)"
_FREQ_LOOSE = re.compile(
    rf"(?:{_NUM_RX}(?:\s*(?:-|to|or)\s*{_NUM_RX})?\s+(?:[\w\-]+\s+){{0,5}}?(?:per|a|each|every|in a)\s+{_UNIT}s?|"
    rf"(?:once|twice)\s+(?:a|per|every|each)?\s*{_UNIT}(?:ly)?s?|(?:daily|weekly|monthly|yearly|annual(?:ly)?))", re.I)
_FREQ_ANY = re.compile(r"per (?:day|week|month|year)|\b(?:a|each) (?:day|week|month|year)\b|\bonce\b|\btwice\b|"
                       r"monthly|weekly|daily|seizure[- ]free|seizure freedom|no (?:recent |further )?seizures", re.I)


def _ground_freq(f: dict, note: str):
    sp = ground_value("clinical_seizure.seizure_frequency", f, note)
    if sp or f.get("seizure_free"):
        return sp
    lo = f.get("count_min")
    for m in _FREQ_LOOSE.finditer(note):
        nums = [_to_num(t) for t in re.findall(_NUM_RX, m.group(0), re.I)]
        nums = [x for x in nums if x is not None]
        word_once = re.match(r"once", m.group(0), re.I) and lo == 1.0
        word_twice = re.match(r"twice", m.group(0), re.I) and lo == 2.0
        if lo is None or word_once or word_twice or any(abs(x - float(lo)) < 1e-6 for x in nums):
            return m.start(), m.end()
    return None


def _val(ev):
    return ev.get("value") if isinstance(ev, dict) else None


def _quote(text: str, span: tuple[int, int]) -> str:
    q = text[span[0]:span[1]].strip()
    return q[:160]


def flat_target(note: str, gold: dict, stats: Counter) -> dict:
    """Gold phenotype + note -> FlatAnswer dict (spans copied from the note)."""
    cs = gold.get("clinical_seizure") or {}
    med = gold.get("medication") or {}
    out: dict = {}

    for fld, path, enum in (("epilepsy_type", "clinical_seizure.epilepsy_type", True),
                            ("predominant_seizure_type", "clinical_seizure.predominant_seizure_type", True),
                            ("age_at_onset_years", "clinical_seizure.age_at_onset_years", False)):
        v = _val(cs.get(fld))
        if v is None:
            out[fld] = {"value": None, "quote": None}
            continue
        stats[f"{fld}:gold"] += 1
        sp = ground_value(path, v, note)
        if sp:
            stats[f"{fld}:grounded"] += 1
            out[fld] = {"value": v if enum else float(v), "quote": _quote(note, sp)}
        else:
            out[fld] = {"value": None, "quote": None}

    f = _val(cs.get("seizure_frequency"))
    out["seizure_frequency"] = {"count_min": None, "count_max": None, "period": None,
                                "seizure_free": None, "quote": None}
    if isinstance(f, dict):
        stats["seizure_frequency:gold"] += 1
        sp = _ground_freq(f, note)
        if not sp and _FREQ_ANY.search(note):
            stats["seizure_frequency:ambiguous"] += 1       # the note seems to talk about it: skip the pair
            out["_skip"] = True
        if sp:
            stats["seizure_frequency:grounded"] += 1
            per = f.get("period")
            out["seizure_frequency"] = {
                "count_min": f.get("count_min"), "count_max": f.get("count_max"),
                "period": per if per in ("day", "week", "month", "year") else None,
                "seizure_free": True if f.get("seizure_free") else None,
                "quote": _quote(note, sp)}

    asms = []
    for ev in med.get("current_asms") or []:
        v = _val(ev) or {}
        name = (v.get("generic_name") or "").strip()
        if not name:
            continue
        stats["current_asms:gold"] += 1
        sp = ground_value("medication.current_asms", v, note)
        if sp:
            stats["current_asms:grounded"] += 1
            asms.append({"name": name, "dose": None, "quote": _quote(note, sp)})
    out["current_asms"] = asms
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default="data/finetune_data")
    ap.add_argument("--val-frac", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--n", type=int, default=3)
    args = ap.parse_args()

    rows = list(csv.DictReader((CORPUS / "manifest.csv").open()))
    pairs, stats, by_type = [], Counter(), defaultdict(Counter)
    for row in rows:
        npath = CORPUS / row["note_path"]
        tpath = TARGETS / row["patient_id"] / "target_phenotype.json"
        if not npath.exists() or not tpath.exists():
            continue
        note = npath.read_text(encoding="utf-8").strip()
        if not note:
            continue
        gold = json.loads(tpath.read_text(encoding="utf-8"))
        st = Counter()
        tgt = flat_target(note, gold, st)
        if tgt.pop("_skip", False):
            stats["pairs_skipped_ambiguous_frequency"] += 1
            continue
        stats.update(st)
        for k, v in st.items():
            by_type[row["note_type"]][k] += v
        pairs.append({"patient_id": row["patient_id"], "visit_id": row["visit_id"],
                      "note_type": row["note_type"],
                      "prompt": build_flat_prompt(note, "L0"),
                      "completion": json.dumps(tgt, ensure_ascii=False)})

    print(f"[emit] pairs: {len(pairs)}  (skipped as ambiguous frequency: "
          f"{stats['pairs_skipped_ambiguous_frequency']})")
    print("[emit] gold facts found in the note (grounded / gold):")
    for fld in FIELDS:
        g, k = stats[f"{fld}:gold"], stats[f"{fld}:grounded"]
        print(f"    {fld:<26} {k:5d} / {g:5d}  ({(k / g if g else 0):.1%})")
    print("[emit] by note type, grounded share:")
    for nt, c in sorted(by_type.items()):
        g = sum(v for k, v in c.items() if k.endswith(":gold"))
        k = sum(v for k, v in c.items() if k.endswith(":grounded"))
        print(f"    {nt:<28} {k:5d} / {g:5d}  ({(k / g if g else 0):.1%})")

    if args.dry_run:
        for p in pairs[:args.n]:
            print("=" * 70)
            print(p["visit_id"], p["note_type"])
            print(p["completion"][:900])
        return 0

    by_pid = defaultdict(list)
    for p in pairs:
        by_pid[p["patient_id"]].append(p)
    pids = sorted(by_pid)
    random.Random(args.seed).shuffle(pids)
    n_val = max(1, int(round(len(pids) * args.val_frac)))
    val_pids = set(pids[:n_val])
    out = REPO / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    with (out / "flat_polish_train.jsonl").open("w") as ft, (out / "flat_polish_val.jsonl").open("w") as fv:
        for pid in pids:
            for p in by_pid[pid]:
                (fv if pid in val_pids else ft).write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"[emit] val patients ({len(val_pids)}): {sorted(val_pids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
