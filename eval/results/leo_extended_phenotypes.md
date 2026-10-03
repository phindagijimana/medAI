# Specialist on the extended synthetic set (v4_ext; 37 patients, 113 notes joined per patient; no LLM)

Reference = plan. "in text" = only items whose key words appear in the generated text.

| item | n (all) | answered | right | accuracy (all) | when answered | n (in text) | right (in text) | accuracy (in text) |
|---|---|---|---|---|---|---|---|---|
| eeg_background_normal_vs_slowing | 37 | 37 | 37 | 1.0 | 1.0 | 37 | 37 | 1.0 |
| eeg_ictal_lobe | 5 | 4 | 4 | 0.8 | 1.0 | 5 | 4 | 0.8 |
| eeg_ictal_side | 5 | 4 | 4 | 0.8 | 1.0 | 5 | 4 | 0.8 |
| eeg_ied_found | 27 | 27 | 17 | 0.63 | 0.63 | 27 | 17 | 0.63 |
| eeg_ied_lobe | 12 | 8 | 8 | 0.667 | 1.0 | 12 | 8 | 0.667 |
| eeg_ied_side | 12 | 10 | 8 | 0.667 | 0.8 | 12 | 8 | 0.667 |
| eeg_study_type | 37 | 37 | 24 | 0.649 | 0.649 | 37 | 24 | 0.649 |
| focal_motor_onset | 12 | 12 | 7 | 0.583 | 0.583 | 12 | 7 | 0.583 |
| focal_nonmotor_onset | 15 | 15 | 8 | 0.533 | 0.533 | 15 | 8 | 0.533 |

Rules gave a value where the plan has none: {'focal_nonmotor_reported_but_unsupported': 4, 'ictal_onset_reported_but_none': 13, 'focal_motor_in_semiology_not_onset': 16, 'focal_nonmotor_in_semiology_not_onset': 5, 'ied_reported_but_none': 4}

Semiology motor features found in the semiology text: 19 of 34 in text (34 in plan); aura: 3 of 13 in text (13 in plan). Lenient key-word match.

| list | scope | tp / fp / fn | precision | recall | F1 |
|---|---|---|---|---|---|
| rescue | all | 21 / 6 / 1 | 0.778 | 0.955 | 0.857 |
| rescue | in_text | 21 / 6 / 1 | 0.778 | 0.955 | 0.857 |
| surgery | all | 11 / 1 / 0 | 0.917 | 1.0 | 0.957 |
| surgery | in_text | 11 / 1 / 0 | 0.917 | 1.0 | 0.957 |

Rescue false positives by what the sentence says: {'inpatient_or_protocol_order': 3, 'hypothetical_instruction': 3} (hypothetical_instruction = "should he have a cluster, use nasal midazolam", written from the plan's hypothetical triggers; inpatient_or_protocol_order = an EMU / hospital PRN order).

Patients with no reference rescue drug: {'patients_without_reference': 15, 'with_rescue_reported': 2}; no reference surgery: {'patients_without_reference': 26, 'with_surgery_reported': 2}.
