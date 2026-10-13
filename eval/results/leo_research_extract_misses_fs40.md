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

The three “no” rows are mostly lexicon holes, not unsupported quotes: “Juvenile Myoclonic Epilepsy” is not matched as `JME`; “symptomatic epilepsy” is not a type keyword. Do not retune that lexicon on these letters.

Eight of ten misses are typed epilepsy versus gold `unknown` (diagnosis-line convention). Frozen extras remain 71/82; this list is the current chain (74/84, 10 misses).

Not a gold-error adjudication. Wittlinger-style: these rows are the place a person would look first.