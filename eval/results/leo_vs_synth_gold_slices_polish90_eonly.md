# EpExtra hard slices (all notes, no LLM)

Patient-level micro-F1 on seven fields. Specialist only. Not a headline; rules were developed on this corpus. Stopped-drug leak = plan `PRIOR_ASMS` ∩ predicted `current_asms`.

## all  (90 patients, 443 notes; stopped-drug leak 17/131)

| system | micro P | micro R | micro F1 | 95% CI |
|---|---:|---:|---:|---|
| specialist | 0.932 | 0.946 | 0.939 | [0.916, 0.960] |

Per-field F1:

| field | n | specialist |
|---|---:|---:|
| `current_asms` | 90 | 0.947 |
| `seizure_frequency.period` | 63 | 0.932 |
| `seizure_frequency.count_min` | 90 | 0.916 |
| `seizure_frequency.count_max` | 90 | 0.916 |
| `epilepsy_type` | 90 | 0.978 |
| `predominant_seizure_type` | 82 | 0.878 |
| `age_at_onset_years` | 90 | 0.989 |
| `epilepsy_type|typed` | 87 | 0.994 |
| `epilepsy_type|abstain` | 90 | 0.978 |
| `predominant_seizure_type|class` | 82 | 0.951 |

## polish_train  (90 patients, 443 notes; stopped-drug leak 17/131)

| system | micro P | micro R | micro F1 | 95% CI |
|---|---:|---:|---:|---|
| specialist | 0.932 | 0.946 | 0.939 | [0.916, 0.960] |

Per-field F1:

| field | n | specialist |
|---|---:|---:|
| `current_asms` | 90 | 0.947 |
| `seizure_frequency.period` | 63 | 0.932 |
| `seizure_frequency.count_min` | 90 | 0.916 |
| `seizure_frequency.count_max` | 90 | 0.916 |
| `epilepsy_type` | 90 | 0.978 |
| `predominant_seizure_type` | 82 | 0.878 |
| `age_at_onset_years` | 90 | 0.989 |
| `epilepsy_type|typed` | 87 | 0.994 |
| `epilepsy_type|abstain` | 90 | 0.978 |
| `predominant_seizure_type|class` | 82 | 0.951 |

## slice:prior_asms  (65 patients, 319 notes; stopped-drug leak 17/131)

| system | micro P | micro R | micro F1 | 95% CI |
|---|---:|---:|---:|---|
| specialist | 0.929 | 0.951 | 0.940 | [0.915, 0.962] |

Per-field F1:

| field | n | specialist |
|---|---:|---:|
| `current_asms` | 65 | 0.937 |
| `seizure_frequency.period` | 46 | 0.943 |
| `seizure_frequency.count_min` | 65 | 0.930 |
| `seizure_frequency.count_max` | 65 | 0.930 |
| `epilepsy_type` | 65 | 0.985 |
| `predominant_seizure_type` | 59 | 0.864 |
| `age_at_onset_years` | 65 | 0.985 |
| `epilepsy_type|typed` | 63 | 0.992 |
| `epilepsy_type|abstain` | 65 | 0.985 |
| `predominant_seizure_type|class` | 59 | 0.949 |

## slice:denied  (39 patients, 204 notes; stopped-drug leak 11/59)

| system | micro P | micro R | micro F1 | 95% CI |
|---|---:|---:|---:|---|
| specialist | 0.930 | 0.960 | 0.945 | [0.911, 0.971] |

Per-field F1:

| field | n | specialist |
|---|---:|---:|
| `current_asms` | 39 | 0.923 |
| `seizure_frequency.period` | 32 | 0.951 |
| `seizure_frequency.count_min` | 39 | 0.923 |
| `seizure_frequency.count_max` | 39 | 0.923 |
| `epilepsy_type` | 39 | 0.974 |
| `predominant_seizure_type` | 37 | 0.946 |
| `age_at_onset_years` | 39 | 1.000 |
| `epilepsy_type|typed` | 38 | 1.000 |
| `epilepsy_type|abstain` | 39 | 0.974 |
| `predominant_seizure_type|class` | 37 | 0.973 |

