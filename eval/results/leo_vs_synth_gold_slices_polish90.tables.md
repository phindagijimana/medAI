# Hard slices — polish90 (robustness, not a headline)

D14. `MEDAI_SYNTH_SET=polish90`. Frozen extras stay 71/82. Do not retune E.

Sources: `leo_vs_synth_gold_slices_polish90_eonly.*` (EpExtra, all 443 notes). `slices30.*` is a 4–5-patient smoke test. L1C manifests cover 277/443 notes (5/90 patients complete) — do not read L1C/LEO F1 on this set as a complete-patient result.

Plan tags on 90 polish **training** patients (adapter trained here; rules developed here):

| slice | n patients | notes |
|---|---:|---:|
| prior (`PRIOR_ASMS`) | 65 | 319 |
| denied | 39 | 204 |
| hedged | 36 | 181 |
| hypothetical | 23 | 110 |
| any distractor | 83 | 409 |
| no distractor | 7 | 34 |

EpExtra, seven fields, patient-level micro-F1:

| group | n | P | R | F1 [95% CI] | stopped-drug leak |
|---|---:|---:|---:|---|---|
| all | 90 | 0.932 | 0.946 | 0.939 [0.916, 0.960] | 17/131 |
| prior | 65 | 0.929 | 0.951 | 0.940 [0.915, 0.962] | 17/131 |
| denied | 39 | 0.930 | 0.960 | 0.945 [0.911, 0.971] | 11/59 |
| hedged | 36 | 0.911 | 0.957 | 0.933 [0.902, 0.962] | 13/53 |
| hypothetical | 23 | 0.947 | 0.925 | 0.936 [0.888, 0.974] | 0/28 |
| any distractor | 83 | 0.930 | 0.946 | 0.938 [0.916, 0.960] | 17/131 |
| no distractor | 7 | 0.961 | 0.942 | 0.951 [0.854, 1.000] | — |

Stopped-drug leak = plan `PRIOR_ASMS` ∩ predicted `current_asms`. F1 does not drop on tagged slices versus the pool. 17/131 prior drugs (0.13) still appear as current. Not an unused-set confirmation.
