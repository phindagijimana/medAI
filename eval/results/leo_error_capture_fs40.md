# LEO error capture (F-S held-out letters; model errors vs fusion routing)

`leo-v0.9` rematch (stored L1C; no GPU). Pre-v0.9 counts (19/49 leak) are in `leo_error_capture_fs40_pre_v09.md`. Headline extras / auto P 0.851 stay frozen.

A value is one of the seven headline fields on one letter with gold. The model is wrong when `score_doc` reports fp+fn > 0. Captured = LEO did not auto-accept (review, reject, or silent). That is **not** the same as “the accepted value is gold-wrong” (see EA0197). False alarm among flags = flagged values that were already right.

## L1C (arm L1C, 40 letters)

- Model-wrong values: **49** of 124 scored.
- Captured (not accepted): **29** (0.59); of those, review 28, reject 0, silent 1.
- Model errors LEO auto-accepted: **20** (0.41).
- Flagged values that were already right: **15** of 43 (0.35).

| field | scored | LLM wrong | captured | accepted anyway | flagged | flag already right |
|---|---:|---:|---:|---:|---:|---:|
| `current_asms` | 37 | 9 | 2 | 7 | 3 | 1 |
| `seizure_frequency.period` | 15 | 5 | 4 | 1 | 9 | 5 |
| `seizure_frequency.count_min` | 6 | 0 | 0 | 0 | 1 | 1 |
| `seizure_frequency.count_max` | 6 | 0 | 0 | 0 | 1 | 1 |
| `epilepsy_type` | 38 | 26 | 18 | 8 | 19 | 1 |
| `predominant_seizure_type` | 18 | 9 | 5 | 4 | 9 | 5 |
| `age_at_onset_years` | 4 | 0 | 0 | 0 | 1 | 1 |

### Accepted model-wrong cells (the leak)

Hold-out list only. **Do not write E/fusion rules from these rows.** Leak did not fall (19→20); cluster-if was written on EA0001–160, not from this table.

How to read the 20 rows (do not train or retune from them):

- **8 epilepsy type** — typed vs gold `unknown` (diagnosis-line convention). Not a broken reader.
- **4 seizure type** — three rules-only `focal_impaired_awareness` vs gold `focal_unknown_awareness` (`dyscognitive`); one both-readers FBTCS. Clash display stays D17.
- **1 frequency** — EA0188 `day` vs gold `month`.
- **7 current ASMs** — several gold lists repeat the same name (multiset); F-S gold counts rescue as current (D6; EA0165 midazolam). EA0197 accept matches gold; the model’s extra levetiracetam was not accepted.

| letter | field | gold | leo accept | llm | source |
|---|---|---|---|---|---|
| EA0165 | `current_asms` | ['lamotrigine', 'clobazam', 'midazolam', 'lamotrigine', 'brivaracetam'] | ['lamotrigine', 'brivaracetam', 'clobazam'] | ['lamotrigine', 'brivaracetam', 'clobazam', 'buccalmidazolam'] | epextra+llm |
| EA0166 | `epilepsy_type` | 'unknown' | 'generalized' | 'generalized' | epextra+llm |
| EA0167 | `epilepsy_type` | 'unknown' | 'focal' | 'focal' | epextra+llm |
| EA0168 | `epilepsy_type` | 'unknown' | 'generalized' | 'generalized' | epextra+llm |
| EA0169 | `epilepsy_type` | 'unknown' | 'focal' | 'focal' | epextra+llm |
| EA0169 | `predominant_seizure_type` | 'focal_unknown_awareness' | 'focal_impaired_awareness' | None | epextra |
| EA0178 | `current_asms` | ['carbamazepine', 'carbamazepine', 'levetiracetam'] | ['levetiracetam', 'carbamazepine'] | ['levetiracetam', 'carbamazepine'] | epextra+llm |
| EA0180 | `epilepsy_type` | 'unknown' | 'generalized' | 'generalized' | epextra+llm |
| EA0181 | `epilepsy_type` | 'unknown' | 'focal' | 'focal' | epextra+llm |
| EA0181 | `predominant_seizure_type` | 'focal_unknown_awareness' | 'focal_impaired_awareness' | None | epextra |
| EA0182 | `current_asms` | ['lamotrigine', 'lamotrigine'] | ['lamotrigine'] | ['lamotrigine'] | epextra+llm |
| EA0182 | `epilepsy_type` | 'unknown' | 'focal' | 'focal' | epextra+llm |
| EA0183 | `current_asms` | ['sodiumvalproate', 'sodiumvalproate'] | ['sodiumvalproate'] | ['sodiumvalproate'] | epextra+llm |
| EA0186 | `predominant_seizure_type` | 'focal_unknown_awareness' | 'focal_to_bilateral_tonic_clonic' | 'focal_to_bilateral_tonic_clonic' | epextra+llm |
| EA0188 | `seizure_frequency.period` | 'month' | 'day' | 'day' | epextra+llm |
| EA0188 | `epilepsy_type` | 'unknown' | 'focal' | 'focal' | epextra+llm |
| EA0194 | `current_asms` | ['sodiumvalproate', 'brivaracetam'] | ['sodiumvalproate'] | ['sodiumvalproate', 'briviteracetam'] | epextra+llm |
| EA0194 | `predominant_seizure_type` | 'focal_unknown_awareness' | 'focal_impaired_awareness' | None | epextra |
| EA0195 | `current_asms` | ['carbamazepine', 'carbamazepine'] | ['carbamazepine'] | ['carbamazepine'] | epextra+llm |
| EA0197 | `current_asms` | ['lamotrigine'] | ['lamotrigine'] | ['lamotrigine', 'levetiracetam'] | epextra+llm |
