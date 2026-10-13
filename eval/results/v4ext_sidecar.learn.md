# LEO learn (labels only; extract unchanged)

Files: 1. Decisions: 4. Gate: ≥100 scored cases/field. D17 stays until a new leo-v0.x.

leo learn does not change extract. If a policy JSON meets the ≥100/field CI gate, apply it on a new leo-v0.x with --disagree-llm policy:FILE. D17 stays until then.

Loop C (few-shot / LoRA / BIO) is paused until IRB notes exist and a frozen test set is held out. Doctor clicks are labels, not completions. See docs/ACTIVE_LEARNING_PLAN.md.

## Loop A — routing (which reader to show)

No `reader_preferred` votes yet. On a disagreement the Validator requires rules / model / both / neither.

## Loop B — accept thresholds (still rules)

| field | n | accept | correct | deny | add | audit n | flagged n |
|---|---:|---:|---:|---:|---:|---:|---:|
| `current_asms` | 1 | 0 | 0 | 1 | 0 | 0 | 1 |
| `epilepsy_type` | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| `other_seizure_types` | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| `seizure_type` | 1 | 0 | 0 | 1 | 0 | 0 | 1 |

Accepted audit (proposed_status=accepted): n=0 kept=0 changed=0 precision=n/a. Flagged queue: n=3 kept=1 changed=2 precision=0.33.
Flagged-only rates are biased; the 10% accepted sample is the silent-error check.
Why tags: `wrong_status` 1, `missed` 1, `wrong_value` 1.

Recommendations (not applied):
- Loop B: fewer than 10 accepted-audit clicks. Switch the Validator to Accepted sample (10% audit) so silent errors are measured.
- Loop B gate: no field has ≥100 reviewed cells. Report rates; do not change auto-accept thresholds yet.
- Recommendations are not applied. A threshold change is a new pipeline version after a held-out re-score.

## Loop C — paused

Loop C (few-shot / LoRA / BIO) is paused until IRB notes exist and a frozen test set is held out. Doctor clicks are labels, not completions. See docs/ACTIVE_LEARNING_PLAN.md.

