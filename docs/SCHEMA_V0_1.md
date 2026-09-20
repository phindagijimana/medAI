# MedAI-EPI Phenotype Schema v0.1

**⚠️ SUPERSEDED.** This document describes v0.1. The active schema is v0.2 — see `SCHEMA_V0_2.md`. v0.1 is retained for historical reference only.

---

**Purpose.** A single, versioned, machine-checkable specification of the epilepsy phenotype fields MedAI-EPI extracts from clinical documents. This document is the human-readable companion to `schema/`. Any change to the enums, modules, or applicability masks in code must be reflected here before v0.1 is frozen.

**Framing (§21).** MedAI-EPI is a **research phenotyping assistant**. Every field is an extraction from a source document, not a clinical inference. The schema is designed so that unknown / not-documented is always a valid answer and is preferred over guessing.

**Reviewer's job.** Read each module, confirm the field list and allowed values, and flag: (1) missing fields the annotators will need, (2) allowed values that are wrong or too coarse/fine, (3) source doc types that should or should not be able to populate the field. Sign-off on this document freezes v0.1; changes after that become v0.2.

---

## 1. Core concepts

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

| Value          | When to use                                              |
| -------------- | -------------------------------------------------------- |
| `current`      | Present state at the time of the note.                   |
| `historical`   | Past finding no longer active or explicitly prior.       |
| `planned`      | Intended future action / status.                         |
| `hypothetical` | Conditional or counterfactual (differential, if-then).   |
| `unspecified`  | Note does not clarify.                                   |

### 1.4 Not documented vs. unknown vs. not applicable

Three distinct states, per §7.2:

- **Not documented** — the note doesn't discuss the field. Coded as `value=None`, `certainty=not_documented`.
- **Unknown** — the note discusses it and states it's unknown ("laterality could not be determined"). Coded as `value=None`, `certainty=unknown`, `evidence_text=<span>`.
- **Not applicable** — the field does not apply to this document type. Handled by the **applicability mask** (§4); the field is not scored on that document.

---

## 2. Documents

The atomic unit is one document → one phenotype record. Patient-level aggregation is a separate deterministic step handled elsewhere (§14 of the paper blueprint).

`DocumentMetadata` fields: `doc_id`, `doc_type`, `doc_date`, `patient_id`.

**Document types** (`DocumentType`):
`mri_report`, `eeg_report`, `progress_note`, `initial_consult`, `presurgical_evaluation`, `emu_admission`, `emu_discharge`, `surgery_conference`, `procedure_seeg`, `procedure_resection`, `procedure_neurostim`, `other`.

---

## 3. Modules

### 3.1 ClinicalSeizureModule

Applicable to: progress notes, initial consult, EMU admission/discharge, presurgical evaluation, surgery conference.

| Field                          | Type / allowed values                                                                 | Notes |
| ------------------------------ | -------------------------------------------------------------------------------------- | ----- |
| `epilepsy_type`                | `focal` / `generalized` / `combined_focal_generalized` / `unknown`                    | ILAE 2017 |
| `predominant_seizure_type`     | `SeizureType` enum (ILAE 2017 basic seizure types)                                    | The type documented most centrally. |
| `other_seizure_types`          | list of `SeizureType` (multi-valued)                                                  | Each with its own evidence object. |
| `awareness`                    | `aware` / `impaired` / `unknown`                                                      | Focal seizures. Non-applicable for pure generalized cases — code as `not_documented`. |
| `semiology_text`               | free text (Evidence[str])                                                             | The raw semiology description; downstream normalization is a separate task. |
| `age_at_onset_years`           | float                                                                                 | If given in months, convert. Preserve the raw quote in `evidence_text`. |
| `seizure_frequency`            | `SeizureFrequency` object                                                             | `raw_text` required; count/period optional. `seizure_free=True` when explicitly stated. |
| `status_epilepticus_history`   | bool                                                                                  | True if any prior status episode is documented, current or historical (encoded via `temporal_status`). |

**SeizureType allowed values:** `focal_aware`, `focal_impaired_awareness`, `focal_unknown_awareness`, `focal_to_bilateral_tonic_clonic`, `generalized_tonic_clonic`, `generalized_tonic`, `generalized_clonic`, `generalized_myoclonic`, `generalized_absence_typical`, `generalized_absence_atypical`, `generalized_atonic`, `generalized_epileptic_spasms`, `unknown_onset_tonic_clonic`, `unknown_onset_motor_other`, `unknown_onset_nonmotor`, `unclassified`.

