## Per-field F1 breakdown — pilot corpus — base_constr (lenient)

*Aggregated across all render-arm / cond / extraction-arm cells per variant. Manifests: `data/run_manifests_pilot_base_constr`.*

| variant | field | n | HIT | MISS | mismatch | P | R | F1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| constr | `clinical_seizure.age_at_onset_years` | 180 | 180 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| constr | `clinical_seizure.epilepsy_type` | 180 | 60 | 120 | 0 | 1.000 | 0.333 | 0.500 |
| constr | `clinical_seizure.etiology_category` | 180 | 180 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| constr | `clinical_seizure.predominant_seizure_type` | 180 | 180 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| constr | `clinical_seizure.seizure_frequency` | 120 | 120 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| constr | `clinical_seizure.seizure_frequency.count_max` | 60 | 0 | 60 | 0 | 0.000 | 0.000 | 0.000 |
| constr | `clinical_seizure.seizure_frequency.count_min` | 60 | 0 | 60 | 0 | 0.000 | 0.000 | 0.000 |
| constr | `clinical_seizure.seizure_frequency.period` | 60 | 0 | 60 | 0 | 0.000 | 0.000 | 0.000 |
| constr | `eeg.background` | 180 | 131 | 43 | 6 | 0.956 | 0.728 | 0.826 |
| constr | `medication.drug_resistance_status` | 180 | 172 | 0 | 8 | 0.956 | 0.956 | 0.956 |
