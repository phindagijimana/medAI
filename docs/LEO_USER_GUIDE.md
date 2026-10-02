# LEO user guide

LEO (pipeline `leo-v0.5`) reads clinical notes and fills a table: one row per note, one set of columns per phenotype. Each value carries the exact words it came from, where it came from (LLM, specialist or both), and whether it is accepted or needs a person to look at it. **LEO has been tested on synthetic notes only, never on real clinical notes** (section 7).

LEO = Med42-8B (language model, constrained to a fixed answer format) + EpExtra (the MedCAT/ExECT-style specialist) + ontology candidates, joined by fixed fusion rules (described in the project's routing-rules document).

## 1. Quick start

```bash
bin/leo install --check-only          # are the packages there?   (drop --check-only to install the missing ones)
bin/leo check                         # login-node check (CPU, specialist only)
bin/leo check --slurm                 # the same plus the model on a GPU node; output in logs/leo_jobs/
bin/leo phenotypes                    # what can be extracted
bin/leo batch notes.xlsx              # submits a Slurm GPU job; writes notes_leo.xlsx next to the input
bin/leo start                         # web app as a Slurm GPU job; then `bin/leo status`
bin/leo review notes_leo.csv         # list the values to review in notes_leo.reviewed.csv (fill in `decision`)
bin/leo merge notes_leo.csv notes_leo.reviewed.csv   # add the reviewed values as new columns
```

## 2. Where it runs

| You type | Runs on | Model | Use it for |
|---|---|---|---|
| `leo batch / start` (default) | Slurm GPU node (`gpu:l40s.24g:1`, partition `interactive` for batch, `general` for the server) | Med42-8B + EpExtra | real extraction |
| `... --cpu` | Slurm CPU node | EpExtra only | quick look, no GPU available |
| `... --local` | this node | `--mode auto` (GPU if present, else CPU and it says so) | tests, small files |

CPU / rules-only mode has no second reader, so **every value is marked `needs_review`** (reason `no_second_reader`) and nothing is `accepted`; with `--accepted-only` the table is empty. The reason is measured: claims made by the rules alone were right 25% of the time on the F-S letters and 86% on the synthetic US-style notes (`bin/leo evidence`). Free-text questions are unavailable. The output says `specialist_only` in `provenance.json`, the About sheet and the `leo_llm_used` column.

Slurm jobs source `.env` (the key stays in `.env`; scripts never contain it) and use `venv-medcat`. Change time or partition with `--hours` and `--partition`.

## 3. Input

| Format | Notes |
|---|---|
| `.csv`, `.tsv` | UTF-8 (BOM fine). Everything is read as text, so ids like `007` are kept |
| `.xlsx`, `.xlsm` | first sheet, or `--sheet NAME` |
| `.jsonl` | one JSON object per line |
| `.txt` | one note |
| a directory | every `*.txt` in it, one row per file (`note_id` = file name) |

The note column is found automatically from `text, note, note_text, clinical_note, source_text, content, report`; otherwise pass `--text-col`. LEO stops with an error rather than guess. Optional `--id-col` (a row id is used if none) and `--date-col` (EpExtra uses the note date for date arithmetic; the model path does not use it).

Your own columns are copied through first, unchanged. If your file already has a column with an LEO name (for example `epilepsy_type`), LEO's column gets a `_leo` suffix instead of overwriting yours.

## 4. Output

| `--format` | Files |
|---|---|
| `csv` (default for csv/tsv/txt/jsonl input) | `<out>.csv` (your columns + LEO columns, UTF-8 with BOM so Excel opens it), `<out>.claims.csv` (one row per claim), `<out>.provenance.json` (settings and versions, no note text) |
| `xlsx` (default for Excel input) | `<out>.xlsx` with sheets `LEO` (the table), `Claims`, `About` (settings, definitions, caveats) |

Default output name is `<input>_leo.csv|xlsx` next to the input (or the current directory if that is read only). The files contain note text: keep them wherever the notes are allowed to be. They are gitignored (`*_leo.*`, `leo_out/`).

### Columns per phenotype

For a phenotype `X`:

| Column | Meaning |
|---|---|
| `X` | the value (`focal`, `11`, `2 per month`, `lamotrigine; levetiracetam`) |
| `X_status` | `accepted` (passed LEO's automatic checks: the two sources agree, or one source made the claim and nothing contradicted it; this is not a guarantee, see section 7), `needs_review` or `not_found` |
| `X_evidence` | the exact words in the note |
| `X_source` | `llm`, `specialist` or `llm+specialist` |
| `X_why` | reason codes (`source_disagreement`, `llm_only`, `specificity_unsupported`, `conflicting_values` ...) |
| `X_detail` | lists only: drugs with dose text |
| `seizure_frequency_count_min/_max/_period/_seizure_free` | frequency as numbers, for sorting and counting |

Per row: `leo_doc_id`, `leo_status` (`ok` or `error: ...`; a bad row never stops the run), `leo_llm_used`, `leo_n_chunks`, `leo_n_claims`, `leo_n_review`.

`needs_review` means a person should check it; the value is still shown. `--accepted-only` leaves those cells blank for a conservative table. Rejected claims (words not found in the note) are never shown in the table; they stay in `claims.csv` with their verdict.

Cells beginning with `= + - @` get a leading apostrophe so Excel does not run them as formulas. Cells are cut at 2000 characters.

Offsets in `claims.csv` point into the note after LEO normalises section headers, not the raw file.

## 5. What it extracts

`bin/leo phenotypes` lists them. Choose with `--phenotypes core`, `--phenotypes seizure,eeg` or `--phenotypes epilepsy_type,current_asms`.

| Panel | Contents |
|---|---|
| `core` (default) | epilepsy type, seizure type, age at onset, seizure frequency, current ASMs |
| `seizure` | the above plus semiology and focal motor / non-motor onset |
| `medication` | current, prior, failed ASMs, rescue medication, one-off administration, drug resistance |
| `etiology`, `eeg`, `mri`, `surgery` | as named |
| `all` | all 23 |

**What has been tested.** Five phenotypes (epilepsy type, seizure type, onset age, seizure frequency, current ASMs) have accuracy figures on synthetic notes (section 7). Rescue medication, one-off administration and prior ASMs are only **partly tested**: their effect on the current-ASM list was checked, not their own accuracy. The other fifteen have **no accuracy figures**; use them as a first draft to review and do not quote performance for them. `bin/leo phenotypes` and the app show this level beside every item. Drug resistance status is **inferred** by a rule from the ASM history (an approximation of Kwan et al. 2010 that cannot judge whether a trial was adequate or tolerated), so its evidence text can be a rule description rather than a quote.

### Questions

Besides fixed phenotypes you can ask a question of every note:

```bash
bin/leo batch notes.csv --ask-template aura --ask-template status_epilepticus
bin/leo batch notes.csv --question "Which side is the lesion?" --question-type text
bin/leo ask note.txt "Has the patient had a seizure in the last year?" --type yes_no
```

Templates: `status_epilepticus, epilepsy_surgery, neurostimulation, family_history, febrile_seizures, aura, nocturnal, triggers, adverse_effects, driving, pregnancy, developmental, psychiatric, seizure_free_duration`.

Questions are answered by the LLM alone (the specialist has no concept for them) and need the GPU. The LLM must give a quote and LEO checks that the quote is in the note. That check shows the quote exists, not that it supports the answer. Outcomes: `needs_review` (quote found; always reviewed, because there is one reader), `rejected` (quote not in the note; the answer is shown but not trusted), `not_documented` (the note does not say). Question accuracy has not been tested. Columns: `ask_<id>`, `_status`, `_evidence`, `_question`.

## 6. Long notes

Notes up to 8000 characters go to the LLM whole. Longer notes are cut at section, then paragraph boundaries into chunks of at most 8000 characters with 400 characters of overlap. Single-value fields take the value most chunks agree on (a tie goes to the earliest chunk); drug lists are unioned. The specialist always reads the whole note, so a long note is still read end to end by one channel. Change the limit with `--chunk-chars` or `MEDAI_LEO_CHUNK_CHARS`; `leo_n_chunks` shows what happened.

Caveat: the evaluation sets are short notes. Chunk merging is unit tested but **not yet validated on long real notes**. Check a sample of long ones by hand before trusting them.

## 7. What the evidence supports

**LEO versus the model alone, in one paragraph.** On the tests so far, LEO is not more accurate than Med42-8B used by itself. On the 40 F-S letters the model alone scored 0.70 and LEO's reviewed output 0.68 (difference -0.02, 95% CI -0.06 to +0.02, so no detectable difference). What LEO adds is a record of where each value came from (a quote, a source, a reason), a second reader that catches some mistakes (values where the model and rules agreed were right 83% of the time, against 31% where they disagreed), and a review flag instead of silent guessing. Whether that is worth the extra machinery for your use depends on whether you need the audit trail. That has not been tested with real clinicians, and none of this has been tested on real notes.


`bin/leo evidence` (also `GET /leo/evidence`) prints the figures; they are read from the evaluation scorer outputs, not typed into the code, and a test checks they match. They describe the shipped configuration: `leo-v0.5`, arm L1C (base Med42-8B, two fixed examples, schema-constrained decoding), no override of disagreements (section 10.9 of the evaluation protocol).

| Test set | n | Model alone | Rules alone | LEO auto-accepted | LEO reviewed |
|---|---|---|---|---|---|
| 40 held-out F-S letters (UK style, synthetic) | 40 letters | 0.70 | 0.66 | 0.66 | 0.68 |
| 30 synthetic US-style patients | 30 patients | 0.99 | 0.97 | 1.00 | 0.97 |

Micro-F1 over seven fields. What this does and does not show:

- Every test note is synthetic. Nothing here measures performance on real clinical notes.
- On the F-S letters, LEO's reviewed output (0.68) does not beat the model alone (0.70; paired difference -0.02, 95% CI -0.06 to +0.02). It beats the rules alone only narrowly (+0.02, CI -0.01 to +0.06). The fusion's value shown so far is the audit trail (quotes, sources, review flags), not higher accuracy.
- Seizure type is weak on the F-S letters (F1 0.34 reviewed, 0.56 for the model alone) with the shipped default. A policy that lets the model win seizure-type disagreements scored 0.57 there, but it was chosen on F-S development letters and is not on by default (`--disagree-llm predominant_seizure_type`). Confirm it on an unused set before turning it on.
- Epilepsy type: the F-S reference says "unknown" when the diagnosis line names no type (25 of 38 letters). Where the reference names a type (13 letters) reviewed F1 is 1.00; over all 38 letters it is 0.42 because LEO often states a type where the reference says unknown. Whether those are errors was not adjudicated.
- Onset age has only 4 reference values on the F-S letters, so 1.00 there is weak evidence.
- Agreement is informative: values where model and rules agreed were right 83% (F-S) and 100% (synthetic) of the time; values from the rules alone 25% and 86%; model alone 46% and 94%.
- The synthetic US-style notes are close to saturated (the model alone scores 0.99) because they were written from the same plan as their reference; they cannot rank methods. The EpExtra rules were developed against these corpora.
- The live GPU path uses the same prompt and decoding code as the evaluation, but its output has not been compared with the evaluation manifests on a GPU yet.

### Accuracy by field (F1)

"Reviewed" is every value LEO returns, including those flagged for review. "Auto-accepted" is only the values LEO accepted without review. "Model alone" is Med42-8B without the rules. n is the number of notes with a reference value.

| Field | Scored as | F-S letters: reviewed / auto / model alone (n) | Synthetic US: reviewed / auto / model alone (n) |
|---|---|---|---|
| Epilepsy type | all records | 0.42 / 0.39 / 0.33 (38) | 0.97 / 1.00 / 0.97 (30) |
| Epilepsy type | only where the reference names a type | 1.00 / 0.92 / 0.92 (13) | 1.00 / 1.00 / 1.00 (29) |
| Seizure type | predominant type | 0.34 / 0.31 / 0.56 (18) | 0.92 / 0.98 / 1.00 (26) |
| Age at onset | within 1 year | 1.00 / 0.86 / 1.00 (4) | 1.00 / 1.00 / 1.00 (30) |
| Seizure frequency | period | 0.71 / 0.48 / 0.71 (15) | 0.97 / 1.00 / 1.00 (19) |
| Seizure frequency | count, lower bound | 1.00 / 0.91 / 1.00 (6) | 0.97 / 1.00 / 1.00 (30) |
| Seizure frequency | count, upper bound | 0.83 / 0.91 / 1.00 (6) | 0.97 / 1.00 / 1.00 (30) |
| Current ASMs | drug names | 0.84 / 0.87 / 0.88 (37) | 0.98 / 1.00 / 0.99 (30) |

Fields not in this table (the other 15 phenotypes, and all free-text questions) have not been scored. Partly tested: rescue medication, acute administration and prior ASMs (only their effect on current ASMs was checked). Drug resistance is inferred by a rule from the medication history, an approximation of the ILAE 2010 definition, and is not scored.

### Precision of accepted values, by agreement

| Values where | F-S letters | Synthetic US |
|---|---|---|
| Model and rules agree | 0.835 | 0.999 |
| They disagree | 0.312 | 0.116 |
| Model only | 0.455 | 0.943 |
| Rules only | 0.250 | 0.857 |

Definitions follow Fisher et al. 2017 and Scheffer et al. 2017 (ILAE) and Kwan et al. 2010 (drug resistance); the full citations are listed in the project's references document.

## 8. Web app

`bin/leo start` queues the server; `bin/leo status` prints the node, port and an SSH tunnel command; the page is `/leo/ui` (also linked from the extract page). Pick a panel or individual phenotypes (items without accuracy figures are marked "not tested" or "partly tested"), add predefined or typed questions, paste a note or upload a file, choose csv or xlsx, watch progress, download (csv comes as a zip) and delete the job. Jobs live in `data/leo_jobs/` for 24 hours (`MEDAI_LEO_JOB_TTL_H`). `bin/leo stop` cancels the Slurm job. The page links to this guide (`/leo/guide`, which redirects to the copy on GitHub; set `LEO_GUIDE_URL` to point elsewhere).

### Reviewing values

After a file run finishes, the **Review** tab (also linked from the result as "Review N values") lists the values that need review, one at a time: LEO's value, why it was flagged, the quote, and a **Show in note** button that highlights the quote in the note. For each value choose **Right**, **Correct it** (type the right value) or **Wrong** (the final value is left blank). **Undo** withdraws a decision. Enter a reviewer name or ID first (initials or a pseudonym, never a patient name). Decisions are saved as you click. Switch the view to "All values found" to spot-check values LEO accepted on its own.

Two files are kept next to the result (both contain note text, so treat them like the input):

- `<out>.reviews.jsonl`: every decision ever made, with LEO's original proposal, the reviewer and the time. Append only.
- `<out>.reviewed.csv`: the latest decision per value, one row each. You can open it in Excel.

LEO's own columns are never changed. **Results with reviewed values** (or `bin/leo merge`) writes a copy of the result with two columns added after each field:

| Column | Meaning |
|---|---|
| `<field>_final` | The value to use: the reviewer's, or LEO's if the value was auto-accepted. |
| `<field>_review` | Where it came from: `accepted_by_reviewer`, `corrected`, `rejected`, `auto_accepted` (LEO's own checks passed and nobody looked; not a human decision), `unreviewed`, or blank (nothing found). |

A value that needed review and was not reviewed is left blank in `_final` (marked `unreviewed`), because LEO did not trust it. Choose "keep LEO's value" to fill it with LEO's value instead. For Excel output the merged workbook keeps the Claims and About sheets and adds a Reviews sheet.

Without the web app: `bin/leo review RESULT.csv` writes a `RESULT.reviewed.csv` listing the values to review with `decision` empty. Fill `decision` (`accept`, `correct` or `reject`) and, for `correct`, `final_value`; then `bin/leo merge RESULT.csv RESULT.reviewed.csv` (add `--keep-unreviewed` to fill unreviewed values with LEO's). The merge refuses a reviewed file whose rows or `doc_id`s do not match the result.

What review does not do yet: a reviewer cannot add a value LEO missed (`not_found`), so misses do not appear in these files, and nothing learns from the decisions automatically. The decisions are the raw material for measuring accuracy on real notes and, later, for recalibrating the routing rules or retraining (needs IRB approval and secure compute; see the project's future-work notes). Corrections made on synthetic notes say nothing about real notes. Review is for file runs; a single pasted note has no review step.

API: `GET /leo/phenotypes`, `GET /leo/evidence`, `GET /leo/guide`, `GET /leo/status`, `POST /leo/extract`, `POST /leo/batch`, `GET /leo/jobs/<id>[/download]`, `GET|POST /leo/jobs/<id>/review`, `GET /leo/jobs/<id>/note/<row>`, `GET /leo/jobs/<id>/review/export?kind=reviewed|merged&unreviewed=blank|proposal`, `POST /leo/jobs/<id>/cancel`, `DELETE /leo/jobs/<id>`. `llm=auto|on|off` per request.

## 9. Data protection

- Notes, outputs and job files can contain PHI. Run real notes only on approved secure compute with IRB approval. The server has no login: reach it through the SSH tunnel and do not expose the port.
- The audit ledger is off by default (it would store note text).
- RxNorm and SNOMED CT are UMLS-licensed. They are not in git (`data/ontologies/*` is ignored except the manifest) and must not be redistributed.
- The UMLS key lives only in `.env` and is never printed.

## 10. Adapters

A flat-contract LoRA adapter (Arm H2, once trained and evaluated) is used with `--adapter DIR` (arm becomes `L0C`). Arm H adapters trained on the full phenotype contract are not used by this path.

## 11. Known limits

- Live GPU path: unit tested with a fake model and run on CPU; the first real GPU run is `bin/leo check --slurm`. Record the result in the evaluation protocol.
- No patient-level roll-up yet (several notes per patient into one row): see the project's future-work notes.
- Not validated on real clinical notes yet (needs IRB and secure compute; plan in the evaluation protocol).
