"""Versioned prompt registry for MedAI-EPI extraction (paper §10, §20, Table 9).

Prompts are addressed by `(module_name, arm, version)`. `doc_type` is stored
for documentation but the same prompt template applies to any doc_type where
the module is applicable per the applicability mask. Use `resolve()` for the
canonical lookup and `for_arm()` for exact filtering.

Arms per paper Table 6:
  M0 — zero-shot: instruction + doc, no examples
  M1 — few-shot: M0 + 1 fixed synthetic demonstration
  M2 — few-shot + schema-constrained: M1 + JSON schema injected in prompt
       (post-hoc validate/repair preserves raw-vs-repaired validity per §11)

All prompts explicitly forbid diagnosis / clinical advice per §21.
Few-shot examples are synthetic; not drawn from patient data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from schema import DocumentType


ARM_M0 = "M0"
ARM_M1 = "M1"
ARM_M2 = "M2"
ALL_ARMS = (ARM_M0, ARM_M1, ARM_M2)


@dataclass(frozen=True)
class FewShotExample:
    example_id: str
    document_excerpt: str
    expected_json: dict[str, Any]


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    doc_type: DocumentType                # canonical doc_type for docs; module may apply to more
    module_name: str
    arm: str
    version: str
    system_prompt: str
    task_instruction: str
    output_directives: str
    few_shot: tuple[FewShotExample, ...] = field(default_factory=tuple)
    rationale: str = ""

    def render(self, source_text: str, module_schema: dict | None = None) -> str:
        parts: list[str] = ["<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"]
        parts.append(self.system_prompt.strip())
        parts.append("\n\n" + self.task_instruction.strip())
        if module_schema is not None:
            parts.append(
                "\n\nThe output MUST be a JSON object conforming to this JSON schema:\n\n"
                "```json\n" + json.dumps(module_schema, indent=2) + "\n```"
            )
        parts.append("\n\n" + self.output_directives.strip())
        parts.append("<|eot_id|>")
        for ex in self.few_shot:
            parts.append("<|start_header_id|>user<|end_header_id|>\n\n")
            parts.append(f"DOCUMENT:\n{ex.document_excerpt.strip()}<|eot_id|>")
            parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
            parts.append(json.dumps(ex.expected_json, indent=2))
            parts.append("<|eot_id|>")
        parts.append("<|start_header_id|>user<|end_header_id|>\n\n")
        parts.append(f"DOCUMENT:\n{source_text.strip()}<|eot_id|>")
        parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
        return "".join(parts)


# ---------------------------------------------------------------------------
# Shared preambles (§21 language)
# ---------------------------------------------------------------------------

_ROLE_PREAMBLE = """You are a clinical information extraction assistant for a research phenotyping study.
Your job is to read a clinical document and extract structured phenotype fields exactly as documented.