## slice:hedged  (36 patients, 181 notes; stopped-drug leak 13/53)

| system | micro P | micro R | micro F1 | 95% CI |
|---|---:|---:|---:|---|
| specialist | 0.911 | 0.957 | 0.933 | [0.902, 0.962] |

Per-field F1:

| field | n | specialist |
|---|---:|---:|
| `current_asms` | 36 | 0.901 |
| `seizure_frequency.period` | 25 | 0.958 |
| `seizure_frequency.count_min` | 36 | 0.944 |
| `seizure_frequency.count_max` | 36 | 0.944 |
| `epilepsy_type` | 36 | 0.944 |
| `predominant_seizure_type` | 35 | 0.886 |
| `age_at_onset_years` | 36 | 1.000 |
| `epilepsy_type|typed` | 34 | 0.985 |
| `epilepsy_type|abstain` | 36 | 0.944 |
| `predominant_seizure_type|class` | 35 | 0.914 |

## slice:hypothetical  (23 patients, 110 notes; stopped-drug leak 0/28)

| system | micro P | micro R | micro F1 | 95% CI |
|---|---:|---:|---:|---|
| specialist | 0.947 | 0.925 | 0.936 | [0.888, 0.974] |

Per-field F1:

| field | n | specialist |
|---|---:|---:|
| `current_asms` | 23 | 0.989 |
| `seizure_frequency.period` | 17 | 0.903 |
| `seizure_frequency.count_min` | 23 | 0.889 |
| `seizure_frequency.count_max` | 23 | 0.889 |
| `epilepsy_type` | 23 | 0.957 |
| `predominant_seizure_type` | 21 | 0.857 |
| `age_at_onset_years` | 23 | 1.000 |
| `epilepsy_type|typed` | 22 | 0.977 |
| `epilepsy_type|abstain` | 23 | 0.957 |
| `predominant_seizure_type|class` | 21 | 0.952 |

## slice:any_distractor  (83 patients, 409 notes; stopped-drug leak 17/131)

| system | micro P | micro R | micro F1 | 95% CI |
|---|---:|---:|---:|---|
| specialist | 0.930 | 0.946 | 0.938 | [0.916, 0.960] |

Per-field F1:

| field | n | specialist |
|---|---:|---:|
| `current_asms` | 83 | 0.944 |
| `seizure_frequency.period` | 59 | 0.937 |
| `seizure_frequency.count_min` | 83 | 0.921 |
| `seizure_frequency.count_max` | 83 | 0.921 |
| `epilepsy_type` | 83 | 0.976 |
| `predominant_seizure_type` | 75 | 0.867 |
| `age_at_onset_years` | 83 | 0.988 |
| `epilepsy_type|typed` | 80 | 0.994 |
| `epilepsy_type|abstain` | 83 | 0.976 |
| `predominant_seizure_type|class` | 75 | 0.947 |

## slice:no_distractor  (7 patients, 34 notes)

| system | micro P | micro R | micro F1 | 95% CI |
|---|---:|---:|---:|---|
| specialist | 0.961 | 0.942 | 0.951 | [0.854, 1.000] |

Per-field F1:

| field | n | specialist |
|---|---:|---:|
| `current_asms` | 7 | 1.000 |
| `seizure_frequency.period` | 4 | 0.857 |
| `seizure_frequency.count_min` | 7 | 0.857 |
| `seizure_frequency.count_max` | 7 | 0.857 |
| `epilepsy_type` | 7 | 1.000 |
| `predominant_seizure_type` | 7 | 1.000 |
| `age_at_onset_years` | 7 | 1.000 |
| `epilepsy_type|typed` | 7 | 1.000 |
| `epilepsy_type|abstain` | 7 | 1.000 |
| `predominant_seizure_type|class` | 7 | 1.000 |

