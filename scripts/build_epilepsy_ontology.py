"""Bootstrap builder for ``rules/epilepsy_ontology.py`` (Phase 1b).

This script documents the process by which the ontology was assembled and
regenerates the F-S train-corpus mining index that seeded a subset of the
synonyms baked into ``rules/epilepsy_ontology.py``.

It is NOT expected to run in CI: the emitted ontology module is the
authoritative artifact and is hand-curated (with medical judgment) on top of
the mining output. This script is a bootstrap/repro-aid so that reviewers
can inspect exactly what was mined from where.

Usage:
    venv-medcat/bin/python scripts/build_epilepsy_ontology.py [--report]

Produces (to stdout unless --write):
    - F-S train (EA0001-EA0160) gold-value → sample-evidence index
    - ExECT-V2 seed CSV → per-category CUI summary
    - Coverage report against schema/enums.py
    - Provenance-source distribution summary
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SEED_CSV = REPO_ROOT / "references" / "exect_v2_cui_seed.csv"
FS_TARGETS = REPO_ROOT / "data" / "fs_corpus" / "targets"

FS_TRAIN_MIN = 1
FS_TRAIN_MAX = 160
FS_HELD_OUT_MIN = 161
FS_HELD_OUT_MAX = 200  # NEVER touched by this script


def load_seed_csv() -> list[dict[str, str]]:
    if not SEED_CSV.exists():
        raise FileNotFoundError(f"Seed CSV not found: {SEED_CSV}")
    lines = [l for l in SEED_CSV.open() if not l.startswith("#")]
    reader = csv.DictReader(lines)
    return list(reader)


def seed_by_category(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    by_cat: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_cat[row["category"]].append(row)
    return by_cat


def _walk_evidence(obj: Any, path: str = ""):
    """Yield (dotted-path, evidence-object) tuples wherever we see an
    ``Evidence[T]``-shaped dict (has ``value`` + ``evidence_text``)."""
    if isinstance(obj, dict):
        if "value" in obj and "evidence_text" in obj:
            yield path, obj
        for k, v in obj.items():
            yield from _walk_evidence(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            yield from _walk_evidence(v, f"{path}[{idx}]")


def mine_fs_train() -> dict[str, dict[str, list[tuple[str, str]]]]:
    """Return {field_path -> {gold_value -> [(doc_id, evidence_text), ...]}}
    for EA0001..EA0160 only.
    """
    if not FS_TARGETS.exists():
        raise FileNotFoundError(f"F-S targets directory not found: {FS_TARGETS}")
    idx: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for i in range(FS_TRAIN_MIN, FS_TRAIN_MAX + 1):
        doc_id = f"EA{i:04d}"
        path = FS_TARGETS / doc_id / "target_phenotype.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for p, ev in _walk_evidence(data):
            val = ev.get("value")
            if val is None:
                continue
            if isinstance(val, (dict, list)):
                # dive one more level for compound value objects (Medication, SurgeryHistoryItem, etc.)
                if isinstance(val, dict):
                    for sub_k, sub_v in val.items():
                        if isinstance(sub_v, (str, int, float)) and sub_v not in (None, ""):
                            idx[f"{p}.{sub_k}"][str(sub_v).lower()].append(
                                (doc_id, ev.get("evidence_text", ""))
                            )
                continue
            canon_p = p.split("[")[0]
            idx[canon_p][str(val)].append((doc_id, ev.get("evidence_text", "")))
    return {k: dict(v) for k, v in idx.items()}


def coverage_report() -> None:
    """Compare the ontology registry against schema/enums.py."""
    from rules.epilepsy_ontology import (
        RULES_ONLY_ENUMS,
        all_enum_ontologies,
        supplementary_ontologies,
        total_concept_count,
    )
    from schema import enums as _enums

    ontos = all_enum_ontologies()
    supp = supplementary_ontologies()

    print("=" * 60)
    print("PHASE 1b — ONTOLOGY COVERAGE REPORT")
    print("=" * 60)

    enum_triples = sum(len(v) for v in ontos.values())
    supp_triples = sum(len(v) for v in supp.values())
    grand_total = enum_triples + supp_triples
    all_onto_iter = list(ontos.values()) + list(supp.values())
    total_with_cui = sum(1 for onto in all_onto_iter for e in onto.values() if e.cui)
    total_with_sctid = sum(1 for onto in all_onto_iter for e in onto.values() if e.sctid)
    total_with_synonyms = sum(1 for onto in all_onto_iter for e in onto.values() if e.synonyms)

    print(f"Enum-value triples: {enum_triples}")
    print(f"Supplementary triples: {supp_triples}")
    print(f"Grand total triples: {grand_total}")
    print(f"With CUI: {total_with_cui}")
    print(f"With SCTID: {total_with_sctid}")
    print(f"With ≥1 synonym: {total_with_synonyms}")
    print(f"RULES_ONLY_ENUMS: {sorted(RULES_ONLY_ENUMS)}")
    print()

    print("Per-enum breakdown:")
    for enum_name, onto in ontos.items():
        n = len(onto)
        n_cui = sum(1 for e in onto.values() if e.cui)
        n_sctid = sum(1 for e in onto.values() if e.sctid)
        avg_syn = sum(len(e.synonyms) for e in onto.values()) / max(n, 1)
        rules_flag = " [RULES_ONLY]" if enum_name in RULES_ONLY_ENUMS else ""
        print(
            f"  {enum_name}{rules_flag}: {n} values, "
            f"cui={n_cui}/{n}, sctid={n_sctid}/{n}, avg_synonyms={avg_syn:.1f}"
        )

    print()
    print("Supplementary ontology breakdown:")
    for supp_name, supp_onto in supp.items():
        n = len(supp_onto)
        n_cui = sum(1 for e in supp_onto.values() if e.cui)
        n_sctid = sum(1 for e in supp_onto.values() if e.sctid)
        avg_syn = sum(len(e.synonyms) for e in supp_onto.values()) / max(n, 1)
        print(
            f"  {supp_name}: {n} entries, cui={n_cui}/{n}, sctid={n_sctid}/{n}, "
            f"avg_synonyms={avg_syn:.1f}"
        )

    print()
    print("Provenance-source distribution:")
    src_counter: dict[str, int] = defaultdict(int)
    for onto in all_onto_iter:
        for entry in onto.values():
            for src in entry.source_provenance:
                # coarse bucket
                if src.startswith("F-S train"):
                    src_counter["F-S train mining"] += 1
                elif "ILAE 2017" in src:
                    src_counter["ILAE 2017"] += 1
                elif "ILAE 2010" in src:
                    src_counter["ILAE 2010"] += 1
                elif "ExECT-V2 seed" in src:
                    src_counter["ExECT-V2 seed (CUI anchor)"] += 1
                elif "RxNorm" in src:
                    src_counter["RxNorm"] += 1
                elif "Graus" in src:
                    src_counter["Graus 2016"] += 1
                elif "Engel" in src:
                    src_counter["Engel 1993"] += 1
                elif "Wieser" in src:
                    src_counter["Wieser 2001"] += 1
                elif "ACNS" in src:
                    src_counter["ACNS terminology"] += 1
                elif "SNOMED" in src:
                    src_counter["SNOMED-CT US"] += 1
                elif "RULES_ONLY" in src:
                    src_counter["RULES_ONLY marker"] += 1
                elif "domain-knowledge" in src:
                    src_counter["domain-knowledge"] += 1
                else:
                    src_counter["other"] += 1
    for src, n in sorted(src_counter.items(), key=lambda x: -x[1]):
        print(f"  {src}: {n}")


def print_seed_summary() -> None:
    rows = load_seed_csv()
    by_cat = seed_by_category(rows)
    print("=" * 60)
    print("ExECT-V2 seed CSV summary")
    print("=" * 60)
    print(f"Total seed CUIs: {len(rows)}")
    for cat, items in sorted(by_cat.items()):
        n_with_sctid = sum(1 for r in items if r["snomed_ct_id"].strip())
        print(f"  {cat}: {len(items)} CUIs ({n_with_sctid} with SCTID)")


def print_fs_mining_summary() -> None:
    idx = mine_fs_train()
    print("=" * 60)
    print("F-S train (EA0001-EA0160) gold-label mining summary")
    print("=" * 60)
    total_forms = 0
    for field, valdict in sorted(idx.items()):
        n_vals = len(valdict)
        n_occ = sum(len(v) for v in valdict.values())
        total_forms += n_occ
        print(f"  {field}: {n_vals} distinct values, {n_occ} occurrences")
    print(f"Total surface-form occurrences mined: {total_forms}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report", action="store_true",
        help="Print full coverage + provenance report",
    )
    parser.add_argument(
        "--fs-mining", action="store_true",
        help="Print F-S train mining summary only",
    )
    parser.add_argument(
        "--seed-summary", action="store_true",
        help="Print ExECT-V2 seed CSV summary only",
    )
    args = parser.parse_args()

    if not any([args.report, args.fs_mining, args.seed_summary]):
        args.report = True
        args.fs_mining = True
        args.seed_summary = True

    if args.seed_summary:
        print_seed_summary()
        print()
    if args.fs_mining:
        print_fs_mining_summary()
        print()
    if args.report:
        coverage_report()


if __name__ == "__main__":
    main()