Ground rules (do NOT violate):
- Do not diagnose. Do not recommend treatment. Do not infer beyond the document.
- If a field is not mentioned in the document, output value=null with certainty="not_documented" and evidence_text=null.
- If a field is stated as unknown, output value=null with certainty="unknown" and quote the relevant span in evidence_text.
- Every non-null value MUST have evidence_text that is a verbatim minimal-sufficient quote from the document.
- Use the canonical enum values exactly as listed; do not invent values.
- Do not convert "no clear lateralization" to a specific side."""


_OUTPUT_DIRECTIVES_M0M1 = """Output format:
- One JSON object on a single line, no surrounding prose, no code fences.
- All fields required by the schema must appear. Use null / "not_documented" for absent fields.
- Do not include any keys outside the schema."""


_OUTPUT_DIRECTIVES_M2 = """Output format:
- Exactly one JSON object that conforms to the schema shown above.
- No prose. No code fences. No comments.
- Every extra key or missing required key will be rejected.
- Preserve the exact enum spelling.
- evidence_text must be a substring of the document verbatim."""


# ---------------------------------------------------------------------------
# Per-module task instructions
# ---------------------------------------------------------------------------

_TASK_MRI = """Task: extract structured MRI-report phenotype fields for a research epilepsy study.
Focus on: overall_normal, findings list (from the canonical MriFinding enum),
lesion_lobe, lesion_laterality, hippocampal_sclerosis boolean, focal_cortical_dysplasia
boolean, mri_negative_for_epilepsy boolean, field_strength_tesla."""

_TASK_EEG = """Task: extract structured EEG-report phenotype fields.
Focus on: study_type (routine/prolonged/ambulatory/video_eeg/emu/intraoperative/seeg/ecog),
background, ied_present bool, ied_findings list (each with ied_type, optional
localization + laterality + dominant_frequency_hz), seizures_captured bool,
seizures_captured_count int, ictal_onset_lobe, ictal_onset_laterality."""

_TASK_CLINICAL_SEIZURE = """Task: extract clinical seizure phenotype from a clinical note.
Focus on: epilepsy_type (focal/generalized/combined/unknown, ILAE 2017),
predominant_seizure_type + other_seizure_types (ILAE 2017), awareness,
semiology_text, age_at_onset_years, seizure_frequency (with duration_text
and applies_to_type when multiple types coexist), status_epilepticus_history,
etiology_category (structural/genetic/infectious/immune/metabolic/unknown),
etiology_details_text, etiology_specifics (structured slots for gene, variant,
autoantibody, tumor, pathogen, metabolic condition), focal_motor_onset and
focal_nonmotor_onset (ILAE 2017 subtypes) when the seizure type is focal."""

_TASK_MEDICATION = """Task: extract medication and treatment history for a research phenotyping study.
Focus on: current_asms, prior_asms, failed_asms (each with generic_name,
status, dose_text, optional reason_discontinued and rxnorm_cui),
adverse_effects_text, drug_resistance_status (ILAE 2010 definition:
failure of two tolerated appropriately chosen ASM schedules),
surgery_history (each with surgery_type, target, laterality, year,
outcome_text, engel_class, ilae_outcome, device_model_text,
stimulation_parameters_text, pathology_notes_text),
non_drug_therapies (ketogenic diet, IVIG, plasmapheresis, steroids, etc.)."""

_TASK_CLINICAL_LOC = """Task: extract the clinician's clinical localization hypothesis.
This is the localization the clinician infers from history and semiology
BEFORE integrating imaging / EEG findings (those live in their own modules).
Focus on: primary_claim (LobarClaim with lobe, laterality, source=clinician_hypothesis),
alternative_claims list for differential possibilities the clinician explicitly names.
Do not synthesize from imaging or EEG here — that belongs in the integrated module."""

_TASK_INTEGRATED = """Task: extract cross-modality synthesis / concordance statements from a document
that itself integrates clinical, EEG, and MRI findings (typically presurgical
evaluation, EMU discharge summary, or surgery conference note).
Focus on: clinical_localization, eeg_localization, mri_localization
(each a LobarClaim with lobe, laterality, and appropriate source),
concordance (concordant/partially_concordant/discordant/not_assessed —
only when the document explicitly discusses concordance; do not infer),
concordance_notes_text."""


# ---------------------------------------------------------------------------
# Few-shot examples (one per module — synthetic, patient-leakage-safe)
# ---------------------------------------------------------------------------

_DOC = {
    "doc_id": "SYN-EX-01",
    "doc_type": "mri_report",
    "source_date": "2025-01-01",
}


def _ev(value, evidence_text, doc_id, doc_type, source_date,
        certainty="definite", temporal_status="current"):
    return {
        "value": value,
        "certainty": certainty,
        "temporal_status": temporal_status,
        "evidence_text": evidence_text,
        "source_doc_id": doc_id,
        "source_doc_type": doc_type,
        "source_date": source_date,
    }


_MRI_EX = FewShotExample(
    example_id="mri.fewshot.synthetic-01.v1",
    document_excerpt=(
        "MRI BRAIN 3T without contrast.\n"
        "TECHNIQUE: Standard epilepsy protocol.\n"
        "FINDINGS: There is marked volume loss and T2/FLAIR hyperintensity of the "
        "right hippocampus consistent with right mesial temporal sclerosis. No other "
        "focal lesion is identified.\n"
        "IMPRESSION: Right hippocampal sclerosis."
    ),
    expected_json={
        "overall_normal": _ev(False, "Right hippocampal sclerosis", "SYN-MRI-01", "mri_report", "2025-01-01"),
        "findings": [
            _ev("hippocampal_sclerosis", "right mesial temporal sclerosis",
                "SYN-MRI-01", "mri_report", "2025-01-01"),
        ],
        "lesion_lobe": _ev("temporal", "right mesial temporal sclerosis",
                           "SYN-MRI-01", "mri_report", "2025-01-01"),
        "lesion_laterality": _ev("right", "right hippocampus",
                                 "SYN-MRI-01", "mri_report", "2025-01-01"),
        "hippocampal_sclerosis": _ev(True, "right mesial temporal sclerosis",
                                     "SYN-MRI-01", "mri_report", "2025-01-01"),
        "focal_cortical_dysplasia": _ev(False, "No other focal lesion is identified",
                                        "SYN-MRI-01", "mri_report", "2025-01-01",
                                        certainty="negated"),
        "mri_negative_for_epilepsy": _ev(False, "Right hippocampal sclerosis",
                                         "SYN-MRI-01", "mri_report", "2025-01-01"),
        "field_strength_tesla": _ev(3.0, "MRI BRAIN 3T",
                                    "SYN-MRI-01", "mri_report", "2025-01-01"),
    },
)


_EEG_EX = FewShotExample(
    example_id="eeg.fewshot.synthetic-01.v1",
    document_excerpt=(
        "EEG STUDY: Routine 30-minute EEG.\n"
        "BACKGROUND: Well-organized posterior dominant rhythm at 9 Hz. No slowing.\n"
        "EPILEPTIFORM ACTIVITY: Frequent left temporal sharp waves at 3-4 Hz.\n"
        "SEIZURES: No electrographic seizures captured.\n"
        "IMPRESSION: Abnormal EEG due to left temporal sharp waves."
    ),
    expected_json={
        "study_type": _ev("routine", "Routine 30-minute EEG",
                          "SYN-EEG-01", "eeg_report", "2025-01-01"),
        "background": _ev("normal", "Well-organized posterior dominant rhythm at 9 Hz",
                          "SYN-EEG-01", "eeg_report", "2025-01-01"),
        "ied_present": _ev(True, "Frequent left temporal sharp waves",
                           "SYN-EEG-01", "eeg_report", "2025-01-01"),
        "ied_findings": [{
            "value": {
                "ied_type": "sharp_wave",
                "localization": "temporal",
                "laterality": "left",
                "dominant_frequency_hz": 3.5,
            },
            "certainty": "definite",
            "temporal_status": "current",
            "evidence_text": "Frequent left temporal sharp waves at 3-4 Hz",
            "source_doc_id": "SYN-EEG-01",
            "source_doc_type": "eeg_report",
            "source_date": "2025-01-01",
        }],
        "seizures_captured": _ev(False, "No electrographic seizures captured",
                                 "SYN-EEG-01", "eeg_report", "2025-01-01",
                                 certainty="negated"),
        "seizures_captured_count": {
            "value": None,
            "certainty": "not_documented",
            "temporal_status": "unspecified",
            "evidence_text": None,
            "source_doc_id": "SYN-EEG-01",
            "source_doc_type": "eeg_report",
            "source_date": "2025-01-01",
        },
        "ictal_onset_lobe": {
            "value": None,
            "certainty": "not_documented",
            "temporal_status": "unspecified",
            "evidence_text": None,
            "source_doc_id": "SYN-EEG-01",
            "source_doc_type": "eeg_report",
            "source_date": "2025-01-01",
        },
        "ictal_onset_laterality": {
            "value": None,
            "certainty": "not_documented",
            "temporal_status": "unspecified",
            "evidence_text": None,
            "source_doc_id": "SYN-EEG-01",
            "source_doc_type": "eeg_report",
            "source_date": "2025-01-01",
        },
    },
)


_CLIN_SEIZURE_EX = FewShotExample(
    example_id="clinical_seizure.fewshot.synthetic-01.v1",
    document_excerpt=(
        "NEUROLOGY PROGRESS NOTE: 32-year-old woman with focal epilepsy since age 20. "
        "Focal impaired-awareness seizures occurring 2-3 per month, each lasting "
        "1-2 minutes with automatisms and post-ictal confusion. Occasional secondary "
        "generalization to bilateral tonic-clonic (2-3 per year). No status "
        "epilepticus. Etiology: right mesial temporal sclerosis on MRI. "
        "Structural etiology confirmed."
    ),
    expected_json={
        "epilepsy_type": _ev("focal", "focal epilepsy",
                             "SYN-PROG-01", "progress_note", "2025-01-01"),
        "predominant_seizure_type": _ev("focal_impaired_awareness",
                                        "Focal impaired-awareness seizures",
                                        "SYN-PROG-01", "progress_note", "2025-01-01"),
        "other_seizure_types": [
            _ev("focal_to_bilateral_tonic_clonic",
                "secondary generalization to bilateral tonic-clonic",
                "SYN-PROG-01", "progress_note", "2025-01-01"),
        ],
        "awareness": _ev("impaired", "impaired-awareness",
                         "SYN-PROG-01", "progress_note", "2025-01-01"),
        "semiology_text": _ev("automatisms and post-ictal confusion",
                              "automatisms and post-ictal confusion",
                              "SYN-PROG-01", "progress_note", "2025-01-01"),
        "age_at_onset_years": _ev(20.0, "since age 20",
                                  "SYN-PROG-01", "progress_note", "2025-01-01"),
        "seizure_frequency": {
            "value": {
                "raw_text": "2-3 per month",
                "period": "month",
                "count_min": 2, "count_max": 3,
                "seizure_free": False,
                "duration_text": "1-2 minutes",
                "applies_to_type": "focal_impaired_awareness",
            },
            "certainty": "definite",
            "temporal_status": "current",
            "evidence_text": "2-3 per month, each lasting 1-2 minutes",
            "source_doc_id": "SYN-PROG-01",
            "source_doc_type": "progress_note",
            "source_date": "2025-01-01",
        },
        "other_seizure_frequencies": [],
        "status_epilepticus_history": _ev(False, "No status epilepticus",
                                          "SYN-PROG-01", "progress_note", "2025-01-01",
                                          certainty="negated"),
        "etiology_category": _ev("structural", "Structural etiology confirmed",
                                 "SYN-PROG-01", "progress_note", "2025-01-01"),
        "etiology_details_text": _ev("right mesial temporal sclerosis on MRI",
                                     "right mesial temporal sclerosis on MRI",
                                     "SYN-PROG-01", "progress_note", "2025-01-01"),
        "etiology_specifics": {
            "value": None,
            "certainty": "not_documented",
            "temporal_status": "unspecified",
            "evidence_text": None,
            "source_doc_id": "SYN-PROG-01",
            "source_doc_type": "progress_note",
            "source_date": "2025-01-01",
        },
        "focal_motor_onset": _ev("automatisms",
                                 "automatisms",
                                 "SYN-PROG-01", "progress_note", "2025-01-01"),
        "focal_nonmotor_onset": {
            "value": None,
            "certainty": "not_documented",
            "temporal_status": "unspecified",
            "evidence_text": None,
            "source_doc_id": "SYN-PROG-01",
            "source_doc_type": "progress_note",
            "source_date": "2025-01-01",
        },
    },
)


_MEDICATION_EX = FewShotExample(
    example_id="medication.fewshot.synthetic-01.v1",
    document_excerpt=(
        "MEDICATIONS: Currently on levetiracetam 1500 mg BID and lacosamide 200 mg BID. "
        "Prior failed trials: valproic acid (inadequate control), carbamazepine "
        "(rash - discontinued). No adverse effects with current regimen. "
        "Meets ILAE criteria for drug-resistant epilepsy. Underwent right anterior "
        "temporal lobectomy in 2018. Post-operative status: Engel Class IA at "
        "18-month follow-up."
    ),
    expected_json={
        "current_asms": [
            {
                "value": {
                    "generic_name": "levetiracetam",
                    "status": "current",
                    "dose_text": "1500 mg BID",
                    "reason_discontinued": None,
                    "rxnorm_cui": None,
                },
                "certainty": "definite",
                "temporal_status": "current",
                "evidence_text": "levetiracetam 1500 mg BID",
                "source_doc_id": "SYN-MED-01",
                "source_doc_type": "progress_note",
                "source_date": "2025-01-01",
            },
            {
                "value": {
                    "generic_name": "lacosamide",
                    "status": "current",
                    "dose_text": "200 mg BID",
                    "reason_discontinued": None,
                    "rxnorm_cui": None,
                },
                "certainty": "definite",
                "temporal_status": "current",
                "evidence_text": "lacosamide 200 mg BID",
                "source_doc_id": "SYN-MED-01",
                "source_doc_type": "progress_note",
                "source_date": "2025-01-01",
            },
        ],
        "prior_asms": [],
        "failed_asms": [
            {
                "value": {
                    "generic_name": "valproic_acid",
                    "status": "failed",
                    "dose_text": None,
                    "reason_discontinued": "inadequate control",
                    "rxnorm_cui": None,
                },
                "certainty": "definite",
                "temporal_status": "historical",
                "evidence_text": "valproic acid (inadequate control)",
                "source_doc_id": "SYN-MED-01",
                "source_doc_type": "progress_note",
                "source_date": "2025-01-01",
            },
            {
                "value": {
                    "generic_name": "carbamazepine",
                    "status": "discontinued_adverse_effect",
                    "dose_text": None,
                    "reason_discontinued": "rash",
                    "rxnorm_cui": None,
                },
                "certainty": "definite",
                "temporal_status": "historical",
                "evidence_text": "carbamazepine (rash - discontinued)",
                "source_doc_id": "SYN-MED-01",
                "source_doc_type": "progress_note",
                "source_date": "2025-01-01",
            },
        ],
        "adverse_effects_text": _ev("No adverse effects with current regimen",
                                    "No adverse effects with current regimen",
                                    "SYN-MED-01", "progress_note", "2025-01-01",
                                    certainty="negated"),
        "drug_resistance_status": _ev("drug_resistant",
                                      "Meets ILAE criteria for drug-resistant epilepsy",
                                      "SYN-MED-01", "progress_note", "2025-01-01"),
        "surgery_history": [
            {
                "value": {
                    "surgery_type": "resection",
                    "target": "right anterior temporal lobe",
                    "laterality": "right",
                    "year": 2018,
                    "outcome_text": "Engel Class IA at 18-month follow-up",
                    "engel_class": "IA",
                    "ilae_outcome": None,
                    "device_model_text": None,
                    "stimulation_parameters_text": None,
                    "pathology_notes_text": None,
                },
                "certainty": "definite",
                "temporal_status": "historical",
                "evidence_text": "right anterior temporal lobectomy in 2018",
                "source_doc_id": "SYN-MED-01",
                "source_doc_type": "progress_note",
                "source_date": "2025-01-01",
            },
        ],
        "non_drug_therapies": [],
    },
)


_CLIN_LOC_EX = FewShotExample(
    example_id="clinical_localization.fewshot.synthetic-01.v1",
    document_excerpt=(
        "PRESURGICAL ASSESSMENT: Based on semiology (deja vu, oral automatisms, "
        "loss of awareness), clinical localization favors left mesial temporal "
        "onset. Alternative considerations include left insular onset given "
        "occasional autonomic features."
    ),
    expected_json={
        "primary_claim": {
            "value": {
                "lobe": "temporal",
                "laterality": "left",
                "source": "clinician_hypothesis",
            },
            "certainty": "probable",
            "temporal_status": "current",
            "evidence_text": "clinical localization favors left mesial temporal onset",
            "source_doc_id": "SYN-LOC-01",
            "source_doc_type": "presurgical_evaluation",
            "source_date": "2025-01-01",
        },
        "alternative_claims": [
            {
                "value": {
                    "lobe": "insular",
                    "laterality": "left",
                    "source": "clinician_hypothesis",
                },
                "certainty": "possible",
                "temporal_status": "current",
                "evidence_text": "Alternative considerations include left insular onset",
                "source_doc_id": "SYN-LOC-01",
                "source_doc_type": "presurgical_evaluation",
                "source_date": "2025-01-01",
            },
        ],
    },
)


_INTEGRATED_EX = FewShotExample(
    example_id="integrated.fewshot.synthetic-01.v1",
    document_excerpt=(
        "EPILEPSY SURGERY CONFERENCE: Case discussed by MDT. Clinical semiology "
        "consistent with left mesial temporal onset. Video-EEG monitoring "
        "captured 4 seizures with left temporal ictal onset. MRI shows left "
        "hippocampal sclerosis. Multimodal findings are concordant for left "
        "temporal epilepsy. Recommend left anterior temporal lobectomy."
    ),
    expected_json={
        "clinical_localization": {
            "value": {
                "lobe": "temporal",
                "laterality": "left",
                "source": "clinician_hypothesis",
            },
            "certainty": "definite",
            "temporal_status": "current",
            "evidence_text": "Clinical semiology consistent with left mesial temporal onset",
            "source_doc_id": "SYN-INT-01",
            "source_doc_type": "surgery_conference",
            "source_date": "2025-01-01",
        },
        "eeg_localization": {
            "value": {
                "lobe": "temporal",
                "laterality": "left",
                "source": "eeg_confirmed",
            },
            "certainty": "definite",
            "temporal_status": "current",
            "evidence_text": "Video-EEG monitoring captured 4 seizures with left temporal ictal onset",
            "source_doc_id": "SYN-INT-01",
            "source_doc_type": "surgery_conference",
            "source_date": "2025-01-01",
        },
        "mri_localization": {
            "value": {
                "lobe": "temporal",
                "laterality": "left",
                "source": "mri_confirmed",
            },
            "certainty": "definite",
            "temporal_status": "current",
            "evidence_text": "MRI shows left hippocampal sclerosis",
            "source_doc_id": "SYN-INT-01",
            "source_doc_type": "surgery_conference",
            "source_date": "2025-01-01",
        },
        "concordance": _ev("concordant",
                           "Multimodal findings are concordant for left temporal epilepsy",
                           "SYN-INT-01", "surgery_conference", "2025-01-01"),
        "concordance_notes_text": _ev(
            "Multimodal findings are concordant for left temporal epilepsy",
            "Multimodal findings are concordant for left temporal epilepsy",
            "SYN-INT-01", "surgery_conference", "2025-01-01"),
    },
)


# ---------------------------------------------------------------------------
# Prompt templates — one per (module, arm). doc_type is canonical / most common.
# ---------------------------------------------------------------------------


def _make_arm_triple(module: str, doc_type: DocumentType, task: str,
                     example: FewShotExample) -> tuple[PromptTemplate, PromptTemplate, PromptTemplate]:
    """Build the three-arm set (M0, M1, M2) for a module."""
    m0 = PromptTemplate(
        prompt_id=f"{module}.M0.v1",
        doc_type=doc_type, module_name=module, arm=ARM_M0, version="v1",
        system_prompt=_ROLE_PREAMBLE, task_instruction=task,
        output_directives=_OUTPUT_DIRECTIVES_M0M1, few_shot=(),
        rationale=f"Zero-shot {module} extraction. Baseline for the M0 arm.",
    )
    m1 = PromptTemplate(
        prompt_id=f"{module}.M1.v1",
        doc_type=doc_type, module_name=module, arm=ARM_M1, version="v1",
        system_prompt=_ROLE_PREAMBLE, task_instruction=task,
        output_directives=_OUTPUT_DIRECTIVES_M0M1, few_shot=(example,),
        rationale=f"M0 + one synthetic {module} demonstration.",
    )
    m2 = PromptTemplate(
        prompt_id=f"{module}.M2.v1",
        doc_type=doc_type, module_name=module, arm=ARM_M2, version="v1",
        system_prompt=_ROLE_PREAMBLE, task_instruction=task,
        output_directives=_OUTPUT_DIRECTIVES_M2, few_shot=(example,),
        rationale=(
            f"M1 + schema injected into the system prompt. Prompt-level constraint "
            "only; raw validity still measured downstream (no token-level constraint)."
        ),
    )
    return m0, m1, m2


# MRI
MRI_M0_V1, MRI_M1_V1, MRI_M2_V1 = _make_arm_triple(
    "mri", DocumentType.MRI_REPORT, _TASK_MRI, _MRI_EX,
)
# EEG
EEG_M0_V1, EEG_M1_V1, EEG_M2_V1 = _make_arm_triple(
    "eeg", DocumentType.EEG_REPORT, _TASK_EEG, _EEG_EX,
)
# Clinical seizure — canonical doc_type is progress_note; module applies to more
CLIN_SEIZURE_M0_V1, CLIN_SEIZURE_M1_V1, CLIN_SEIZURE_M2_V1 = _make_arm_triple(
    "clinical_seizure", DocumentType.PROGRESS_NOTE, _TASK_CLINICAL_SEIZURE, _CLIN_SEIZURE_EX,
)
# Medication
MEDICATION_M0_V1, MEDICATION_M1_V1, MEDICATION_M2_V1 = _make_arm_triple(
    "medication", DocumentType.PROGRESS_NOTE, _TASK_MEDICATION, _MEDICATION_EX,
)
# Clinical localization
CLIN_LOC_M0_V1, CLIN_LOC_M1_V1, CLIN_LOC_M2_V1 = _make_arm_triple(
    "clinical_localization", DocumentType.PROGRESS_NOTE, _TASK_CLINICAL_LOC, _CLIN_LOC_EX,
)
# Integrated
INTEGRATED_M0_V1, INTEGRATED_M1_V1, INTEGRATED_M2_V1 = _make_arm_triple(
    "integrated", DocumentType.SURGERY_CONFERENCE, _TASK_INTEGRATED, _INTEGRATED_EX,
)


_ALL_TEMPLATES = (
    MRI_M0_V1, MRI_M1_V1, MRI_M2_V1,
    EEG_M0_V1, EEG_M1_V1, EEG_M2_V1,
    CLIN_SEIZURE_M0_V1, CLIN_SEIZURE_M1_V1, CLIN_SEIZURE_M2_V1,
    MEDICATION_M0_V1, MEDICATION_M1_V1, MEDICATION_M2_V1,
    CLIN_LOC_M0_V1, CLIN_LOC_M1_V1, CLIN_LOC_M2_V1,
    INTEGRATED_M0_V1, INTEGRATED_M1_V1, INTEGRATED_M2_V1,
)


_REGISTRY: dict[str, PromptTemplate] = {p.prompt_id: p for p in _ALL_TEMPLATES}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get(prompt_id: str) -> PromptTemplate:
    if prompt_id not in _REGISTRY:
        raise KeyError(f"Unknown prompt_id: {prompt_id!r}. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[prompt_id]


def for_arm(doc_type: DocumentType, module_name: str, arm: str, version: str = "v1") -> PromptTemplate:
    """Exact filter. Raises KeyError if no exact match — do not fall back silently."""
    for p in _REGISTRY.values():
        if (p.doc_type == doc_type and p.module_name == module_name
                and p.arm == arm and p.version == version):
            return p
    raise KeyError(
        f"No prompt for doc_type={doc_type.value}, module={module_name}, "
        f"arm={arm}, version={version}"
    )


def resolve(module_name: str, arm: str, version: str = "v1") -> PromptTemplate:
    """Module-agnostic-of-doc-type lookup. Same prompt used across all doc_types
    where the module is applicable (per applicability mask). Raises KeyError if
    no prompt exists for the module."""
    for p in _REGISTRY.values():
        if p.module_name == module_name and p.arm == arm and p.version == version:
            return p
    raise KeyError(
        f"No prompt registered for module={module_name}, arm={arm}, version={version}"
    )


def all_prompt_ids() -> list[str]:
    return sorted(_REGISTRY)


def module_schema_for(module_cls: type[BaseModel]) -> dict[str, Any]:
    """Return the JSON schema for a Pydantic module class."""
    return module_cls.model_json_schema()
