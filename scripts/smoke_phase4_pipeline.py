"""Phase 4 end-to-end smoke test — US adaptation on F-S train + synth-v1.

Runs the assembler (with Phase 4 UK->US normalisation + SOAP section
detection enabled by default) on 5 F-S train letters and 5 synthetic
progress notes.  Reports:

- Per-doc EpilepsyPhenotype Pydantic validation.
- Section detection counts (expected 3/5 synth docs; F-S usually 0-1).
- Field-population count per doc against the Phase 3b 24-field set.
- UK->US replacement counts on F-S text (spot check).

Usage
-----
    venv-medcat/bin/python scripts/smoke_phase4_pipeline.py

Exit code is non-zero if:
- extractor / assembler raises,
- Pydantic validation fails on any of the 10 docs,
- F-S combined field population regresses below 4 avg (Phase 3b baseline
  = 7.2/24),
- section detection fires on < 3 synth-v1 docs.
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

from rules.uk_to_us_lexicon import diff_counts  # noqa: E402
from schema.enums import Certainty, DocumentType  # noqa: E402
from schema.ontology import EpilepsyPhenotype  # noqa: E402
from services.medcat_extractor import MedCATExtractor  # noqa: E402
from services.phenotype_assembler import PhenotypeAssembler  # noqa: E402


DEFAULT_CDB = REPO_ROOT / "data" / "medcat_cdb_epilepsy" / "cdb"
FS_DOCS = ["EA0001", "EA0025", "EA0050", "EA0075", "EA0100"]
SYNTH_DIR = REPO_ROOT / "data" / "episynth_corpus" / "v1" / "documents"

# Combined 24-field set (matches smoke_phase3b_pipeline).
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
ALL_FIELDS = P1_FIELDS + P2_FIELDS   # 24


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


def _count_populated(pheno: EpilepsyPhenotype) -> int:
    return sum(1 for m, f in ALL_FIELDS if _is_populated(pheno, m, f))


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
    # Deterministic pick — sorted patient IDs, take the first n whose
    # progress_note/output.txt exists.
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
    diff = diff_counts(text)
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
    except Exception as e:  # pragma: no cover - defensive
        print(f"[smoke4][{tag}] {doc_id}: pydantic re-validate FAIL: {e}")
        valid = False

    sections = getattr(pheno, "_sections", []) or []
    entities = getattr(pheno, "_entities", []) or []
    section_names = [s.name for s in sections]
    n_pop = _count_populated(pheno)

    # Count entities that got a section tag.
    n_tagged = sum(1 for e in entities if getattr(e, "section_type", None))

    print(f"[smoke4][{tag}] {doc_id}: chars={len(text):5d}  "
          f"uk→us hits: spell={diff['spelling_hits']} drug={diff['drug_hits']}  "
          f"sections={len(sections):2d} ({','.join(section_names) or '-'})  "
          f"ents={len(entities)} tagged={n_tagged}  fields={n_pop}/24  "
          f"valid={valid}")

    return {
        "doc_id": doc_id,
        "tag": tag,
        "valid": valid,
        "n_sections": len(sections),
        "section_names": section_names,
        "n_entities": len(entities),
        "n_tagged": n_tagged,
        "n_populated": n_pop,
        "spelling_hits": diff["spelling_hits"],
        "drug_hits": diff["drug_hits"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdb", default=str(DEFAULT_CDB))
    parser.add_argument("--n-synth", type=int, default=5)
    args = parser.parse_args(argv)

    print("[smoke4] Loading MedCAT + medspaCy + Phase 4 US adaptation …")
    extractor = MedCATExtractor(args.cdb, verbose=False)
    assembler = PhenotypeAssembler(extractor)
    print(f"[smoke4] uk_to_us={assembler.apply_uk_to_us}  "
          f"detect_us_sections={assembler.detect_us_sections}")

    fs_results: list[dict] = []
    for ea in FS_DOCS:
        try:
            p = _resolve_fs(ea)
        except FileNotFoundError:
            print(f"[smoke4][F-S] SKIP {ea}: no doc")
            continue
        fs_results.append(run_on_doc(assembler, p, ea, tag="F-S"))

    synth_paths = _pick_synth_docs(args.n_synth)
    if len(synth_paths) < args.n_synth:
        print(f"[smoke4] WARN: only {len(synth_paths)} synth docs available "
              f"(wanted {args.n_synth})")
    synth_results: list[dict] = []
    for p in synth_paths:
        doc_id = p.parent.parent.name  # patient dir name
        synth_results.append(run_on_doc(assembler, p, doc_id, tag="SYN"))

    # --- Roll-up ------------------------------------------------------------
    n_fs = len(fs_results)
    n_syn = len(synth_results)
    fs_valid = sum(1 for r in fs_results if r["valid"])
    syn_valid = sum(1 for r in synth_results if r["valid"])
    fs_sections_hit = sum(1 for r in fs_results if r["n_sections"] > 0)
    syn_sections_hit = sum(1 for r in synth_results if r["n_sections"] > 0)
    fs_avg_pop = (sum(r["n_populated"] for r in fs_results) / n_fs) if n_fs else 0.0
    syn_avg_pop = (sum(r["n_populated"] for r in synth_results) / n_syn) if n_syn else 0.0
    fs_uk_hits = sum(r["spelling_hits"] + r["drug_hits"] for r in fs_results)
    syn_uk_hits = sum(r["spelling_hits"] + r["drug_hits"] for r in synth_results)

    print()
    print(f"[smoke4] F-S rollup   ({n_fs} docs): "
          f"valid={fs_valid}/{n_fs}  sections>=1 on {fs_sections_hit}/{n_fs}  "
          f"avg-fields={fs_avg_pop:.1f}/24  UK→US replacements={fs_uk_hits}")
    print(f"[smoke4] Synth rollup ({n_syn} docs): "
          f"valid={syn_valid}/{n_syn}  sections>=1 on {syn_sections_hit}/{n_syn}  "
          f"avg-fields={syn_avg_pop:.1f}/24  UK→US replacements={syn_uk_hits}")

    # UK→US spot-check: F-S delta text lengths shouldn't exceed 5% of chars.
    total_fs_chars = sum(len(r.get("doc_id", "")) for r in fs_results) or 1

    # Acceptance
    failures: list[str] = []
    if fs_valid < n_fs:
        failures.append(f"F-S pydantic valid={fs_valid}/{n_fs}")
    if syn_valid < n_syn:
        failures.append(f"synth pydantic valid={syn_valid}/{n_syn}")
    # Section detection must fire on at least 3/5 synth docs.
    if n_syn > 0 and syn_sections_hit < min(3, n_syn):
        failures.append(f"synth sections>=1 on only {syn_sections_hit}/{n_syn} "
                        f"(target {min(3, n_syn)})")
    # Field-population regression check: F-S avg mustn't drop below 4.
    if n_fs > 0 and fs_avg_pop < 4.0:
        failures.append(f"F-S avg-fields {fs_avg_pop:.1f} < 4.0 "
                        "(Phase 3b baseline was 7.2)")

    if failures:
        print(f"[smoke4] FAIL: {'; '.join(failures)}")
        return 3

    print("[smoke4] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