### 3.2 MedicationModule

Applicable to: progress notes, initial consult, EMU admission/discharge, presurgical evaluation, surgery conference, procedure_resection, procedure_neurostim.

| Field                       | Type                                              | Notes |
| --------------------------- | ------------------------------------------------- | ----- |
| `current_asms`              | list of `Medication` (status=`current`)           | One entry per drug. |
| `prior_asms`                | list of `Medication` (status=`prior`)             | |
| `failed_asms`               | list of `Medication` (status=`failed`)            | ILAE definition of *failure*: seizure freedom not achieved at tolerated dose after adequate trial. |
| `adverse_effects_text`      | free text                                         | Raw AE description; normalization deferred to v0.2. |
| `drug_resistance_status`    | `drug_responsive` / `undefined` / `drug_resistant` | Per ILAE 2010 definition (failure of 2 tolerated, appropriately chosen ASMs). |
| `surgery_history`           | list of `SurgeryHistoryItem`                      | Each with type, target (optional), laterality (optional), year (optional), outcome free text. |

**Medication fields:** `generic_name` (canonicalized generic, e.g., `levetiracetam` not `Keppra`), `status`, `dose_text` (raw, e.g., "1500 mg BID"), `reason_discontinued` (free text if given).

**MedicationStatus values:** `current`, `prior`, `failed`, `discontinued_adverse_effect`, `planned`.

**SurgeryType values:** `resection`, `laser_ablation`, `disconnection`, `hemispherectomy`, `callosotomy`, `neurostimulation_vns`, `neurostimulation_rns`, `neurostimulation_dbs`, `other`.

### 3.3 ClinicalLocalizationModule

Applicable to: progress notes, initial consult, EMU admission/discharge, presurgical evaluation, surgery conference, procedure_seeg, procedure_resection, procedure_neurostim.

This module captures the **clinician's hypothesis** based on history and semiology. Confirmed localization from EEG/MRI/SEEG is captured in the respective imaging modules, and cross-modality synthesis lives in `IntegratedPhenotypeModule`.

| Field                | Type                          | Notes |
| -------------------- | ----------------------------- | ----- |
| `primary_claim`      | `LobarClaim`                  | The dominant localization stated. |
| `alternative_claims` | list of `LobarClaim`          | Differential possibilities the clinician explicitly lists. |

**LobarClaim fields:** `lobe`, `laterality`, `source` (always `clinician_hypothesis` in this module).

**LobarLocalization values:** `frontal`, `temporal`, `parietal`, `occipital`, `insular`, `cingulate`, `multifocal`, `unknown`.
**Laterality values:** `left`, `right`, `bilateral`, `midline`, `diffuse`, `unknown`.
**LocalizationSource values:** `clinician_hypothesis`, `eeg_confirmed`, `mri_confirmed`, `seeg_confirmed`, `surgical_confirmed`.

### 3.4 EegModule

Applicable to: EEG reports, EMU discharge, presurgical evaluation, surgery conference, procedure_seeg.

| Field                       | Type / allowed values                                             | Notes |
| --------------------------- | ------------------------------------------------------------------ | ----- |
| `study_type`                | `routine` / `prolonged` / `ambulatory` / `video_eeg` / `emu` / `intraoperative` / `seeg` / `ecog` | |
| `background`                | `normal` / `diffuse_slowing` / `focal_slowing` / `asymmetric` / `suppressed` / `burst_suppression` / `other` | |
| `ied_present`               | bool                                                              | Are interictal epileptiform discharges reported at all. |
| `ied_findings`              | list of `IedFinding`                                              | One per distinct IED locus. |
| `seizures_captured`         | bool                                                              | Were any electrographic or clinical seizures recorded during the study. |
| `seizures_captured_count`   | int                                                               | Only if the report gives a number. |
| `ictal_onset_lobe`          | `LobarLocalization`                                               | Lobe of ictal onset when captured. |
| `ictal_onset_laterality`    | `Laterality`                                                      | Laterality of ictal onset. Do **not** convert "no clear lateralization" to a side (§12). |

