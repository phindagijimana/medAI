# MedAI-EPI Phenotype Schema v0.2.1

**Status.** Supersedes `SCHEMA_V0_1.md`. Applies the 12 changes recommended by the v0.1 stress test (`SCHEMA_V0_1_STRESS_TEST.md`), plus the v0.2.1 patch adding structured etiology specifics + coding cross-references (see §7.1). Items marked **PROVISIONAL** below still need epileptologist confirmation before v0.2.1 is frozen.

**Framing.** Unchanged. MedAI-EPI is a research phenotyping assistant. Every field is an extraction from a source document, not a clinical inference. Unknown / not-documented is always a valid answer and is preferred over guessing.

**How to review this doc.** If you already reviewed v0.1, jump straight to §7 ("v0.2 change log") — it tells you exactly what's new and which items still need your sign-off. §1–§6 restate the schema in full so the doc is self-contained.

---

## 1. Core concepts (unchanged from v0.1)

### 1.1 The Evidence wrapper

Every extractable field is wrapped in an `Evidence` object:

| Attribute          | Meaning                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| `value`            | The extracted value (typed per field). `None` = not documented.         |
| `certainty`        | How the source text asserts it (see §1.2).                              |
| `temporal_status`  | Whether the finding is current, historical, planned, hypothetical.      |
| `evidence_text`    | Minimal sufficient span from the source document that supports `value`. |
| `source_doc_id`    | ID of the document the evidence came from.                              |
| `source_doc_type`  | Document family (MRI, EEG, progress, …).                                |
| `source_date`      | Date of that document.                                                  |
| `char_start/end`   | Optional character offsets; only if robust.                             |

**Rules enforced by the validator:**
- `value=None` requires `certainty ∈ {NOT_DOCUMENTED, UNKNOWN, NEGATED}` and `evidence_text=None` (for NOT_DOCUMENTED).
- `value` present requires a non-empty `evidence_text`.
- Character offsets are all-or-nothing.

### 1.2 Certainty values

| Value             | When to use                                                                    |
| ----------------- | ------------------------------------------------------------------------------ |
| `definite`        | Unambiguous positive assertion ("right hippocampal sclerosis is present").     |
| `probable`        | "likely", "consistent with", "highly suggestive of".                           |
| `possible`        | "possible", "cannot rule out", "may represent".                                |
| `negated`         | Explicitly ruled out ("no epileptogenic lesion identified").                   |
| `unknown`         | The note explicitly states the value is unknown / cannot be determined.        |
| `not_documented`  | The note does not address the field at all. Use with `value=None`.             |

### 1.3 Temporal status

`current`, `historical`, `planned`, `hypothetical`, `unspecified`.

### 1.4 Not documented vs. unknown vs. not applicable

- **Not documented** — the note doesn't discuss the field. `value=None`, `certainty=not_documented`.
- **Unknown** — the note discusses it and states it's unknown. `value=None`, `certainty=unknown`, `evidence_text=<span>`.
- **Not applicable** — the field doesn't apply to this document type. Handled by the applicability mask (§4).

### 1.5 One document → one phenotype record

The atomic unit of extraction is a single document. When a patient has multiple imaging studies, multiple progress notes, or multiple EEGs, each produces its own phenotype record. Comparing across documents (day-0 vs. day-8 MRI, progression over time, cross-modality concordance from independent sources) happens at a separate **patient-level aggregation** step, not inside the ontology.

---

## 2. Documents

`DocumentMetadata` fields: `doc_id`, `doc_type`, `doc_date`, `patient_id`, **`icd10cm_codes`** *(v0.2.1)*, **`snomed_ct_codes`** *(v0.2.1)*.

The `icd10cm_codes` and `snomed_ct_codes` fields are optional lists of strings captured from the EHR encounter header, not from narrative extraction. They exist for cohort-validation and cross-referencing, **not** as substitutes for the ILAE-native phenotype fields. See §7.1 for the rationale.

**Document types** (`DocumentType`):
`mri_report`, `eeg_report`, `progress_note`, `initial_consult`, `presurgical_evaluation`, `emu_admission`, `emu_discharge`, `surgery_conference`, `procedure_seeg`, `procedure_resection`, `procedure_neurostim`, `other`.

---

## 3. Modules

### 3.1 ClinicalSeizureModule

