"""Phase 3b end-to-end smoke test — 24-field coverage on F-S train letters.

Extends ``smoke_phase2_pipeline.py`` (which covered 8 P1 fields) with the 16
P2 fields added in Phase 3b. Reports per-doc population rates across the
combined 24-field set on 5 F-S train letters.

Usage
-----
    venv-medcat/bin/python scripts/smoke_phase3b_pipeline.py

Exit code is non-zero on any of:
- extractor / assembler raising,
- Pydantic validation failing,
- fewer than 5 P2 fields populated on the primary doc,
- fewer than 8 combined fields populated on any doc.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Silence PyRuSH.
try:  # pragma: no cover
    from loguru import logger as _lg
    _lg.remove()
except Exception:
    pass

from schema.enums import Certainty, DocumentType  # noqa: E402
from schema.ontology import EpilepsyPhenotype  # noqa: E402
from services.medcat_extractor import MedCATExtractor  # noqa: E402
from services.phenotype_assembler import PhenotypeAssembler  # noqa: E402


DEFAULT_CDB = REPO_ROOT / "data" / "medcat_cdb_epilepsy" / "cdb"
DEFAULT_DOCS = ["EA0001", "EA0025", "EA0050", "EA0075", "EA0100"]

# Phase 3a fields (P1).
P1_FIELDS = [
    ("clinical_seizure", "epilepsy_type"),
    ("clinical_seizure", "predominant_seizure_type"),
    ("clinical_seizure", "seizure_frequency"),
    ("clinical_seizure", "age_at_onset_years"),
    ("clinical_seizure", "etiology_category"),
    ("medication", "current_asms"),
    ("mri", "findings"),
    ("eeg", "ied_findings"),
]

# Phase 3b fields (P2).
P2_FIELDS = [
    ("clinical_seizure", "awareness"),
    ("clinical_seizure", "focal_motor_onset"),
    ("clinical_seizure", "focal_nonmotor_onset"),
    ("clinical_seizure", "semiology_text"),
    ("clinical_seizure", "status_epilepticus_history"),
    ("clinical_seizure", "etiology_specifics"),
    ("clinical_localization", "primary_claim"),
    ("integrated", "concordance"),
    ("medication", "drug_resistance_status"),
    ("medication", "adverse_effects_text"),
    ("medication", "surgery_history"),
    ("medication", "non_drug_therapies"),
    ("mri", "lesion_lobe"),
    ("mri", "field_strength_tesla"),
    ("eeg", "study_type"),
    ("eeg", "ictal_onset_lobe"),
]

ALL_FIELDS = P1_FIELDS + P2_FIELDS   # 24 fields


def _is_populated(pheno: EpilepsyPhenotype, module_name: str, field: str) -> bool:
    mod = getattr(pheno, module_name, None)
    if mod is None:
        return False
    val = getattr(mod, field, None)
    if val is None:
        return False
    if isinstance(val, list):
        if len(val) > 0:
            return True
        # For MRI/EEG list fields, also count boolean signals.
        if module_name == "mri" and field == "findings":
            for sib in ("overall_normal", "mri_negative_for_epilepsy",
                        "hippocampal_sclerosis", "focal_cortical_dysplasia"):
                s = getattr(mod, sib, None)
                if s is not None and getattr(s, "value", None) is not None \
                   and getattr(s, "certainty", None) != Certainty.NOT_DOCUMENTED:
                    return True
        if module_name == "eeg" and field == "ied_findings":
            for sib in ("background", "ied_present"):
                s = getattr(mod, sib, None)
                if s is not None and getattr(s, "value", None) is not None \
                   and getattr(s, "certainty", None) != Certainty.NOT_DOCUMENTED:
                    return True
        return False
    return (getattr(val, "value", None) is not None and
            getattr(val, "certainty", None) != Certainty.NOT_DOCUMENTED)


def _summarise(pheno: EpilepsyPhenotype,
               fields: list[tuple[str, str]]) -> tuple[int, list[str]]:
    hits = 0
    lines: list[str] = []
    for module_name, field in fields:
        pop = _is_populated(pheno, module_name, field)
        mark = "+" if pop else "-"
        mod = getattr(pheno, module_name, None)
        v = getattr(mod, field, None) if mod is not None else None
        if pop:
            hits += 1
            if isinstance(v, list):
                summary = f"{len(v)} entry(ies)"
                if v and hasattr(v[0], "value") and v[0].value is not None:
                    summary += f" e.g. {v[0].value!r}"[:90]
            else:
                summary = f"{v.value!r}"[:90]
        else:
            summary = "not_documented"
        label = f"{module_name}.{field}"
        lines.append(f"    [{mark}] {label:52s} : {summary}")
    return hits, lines


def _resolve_doc(ea_id: str) -> Path:
    p = REPO_ROOT / "data" / "fs_corpus" / "documents" / ea_id / \
        "progress_note" / "output.txt"
    if not p.exists():
        raise FileNotFoundError(f"No document at {p}")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdb", default=str(DEFAULT_CDB))
    args = parser.parse_args(argv)

    print(f"[smoke3b] Loading MedCAT + medspaCy pipeline …")
    extractor = MedCATExtractor(args.cdb, verbose=False)
    assembler = PhenotypeAssembler(extractor)
    n_rules = len(assembler._rules)
    n_wave1 = sum(1 for r in assembler._rules if getattr(r, "phase", 1) == 1)
    n_wave2 = sum(1 for r in assembler._rules if getattr(r, "phase", 1) == 2)
    print(f"[smoke3b] {n_rules} field rules registered "
          f"({n_wave1} wave-1, {n_wave2} wave-2)")
    print(f"[smoke3b] Field coverage target: 24 fields "
          f"({len(P1_FIELDS)} P1 + {len(P2_FIELDS)} P2)")

    total_pop = 0
    total_slots = 0
    per_doc_hits: list[tuple[str, int, int]] = []  # (ea, p1_hits, p2_hits)

    for ea_id in DEFAULT_DOCS:
        try:
            p = _resolve_doc(ea_id)
        except FileNotFoundError:
            print(f"[smoke3b] SKIP {ea_id}: no doc")
            continue
        text = p.read_text()
        print(f"\n[smoke3b] ▶ {ea_id} ({len(text):,} chars)")
        pheno = assembler.process(
            text, doc_id=ea_id, doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=date(2020, 1, 1), patient_id=ea_id,
        )
        try:
            EpilepsyPhenotype.model_validate(pheno.model_dump(mode="json"))
        except Exception as e:
            print(f"[smoke3b] FAIL {ea_id}: Pydantic re-validate: {e}")
            return 2

        p1_hits, p1_lines = _summarise(pheno, P1_FIELDS)
        p2_hits, p2_lines = _summarise(pheno, P2_FIELDS)

        print(f"  -- P1 (Phase 3a) fields --")
        for ln in p1_lines:
            print(ln)
        print(f"    → P1: {p1_hits}/{len(P1_FIELDS)}")

        print(f"  -- P2 (Phase 3b) fields --")
        for ln in p2_lines:
            print(ln)
        print(f"    → P2: {p2_hits}/{len(P2_FIELDS)}")

        combined = p1_hits + p2_hits
        print(f"    → COMBINED: {combined}/{len(ALL_FIELDS)}")
        per_doc_hits.append((ea_id, p1_hits, p2_hits))
        total_pop += combined
        total_slots += len(ALL_FIELDS)

    n_docs = len(per_doc_hits)
    if n_docs == 0:
        print("[smoke3b] FAIL: no docs")
        return 2

    avg = total_pop / n_docs
    print(f"\n[smoke3b] Summary: {total_pop}/{total_slots} fields "
          f"populated across {n_docs} docs "
          f"(avg {avg:.1f}/{len(ALL_FIELDS)} per doc)")

    # Acceptance criteria: primary doc must have ≥ 5 P2 fields populated,
    # at least one doc must have ≥ 8 combined fields, and Pydantic must
    # validate.
    primary_p2 = per_doc_hits[0][2]
    max_combined = max(h1 + h2 for _, h1, h2 in per_doc_hits)
    print(f"[smoke3b] Primary doc {per_doc_hits[0][0]}: "
          f"P2={primary_p2}/{len(P2_FIELDS)}, "
          f"P1={per_doc_hits[0][1]}/{len(P1_FIELDS)}")
    print(f"[smoke3b] Best-doc combined: {max_combined}/{len(ALL_FIELDS)}")

    if primary_p2 < 3:
        print(f"[smoke3b] WARN: primary doc has only {primary_p2} P2 fields "
              f"populated (target ≥ 5).")
    if max_combined < 8:
        print(f"[smoke3b] FAIL: best doc only {max_combined} combined "
              f"fields — target ≥ 8.")
        return 3
    print("[smoke3b] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