**IedFinding fields:** `ied_type`, `localization` (optional), `laterality` (optional).
**IedType values:** `spike`, `sharp_wave`, `spike_and_wave`, `polyspike`, `polyspike_and_wave`, `sharp_and_slow`, `generalized_spike_wave_3hz`, `other`.

### 3.5 MriModule

Applicable to: MRI reports, EMU discharge, presurgical evaluation, surgery conference.

| Field                        | Type                          | Notes |
| ---------------------------- | ------------------------------ | ----- |
| `overall_normal`             | bool                          | True only if the report explicitly concludes the study is normal. |
| `findings`                   | list of `MriFinding`          | One entry per distinct finding. |
| `lesion_lobe`                | `LobarLocalization`           | Lobe of the primary lesion, if any. |
| `lesion_laterality`          | `Laterality`                  | Laterality of the primary lesion. |
| `hippocampal_sclerosis`      | bool                          | Convenience flag for the most common finding; also encoded in `findings`. |
| `focal_cortical_dysplasia`   | bool                          | Convenience flag; also in `findings`. |
| `mri_negative_for_epilepsy`  | bool                          | Only True when the report **explicitly** states MRI-negative for epilepsy-relevant lesion. Do not derive from absent findings alone. |

**MriFinding values:** `normal`, `hippocampal_sclerosis`, `focal_cortical_dysplasia`, `tumor`, `vascular_malformation`, `encephalomalacia`, `gliosis`, `stroke_sequelae`, `polymicrogyria`, `heterotopia`, `lissencephaly`, `tuberous_sclerosis`, `other_lesion`, `mri_negative`.

### 3.6 IntegratedPhenotypeModule

Applicable to: presurgical evaluation, EMU discharge, surgery conference.

Only populate this module from documents that themselves synthesize across modalities. Do not synthesize from separate documents — that's patient-level aggregation, handled elsewhere.

| Field                       | Type                             | Notes |
| --------------------------- | -------------------------------- | ----- |
| `clinical_localization`     | `LobarClaim` (source=clinician)  | The clinician's hypothesis as stated in this synthesis doc. |
| `eeg_localization`          | `LobarClaim` (source=eeg_*)      | The EEG-derived localization as stated in this doc. |
| `mri_localization`          | `LobarClaim` (source=mri_*)      | The MRI-derived localization as stated in this doc. |
| `concordance`               | `concordant` / `partially_concordant` / `discordant` / `not_assessed` | Only when the document itself states concordance; do not infer. |
| `concordance_notes_text`    | free text                        | Any additional narrative about agreement / discordance. |

---

## 4. Applicability mask (which modules apply where)

Extraction and scoring **only** run on applicable modules. If a note references a finding whose canonical location is a different document type, do not extract it here — it will be captured against its source document.

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
| `procedure_resection`      | `clinical_localization`, `medication` |
| `procedure_neurostim`      | `medication`, `clinical_localization` |
| `other`                    | all six (permissive; annotator uses `not_documented`) |

---

## 5. Change control

- Any field, enum value, or applicability edit changes the schema **version**.
- v0.1 → v0.2 is the expected path after pilot annotation (§7.3). All revisions go through the epileptologist reviewer.
- Locked test set predictions must be produced against exactly one schema version, recorded in the run manifest.

## 6. Known open questions for reviewer

1. **Predominant vs. all seizure types.** Current schema forces one "predominant" plus a list of "others". Alternative: single unordered list. Preference?
2. **Convenience booleans on `MriModule` (`hippocampal_sclerosis`, `focal_cortical_dysplasia`).** These duplicate information in `findings`. Keep for annotator/model convenience or drop to avoid inconsistency risk?
3. **Age at onset units.** Currently `float` years. If notes routinely give months for infants, we may want a separate `age_at_onset_months` or a discriminated union.
4. **Semiology.** Kept as free text for v0.1. Do you want a structured motor / non-motor / autonomic decomposition in v0.2, or is that a separate downstream task?
5. **EEG channels / bilaterality.** Should `ictal_onset_laterality` include a `bilateral_independent` value, distinct from `bilateral`?
6. **MRI post-processing findings** (e.g., MAP, morphometric). Add to `MriFinding` or defer?
7. **Genetic etiology.** Not in v0.1. Add as a module or a field on `ClinicalSeizureModule`?
8. **Surgery outcome.** Currently free text (`outcome_text`). Add Engel / ILAE outcome enums?

Sign-off: ______________________  Date: __________
