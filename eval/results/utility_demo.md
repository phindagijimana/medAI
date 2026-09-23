## Downstream utility demonstration — ILAE 2010 drug-resistance identification

Across the 200 Fonferko-Shadrach clinic letters, silver-labeled medication timelines flag 16 candidates meeting an operationalized ILAE 2010 drug-resistance criterion (direct `drug_resistant` status OR ≥2 failed / prior ASMs). Below we report each Med42-8B arm's candidate identification against the silver reference — treating this as a plausibility check on the downstream analytic pipeline the framework enables, not a claim of clinical performance.

### Table 6. Drug-resistant candidate identification per arm

| Arm | Extractions parsed | Arm-flagged | Silver-flagged | Overlap | Arm-only | Silver-only | Sens vs silver | PPV vs silver |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M0 | 200 | 3 | 16 | 2 | 1 | 14 | 0.12 | 0.67 |
| M1 | 200 | 9 | 16 | 3 | 6 | 13 | 0.19 | 0.33 |
| M2 | 202 | 2 | 16 | 0 | 2 | 16 | 0.00 | 0.00 |

Extraction pipeline throughput (M1 arm, empirical from SLURM job 89472): ~9 s per letter. Baseline manual chart review for drug-resistance identification (conservative estimate from prior epilepsy-NLP literature): ~8 min per letter. Aggregate ratio for the 200-letter corpus: **~53× faster** (30 min extraction vs. 1600 min manual). This estimate is illustrative — the framework's value on real cohorts is proportional to the letter count and the number of downstream variables extracted; drug-resistance is one of many.

