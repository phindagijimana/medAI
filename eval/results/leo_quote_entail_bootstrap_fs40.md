# Quote-entail letter-bootstrap (F-S 40, L1C, no GPU)

Description of the 10.49 rematch on the **current** `leo-v0.9` chain. **Default stays off (D22).** Same 40 held-out letters already used in 10.49: this CI is not a confirmatory flip. Frozen extras (`leo_paper_extras_fs40`) and the 10.49 point-estimate file (`leo_quote_entail_fs40`) are not overwritten.

Letter-level bootstrap 2000 draws, seed 0. Δ = `--quote-entail` minus default.

Current-chain auto P/R (0.865 / 0.565) is not the 10.49 row (0.870 / 0.592). Do not mix them.

## Auto-accept (field micro)

| setting | P | R | F1 |
|---|---:|---:|---:|
| default (off) | 0.865 | 0.565 | 0.683 |
| `--quote-entail` | 0.910 | 0.483 | 0.631 |

| contrast | ΔP | ΔR | ΔF1 |
|---|---|---|---|
| entail − default | +0.044 [−0.008, 0.106] | −0.081 [−0.124, −0.040] | −0.052 [−0.095, −0.016] |

Δ auto-P includes 0. Δ auto-R excludes 0 (recall falls).

## Research-extract PPV

| bucket | default | entail on | Δ PPV (entail − default) |
|---|---|---|---|
| All extract cells | 74/84 = 0.881 | 62/69 = 0.899 | +0.017 [−0.020, 0.060] |
| Gold-`unknown` convention | 0/8 = 0.000 | 0/5 = 0.000 | 0.000 [0.000, 0.000] |
| Residual | 74/76 = 0.974 | 62/64 = 0.969 | −0.005 [−0.017, 0.000] |

Demoted `quote_not_entailed`: 24 (of which 12 were gold-correct).

**Decision.** KEEP default off. Residual Δ extract-PPV does not rise (point estimate −0.005; CI touches 0 from below). Mixed-extract Δ PPV includes 0. The cost is 12 gold-correct demotions. Exploratory on the same 40 letters as 10.49; not a confirmatory flip. `flip_default` = false.

The two residual extract misses on the default chain both pass the lexical entail check, so the flag does not catch true shared mistakes on this list. Mixed-extract precision rises only by dropping convention cells and gold-correct accepts.