| Field                          | Type / allowed values                                                             | Notes |
| ------------------------------ | ---------------------------------------------------------------------------------- | ----- |
| `epilepsy_type`                | `focal` / `generalized` / `combined_focal_generalized` / `unknown`                | ILAE 2017 |
| `predominant_seizure_type`     | `SeizureType` enum                                                                | The type documented most centrally. |
| `other_seizure_types`          | list of `SeizureType` (multi-valued)                                              | Each with its own evidence object. |
| `awareness`                    | `aware` / `impaired` / `unknown`                                                  | Focal seizures. |
| `semiology_text`               | free text (Evidence[str])                                                         | Raw semiology description. |
| `age_at_onset_years`           | float                                                                             | Months → years conversion; raw quote in `evidence_text`. |
| `seizure_frequency`            | `SeizureFrequency` object                                                         | See §3.1.1 for v0.2 field additions. |
| `other_seizure_frequencies`    | list of `SeizureFrequency` **[v0.2]**                                             | Attach a separate frequency to each secondary seizure type. |
| `status_epilepticus_history`   | bool                                                                              | Prior status episodes, historical or current per `temporal_status`. |
| `etiology_category` **[v0.2 PROVISIONAL]** | `structural` / `genetic` / `infectious` / `immune` / `metabolic` / `unknown` | ILAE 2017 top-level etiology category. Reviewer: confirm category list and whether `genetic + structural` combo needs a special case (e.g., tuberous sclerosis). |
| `etiology_details_text` **[v0.2]** | free text                                                                     | Raw quote: gene name, antibody name, tumor, injury etc. Free text avoids proliferating enum values for rare specifics. |
| `etiology_specifics` **[v0.2.1]** | `EtiologySpecifics` object (Evidence-wrapped)                              | Structured slots for the common cases: gene (HGNC), variant (HGVS), autoantibody (curated enum), tumor, pathogen, metabolic condition. See §3.1.2. |
| `focal_motor_onset` **[v0.2 PROVISIONAL]** | `automatisms` / `atonic` / `clonic` / `epileptic_spasms` / `hyperkinetic` / `myoclonic` / `tonic` | ILAE 2017 focal-motor subtypes. Applicable when `predominant_seizure_type` is focal. Reviewer: confirm subtype list is sufficient. |
| `focal_nonmotor_onset` **[v0.2 PROVISIONAL]** | `autonomic` / `behavior_arrest` / `cognitive` / `emotional` / `sensory` | ILAE 2017 focal non-motor subtypes. |

**SeizureType allowed values (unchanged from v0.1):** `focal_aware`, `focal_impaired_awareness`, `focal_unknown_awareness`, `focal_to_bilateral_tonic_clonic`, `generalized_tonic_clonic`, `generalized_tonic`, `generalized_clonic`, `generalized_myoclonic`, `generalized_absence_typical`, `generalized_absence_atypical`, `generalized_atonic`, `generalized_epileptic_spasms`, `unknown_onset_tonic_clonic`, `unknown_onset_motor_other`, `unknown_onset_nonmotor`, `unclassified`.

#### 3.1.1 SeizureFrequency (extended in v0.2)

| Field                | Type                                                            | Notes |
| -------------------- | --------------------------------------------------------------- | ----- |
| `raw_text`           | str (required)                                                  | e.g. "2–8 seizures per month" |
| `period`             | `day` / `week` / `month` / `year` / `unspecified`               | |
| `count_min/max`      | float, optional                                                 | Parsed range if the raw text supports it. |
| `seizure_free`       | bool                                                            | True when explicitly stated. |
| `duration_text` **[v0.2]** | str, optional                                             | Raw per-event duration quote, e.g. "16 to 30 seconds", "2 to 3 minutes". |
| `applies_to_type` **[v0.2]** | `SeizureType`, optional                                 | Ties this frequency to a specific seizure type when multiple types coexist with different frequencies. |

#### 3.1.2 EtiologySpecifics **[v0.2.1]**

Structured slots for the well-known etiology sub-categories. All fields optional — annotators fill only those relevant to `etiology_category`. When multiple sub-fields apply (e.g., paraneoplastic with both antibody and tumor), fill all.

