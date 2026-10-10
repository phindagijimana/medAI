# Quote-entail rematch and research-extract misses (F-S 40, L1C, no GPU)

Default fusion is unchanged (`quote_entail` off). This is a measurement of `--quote-entail` and the Wittlinger-style list of accepted ∧ agree cells that miss gold.

Letters: 40. Arm L1C from `data/run_manifests_fs_test_flat_c`.

## Headline systems

| setting | auto P | auto R | auto F1 | reviewed F1 | research extract |
|---|---:|---:|---:|---:|---|
| default (off) | 0.870 | 0.592 | 0.704 | 0.773 | 74/84 = 0.881 |
| --quote-entail | 0.910 | 0.483 | 0.631 | 0.773 | 62/69 = 0.899 |

Routing with entail on: accept 181, review 284, demoted `quote_not_entailed` 28 (of which 16 were gold-correct).

**Decision.** Precision rose; still keep default off until a letter-bootstrap CI excludes 0 (this script does not flip D22). Default stays off (D22).

## Research-extract misses on the default chain (n=10)

These are the cells in the research extract (accepted ∧ both readers) that do not match gold. `quote_entails` is the lexical check, run on the default accept (the flag is off, so they stayed accepted).

| letter | field | pred | gold | quote entails? | quote |
|---|---|---|---|---|---|
| EA0166 | `clinical_seizure.epilepsy_type` | generalized | unknown | **no** | Juvenile Myoclonic Epilepsy |
| EA0167 | `clinical_seizure.epilepsy_type` | focal | unknown | yes | temporal lobe epilepsy |
| EA0168 | `clinical_seizure.epilepsy_type` | generalized | unknown | yes | Juvenile Myoclonic Epilepsy |
| EA0169 | `clinical_seizure.epilepsy_type` | focal | unknown | **no** | symptomatic epilepsy |
| EA0180 | `clinical_seizure.epilepsy_type` | generalized | unknown | yes | Juvenile Myoclonic Epilepsy |
| EA0181 | `clinical_seizure.epilepsy_type` | focal | unknown | **no** | symptomatic epilepsy |
| EA0182 | `clinical_seizure.epilepsy_type` | focal | unknown | yes | TLE |
| EA0186 | `clinical_seizure.predominant_seizure_type` | focal_to_bilateral_tonic_clonic | focal_unknown_awareness | yes |  focal to bilateral convulsive seizur |
| EA0188 | `clinical_seizure.epilepsy_type` | focal | unknown | yes | Focal epilepsy |
| EA0188 | `clinical_seizure.seizure_frequency` | {'period': 'day', 'count_min': 1.0, 'count_max': 1.0} | {'seizure_period': 'month'} | yes | 1 seizure per day |

Of 10 misses, 3 have a quote that does not entail the value. Those would have gone to review if the flag were on.

The three “no” rows are mostly **lexicon holes**, not Windisch unsupported quotes: “Juvenile Myoclonic Epilepsy” is not matched as `JME` / “generalized epilepsy”; “symptomatic epilepsy” is not a type keyword. Do not retune that lexicon on these held-out letters.

Eight of ten misses are a **typed** epilepsy (JME, TLE, focal) versus gold `unknown`. That is the F-S diagnosis-line convention, not a silent quote failure.

Frozen paper extras (`leo_paper_extras_fs40.md`, earlier pipeline) remain **71/82 = 0.866**. This rematch is the current chain: **74/84 = 0.881**. Do not mix the two rows.

Not a gold-error adjudication. Wittlinger-style: these rows are the place a person would look first. Default `--quote-entail` stays **off** (16 gold-correct cells demoted).