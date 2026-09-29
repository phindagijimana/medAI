"""Phase 5 end-to-end smoke test — compound / relational rules on F-S + synth-v1.

Runs the full assembler (Phase 4 US adaptation + Phase 5 compound rules
enabled by default) on 5 F-S train letters and 5 synthetic progress
notes. Reports:

- Per-doc EpilepsyPhenotype Pydantic validation.
- Wave-1 field population against the 24-field set (matches Phase 4).
- Wave-2 compound field population against the 10 compound rules.
- Combined completeness = wave-1 fields + populated compound rules.

Usage
-----
    venv-medcat/bin/python scripts/smoke_phase5_pipeline.py

Exit code is non-zero if:
- extractor / assembler raises,
- Pydantic validation fails on any of the 10 docs,
- F-S combined field population regresses below 4/24 avg (Phase 3b baseline
  was 7.2),
- fewer than 3 distinct compound rules fire on the F-S corpus.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Silence PyRuSH banner.
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
FS_DOCS = ["EA0001", "EA0025", "EA0050", "EA0075", "EA0100"]
SYNTH_DIR = REPO_ROOT / "data" / "episynth_corpus" / "v1" / "documents"

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
WAVE1_FIELDS = P1_FIELDS + P2_FIELDS   # 24 fields

# Compound rules — 10 total. Some overlap with wave-1 schema slots
# (drug_resistance_status, concordance, predominant_seizure_type); those
# fire only when the compound rule actually derives a NEW value.
COMPOUND_RULES = [
    "derive_drug_resistance",
    "derive_epilepsy_duration_years",
    "derive_medication_currently_taking",
    "derive_ilae_classification_full",
    "derive_seizure_free_since",
    "derive_focal_to_bilateral_tc",
    "derive_localization_concordance",
    "derive_surgery_outcome_class",
    "derive_autoimmune_probable",
    "derive_polytherapy_flag",
]


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


def _count_wave1(pheno: EpilepsyPhenotype) -> int:
    return sum(1 for m, f in WAVE1_FIELDS if _is_populated(pheno, m, f))


def _count_compound(pheno: EpilepsyPhenotype) -> tuple[int, list[str]]:
    outcomes = getattr(pheno, "_compound_outcomes", {}) or {}
    hit = [name for name, status in outcomes.items()
           if status not in ("skipped", None) and not str(status).startswith("error")]
    return len(hit), hit


def _resolve_fs(ea: str) -> Path:
    p = REPO_ROOT / "data" / "fs_corpus" / "documents" / ea / \
        "progress_note" / "output.txt"
    if not p.exists():
        raise FileNotFoundError(str(p))
    return p


def _pick_synth_docs(n: int) -> list[Path]:
    out: list[Path] = []
    if not SYNTH_DIR.exists():
        return out
    for pid_dir in sorted(SYNTH_DIR.iterdir()):
        if not pid_dir.is_dir():
            continue
        p = pid_dir / "progress_note" / "output.txt"
        if p.exists():
            out.append(p)
        if len(out) >= n:
            break
    return out


def run_on_doc(assembler, path: Path, doc_id: str, *, tag: str) -> dict:
    text = path.read_text()
    pheno = assembler.process(
        text,
        doc_id=doc_id,
        doc_type=DocumentType.PROGRESS_NOTE,
        doc_date=date(2020, 1, 1),
        patient_id=doc_id,
    )
    try:
        EpilepsyPhenotype.model_validate(pheno.model_dump(mode="json"))
        valid = True
    except Exception as e:  # pragma: no cover
        print(f"[smoke5][{tag}] {doc_id}: pydantic re-validate FAIL: {e}")
        valid = False

    n_wave1 = _count_wave1(pheno)
    n_compound, compound_hits = _count_compound(pheno)
    derived = getattr(pheno, "_derived", {}) or {}

    print(f"[smoke5][{tag}] {doc_id}: chars={len(text):5d}  "
          f"wave1={n_wave1}/24  compound={n_compound}/10  "
          f"valid={valid}  hits={compound_hits}")
    if derived:
        print(f"[smoke5][{tag}]     derived: {list(derived.keys())}")

    return {
        "doc_id": doc_id,
        "tag": tag,
        "valid": valid,
        "n_wave1": n_wave1,
        "n_compound": n_compound,
        "compound_hits": compound_hits,
        "derived_keys": list(derived.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdb", default=str(DEFAULT_CDB))
    parser.add_argument("--n-synth", type=int, default=5)
    args = parser.parse_args(argv)

    print("[smoke5] Loading MedCAT + medspaCy + Phase 4/5 …")
    extractor = MedCATExtractor(args.cdb, verbose=False)
    assembler = PhenotypeAssembler(extractor)
    print(f"[smoke5] uk_to_us={assembler.apply_uk_to_us}  "
          f"detect_us_sections={assembler.detect_us_sections}")

    fs_results: list[dict] = []
    for ea in FS_DOCS:
        try:
            p = _resolve_fs(ea)
        except FileNotFoundError:
            print(f"[smoke5][F-S] SKIP {ea}: no doc")
            continue
        fs_results.append(run_on_doc(assembler, p, ea, tag="F-S"))

    synth_paths = _pick_synth_docs(args.n_synth)
    if len(synth_paths) < args.n_synth:
        print(f"[smoke5] WARN: only {len(synth_paths)} synth docs available "
              f"(wanted {args.n_synth})")
    synth_results: list[dict] = []
    for p in synth_paths:
        doc_id = p.parent.parent.name
        synth_results.append(run_on_doc(assembler, p, doc_id, tag="SYN"))

    n_fs = len(fs_results)
    n_syn = len(synth_results)
    fs_valid = sum(1 for r in fs_results if r["valid"])
    syn_valid = sum(1 for r in synth_results if r["valid"])
    fs_avg_wave1 = (sum(r["n_wave1"] for r in fs_results) / n_fs) if n_fs else 0.0
    syn_avg_wave1 = (sum(r["n_wave1"] for r in synth_results) / n_syn) if n_syn else 0.0
    fs_avg_compound = (sum(r["n_compound"] for r in fs_results) / n_fs) if n_fs else 0.0
    syn_avg_compound = (sum(r["n_compound"] for r in synth_results) / n_syn) if n_syn else 0.0

    # Distinct compound rules that fired on ANY F-S doc.
    fs_distinct_compounds: set[str] = set()
    for r in fs_results:
        fs_distinct_compounds.update(r["compound_hits"])

    print()
    print(f"[smoke5] F-S rollup   ({n_fs} docs): "
          f"valid={fs_valid}/{n_fs}  "
          f"avg-wave1={fs_avg_wave1:.1f}/24  "
          f"avg-compound={fs_avg_compound:.1f}/10  "
          f"distinct-compound-fired={len(fs_distinct_compounds)}/10")
    print(f"[smoke5] F-S compound rules fired: {sorted(fs_distinct_compounds)}")
    print(f"[smoke5] Synth rollup ({n_syn} docs): "
          f"valid={syn_valid}/{n_syn}  "
          f"avg-wave1={syn_avg_wave1:.1f}/24  "
          f"avg-compound={syn_avg_compound:.1f}/10")

    failures: list[str] = []
    if fs_valid < n_fs:
        failures.append(f"F-S pydantic valid={fs_valid}/{n_fs}")
    if syn_valid < n_syn:
        failures.append(f"synth pydantic valid={syn_valid}/{n_syn}")
    if n_fs > 0 and fs_avg_wave1 < 4.0:
        failures.append(f"F-S avg-wave1 {fs_avg_wave1:.1f} < 4.0 "
                        "(Phase 3b baseline was 7.2)")
    # Compound-rule coverage — expect ≥ 3 distinct compound rules fired on F-S.
    if n_fs > 0 and len(fs_distinct_compounds) < 3:
        failures.append(
            f"F-S distinct compound rules fired {len(fs_distinct_compounds)} < 3"
        )

    if failures:
        print(f"[smoke5] FAIL: {'; '.join(failures)}")
        return 3

    print("[smoke5] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