| Field                        | Type                       | When to use                                                                     |
| ---------------------------- | -------------------------- | ------------------------------------------------------------------------------- |
| `causative_gene`             | str (HGNC symbol)          | `etiology_category=genetic`. Use approved HGNC symbol ("SCN1A", "DEPDC5", "TSC1"). |
| `causative_variant`          | str (HGVS)                 | Variant notation if given ("c.4213G>T", "p.Arg1405Ter").                        |
| `causative_antibody`         | `CausativeAntibody` enum   | `etiology_category=immune`. Curated list of ~20 antibodies, plus `other` and `none_detected`. |
| `associated_tumor_text`      | free text                  | For paraneoplastic: raw tumor description ("SCLC, right lung", "ovarian teratoma"). |
| `causative_pathogen_text`    | free text                  | `etiology_category=infectious`: raw pathogen description ("neurocysticercosis", "HSV-1"). |
| `causative_metabolic_text`   | free text                  | `etiology_category=metabolic`: raw condition description ("pyridoxine-dependent epilepsy"). |

**CausativeAntibody enum values (v0.2.1):**
Cell-surface: `anti_lgi1`, `anti_caspr2`, `anti_nmdar`, `anti_gababr`, `anti_ampar`, `anti_dppx`, `anti_glyr`, `anti_iglon5`, `anti_mglur5`.
Intracellular / paraneoplastic: `anti_hu`, `anti_ma2`, `anti_yo`, `anti_ri`, `anti_amphiphysin`, `anti_gad65`, `anti_sox1`, `anti_cv2`, `anti_zic4`.
Sentinel values: `other`, `none_detected`.

### 3.2 MedicationModule

| Field                       | Type                                              | Notes |
| --------------------------- | ------------------------------------------------- | ----- |
| `current_asms`              | list of `Medication` (status=`current`)           | |
| `prior_asms`                | list of `Medication` (status=`prior`)             | |
| `failed_asms`               | list of `Medication` (status=`failed`)            | ILAE definition of failure: seizure freedom not achieved at tolerated dose after adequate trial. |
| `adverse_effects_text`      | free text                                         | Raw AE description. |
| `drug_resistance_status`    | `drug_responsive` / `undefined` / `drug_resistant` | ILAE 2010. |
| `surgery_history`           | list of `SurgeryHistoryItem`                      | Extended in v0.2 — see §3.2.1. |
| `non_drug_therapies` **[v0.2]** | list of `NonDrugTherapy`                      | See §3.2.2. |

**MedicationStatus values:** `current`, `prior`, `failed`, `discontinued_adverse_effect`, `planned`.

**Medication fields:** `generic_name` (canonical generic, e.g. `levetiracetam`), `status`, `dose_text` (raw quote), `reason_discontinued` (free text), **`rxnorm_cui`** *(v0.2.1, optional str)* — RxNorm concept ID for medication normalization. Populate when the RxNorm CUI is directly available from the EHR or an authoritative crosswalk; do not guess.

#### 3.2.1 SurgeryHistoryItem (extended in v0.2)

| Field                            | Type                                     | Notes |
| -------------------------------- | ---------------------------------------- | ----- |
| `surgery_type`                   | `SurgeryType` enum (now includes `unknown` **[v0.2]**) | For notes that reference a prior surgery of unspecified type. |
| `target`                         | str, optional                            | Anatomical target. |
| `laterality`                     | `Laterality`, optional                   | |
| `year`                           | int, optional                            | |
| `outcome_text`                   | str, optional                            | Raw outcome quote. |
| `engel_class` **[v0.2]**         | `IA`/`IB`/…/`IVC`                        | Engel post-surgical outcome. |
| `ilae_outcome` **[v0.2]**        | `1`–`6`                                  | ILAE post-surgical outcome. |
| `device_model_text` **[v0.2]**   | str, optional                            | For neurostim: raw device/lead identifier ("AspireSR 106", "LivaNova 302"). |
| `stimulation_parameters_text` **[v0.2]** | str, optional                     | Raw programming quote ("output current 1.75 mA, frequency 30 Hz, pulse duration 500 μs"); structured parsing deferred to v0.3+. |
| `pathology_notes_text` **[v0.2]** | str, optional                          | Raw histopath quote from the resected specimen (MOGHE, FCD Palmini classification, etc.). |

**SurgeryType values:** `resection`, `laser_ablation`, `disconnection`, `hemispherectomy`, `callosotomy`, `neurostimulation_vns`, `neurostimulation_rns`, `neurostimulation_dbs`, `other`, **`unknown`** *(v0.2)*.

