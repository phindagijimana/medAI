"""Phase 5 end-to-end smoke test - compound / relational rule firings.

Runs the assembler on 5 F-S train letters and 5 synthetic progress notes
and reports which of the ten `rules.compound` compound / relational
rules populated their target field (or `pheno._derived` slot).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from loguru import logger as _lg
    _lg.remove()
except Exception:
    pass

from schema.enums import Certainty, DocumentType, DrugResistanceStatus  # noqa: E402
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
ALL_FIELDS = P1_FIELDS + P2_FIELDS

COMPOUND_RULE_NAMES = [
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


def _count_populated(pheno):
    return sum(1 for m, f in ALL_FIELDS if _is_populated(pheno, m, f))


def _resolve_fs(ea):
    p = REPO_ROOT / "data" / "fs_corpus" / "documents" / ea / \
        "progress_note" / "output.txt"
    if not p.exists():
        raise FileNotFoundError(str(p))
    return p


def _pick_synth_docs(n):
    out = []
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


def _compound_fired(pheno, rule_name):
    outcomes = getattr(pheno, "_compound_outcomes", {}) or {}
    tag = outcomes.get(rule_name)
    return tag in ("populated", "mutated")


def run_on_doc(assembler, path, doc_id, tag):
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
    except Exception as e:
        print("[smoke5][%s] %s: pydantic re-validate FAIL: %s" % (tag, doc_id, e))
        valid = False

    n_pop = _count_populated(pheno)
    outcomes = getattr(pheno, "_compound_outcomes", {}) or {}
    fired = [n for n in COMPOUND_RULE_NAMES if _compound_fired(pheno, n)]
    n_fired = len(fired)

    dr_status = None
    if pheno.medication is not None and pheno.medication.drug_resistance_status is not None:
        v = pheno.medication.drug_resistance_status.value
        dr_status = v.value if v is not None else None

    print("[smoke5][%s] %s: chars=%5d  fields=%d/24  compound-fired=%d/10  DR=%s  valid=%s"
          % (tag, doc_id, len(text), n_pop, n_fired, dr_status or "-", valid))
    print("[smoke5][%s]   fired: %s" % (tag, ", ".join(fired) or "(none)"))

    return {
        "doc_id": doc_id,
        "tag": tag,
        "valid": valid,
        "n_populated": n_pop,
        "n_compound_fired": n_fired,
        "fired_rules": fired,
        "outcomes": outcomes,
        "dr_status": dr_status,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdb", default=str(DEFAULT_CDB))
    parser.add_argument("--n-synth", type=int, default=5)
    args = parser.parse_args(argv)

    print("[smoke5] Loading MedCAT + medspaCy + Phase 5 compound rules ...")
    extractor = MedCATExtractor(args.cdb, verbose=False)
    assembler = PhenotypeAssembler(extractor)

    fs_results = []
    for ea in FS_DOCS:
        try:
            p = _resolve_fs(ea)
        except FileNotFoundError:
            print("[smoke5][F-S] SKIP %s: no doc" % ea)
            continue
        fs_results.append(run_on_doc(assembler, p, ea, tag="F-S"))

    synth_paths = _pick_synth_docs(args.n_synth)
    if len(synth_paths) < args.n_synth:
        print("[smoke5] WARN: only %d synth docs available (wanted %d)"
              % (len(synth_paths), args.n_synth))
    synth_results = []
    for p in synth_paths:
        doc_id = p.parent.parent.name
        synth_results.append(run_on_doc(assembler, p, doc_id, tag="SYN"))

    all_results = fs_results + synth_results

    per_rule_fs = {n: 0 for n in COMPOUND_RULE_NAMES}
    per_rule_syn = {n: 0 for n in COMPOUND_RULE_NAMES}
    for r in fs_results:
        for n in r["fired_rules"]:
            per_rule_fs[n] += 1
    for r in synth_results:
        for n in r["fired_rules"]:
            per_rule_syn[n] += 1

    n_fs = len(fs_results)
    n_syn = len(synth_results)
    fs_valid = sum(1 for r in fs_results if r["valid"])
    syn_valid = sum(1 for r in synth_results if r["valid"])
    fs_avg_pop = (sum(r["n_populated"] for r in fs_results) / n_fs) if n_fs else 0.0
    syn_avg_pop = (sum(r["n_populated"] for r in synth_results) / n_syn) if n_syn else 0.0
    total_firings = sum(r["n_compound_fired"] for r in all_results)

    print()
    print("[smoke5] Per-compound-rule firings (F-S / Synth):")
    for n in COMPOUND_RULE_NAMES:
        print("[smoke5]   %-40s F-S %d/%d   SYN %d/%d"
              % (n, per_rule_fs[n], n_fs, per_rule_syn[n], n_syn))

    print()
    print("[smoke5] F-S rollup   (%d docs): valid=%d/%d  avg-fields=%.1f/24"
          % (n_fs, fs_valid, n_fs, fs_avg_pop))
    print("[smoke5] Synth rollup (%d docs): valid=%d/%d  avg-fields=%.1f/24"
          % (n_syn, syn_valid, n_syn, syn_avg_pop))
    print("[smoke5] Cumulative compound firings across %d docs: %d"
          % (len(all_results), total_firings))

    ea0075 = next((r for r in fs_results if r["doc_id"] == "EA0075"), None)
    ea0075_dr = ea0075["dr_status"] if ea0075 is not None else None
    n_rules_fs_hit = sum(1 for n in COMPOUND_RULE_NAMES if per_rule_fs[n] >= 1)

    failures = []
    if fs_valid < n_fs:
        failures.append("F-S pydantic valid=%d/%d" % (fs_valid, n_fs))
    if syn_valid < n_syn:
        failures.append("synth pydantic valid=%d/%d" % (syn_valid, n_syn))
    if n_fs > 0 and fs_avg_pop < 4.0:
        failures.append("F-S avg-fields %.1f < 4.0 (Phase 3b baseline 7.2)" % fs_avg_pop)
    if n_rules_fs_hit < 3:
        failures.append("only %d/10 compound rules fired on >=1 F-S doc (target >=3)"
                        % n_rules_fs_hit)
    if ea0075 is not None and ea0075_dr != DrugResistanceStatus.DRUG_RESISTANT.value:
        failures.append("EA0075 drug_resistance_status = %r (expected drug_resistant)"
                        % ea0075_dr)

    if failures:
        print("[smoke5] FAIL: %s" % "; ".join(failures))
        return 3

    print("[smoke5] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
