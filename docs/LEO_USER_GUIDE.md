# LEO user guide

LEO (pipeline `leo-v0.9`) reads a clinical note and fills a phenotype table: value, quote from the note, which reader said it (model, rules, or both), and whether a person should look. On a clash both values are kept; the **rules** are shown and the cell is flagged (D17 — not flipped). One note = one row. Roll-up is optional and is **not** the extract. **Tested on synthetic notes only, never on real clinical notes.**

How it was built, and what the numbers mean: `docs/IMPLEMENTATION.md`, `docs/INTERPRETING_RESULTS.md`. Figures: `bin/leo evidence`.

## 1. Commands

```bash
bin/leo install --check-only
bin/leo check                         # CPU / specialist only
bin/leo check --slurm                 # plus Med42 on a GPU node
bin/leo phenotypes                    # catalogue and evidence level
bin/leo evidence                      # measured figures (not typed into the UI)
bin/leo batch notes.xlsx              # Slurm GPU; writes notes_leo.xlsx next to the input
bin/leo batch notes.xlsx --cpu        # rules only; every cell needs_review
bin/leo batch notes.xlsx --local      # this node
bin/leo run "seizure types for the first 100 subjects" --input notes.xlsx
bin/leo start                         # web app; then bin/leo status
bin/leo review notes_leo.csv          # cells to review → notes_leo.reviewed.csv
bin/leo review notes_leo.reviewed.csv --summarize
bin/leo merge notes_leo.csv notes_leo.reviewed.csv
bin/leo learn notes_leo.reviewed.csv   # Loop A/B; does not change extract
bin/leo disagreements notes_leo.claims.csv   # model-vs-rules for blind adjudication
bin/leo rollup notes_leo.csv --patient-col patient_id [--date-col visit_date]
```

Web: `bin/leo user add NAME` (turns login on), `bin/leo start`, `bin/leo status`, `bin/leo stop`. Page: `/leo/ui`.

## 2. Where it runs

| Command | Where | Readers |
|---|---|---|
| `leo batch` / `start` (default) | Slurm GPU | Med42-8B + EpExtra |
| `--cpu` | Slurm CPU | EpExtra only — **every value is `needs_review`** |
| `--local` | this node | GPU if present, else CPU (it says so) |

CPU / rules-only has no second reader. `--accepted-only` then yields an empty table. Jobs source `.env` and `venv-medcat`.

Slurm resources (override per site): `--partition`, `--hours`, `--gres` (default `gpu:l40s.24g:1` or `MEDAI_LEO_GRES`), `--cpus`, `--mem`. Defaults here: GPU 8 CPU / 64G / L40S 24G; CPU 16 / 48G. Workstation vs HPC: `docs/LEO_HOSTING.md`.

## 3. Input and output

**In:** `.csv` `.tsv` `.xlsx` `.jsonl` `.txt`, or a directory of `*.txt`. Note column is found from `text, note, note_text, clinical_note, source_text, content, report`, else `--text-col`. Your columns are copied through; a name clash gets `_leo`.

**Out:** `<input>_leo.csv|xlsx` plus `.claims.csv` and `.provenance.json` (xlsx has sheets LEO / Claims / About). Files contain note text. Gitignored.

For each phenotype `X`: `X`, `X_status` (`accepted` / `needs_review` / `not_found`), `X_evidence` (quote), `X_source` (`llm` / `specialist` / `llm+specialist`), `X_why`, `X_alternative` (other reader on a clash). Row: `visit_summary` (under 50 words from this note’s cells; `[?]` = review).

**Research extract** (GPU): `accepted` **and** `specialist+llm`. That is the table whose accuracy is scored (71/82 = 0.866 on the 40-letter gold). `--accepted-only` is coarser. Do not treat CPU output as accepted facts. `needs_review` is still shown; use `--accepted-only` to blank it. Accepted is an agree-band filter, not a claim the cell is safe or that a clinician trusts it (`docs/INTERPRETING_RESULTS.md`).

`bin/leo rollup` takes, per field, the latest note that states a value. It hides visit-to-visit change. Unmeasured.

## 4. What to extract

