# Active learning from review clicks

Status: **Loops A and B are built as `bin/leo learn`. Extract does not read the files.** 2026-10-07.
Clicks are labels, not training text. Nothing hot-reloads Med42.
**Few-shot and LoRA/BIO (Loop C) are paused** until IRB notes exist and a frozen test set is held out.
Do **not** train on synthetic reviews and ship it (`docs/DEFERRED_BEYOND_MVP.md` item 2).

## How learning is triggered

It is **not** triggered by Accept, Deny, or **Permit use for training**. Those write files.

Learning is a later command you run on the study copy (or the opt-in archive), after IRB:

```bash
# 1. Keep the files (24-hour job folder is scratch)
#    Validator → Permit use for training  →  data/leo_training/<job>/
#    or copy reviewed.csv + reviews.jsonl + extract + claims off the job folder.

# 2. Score labels (does not change extract or D17)
bin/leo learn notes_leo.reviewed.csv
bin/leo learn --archive                          # all permitted jobs in data/leo_training/
bin/leo learn FILE.reviewed.csv --loop a --emit-policy policy.json

# 3. Apply only if the ≥100/field CI gate passed, as a new pipeline version
bin/leo batch notes.xlsx --disagree-llm policy:policy.json
# then re-score held-out notes; record leo-v0.x and a D-number.

# Refused on purpose:
bin/leo learn --apply     # exit: not wired to extract
bin/leo learn --lora      # exit: Loop C paused
```

`leo merge` still writes `_final` for **this job only**. The next extract is unchanged until you pass a flag on a versioned run.

| What | When | Command | Ships into extract? |
|---|---|---|---|
| Validator clicks | during review | UI / `leo review` | no |
| Durable copy | checkbox Permit | `data/leo_training/` | no |
| Loop A routing | after ≥100 scored disagreements/field | `leo learn --loop a --emit-policy` | only if you later pass `--disagree-llm policy:FILE` |
| Loop B thresholds | after enough Accept/Correct/Deny + 10% audit | `leo learn --loop b` (report) | only as a coded fusion change + new `leo-v0.x` |
| Loop C LoRA/BIO | paused | `leo learn --lora` refused | no |

## 1. What a “click” is today

| Action | Where | Stored as |
|---|---|---|
| Accept / Correct / Deny a cell | Validator tab, `bin/leo review` | `decision` on `reviewed.csv` |
| Why-tag; which reader was right | same | `why_tag`, `reader_preferred`, `quote_ok` |
| Add a missed `not_found` value | Validator “Values LEO missed” | `add` / `added_by_reviewer` |
| 10% audit of auto-accepted cells | Validator scope `accepted_audit` | same files |
| Blind disagreement vote | `bin/leo disagreements` | `truth` = A/B/both/neither |
| Label summary | `leo review --summarize FILE` | stdout |
| **Loop A/B analysis** | `bin/leo learn FILE` | stdout; optional `policy.json` |

**Durable copy (opt-in, no training).** **Permit use for training** copies `reviews.jsonl`, `reviewed.csv`, notes, and `consent.json` into `data/leo_training/<job_id>/`. Default off. Survives the 24-hour job TTL. Uncheck withdraws. Extract does not read this folder. `leo learn --archive` does.

## 2. The three loops (in order)

Each loop uses clicks as labels. Each ships as `leo-v0.x` with EVAL re-run. Never a live hot-reload.

### Loop A — routing (`leo learn --loop a`)

**Labels.** `reader_preferred` on disagreements (rules / model / both / neither). Same gate as the blind sheet (`DISAGREEMENT_ADJUDICATION.md` §3.7).

**Model.** A table: `field_path → shown reader`. `leo learn --emit-policy` and `leo disagreements --emit-policy` write the same JSON shape. Apply with `--disagree-llm policy:FILE`.

**Gate.** ≥100 scored cases/field, and the model’s Wilson lower bound above the rules’ rate. Empty JSON if unmet. **D17 stays rules-everywhere until that file is applied on a new version.**

**Do not.** Flip D17 from v4_ext, F-S 18 seizure-type letters, or `leo learn --apply`.

### Loop B — auto-accept threshold (`leo learn --loop b`)

**Labels.** Accept vs Correct vs Deny on flagged cells, **plus** the 10% accepted audit (`proposed_status=accepted`). Flagged-only precision is biased.

**Model.** Still rules: e.g. require `--quote-entail`; stop auto-accepting surgery/plans. `leo learn` prints recommendations; it does not edit fusion.

**Gate.** Held-out notes never used to set the threshold. Report precision on the held-out review sample.

### Loop C — adapter / field heads — **paused**

Do not rewrite L1C few-shot from comments. Do not train LoRA or BIO from these files until IRB + a frozen held-out set. `leo learn --lora` / `--few-shot` / `--bio` exit with that message.

When unpaused: corrected value + supporting quote; Accept only when the quote entails the cell; adapter must agree with E on E-easy cells (`docs/LORA_FLAT_CONTRACT.md`). Doctor notes are `true_value` labels, not completions to imitate.

## 3. Click schema (shipped)

| column | meaning |
|---|---|
| `decision` | accept / correct / reject / add |
| `final_value` | reviewer value (`true_value`) |
| `why_tag` | required on Deny/Correct |
| `reader_preferred` | required on disagreement |
| `quote_ok` | yes on Accept; no when why is quote_does_not_support |
| `comment` | free text; **not** a training target |

## 4. Order vs other techniques

1. Quote-entail + med status/time — reduce junk ACCEPT before we learn.
2. Loop A on **real** `reader_preferred` / disagreement sheets (`leo learn --loop a`).
3. Loop B once ~100 reviewed cells/field exist (`leo learn --loop b`).
4. Loop C **paused**.

70B, chain-of-thought, and self-consistency are not in this plan.

## 5. What would be a failure of this plan

- Training H2 or B1 on synthetic review clicks and calling it an accuracy win.
- Changing D17 from an unblinded operator preference or from `leo learn --apply`.
- Using only flagged cells to claim accepted-cell precision (selection bias).
- Mixing PHI reviews into the public repo.
- Treating Permit use for training as a Train button.