#### 3.2.2 NonDrugTherapy **[v0.2]**

| Field           | Type                                                                      | Notes |
| --------------- | ------------------------------------------------------------------------- | ----- |
| `therapy_type`  | `ketogenic_diet` / `modified_atkins` / `low_glycemic_index` / `ivig` / `plasmapheresis` / `steroids` / `rituximab` / `acth` / `other` | Extend after pilot annotation if needed. |
| `status`        | `MedicationStatus` (reused: current/prior/failed/…)                       | |
| `response_text` | str, optional                                                             | Raw response quote. |

### 3.3 ClinicalLocalizationModule (unchanged)

| Field                | Type                          | Notes |
| -------------------- | ----------------------------- | ----- |
| `primary_claim`      | `LobarClaim`                  | Clinician's dominant localization hypothesis. |
| `alternative_claims` | list of `LobarClaim`          | Differential possibilities. |

**LobarClaim fields:** `lobe`, `laterality`, `source` (`clinician_hypothesis` in this module).

### 3.4 EegModule (extended in v0.2)

| Field                       | Type / allowed values                                             | Notes |
| --------------------------- | ------------------------------------------------------------------ | ----- |
| `study_type`                | `routine` / `prolonged` / `ambulatory` / `video_eeg` / `emu` / `intraoperative` / `seeg` / `ecog` | |
| `background`                | `normal` / `diffuse_slowing` / `focal_slowing` / `asymmetric` / `suppressed` / `burst_suppression` / `other` | |
| `ied_present`               | bool                                                              | Are IEDs reported at all. |
| `ied_findings`              | list of `IedFinding`                                              | v0.2: each entry now supports `dominant_frequency_hz`. |
| `seizures_captured`         | bool                                                              | Any seizures recorded during study. |
| `seizures_captured_count`   | int                                                               | Only if given. |
| `ictal_onset_lobe`          | `LobarLocalization`                                               | |
| `ictal_onset_laterality`    | `Laterality`                                                      | Do **not** convert "no clear lateralization" to a side. |

**IedFinding fields:** `ied_type`, `localization` (optional), `laterality` (optional), **`dominant_frequency_hz`** *(v0.2, optional float)*.

### 3.5 MriModule (extended in v0.2)

| Field                        | Type                          | Notes |
| ---------------------------- | ------------------------------ | ----- |
| `overall_normal`             | bool                          | True only if the report explicitly concludes normal. |
| `findings`                   | list of `MriFinding`          | v0.2: enum extended (see below). |
| `lesion_lobe`                | `LobarLocalization`           | Primary lesion lobe. |
| `lesion_laterality`          | `Laterality`                  | Primary lesion laterality. |
| `hippocampal_sclerosis`      | bool                          | Convenience flag, kept for annotator ergonomics. v0.2 adds a consistency validator with `findings`. |
| `focal_cortical_dysplasia`   | bool                          | Convenience flag; consistency validated against `findings`. |
| `mri_negative_for_epilepsy`  | bool                          | Only True when the report explicitly says MRI-negative for an epilepsy-relevant lesion. |
| `field_strength_tesla` **[v0.2]** | float (Evidence-wrapped) | 1.5, 3.0, 7.0 typical; store raw quote as evidence. |

**MriFinding values (v0.2, extended):** `normal`, `hippocampal_sclerosis`, `focal_cortical_dysplasia`, **`fcd_palmini_i`**, **`fcd_palmini_iia`**, **`fcd_palmini_iib`**, **`moghe`**, `tumor`, `vascular_malformation`, `encephalomalacia`, `gliosis`, `stroke_sequelae`, `polymicrogyria`, `heterotopia`, `lissencephaly`, `tuberous_sclerosis`, `other_lesion`, `mri_negative`.

**v0.2 consistency validator on `MriModule`:** if `hippocampal_sclerosis.value=True`, at least one `findings` entry must be `HIPPOCAMPAL_SCLEROSIS`; if `focal_cortical_dysplasia.value=True`, at least one `findings` entry must be an FCD subtype or `MOGHE`. This catches divergent extraction between the convenience booleans and the enumerated findings list. The validator does **not** run when the booleans are None or unknown.

### 3.6 IntegratedPhenotypeModule (unchanged)

