Per item: correct / wrong / missing / not_reported (n = plan items). Plan items scored as in scripts/score_extended_phenotypes.py; core items added.

| item | n | rules-only (all claims, all needs_review) | LEO+model, all claims (reviewer view) | LEO+model, accepted claims only | LEO+model, accepted AND both readers | model's own claims only |
|---|---|---|---|---|---|---|
| epilepsy type (core) | 37 | 36 / 1 / 0 / 0 | 36 / 1 / 0 / 0 | 35 / 2 / 0 / 0 | 34 / 1 / 2 / 0 | 34 / 2 / 1 / 0 |
| seizure type (core) | 34 | 30 / 4 / 0 / 0 | 30 / 4 / 0 / 0 | 31 / 0 / 3 / 0 | 31 / 0 / 3 / 0 | 31 / 0 / 3 / 0 |
| age at onset (core) | 37 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 |
| EEG study type | 37 | 31 / 6 / 0 / 0 | 36 / 1 / 0 / 0 | 36 / 0 / 1 / 0 | 36 / 0 / 1 / 0 | 36 / 0 / 1 / 0 |
| EEG background | 37 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 |
| interictal discharges found | 27 | 17 / 0 / 10 / 0 | 27 / 0 / 0 / 0 | 17 / 0 / 10 / 0 | 17 / 0 / 10 / 0 | 27 / 0 / 0 / 0 |
| IED lobe | 12 | 12 / 0 / 0 / 0 | 17 / 0 / 0 / 0 | 12 / 0 / 0 / 0 | 12 / 0 / 0 / 0 | 17 / 0 / 0 / 0 |
| IED side | 12 | 11 / 1 / 0 / 0 | 17 / 0 / 0 / 0 | 11 / 1 / 0 / 0 | 12 / 0 / 0 / 0 | 17 / 0 / 0 / 0 |
| ictal onset lobe | 5 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 |
| ictal onset side | 5 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 |
| focal motor onset | 12 | 7 / 5 / 0 / 0 | 7 / 4 / 1 / 0 | 4 / 2 / 6 / 0 | 3 / 1 / 8 / 0 | 3 / 2 / 7 / 0 |
| focal non-motor onset | 15 | 8 / 7 / 0 / 0 | 11 / 4 / 0 / 0 | 11 / 1 / 3 / 0 | 11 / 0 / 4 / 0 | 11 / 0 / 4 / 0 |
| semiology: motor feature (lenient) | 34 | 26 / 0 / 8 / 0 | 26 / 0 / 8 / 0 | 0 / 0 / 34 / 0 | 0 / 0 / 34 / 0 | 0 / 0 / 34 / 0 |
| semiology: aura (lenient) | 13 | 7 / 0 / 6 / 0 | 7 / 0 / 6 / 0 | 0 / 0 / 13 / 0 | 0 / 0 / 13 / 0 | 0 / 0 / 13 / 0 |
| rescue drug | 22 | 21 / 0 / 1 / 0 | 21 / 0 / 1 / 0 | 21 / 0 / 1 / 0 | 21 / 0 / 1 / 0 | 21 / 0 / 1 / 0 |
| surgery procedure | 11 | 11 / 0 / 0 / 0 | 11 / 0 / 0 / 0 | 11 / 0 / 0 / 0 | 11 / 0 / 0 / 0 | 11 / 0 / 0 / 0 |

Where the plan has no value but a value was reported (patients; ideal 0):

| item | rules-only (all claims, all needs_review) | LEO+model, all claims (reviewer view) | LEO+model, accepted claims only | LEO+model, accepted AND both readers | model's own claims only |
|---|---|---|---|---|---|
| eeg_ictal_onset_reported_but_none | 14 | 15 | 0 | 0 | 1 |
| eeg_ied_reported_but_none | 4 | 4 | 0 | 0 | 0 |
| focal_motor_in_semiology_not_onset (not an error) | 16 | 13 | 1 | 1 | 1 |
| focal_nonmotor_in_semiology_not_onset (not an error) | 4 | 4 | 1 | 1 | 2 |
| focal_nonmotor_reported_but_unsupported | 5 | 5 | 1 | 1 | 2 |

Lists, tp / fp / fn (precision, recall):

| list | rules-only (all claims, all needs_review) | LEO+model, all claims (reviewer view) | LEO+model, accepted claims only | LEO+model, accepted AND both readers | model's own claims only |
|---|---|---|---|---|---|
| rescue drugs | 21 / 8 / 1 (0.724, 0.955) | 21 / 9 / 1 (0.7, 0.955) | 21 / 2 / 1 (0.913, 0.955) | 21 / 2 / 1 (0.913, 0.955) | 21 / 7 / 1 (0.75, 0.955) |
| surgery procedures | 11 / 1 / 0 (0.917, 1.0) | 11 / 2 / 0 (0.846, 1.0) | 11 / 0 / 0 (1.0, 1.0) | 11 / 0 / 0 (1.0, 1.0) | 11 / 1 / 0 (0.917, 1.0) |
| current ASMs (patient-level union) | 71 / 17 / 8 (0.807, 0.899) | 71 / 21 / 8 (0.772, 0.899) | 71 / 10 / 8 (0.877, 0.899) | 71 / 10 / 8 (0.877, 0.899) | 71 / 14 / 8 (0.835, 0.899) |

Claim level (scored field paths only; each claim judged against the plan of its patient):

| arm | verdict / source | correct | wrong | not scorable | precision | distinct (patient, field, value) precision |
|---|---|---|---|---|---|---|
| rules_only | review | 892 | 207 | 67 | 0.812 | 0.724 (373/515) |
| rules_only | review|specialist_only | 892 | 207 | 67 | 0.812 | 0.724 (373/515) |
| leo_llm | accept | 848 | 60 | 4 | 0.934 | 0.893 (367/411) |
| leo_llm | accept|both | 810 | 33 | 3 | 0.961 | 0.953 (344/361) |
| leo_llm | accept|specialist_only | 38 | 27 | 1 | 0.585 | 0.565 (35/62) |
| leo_llm | reject | 10 | 4 | 0 | 0.714 | 0.692 (9/13) |
| leo_llm | reject|model_only | 10 | 4 | 0 | 0.714 | 0.692 (9/13) |
| leo_llm | review | 203 | 145 | 37 | 0.583 | 0.523 (126/241) |
| leo_llm | review|both | 1 | 5 | 0 | 0.167 | 0.2 (1/5) |
| leo_llm | review|model_only | 157 | 17 | 6 | 0.902 | 0.846 (88/104) |
| leo_llm | review|specialist_only | 45 | 123 | 31 | 0.268 | 0.286 (38/133) |

Verdict shares (all claims, all field paths; reject = dropped):

- rules_only: reject 75, review 2800; of 2800 shown claims: review 100.0%
  - on the scored field paths: review 1166; review 100.0%
- leo_llm: accept 985, reject 89, review 1976; of 2961 shown claims: accept 33.3%, review 66.7%
  - on the scored field paths: accept 912, reject 14, review 385; accept 70.3%, review 29.7%
