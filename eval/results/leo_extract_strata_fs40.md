# Research-extract strata (F-S 40, L1C, no GPU)

Views of the current-chain research extract (`accepted` ∧ both readers). **Frozen headline stays 71/82 = 0.866** (`leo_paper_extras_fs40`). Do not replace that number with these rows.

Letters: 40. Arm L1C from `data/run_manifests_fs_test_flat_c`. Letter-level bootstrap 2000 draws, seed 0.

Convention rule (fixed, not letter-by-letter): `epilepsy_type` and gold is `unknown` and pred is `focal` / `generalized` / `combined_focal_generalized` (D6).

## Default chain (quote-entail off)

| bucket | correct / scored | PPV | letter-bootstrap 95% CI |
|---|---|---:|---|
| All extract cells | 74/84 | 0.881 | [0.805, 0.946] |
| Gold-`unknown` convention | 0/8 | 0.000 | [0.000, 0.000] |
| Residual (true shared mistakes) | 74/76 | 0.974 | [0.933, 1.000] |

Convention misses: 8. Residual misses: 2.

### Residual misses

| letter | field | pred | gold | quote entails? |
|---|---|---|---|---|
| EA0186 | `clinical_seizure.predominant_seizure_type` | focal_to_bilateral_tonic_clonic | focal_unknown_awareness | yes |
| EA0188 | `clinical_seizure.seizure_frequency` | {'period': 'day', 'count_min': 1.0, 'count_max': 1.0} | {'seizure_period': 'month'} | yes |

### Convention misses (typed vs gold `unknown`)

| letter | pred | gold | quote entails? | quote |
|---|---|---|---|---|
| EA0166 | generalized | unknown | **no** | Juvenile Myoclonic Epilepsy |
| EA0167 | focal | unknown | yes | temporal lobe epilepsy |
| EA0168 | generalized | unknown | yes | Juvenile Myoclonic Epilepsy |
| EA0169 | focal | unknown | **no** | symptomatic epilepsy |
| EA0180 | generalized | unknown | yes | Juvenile Myoclonic Epilepsy |
| EA0181 | focal | unknown | **no** | symptomatic epilepsy |
| EA0182 | focal | unknown | yes | TLE |
| EA0188 | focal | unknown | yes | Focal epilepsy |

Do not recode gold to match LEO. Do not train `unknown`. Do not write E from these rows.