| Field                       | Type                             | Notes |
| --------------------------- | -------------------------------- | ----- |
| `clinical_localization`     | `LobarClaim` (source=clinician)  | |
| `eeg_localization`          | `LobarClaim` (source=eeg_*)      | |
| `mri_localization`          | `LobarClaim` (source=mri_*)      | |
| `concordance`               | `concordant` / `partially_concordant` / `discordant` / `not_assessed` | Only when the document states concordance; do not infer. |
| `concordance_notes_text`    | free text                        | Additional narrative. |

---

## 4. Applicability mask (unchanged from v0.1)

Extraction and scoring **only** run on applicable modules.

| Document type              | Applicable modules |
| -------------------------- | ------------------ |
| `mri_report`               | `mri` |
| `eeg_report`               | `eeg` |
| `progress_note`            | `clinical_seizure`, `medication`, `clinical_localization` |
| `initial_consult`          | `clinical_seizure`, `medication`, `clinical_localization` |
| `emu_admission`            | `clinical_seizure`, `medication`, `clinical_localization` |
| `emu_discharge`            | all six modules |
| `presurgical_evaluation`   | all six modules |
| `surgery_conference`       | all six modules |
| `procedure_seeg`           | `eeg`, `clinical_localization` |
| `procedure_resection`      | `clinical_localization`, `medication` (surgery_history + pathology_notes) |
| `procedure_neurostim`      | `medication`, `clinical_localization` |
| `other`                    | all six (permissive) |

---

## 5. Change control

- Any field, enum, or applicability edit changes the schema version.
- v0.2 is provisional until items marked **PROVISIONAL** below are reviewer-confirmed.
- Locked test set predictions must be produced against exactly one schema version, recorded in the run manifest.

---

## 6. Open questions carried forward from v0.1

Still unanswered:

1. **Predominant vs. all seizure types.** Current schema keeps `predominant_seizure_type` + `other_seizure_types`. v0.2 adds `other_seizure_frequencies` to allow per-type frequencies. Is that enough, or do you want a single unordered `SeizureEvent` list instead?
2. **Convenience booleans on MriModule.** v0.2 keeps them but adds a consistency validator. Prefer to keep, drop, or make them derived (read-only) from `findings`?
3. **Age at onset units.** Still `float years`. Add a separate `age_at_onset_months` for infant onset, or is fractional years sufficient?
4. **Semiology.** Kept as free text. Structured motor/non-motor decomposition planned for v0.3?
5. **EEG channels / bilaterality.** Should `ictal_onset_laterality` include `bilateral_independent`, distinct from `bilateral`?
6. **MRI post-processing findings** (MAP, morphometric). Add now or defer?
7. **Genetic etiology detail.** v0.2 handles this via `etiology_category=genetic` + `etiology_details_text` free text. Sufficient for the paper, or add structured `causative_gene`/`variant` fields?
8. **Surgery outcome.** v0.2 adds Engel + ILAE enums. Reviewer confirm those are the right two systems and that our sub-classes are complete.

---

## 7. v0.2 change log (against v0.1)

Non-controversial additions (applied):

| # | Change | Location |
| - | ------ | -------- |
| 1 | `SurgeryType.UNKNOWN` | `enums.py` |
| 2 | MRI field strength | `MriModule.field_strength_tesla` |
| 3 | Ictal dominant frequency | `IedFinding.dominant_frequency_hz` |
| 4 | Per-event duration + per-type frequency | `SeizureFrequency.duration_text`, `.applies_to_type` |
| 5 | Engel + ILAE outcome | `SurgeryHistoryItem.engel_class`, `.ilae_outcome` |
| 6 | MOGHE + FCD Palmini subtypes | `MriFinding` enum |
| 7 | Pathology notes | `SurgeryHistoryItem.pathology_notes_text` |
| 8 | Non-drug therapies | `MedicationModule.non_drug_therapies`, new `NonDrugTherapy` object, `NonDrugTherapyType` enum |
| 9 | Neurostim device + parameters (raw text) | `SurgeryHistoryItem.device_model_text`, `.stimulation_parameters_text` |
| 12a | Per-type frequency list | `ClinicalSeizureModule.other_seizure_frequencies` |
| 12b | MRI convenience-boolean ↔ findings consistency validator | `MriModule.__post_validate__` |

Provisional additions (require reviewer confirmation):

