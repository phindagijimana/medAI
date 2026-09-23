## Utility demonstration #2 — seizure-freedom identification

Applied to the same 200 Fonferko-Shadrach clinic letters, silver labels flag 9 letters where the extracted seizure frequency or nearby free-text signals seizure freedom (structured `seizure_free=True` OR pattern match on "seizure-free" / "no seizures" / "remains seizure-free").

### Table 6. Seizure-freedom candidate identification per arm

| Arm | Extractions parsed | Arm-flagged | Silver-flagged | Overlap | Arm-only | Silver-only | Sens vs silver | PPV vs silver |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M0 | 200 | 0 | 9 | 0 | 0 | 9 | 0.00 | 0.00 |
| M1 | 200 | 0 | 9 | 0 | 0 | 9 | 0.00 | 0.00 |
| M2 | 202 | 0 | 9 | 0 | 0 | 9 | 0.00 | 0.00 |

Throughput at ~12 s per letter (clinical-seizure module) versus ~4 min manual review is ~20× faster.

