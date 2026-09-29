"""Phase 6c smoke — MedCAT+rules on synth-v1 held-out 100.

Runs the full extractor + assembler (Phase 4 US adaptation + Phase 5
compound rules enabled by default) on the first N documents from
``data/eval_corpora/synth_v1_eval_100/`` and reports:

- Per-doc EpilepsyPhenotype Pydantic validation.
- Wave-1 24-field population count.
- Compound-rule fire count.
- Section detection (US SOAP headers) counts.
- ConText fire counts (negation / hypothetical / historical flags).

Usage
-----
    venv-medcat/bin/python scripts/smoke_medcat_on_synth_holdout.py [--n 10]

Exit code non-zero on any of: extractor raising, Pydantic failing,
avg-wave1 < 2 (regression floor — synth-v1 pilot smoke was 5.0).
"""

from __future__ import annotations

import argparse
import csv
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
EVAL_ROOT = REPO_ROOT / "data" / "eval_corpora" / "synth_v1_eval_100"

# Same field list as smoke_phase5_pipeline.
WAVE1_FIELDS = [
    ("clinical_seizure", "epilepsy_type"),
    ("clinical_seizure", "predominant_seizure_type"),
    ("clinical_seizure", "seizure_frequency"),
    ("clinical_seizure", "age_at_onset_years"),
    ("clinical_seizure", "etiology_category"),
    ("medication", "current_asms"),
    ("mri", "findings"),
    ("eeg", "ied_findings"),
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


DOC_TYPE_MAP = {
    "progress_note": DocumentType.PROGRESS_NOTE,
    "mri_report": DocumentType.MRI_REPORT,
    "eeg_report": DocumentType.EEG_REPORT,
}


def _is_populated(pheno, module_name, field):
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


def _count_wave1(pheno):
    return sum(1 for m, f in WAVE1_FIELDS if _is_populated(pheno, m, f))


def _count_compound(pheno):
    outcomes = getattr(pheno, "_compound_outcomes", {}) or {}
    hits = [n for n, s in outcomes.items()
            if s not in ("skipped", None) and not str(s).startswith("error")]
    return len(hits), hits


def _count_context_fires(ents) -> tuple[int, int, int]:
    """Return (n_negated, n_hypothetical, n_historical) across all entities."""
    n_neg = sum(1 for e in ents if getattr(e, "is_negated", False))
    n_hyp = sum(1 for e in ents if getattr(e, "is_hypothetical", False))
    n_hist = sum(1 for e in ents if getattr(e, "is_historical", False))
    return n_neg, n_hyp, n_hist


def _load_manifest(n: int) -> list[dict]:
    m = EVAL_ROOT / "manifest.csv"
    if not m.exists():
        raise FileNotFoundError(f"Manifest not found at {m}. Run "
                                "scripts/build_synth_v1_eval_100.py first.")
    with m.open() as fh:
        rows = list(csv.DictReader(fh))
    # Prefer progress_note first (denser than MRI/EEG reports) then rest.
    rows.sort(key=lambda r: (r["doc_type"] != "progress_note", r["id"]))
    return rows[:n]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cdb", default=str(DEFAULT_CDB))
    p.add_argument("--n", type=int, default=10)
    args = p.parse_args(argv)

    print(f"[smoke-synth] Loading MedCAT + medspaCy + Phase 4/5 …")
    extractor = MedCATExtractor(args.cdb, verbose=False)
    assembler = PhenotypeAssembler(extractor)

    rows = _load_manifest(args.n)
    print(f"[smoke-synth] Running on {len(rows)} synth-v1 held-out docs")

    per_doc: list[dict] = []
    for row in rows:
        doc_id = row["id"]
        pid = row["patient_id"]
        doc_type_str = row["doc_type"]
        doc_type = DOC_TYPE_MAP.get(doc_type_str, DocumentType.PROGRESS_NOTE)
        text_path = REPO_ROOT / row["source_path"]
        text = text_path.read_text()

        # Extract raw entities for ConText/section stats.
        ents = extractor.extract(text)
        n_neg, n_hyp, n_hist = _count_context_fires(ents)
        sections = {getattr(e, "section_name", None) for e in ents
                    if getattr(e, "section_name", None)}
        n_sec = len(sections)

        pheno = assembler.process(
            text, doc_id=doc_id, doc_type=doc_type,
            doc_date=date(2020, 1, 1), patient_id=pid,
        )
        try:
            EpilepsyPhenotype.model_validate(pheno.model_dump(mode="json"))
            valid = True
        except Exception as e:
            print(f"[smoke-synth] {doc_id} pydantic re-validate FAIL: {e}")
            valid = False

        n_wave1 = _count_wave1(pheno)
        n_compound, hits = _count_compound(pheno)

        print(f"[smoke-synth] {doc_id:30s} chars={len(text):5d} "
              f"ents={len(ents):3d} wave1={n_wave1}/24 "
              f"compound={n_compound}/10 "
              f"sec={n_sec} ctx(neg/hyp/hist)={n_neg}/{n_hyp}/{n_hist} "
              f"valid={valid}")
        per_doc.append({
            "doc_id": doc_id,
            "valid": valid,
            "n_wave1": n_wave1,
            "n_compound": n_compound,
            "n_ents": len(ents),
            "n_sections": n_sec,
            "n_neg": n_neg,
            "n_hyp": n_hyp,
            "n_hist": n_hist,
            "compound_hits": hits,
        })

    n = len(per_doc)
    if n == 0:
        print("[smoke-synth] FAIL: no docs processed")
        return 2
    n_valid = sum(1 for r in per_doc if r["valid"])
    avg_wave1 = sum(r["n_wave1"] for r in per_doc) / n
    avg_compound = sum(r["n_compound"] for r in per_doc) / n
    zero_field = sum(1 for r in per_doc if r["n_wave1"] == 0)
    docs_with_sections = sum(1 for r in per_doc if r["n_sections"] > 0)
    distinct_compound = set()
    for r in per_doc:
        distinct_compound.update(r["compound_hits"])

    print()
    print(f"[smoke-synth] Summary: {n_valid}/{n} valid   "
          f"avg-wave1={avg_wave1:.1f}/24   "
          f"avg-compound={avg_compound:.1f}/10   "
          f"docs-with-sections={docs_with_sections}/{n}   "
          f"distinct-compound-fired={len(distinct_compound)}/10")
    print(f"[smoke-synth] Docs with 0 wave-1 fields: {zero_field}")
    print(f"[smoke-synth] Compound rules fired (union): {sorted(distinct_compound)}")

    if n_valid < n:
        print(f"[smoke-synth] FAIL: {n - n_valid} docs failed pydantic validation")
        return 3
    if avg_wave1 < 2.0:
        print(f"[smoke-synth] FAIL: avg-wave1 {avg_wave1:.1f} < 2.0 "
              "(regression vs Phase 5 baseline 5.0)")
        return 4

    print("[smoke-synth] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
