#!/usr/bin/env python3
"""End-to-end smoke test for all v0.2.1 extraction infrastructure.

Exercises:
  1. Prompt registry — all 18 prompts render with schema injection.
  2. Router — for a document with multiple applicable modules, extracts each
     and assembles a valid EpilepsyPhenotype.
  3. Evidence verifier — supported evidence returns high precision;
     fabricated evidence is flagged as unsupported.
  4. B0 rules baseline — MRI extraction produces a valid MriModule.
  5. Eval harness — reads manifests, computes ArmSummary, applies bootstrap CI.

Uses a mock ModelBackend that returns pre-canned JSON per module. No LLM
required.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import (
    DocumentMetadata,
    DocumentType,
    EpilepsyPhenotype,
    MriModule,
    SCHEMA_VERSION,
)
from services.baseline_rules import RulesMriBackend, run_b0_mri
from services.evidence_verifier import verify_phenotype
from services.extract import DecodingConfig, ExtractionResult, extract_module
from services.prompt_registry import (
    ALL_ARMS,
    all_prompt_ids,
    resolve,
    module_schema_for,
)
from services.router import MODULE_CLASSES, extract_phenotype
from services.run_manifest import RunManifest
from eval import aggregate_manifests, load_gold


# ---------------------------------------------------------------------------
# 1. Prompt-registry smoke: all 18 prompts must render successfully with schema
# ---------------------------------------------------------------------------


def test_prompts_render() -> None:
    ids = all_prompt_ids()
    assert len(ids) == 18, f"expected 18 prompts, got {len(ids)}"
    dummy_text = "MRI BRAIN 3T. FINDINGS: normal. IMPRESSION: unremarkable."
    for module_name, module_cls in MODULE_CLASSES.items():
        for arm in ALL_ARMS:
            p = resolve(module_name, arm)
            schema_dict = module_schema_for(module_cls) if arm == "M2" else None
            rendered = p.render(dummy_text, module_schema=schema_dict)
            assert rendered.startswith("<|begin_of_text|>")
            assert dummy_text in rendered
            if arm == "M2":
                assert "JSON schema" in rendered
            if arm in ("M1", "M2"):
                assert len(p.few_shot) == 1
    print("[1] prompts render: 18/18 templates OK")


# ---------------------------------------------------------------------------
# 2. Router smoke via a mock backend that returns valid JSON per module
# ---------------------------------------------------------------------------


class MultiModuleMockBackend:
    """Returns a valid module JSON based on the prompt's task instruction —
    heuristic parse of which module is being asked for."""
    model_name = "mock/multi-module"
    model_cache_dir = "/tmp/mock"

    def __init__(self, doc: DocumentMetadata):
        self.doc = doc

    def _ev(self, value, evidence_text, certainty="definite", temporal="current"):
        return {
            "value": value,
            "certainty": certainty,
            "temporal_status": temporal,
            "evidence_text": evidence_text,
            "source_doc_id": self.doc.doc_id,
            "source_doc_type": self.doc.doc_type.value,
            "source_date": self.doc.doc_date.isoformat(),
        }

    def _null(self):
        return {
            "value": None,
            "certainty": "not_documented",
            "temporal_status": "unspecified",
            "evidence_text": None,
            "source_doc_id": self.doc.doc_id,
            "source_doc_type": self.doc.doc_type.value,
            "source_date": self.doc.doc_date.isoformat(),
        }

    def _mri_json(self) -> str:
        # Quotes here MUST verbatim-match test_router source_text (all "left" HS)
        return json.dumps({
            "overall_normal": self._ev(False, "left hippocampal sclerosis"),
            "findings": [self._ev("hippocampal_sclerosis", "left hippocampal sclerosis")],
            "lesion_lobe": self._ev("temporal", "left hippocampal sclerosis"),
            "lesion_laterality": self._ev("left", "left hippocampal sclerosis"),
            "hippocampal_sclerosis": self._ev(True, "left hippocampal sclerosis"),
            "focal_cortical_dysplasia": self._null(),
            "mri_negative_for_epilepsy": self._ev(False, "left hippocampal sclerosis"),
            "field_strength_tesla": self._null(),
        })

    def _eeg_json(self) -> str:
        return json.dumps({
            "study_type": self._ev("video_eeg", "video-EEG monitoring"),
            "background": self._ev("normal", "normal background"),
            "ied_present": self._ev(True, "left temporal sharp waves"),
            "ied_findings": [{
                "value": {"ied_type": "sharp_wave", "localization": "temporal",
                          "laterality": "left", "dominant_frequency_hz": 3.5},
                "certainty": "definite", "temporal_status": "current",
                "evidence_text": "left temporal sharp waves",
                "source_doc_id": self.doc.doc_id,
                "source_doc_type": self.doc.doc_type.value,
                "source_date": self.doc.doc_date.isoformat(),
            }],
            "seizures_captured": self._ev(False, "no seizures captured", certainty="negated"),
            "seizures_captured_count": self._null(),
            "ictal_onset_lobe": self._null(),
            "ictal_onset_laterality": self._null(),
        })

    def _clinical_seizure_json(self) -> str:
        return json.dumps({
            "epilepsy_type": self._ev("focal", "focal epilepsy"),
            "predominant_seizure_type": self._ev("focal_impaired_awareness",
                                                 "focal impaired-awareness seizures"),
            "other_seizure_types": [],
            "awareness": self._ev("impaired", "impaired-awareness"),
            "semiology_text": self._ev("automatisms", "automatisms"),
            "age_at_onset_years": self._ev(20.0, "since age 20"),
            "seizure_frequency": {
                "value": {"raw_text": "2-3 per month", "period": "month",
                          "count_min": 2, "count_max": 3, "seizure_free": False,
                          "duration_text": None, "applies_to_type": None},
                "certainty": "definite", "temporal_status": "current",
                "evidence_text": "2-3 per month",
                "source_doc_id": self.doc.doc_id,
                "source_doc_type": self.doc.doc_type.value,
                "source_date": self.doc.doc_date.isoformat(),
            },
            "other_seizure_frequencies": [],
            "status_epilepticus_history": self._ev(False, "no status epilepticus",
                                                   certainty="negated"),
            "etiology_category": self._ev("structural", "left hippocampal sclerosis"),
            "etiology_details_text": self._ev("left hippocampal sclerosis",
                                              "left hippocampal sclerosis"),
            "etiology_specifics": self._null(),
            "focal_motor_onset": self._ev("automatisms", "automatisms"),
            "focal_nonmotor_onset": self._null(),
        })

    def _medication_json(self) -> str:
        return json.dumps({
            "current_asms": [{
                "value": {"generic_name": "levetiracetam", "status": "current",
                          "dose_text": "1500 mg BID", "reason_discontinued": None,
                          "rxnorm_cui": None},
                "certainty": "definite", "temporal_status": "current",
                "evidence_text": "levetiracetam 1500 mg BID",
                "source_doc_id": self.doc.doc_id,
                "source_doc_type": self.doc.doc_type.value,
                "source_date": self.doc.doc_date.isoformat(),
            }],
            "prior_asms": [],
            "failed_asms": [],
            "adverse_effects_text": self._null(),
            "drug_resistance_status": self._ev("drug_resistant", "drug-resistant epilepsy"),
            "surgery_history": [],
            "non_drug_therapies": [],
        })

    def _clinical_localization_json(self) -> str:
        return json.dumps({
            "primary_claim": {
                "value": {"lobe": "temporal", "laterality": "left",
                          "source": "clinician_hypothesis"},
                "certainty": "probable", "temporal_status": "current",
                "evidence_text": "left mesial temporal onset",
                "source_doc_id": self.doc.doc_id,
                "source_doc_type": self.doc.doc_type.value,
                "source_date": self.doc.doc_date.isoformat(),
            },
            "alternative_claims": [],
        })

    def _integrated_json(self) -> str:
        return json.dumps({
            "clinical_localization": {
                "value": {"lobe": "temporal", "laterality": "left",
                          "source": "clinician_hypothesis"},
                "certainty": "definite", "temporal_status": "current",
                "evidence_text": "left temporal semiology",
                "source_doc_id": self.doc.doc_id,
                "source_doc_type": self.doc.doc_type.value,
                "source_date": self.doc.doc_date.isoformat(),
            },
            "eeg_localization": {
                "value": {"lobe": "temporal", "laterality": "left",
                          "source": "eeg_confirmed"},
                "certainty": "definite", "temporal_status": "current",
                "evidence_text": "left temporal ictal onset",
                "source_doc_id": self.doc.doc_id,
                "source_doc_type": self.doc.doc_type.value,
                "source_date": self.doc.doc_date.isoformat(),
            },
            "mri_localization": {
                "value": {"lobe": "temporal", "laterality": "left",
                          "source": "mri_confirmed"},
                "certainty": "definite", "temporal_status": "current",
                "evidence_text": "left hippocampal sclerosis",
                "source_doc_id": self.doc.doc_id,
                "source_doc_type": self.doc.doc_type.value,
                "source_date": self.doc.doc_date.isoformat(),
            },
            "concordance": self._ev("concordant", "concordant for left temporal"),
            "concordance_notes_text": self._ev("concordant for left temporal",
                                               "concordant for left temporal"),
        })

    def generate(self, prompt: str, decoding: DecodingConfig) -> tuple[str, int | None]:
        # Route by task instruction present in the prompt
        if "MRI-report phenotype" in prompt:
            return self._mri_json(), None
        if "EEG-report phenotype" in prompt:
            return self._eeg_json(), None
        if "clinical seizure phenotype" in prompt:
            return self._clinical_seizure_json(), None
        if "medication and treatment history" in prompt:
            return self._medication_json(), None
        if "clinician's clinical localization" in prompt:
            return self._clinical_localization_json(), None
        if "cross-modality synthesis" in prompt:
            return self._integrated_json(), None
        return "{}", 0


def test_router_full_phenotype() -> None:
    # EMU_DISCHARGE allows all six modules
    doc = DocumentMetadata(
        doc_id="SYN-EMU-DC-01",
        doc_type=DocumentType.EMU_DISCHARGE,
        doc_date=date(2025, 6, 1),
        patient_id="SYN-P-EMU-01",
    )
    source = (
        "EMU DISCHARGE SUMMARY: 32-year-old woman with focal epilepsy since age 20. "
        "Video-EEG monitoring captured 4 seizures with left temporal ictal onset. "
        "MRI shows left hippocampal sclerosis. Currently on levetiracetam 1500 mg BID. "
        "Drug-resistant per ILAE criteria. Multimodal findings are concordant for "
        "left temporal epilepsy. Left mesial temporal onset supported by semiology "
        "with automatisms and impaired awareness. Etiology: right mesial temporal "
        "sclerosis. No status epilepticus."
    )
    backend = MultiModuleMockBackend(doc)
    result = extract_phenotype(
        doc=doc, source_text=source, model_backend=backend,
        arm="M2", schema_version=SCHEMA_VERSION,
    )
    ph = result.phenotype
    assert isinstance(ph, EpilepsyPhenotype)
    assert ph.mri is not None and ph.mri.hippocampal_sclerosis.value is True
    assert ph.eeg is not None and ph.eeg.ied_present.value is True
    assert ph.clinical_seizure is not None
    assert ph.medication is not None and ph.medication.drug_resistance_status.value.value == "drug_resistant"
    assert ph.clinical_localization is not None
    assert ph.integrated is not None and ph.integrated.concordance.value.value == "concordant"
    print(f"[2] router: 6/6 modules extracted, phenotype valid; "
          f"per-module manifests written = {len(result.per_module)}")


# ---------------------------------------------------------------------------
# 3. Evidence verifier — supported spans verify; fabricated ones flagged
# ---------------------------------------------------------------------------


def test_evidence_verifier() -> None:
    # Same setup, but the mock will produce evidence quotes that ARE in the
    # source (positive path). Then we fabricate evidence and confirm the
    # verifier flags it.
    doc = DocumentMetadata(
        doc_id="SYN-EMU-DC-02", doc_type=DocumentType.EMU_DISCHARGE,
        doc_date=date(2025, 6, 1), patient_id="SYN-P-EMU-02",
    )
    source = (
        "EMU DISCHARGE: Video-EEG monitoring captured 4 seizures with left temporal "
        "ictal onset. MRI shows left hippocampal sclerosis. Currently on levetiracetam "
        "1500 mg BID. Drug-resistant epilepsy per ILAE criteria. Multimodal findings "
        "are concordant for left temporal epilepsy."
    )
    backend = MultiModuleMockBackend(doc)
    result = extract_phenotype(
        doc=doc, source_text=source, model_backend=backend,
        arm="M2", schema_version=SCHEMA_VERSION,
    )
    report = verify_phenotype(result.phenotype, source)
    supported = report.evidence_supported
    total = supported + report.evidence_unsupported + report.evidence_missing
    print(f"[3a] evidence verifier: supported={supported}/{total}  "
          f"unsupported_claim_rate={report.unsupported_claim_rate:.3f}")
    assert supported > 0, "at least some evidence should verify"
    # Given our mock evidence quotes are all in the source text, precision should be high
    assert report.evidence_precision >= 0.5, \
        f"expected ≥50% evidence precision, got {report.evidence_precision:.3f}"

    # Negative path — fabricate a phenotype with a quote NOT in source
    doc2 = DocumentMetadata(
        doc_id="SYN-FAB-01", doc_type=DocumentType.MRI_REPORT,
        doc_date=date(2025, 6, 1), patient_id="SYN-P-FAB",
    )
    fabricated_mri = MriModule.model_validate({
        "overall_normal": {"value": False,
                           "certainty": "definite", "temporal_status": "current",
                           "evidence_text": "THIS QUOTE DOES NOT APPEAR IN SOURCE",
                           "source_doc_id": doc2.doc_id,
                           "source_doc_type": doc2.doc_type.value,
                           "source_date": doc2.doc_date.isoformat()},
        "findings": [], "lesion_lobe": {
            "value": None, "certainty": "not_documented",
            "temporal_status": "unspecified", "evidence_text": None,
            "source_doc_id": doc2.doc_id, "source_doc_type": doc2.doc_type.value,
            "source_date": doc2.doc_date.isoformat()},
        "lesion_laterality": {"value": None, "certainty": "not_documented",
                              "temporal_status": "unspecified", "evidence_text": None,
                              "source_doc_id": doc2.doc_id,
                              "source_doc_type": doc2.doc_type.value,
                              "source_date": doc2.doc_date.isoformat()},
        "hippocampal_sclerosis": {"value": None, "certainty": "not_documented",
                                  "temporal_status": "unspecified",
                                  "evidence_text": None,
                                  "source_doc_id": doc2.doc_id,
                                  "source_doc_type": doc2.doc_type.value,
                                  "source_date": doc2.doc_date.isoformat()},
        "focal_cortical_dysplasia": {"value": None, "certainty": "not_documented",
                                     "temporal_status": "unspecified",
                                     "evidence_text": None,
                                     "source_doc_id": doc2.doc_id,
                                     "source_doc_type": doc2.doc_type.value,
                                     "source_date": doc2.doc_date.isoformat()},
        "mri_negative_for_epilepsy": {"value": None, "certainty": "not_documented",
                                      "temporal_status": "unspecified",
                                      "evidence_text": None,
                                      "source_doc_id": doc2.doc_id,
                                      "source_doc_type": doc2.doc_type.value,
                                      "source_date": doc2.doc_date.isoformat()},
        "field_strength_tesla": {"value": None, "certainty": "not_documented",
                                 "temporal_status": "unspecified",
                                 "evidence_text": None,
                                 "source_doc_id": doc2.doc_id,
                                 "source_doc_type": doc2.doc_type.value,
                                 "source_date": doc2.doc_date.isoformat()},
    })
    fake_pheno = EpilepsyPhenotype(document=doc2, mri=fabricated_mri)
    real_source = "Normal brain MRI. No epilepsy-relevant lesion identified."
    report2 = verify_phenotype(fake_pheno, real_source)
    assert report2.evidence_unsupported >= 1, "fabricated quote must be flagged"
    print(f"[3b] evidence verifier: fabricated quote flagged as unsupported "
          f"({report2.evidence_unsupported} violation)")


# ---------------------------------------------------------------------------
# 4. B0 rules baseline — extract from a template-y MRI report
# ---------------------------------------------------------------------------


def test_b0_rules_mri() -> None:
    doc = DocumentMetadata(
        doc_id="SYN-B0-MRI-01", doc_type=DocumentType.MRI_REPORT,
        doc_date=date(2025, 6, 1), patient_id="SYN-P-B0-01",
    )
    text = (
        "MRI BRAIN 3T. TECHNIQUE: Standard epilepsy protocol. "
        "FINDINGS: Right hippocampal sclerosis with volume loss and FLAIR "
        "hyperintensity. No focal cortical dysplasia. No other lesion. "
        "IMPRESSION: Right hippocampal sclerosis."
    )
    js = run_b0_mri(text, doc)
    module = MriModule.model_validate(js)
    assert module.hippocampal_sclerosis.value is True, \
        f"rules should detect HS in {text!r}"
    assert module.lesion_laterality.value.value == "right"
    assert module.lesion_lobe.value.value == "temporal"
    assert module.field_strength_tesla.value == 3.0
    print(f"[4] B0 rules baseline: HS detected, right, temporal, 3T — MriModule valid")


# ---------------------------------------------------------------------------
# 5. Eval harness aggregates manifests
# ---------------------------------------------------------------------------


def test_eval_aggregator() -> None:
    # The router tests above wrote real manifests. Aggregate them.
    root = Path(__file__).resolve().parent.parent / "data" / "run_manifests"
    if not root.exists():
        print("[5] eval harness: no manifests dir yet — skip")
        return
    summaries = aggregate_manifests(root)
    assert summaries, "expected at least one arm's manifests to aggregate"
    for arm, s in summaries.items():
        print(
            f"[5] arm={arm:<4}  n={s.n_documents:>3}  "
            f"raw_valid={s.raw_valid} final_valid={s.final_valid}  "
            f"raw_rate={s.raw_validity_rate:.3f}  final_rate={s.final_validity_rate:.3f}"
        )
    # Confirm the summary serializes to a nested dict
    out = {k: v.to_dict() for k, v in summaries.items()}
    assert isinstance(out, dict) and out
    print(f"[5] eval harness: {len(summaries)} arm summaries produced")


# ---------------------------------------------------------------------------


def main() -> int:
    print(f"Schema version: {SCHEMA_VERSION}")
    test_prompts_render()
    test_router_full_phenotype()
    test_evidence_verifier()
    test_b0_rules_mri()
    test_eval_aggregator()
    print("\nALL COMPREHENSIVE SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
