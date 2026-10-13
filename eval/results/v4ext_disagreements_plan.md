# v4_ext disagreements scored against the plan (not a clinician)

Sheet: `data/leo_runs/v4ext_llm_x1c.disagreements.csv`. Adjudicator: v4_ext_plan. Default shown reader: rules.

This does **not** change the shipped disagreement policy (D17).

| field | n | scored | rules right | model right | both | neither | unclear |
|---|---:|---:|---:|---:|---:|---:|---:|
| clinical_seizure.age_at_onset_years | 4 | 4 | 0/4 (0.00) | 4/4 (1.00) | 0 | 0 | 0 |
| clinical_seizure.epilepsy_type | 6 | 6 | 3/6 (0.50) | 3/6 (0.50) | 0 | 0 | 0 |
| clinical_seizure.focal_motor_onset | 3 | 3 | 0/3 (0.00) | 3/3 (1.00) | 0 | 0 | 0 |
| clinical_seizure.focal_nonmotor_onset | 12 | 10 | 1/10 (0.10) | 9/10 (0.90) | 0 | 0 | 2 |
| clinical_seizure.predominant_seizure_type | 27 | 24 | 1/24 (0.04) | 22/24 (0.92) | 0 | 1 | 3 |
| clinical_seizure.seizure_frequency | 8 | 8 | 4/8 (0.50) | 8/8 (1.00) | 4 | 0 | 0 |
| eeg.background | 6 | 6 | 4/6 (0.67) | 2/6 (0.33) | 0 | 0 | 0 |
| eeg.ied_present | 3 | 0 | n/a | n/a | 0 | 0 | 3 |
| eeg.study_type | 20 | 20 | 3/20 (0.15) | 14/20 (0.70) | 0 | 3 | 0 |
