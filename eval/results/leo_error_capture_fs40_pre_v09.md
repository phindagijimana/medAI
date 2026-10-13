# LEO error capture (F-S held-out letters; model errors vs fusion routing)

A value is one of the seven headline fields on one letter with gold. The model is wrong when `score_doc` reports fp+fn > 0. Captured = LEO did not auto-accept (review, reject, or silent). False alarm among flags = flagged values that were already right.

## L1C (arm L1C, 40 letters)

- Model-wrong values: **49** of 124 scored.
- Captured (not accepted): **30** (0.61); of those, review 25, reject 1, silent 4.
- Model errors LEO auto-accepted: **19** (0.39).
- Flagged values that were already right: **16** of 41 (0.39).

| field | scored | LLM wrong | captured | accepted anyway | flagged | flag already right |
|---|---:|---:|---:|---:|---:|---:|
| `current_asms` | 37 | 9 | 3 | 6 | 5 | 2 |
| `seizure_frequency.period` | 15 | 5 | 4 | 1 | 9 | 5 |
| `seizure_frequency.count_min` | 6 | 0 | 0 | 0 | 1 | 1 |
| `seizure_frequency.count_max` | 6 | 0 | 0 | 0 | 1 | 1 |
| `epilepsy_type` | 38 | 26 | 18 | 8 | 15 | 1 |
| `predominant_seizure_type` | 18 | 9 | 5 | 4 | 9 | 5 |
| `age_at_onset_years` | 4 | 0 | 0 | 0 | 1 | 1 |