| # | Change | Location | Reviewer question |
| - | ------ | -------- | ----------------- |
| 10 | Etiology category enum + details free text | `ClinicalSeizureModule.etiology_category`, `.etiology_details_text` | Are the six ILAE etiology categories the right split? Any missing (e.g., `combined_structural_genetic`)? |
| 11 | Focal motor + non-motor onset subtypes | `ClinicalSeizureModule.focal_motor_onset`, `.focal_nonmotor_onset` | Are the ILAE 2017 subtype lists complete and correctly enumerated for our use? |
| 12 (structural) | (See §6 questions 1 and 2) | | Kept additive for now; larger restructures deferred to v0.3 if needed. |

Sign-off on §7 provisional items freezes v0.2. Sign-off: ______________________ Date: __________

---

## 7.1 v0.2.1 amendment: coding cross-references + structured etiology specifics

### Motivation

Reviewer question surfaced: are we including ICD codes and other well-known epilepsy etiology documentation standards? The `MedAI_Paper1_Literature_Review_Reference_Guide.docx` is silent on ICD, because every cited epilepsy-NLP paper (ExECT, Xie 2022/2023, Decker, Abeysinghe, Fonferko-Shadrach, Adelson 2026) treats **extraction from clinical text as the primary task** using ILAE-native vocabulary. Adelson 2026 specifically uses Engel + ILAE outcomes precisely because ICD collapses too many distinctions.

Position taken in v0.2.1: **keep ILAE as the primary phenotype vocabulary; add optional cross-reference fields for interoperability and structured slots for the etiology sub-types that show up repeatedly in real cases (genes, autoantibodies, tumors, pathogens).** No ICD as target vocabulary.

### v0.2.1 changes (non-controversial, additive)

| # | Change | Location | Purpose |
| - | ------ | -------- | ------- |
| 13 | `icd10cm_codes: list[str]` | `DocumentMetadata` | EHR encounter-header ICD codes for cohort validation. Not extracted from narrative. |
| 14 | `snomed_ct_codes: list[str]` | `DocumentMetadata` | Same rationale, SNOMED CT. |
| 15 | `rxnorm_cui: str | None` | `Medication` | Optional RxNorm CUI for medication normalization. |
| 16 | `EtiologySpecifics` value object | new (see §3.1.2) | Structured slots: `causative_gene` (HGNC), `causative_variant` (HGVS), `causative_antibody` (curated enum), `associated_tumor_text`, `causative_pathogen_text`, `causative_metabolic_text`. |
| 17 | `CausativeAntibody` enum | new | 18 well-known epilepsy-related autoantibodies + `other` + `none_detected`. See §3.1.2. |
| 18 | `etiology_specifics: Evidence[EtiologySpecifics]` | `ClinicalSeizureModule` | Wire the new value object into the module. |

### Reviewer questions specific to v0.2.1

1. **CausativeAntibody enum coverage.** Are all 18 antibodies clinically important for epilepsy-relevant autoimmune presentations? Anything missing? Any that should be dropped as too rare for the paper's scope?
2. **HGNC symbol convention.** Are we OK requiring the HGNC-approved symbol (e.g. `ARHGAP35`, not `ARGHAP35` as it appeared in one case report)? Should the annotation manual mention this?
3. **HGVS variant.** Is c./p. notation expected, or should annotators just record the raw quote from the note?
4. **ICD-10-CM.** Confirm inclusion of `G40.*`, `G41.*`, `R56.*` as the standard epilepsy code family — anything else worth capturing (e.g., `S06.*` for TBI etiology, `C34.*` for lung ca in paraneoplastic)?
5. **Scope of ICD codes list.** Only epilepsy-relevant codes, or all codes on the encounter? (I'd argue only epilepsy-relevant, to keep the field focused.)

### Things explicitly NOT added in v0.2.1 (deferred to v0.3 if reviewer wants)

- Full SNOMED CT across every extracted field.
- Blümcke 2011 FCD subtype alignment (v0.2 has Palmini I/IIa/IIb + MOGHE; Blümcke revisions are subtle refinements).
- HPO term IDs on every phenotype field (a mapping layer post-extraction).
- Structured CSF / lab result module (touched on in stress test §4 as "out of scope for phenotype extraction").

Sign-off on §7.1 additions: ______________________ Date: __________
