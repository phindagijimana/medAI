"""Phase 6b smoke — MedCAT+rules on MTSamples neurology.

Runs the extractor + assembler on the first N kept notes from
``data/eval_corpora/mtsamples_neuro/`` and reports:

- Per-doc EpilepsyPhenotype Pydantic validation.
- Wave-1 24-field population count.
- Compound-rule fire count.
- US SOAP section-header detection (n distinct sections per doc).
- ConText fires (negation, hypothetical, historical).

Usage
-----
    venv-medcat/bin/python scripts/smoke_medcat_on_mtsamples.py [--n 10]

Exit non-zero on: no MTSamples fetched yet, extractor raising,
Pydantic failing.
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

try:  # silence PyRuSH
    from loguru import logger as _lg
    _lg.remove()
except Exception:
    pass

from schema.enums import Certainty, DocumentType  # noqa: E402
from schema.ontology import EpilepsyPhenotype  # noqa: E402
from services.medcat_extractor import MedCATExtractor  # noqa: E402
from services.phenotype_assembler import PhenotypeAssembler  # noqa: E402


DEFAULT_CDB = REPO_ROOT / "data" / "medcat_cdb_epilepsy" / "cdb"
CORPUS_ROOT = REPO_ROOT / "data" / "eval_corpora" / "mtsamples_neuro"


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


def _is_populated(pheno, mn, f):
    mod = getattr(pheno, mn, None)
    if mod is None:
        return False
    v = getattr(mod, f, None)
    if v is None:
        return False
    if isinstance(v, list):
        if len(v) > 0:
            return True
        if mn == "mri" and f == "findings":
            for sib in ("overall_normal", "mri_negative_for_epilepsy",
                        "hippocampal_sclerosis", "focal_cortical_dysplasia"):
                s = getattr(mod, sib, None)
                if s is not None and getattr(s, "value", None) is not None \
                   and getattr(s, "certainty", None) != Certainty.NOT_DOCUMENTED:
                    return True
        if mn == "eeg" and f == "ied_findings":
            for sib in ("background", "ied_present"):
                s = getattr(mod, sib, None)
                if s is not None and getattr(s, "value", None) is not None \
                   and getattr(s, "certainty", None) != Certainty.NOT_DOCUMENTED:
                    return True
        return False
    return (getattr(v, "value", None) is not None and
            getattr(v, "certainty", None) != Certainty.NOT_DOCUMENTED)


def _count_wave1(pheno):
    return sum(1 for m, f in WAVE1_FIELDS if _is_populated(pheno, m, f))


def _count_compound(pheno):
    out = getattr(pheno, "_compound_outcomes", {}) or {}
    hits = [n for n, s in out.items()
            if s not in ("skipped", None) and not str(s).startswith("error")]
    return len(hits), hits


def _context_fires(ents):
    n_neg = sum(1 for e in ents if getattr(e, "is_negated", False))
    n_hyp = sum(1 for e in ents if getattr(e, "is_hypothetical", False))
    n_hist = sum(1 for e in ents if getattr(e, "is_historical", False))
    return n_neg, n_hyp, n_hist


def _load_manifest(n: int) -> list[dict]:
    m = CORPUS_ROOT / "manifest.csv"
    if not m.exists():
        raise FileNotFoundError(
            f"Manifest not found at {m}. Run "
            "scripts/fetch_mtsamples_neuro.py first."
        )
    with m.open() as fh:
        rows = list(csv.DictReader(fh))
    return rows[:n]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cdb", default=str(DEFAULT_CDB))
    p.add_argument("--n", type=int, default=10)
    args = p.parse_args(argv)

    print(f"[smoke-mt] Loading MedCAT + medspaCy + Phase 4/5 …")
    extractor = MedCATExtractor(args.cdb, verbose=False)
    assembler = PhenotypeAssembler(extractor)

    rows = _load_manifest(args.n)
    print(f"[smoke-mt] Running on {len(rows)} MTSamples notes")

    per_doc: list[dict] = []
    for row in rows:
        doc_id = row["id"]
        text_path = CORPUS_ROOT / doc_id / "note.txt"
        text = text_path.read_text()
        ents = extractor.extract(text)
        n_neg, n_hyp, n_hist = _context_fires(ents)
        sections = {getattr(e, "section_name", None) for e in ents
                    if getattr(e, "section_name", None)}
        n_sec = len(sections)

        pheno = assembler.process(
            text, doc_id=doc_id, doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=date(2020, 1, 1), patient_id=doc_id,
        )
        try:
            EpilepsyPhenotype.model_validate(pheno.model_dump(mode="json"))
            valid = True
        except Exception as e:
            print(f"[smoke-mt] {doc_id} pydantic re-validate FAIL: {e}")
            valid = False

        n_wave1 = _count_wave1(pheno)
        n_compound, hits = _count_compound(pheno)

        print(f"[smoke-mt] {doc_id:15s} chars={len(text):5d} ents={len(ents):3d} "
              f"wave1={n_wave1}/24 compound={n_compound}/10 "
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
        print("[smoke-mt] FAIL: no notes to process (fetch first)")
        return 2
    n_valid = sum(1 for r in per_doc if r["valid"])
    avg_wave1 = sum(r["n_wave1"] for r in per_doc) / n
    avg_compound = sum(r["n_compound"] for r in per_doc) / n
    docs_with_sections = sum(1 for r in per_doc if r["n_sections"] > 0)
    distinct = set()
    for r in per_doc:
        distinct.update(r["compound_hits"])
    zero_field = sum(1 for r in per_doc if r["n_wave1"] == 0)

    print()
    print(f"[smoke-mt] Summary: {n_valid}/{n} valid   "
          f"avg-wave1={avg_wave1:.1f}/24   "
          f"avg-compound={avg_compound:.1f}/10   "
          f"docs-with-sections={docs_with_sections}/{n}   "
          f"distinct-compound-fired={len(distinct)}/10")
    print(f"[smoke-mt] Docs with 0 wave-1 fields: {zero_field}")

    if n_valid < n:
        print(f"[smoke-mt] FAIL: {n - n_valid} docs failed pydantic")
        return 3
    print("[smoke-mt] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
