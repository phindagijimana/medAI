# Fonferko-Shadrach 2019/2024 native gold — evaluation scope

**Purpose**: enumerate which v0.2.1 fields have a direct counterpart in
Fonferko-Shadrach's own clinician-adjudicated gold annotations (Zenodo
8356494), so we can score model output *against their gold directly*
rather than against our derived silver labels. Fields absent from F-S
gold are marked **out of evaluation scope** — the framework can extract
them and the schema documents them, but §4 metrics do not include them.

Reference: `scripts/inventory_fs_gold.py` (200 letters, all annotations
in `data/fonferko_shadrach_2024/zenodo_8356494/Json/*.json`).

## F-S native entity inventory (all 200 letters)

| Entity          | n      | Key attributes used for scoring                             |
|-----------------|-------:|-------------------------------------------------------------|
| PatientHistory  | 656    | (auxiliary — not directly scored)                            |
| Diagnosis       | 572    | DiagCategory ∈ {Epilepsy, MultipleSeizures, SingleSeizure}, Negation, Certainty |
| Prescription    | 294    | DrugName, DrugDose, DoseUnit, Frequency, CUI                 |
| SeizureFrequency| 263    | LowerNumberOfSeizures, UpperNumberOfSeizures, TimePeriod     |
| Investigations  | 183    | CT_Performed, MRI_Performed, EEG_Performed + *_Results       |
| BirthHistory    | 47     | (out of scope — not in v0.2.1)                               |
| EpilepsyCause   | 36     | free-text quoted span                                        |
| Onset           | 24     | Age, AgeLower, AgeUpper, AgeUnit                             |
| WhenDiagnosed   | 17     | Age, YearDate                                                |

## In-scope fields — scored directly against F-S gold

| v0.2.1 field                                         | F-S source                                     | Scoring |
|------------------------------------------------------|------------------------------------------------|---------|
| `MedicationModule.current_asms[i].generic_name`      | Prescription.DrugName (all 294)                | multiset F1 (patient level) |
| `ClinicalSeizureModule.seizure_frequency.count_min`  | SeizureFrequency.LowerNumberOfSeizures         | exact match |
| `ClinicalSeizureModule.seizure_frequency.count_max`  | SeizureFrequency.UpperNumberOfSeizures         | exact match |
| `ClinicalSeizureModule.seizure_frequency.period`     | SeizureFrequency.TimePeriod (Day / Week / Month / Year) | exact match |
| `ClinicalSeizureModule.epilepsy_type`                | Diagnosis where DiagCategory=Epilepsy → normalize text to ILAE 2017 top-level {focal, generalized, combined, unknown} | exact match |
| `ClinicalSeizureModule.predominant_seizure_type`     | Diagnosis where DiagCategory ∈ {MultipleSeizures, SingleSeizure} → normalize text to ILAE 2017 basic seizure type | exact match |
| `ClinicalSeizureModule.age_at_onset_years`           | Onset.Age (or AgeLower/AgeUpper) — cast to float | tolerance ±1 y |
| `ClinicalSeizureModule.etiology_details_text` (free-text) | EpilepsyCause text | evidence-span overlap |

Total shared scoring fields: **8 across 2 modules** (ClinicalSeizure + Medication).

## Out-of-evaluation-scope fields — v0.2.1-only, no F-S counterpart

These are framework-native fields for which F-S gold does not contain a
reference label. The framework documents and extracts them; §4 metrics
do not score them.

**ClinicalSeizureModule**:
`awareness`, `semiology_text`, `status_epilepticus_history`,
`etiology_category`, `etiology_specifics` (causative_gene / _variant /
_antibody / _tumor / _pathogen / _metabolic),
`focal_motor_onset`, `focal_nonmotor_onset`, `other_seizure_types`,
`other_seizure_frequencies`.

**MedicationModule**:
`prior_asms`, `failed_asms` (F-S has no explicit failure-status flag),
`drug_resistance_status` (ILAE 2010 definition — derivable but no
adjudicated reference), `adverse_effects_text`,
`surgery_history` (engel_class, ilae_outcome, device_model_text,
stimulation_parameters_text, pathology_notes_text),
`non_drug_therapies`.

**MriModule / EegModule / ClinicalLocalizationModule /
IntegratedPhenotypeModule**: entire modules — F-S corpus is outpatient
clinic letters and does not include MRI reports, EEG reports,
localization panels, or presurgical-conference notes. Empirical
evaluation of these modules requires a different doc-type corpus (Shape
B follow-up).

## Rationale

- **Direct-to-gold scoring** replaces our silver labels with F-S's own
  clinician annotations as the reference on the 8 shared fields. This
  eliminates the silver-labeling transformation as a source of error in
  our metrics.
- **Out-of-scope marking** is honest about which v0.2.1 additions this
  paper's evaluation cannot validate — a limitation that is intrinsic
  to using an open corpus rather than a shortfall of our framework.
- **Silver labels remain useful** for internal integration tests and
  for pipeline development, but they are no longer the primary reference
  in §Results.
