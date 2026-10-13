# LEO paper extras (F-S held-out 40; no new GPU)

Paired CIs use letter-level bootstrap, 2000 resamples, seed 0. Oracle = perfect reviewer who may only pick among values the two readers produced.

## L1C (arm L1C, 40 letters)

| system | P | R | F1 | P 95% CI | R 95% CI | F1 95% CI |
|---|---:|---:|---:|---|---|---|
| llm | 0.737 | 0.667 | 0.700 | [0.675, 0.797] | [0.605, 0.730] | [0.642, 0.761] |
| specialist | 0.695 | 0.619 | 0.655 | [0.615, 0.773] | [0.537, 0.692] | [0.582, 0.723] |
| leo_auto | 0.851 | 0.544 | 0.664 | [0.772, 0.925] | [0.460, 0.622] | [0.584, 0.734] |
| leo_review | 0.669 | 0.687 | 0.678 | [0.597, 0.743] | [0.620, 0.751] | [0.613, 0.743] |
| oracle_pick | 0.877 | 0.728 | 0.796 | [0.812, 0.938] | [0.662, 0.789] | [0.738, 0.849] |

Paired differences (letter bootstrap):
| contrast | ΔP | ΔR | ΔF1 |
|---|---|---|---|
| leo_auto-llm | +0.114 [0.051, 0.181] | -0.123 [-0.172, -0.076] | -0.037 [-0.082, +0.005] |
| leo_auto-specialist | +0.156 [0.106, 0.210] | -0.075 [-0.118, -0.034] | +0.009 [-0.029, +0.046] |
| leo_review-llm | -0.067 [-0.114, -0.014] | +0.020 [-0.020, +0.062] | -0.022 [-0.062, +0.022] |
| leo_review-specialist | -0.025 [-0.056, +0.005] | +0.068 [0.034, 0.104] | +0.024 [-0.005, +0.056] |
| oracle_pick-llm | +0.141 [0.082, 0.203] | +0.061 [0.026, 0.100] | +0.095 [0.056, 0.138] |

**C1 (auto-accept precision > model and > rules):** leo_auto−llm ΔP +0.114 [0.051, 0.181] → supported; leo_auto−specialist ΔP +0.156 [0.106, 0.210] → supported.
**C3 (reviewed recall > rules):** leo_review−specialist ΔR +0.068 [0.034, 0.104] → supported.
**Oracle** F1 0.796; vs model +0.095 [0.056, 0.138]. Flagged items already right as shown: 19 of 83 (0.229).
**Research extract** (accepted ∧ agree): 71/82 = 0.866 (same band as C2 agree precision).

Cohort on these 40 letters (not the old M1 200-letter demo):
| source | onset n / median | polytherapy rate (≥2 current ASMs) |
|---|---|---|
| llm | 4 / 7.0 | 0.375 |
| specialist | 3 / 6.0 | 0.5405405405405406 |
| leo_auto | 3 / 6.0 | 0.3783783783783784 |
| leo_review | 4 / 7.0 | 0.5641025641025641 |
| oracle_pick | 4 / 7.0 | 0.40540540540540543 |
| gold | 4 / 7.0 | 0.425 |