`bin/leo phenotypes`. Default panel `core`: epilepsy type, seizure type, age at onset, seizure frequency, current ASMs (the five with measured figures on synthetic notes). `seizure_onset_class` (focal / generalized / unknown onset) is in the `seizure` panel; it can be accepted when the readers agree on the class but not the exact seizure type. Epilepsy type `unknown` means the note says epilepsy but names no type. On the F-S gold that `unknown` is a **diagnosis-line keyword**: letters that name JME / TLE / “focal epilepsy” are scored as misses against it. The **typed-only** view (13 of 38 letters) is the fair one; do not train the model to emit `unknown` from those letters. Other panels: `seizure`, `medication`, `etiology`, `eeg`, `mri`, `surgery`, `all`. Evidence level is next to each item (`measured` / `rules_only` / `none`).

Questions (GPU, one reader — always review): `--ask-template aura` or `--question "Which side is the lesion?"`. Quote is checked against the note; that proves the words exist, not that they support the answer.

Optional flags (off by default; they do not flip D17): `--quote-entail`, `--ext-detector …`, `--ask-rag`, `--export-codes`, `--h2`. `--quote-entail` stays off until a letter-bootstrap CI says accept PPV pays the recall; do not retune its lexicon on held-out letters. See `docs/IMPLEMENTATION.md`.

## 5. Web app and Validator

`bin/leo start` → `/leo/ui` (also `/`). Paste a note or upload a file. Paste download is the same CSV zip / Excel as a one-row spreadsheet (`note_id`, `text`, then `epilepsy_type`, `epilepsy_type_status`, …). The on-screen Phenotype / Value / Status table is for reading only. **Describe a job** turns a sentence into a job file you confirm before anything runs (`bin/leo run "…"`). Jobs live 24 hours in `data/leo_jobs/` (`MEDAI_LEO_JOB_TTL_H`). The paper M0/M1/M2 page is a separate URL (`/extract/ui`), not a LEO tab.

**Validator** (same store as the download):

- **Accept** — keep LEO’s value. Note optional.
- **Correct** — typed value + quote. Why required. Do not fold into Deny.
- **Deny** — unsupported / not in the note. Why required. Note encouraged.
- **Add missed** — for `not_found`.
- Why: `wrong_value` / `wrong_status` / `quote_does_not_support` / `wrong_reader` / `copy_forward` / `missed` / `other`.
- On a disagreement: which reader was right (`rules` / `model` / `both` / `neither`).
- **Accepted sample (10% audit)** — silent errors on auto-accepted cells. Flagged-only rates are biased.
- **Permit use for training** — copies this job into `data/leo_training/` (survives 24 h). Off by default. Does not train.

Files: `<out>.reviews.jsonl` (append-only), `<out>.reviewed.csv` (latest per cell). Merge adds `<field>_final` and `<field>_review`; LEO’s columns are never overwritten. CLI: `leo review` then `leo merge`. A pasted single note has no review store.

## 6. Learning (not live)

Clicks are files. Extract does not read them.

```bash
bin/leo learn FILE.reviewed.csv
bin/leo learn --archive
bin/leo learn FILE.reviewed.csv --loop a --emit-policy policy.json
# apply only after the ≥100/field CI gate, as a new leo-v0.x:
bin/leo batch notes.xlsx --disagree-llm policy:policy.json
```

Loop A = which reader to show. Loop B = accept-threshold report (still rules). Loop C (few-shot / LoRA) is paused. `leo learn --apply` and `leo learn --lora` are refused. **Not applied:** no display-policy change until ≥100 scored clashes per field and a CI gate on real `reader_preferred`. `docs/ACTIVE_LEARNING_PLAN.md`.

## 7. Data protection

Real notes only on approved compute with IRB. No login until `bin/leo user add NAME`. `--local` binds `127.0.0.1`. Job folders owner-only, deleted after 24 hours, **not encrypted**. `data/leo_training/` is owner-only and is **not** deleted with the job. UMLS key stays in `.env`. Do not commit review files.

## 8. Limits

Not validated on real notes. LEO does not beat Med42-8B on F1. Fine-tune (H2) is off fusion (C5 not supported vs L2C). Accepted cells are not “safe” (~0.85–0.87 concordant PPV). The ontology does not raise that number. Do not flip D17; do not train epilepsy-type `unknown`; `--quote-entail` stays off. What is weak: `docs/WEAKNESSES.md`. How to quote numbers: `docs/INTERPRETING_RESULTS.md`.
