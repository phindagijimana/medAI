# LEO user guide

LEO (pipeline `leo-v0.5`) reads clinical notes and fills a table: one row per note, one set of columns per phenotype. Each note is answered on its own (visits are independent); if one patient has several notes you get several rows, and a patient-level table is available only when you ask for it (`bin/leo rollup`). Each value carries the exact words it came from, where it came from (LLM, specialist or both), and whether it is accepted or needs a person to look at it. **LEO has been tested on synthetic notes only, never on real clinical notes** (section 7).

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
bin/leo disagreements notes_leo.claims.csv   # optional: export model-vs-rules disagreements for blind adjudication
bin/leo rollup notes_leo.csv --patient-col patient_id [--date-col visit_date]   # optional: one row per patient
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

**Several notes per patient.** Every note is a row with its own answer, so a drug that was stopped or a seizure type that changed shows up as it was written at each visit. To get one row per patient, run `bin/leo rollup RESULT.csv --patient-col ID [--date-col DATE]`: for each field it takes the latest note that states a value (by `--date-col`, else by row order) and never mixes values from different notes. The roll-up adds `<field>_from_row`, `_from_date` and `_why` so you can see which note supplied each value. Roll-up accuracy has not been measured.

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

**What has been tested.** Five phenotypes (epilepsy type, seizure type, onset age, seizure frequency, current ASMs) have accuracy figures on synthetic notes (section 7). Rescue medication, one-off administration and prior ASMs are only **partly tested**: their effect on the current-ASM list was checked, not their own accuracy. Seven more were scored with the rules alone (no LLM) on synthetic notes and are marked **rules tested**: etiology category, drug resistance status, MRI findings, MRI normal, hippocampal sclerosis, focal cortical dysplasia and surgery history (table in section 7). The remaining eight (semiology, focal motor and non-motor onset, failed ASMs, EEG study type, background and ictal onset, etiology details) have **no accuracy figures** because the synthetic reference record has no entries for them; use them as a first draft to review and do not quote performance. `bin/leo phenotypes` and the app show this level beside every item. Drug resistance status is **inferred** by a rule from the ASM history (an approximation of Kwan et al. 2010 that cannot judge whether a trial was adequate or tolerated), so its evidence text can be a rule description rather than a quote.

### Questions

Besides fixed phenotypes you can ask a question of every note:

```bash
bin/leo batch notes.csv --ask-template aura --ask-template status_epilepticus
bin/leo batch notes.csv --question "Which side is the lesion?" --question-type text
bin/leo ask note.txt "Has the patient had a seizure in the last year?" --type yes_no
```

Templates: `status_epilepticus, epilepsy_surgery, neurostimulation, family_history, febrile_seizures, aura, nocturnal, triggers, adverse_effects, driving, pregnancy, developmental, psychiatric, seizure_free_duration`.

Questions are answered by the LLM alone (the specialist has no concept for them) and need the GPU. The LLM must give a quote and LEO checks that the quote is in the note. That check shows the quote exists, not that it supports the answer. Outcomes: `needs_review` (quote found; always reviewed, because there is one reader), `rejected` (quote not in the note; the answer is shown but not trusted), `not_documented` (the note does not say). Question accuracy is in section 11. A drug question is also checked for the quote being about that drug; a quote about other drugs gives `rejected`. Columns: `ask_<id>`, `_status`, `_evidence`, `_question`.

## 6. Long notes

Notes up to 8000 characters go to the LLM whole. Longer notes are cut at section, then paragraph boundaries into chunks of at most 8000 characters with 400 characters of overlap. Single-value fields take the value most chunks agree on (a tie goes to the earliest chunk); drug lists are unioned. The specialist always reads the whole note, so a long note is still read end to end by one channel. Change the limit with `--chunk-chars` or `MEDAI_LEO_CHUNK_CHARS`; `leo_n_chunks` shows what happened.

Caveat: chunking was measured on long synthetic documents only (section 11), not on real notes. Check a sample of long ones by hand before trusting them.

## 7. What the evidence supports

**LEO versus the model alone, in one paragraph.** On the tests so far, LEO is not more accurate than Med42-8B used by itself. On the 40 F-S letters the model alone scored 0.70 and LEO's reviewed output 0.68 (difference -0.02, 95% CI -0.06 to +0.02, so no detectable difference). On the near-saturated synthetic US notes the model scored 0.993 and LEO reviewed 0.969 (-0.024, CI -0.053 to -0.004). What LEO adds is a record of where each value came from (a quote, a source, a reason), a second reader that catches some mistakes (values where the model and rules agreed were right 83% of the time on the F-S letters and 99.9% on the synthetic notes, against 31% and 12% where they disagreed), and a review flag instead of silent guessing. Whether that is worth the extra machinery for your use depends on whether you need the audit trail. That has not been tested with real clinicians, and none of this has been tested on real notes.

`bin/leo evidence` (also `GET /leo/evidence`) prints the figures; they are read from the evaluation scorer outputs, not typed into the code, and a test checks they match. They describe the shipped configuration: `leo-v0.5`, arm L1C (base Med42-8B, two fixed examples, schema-constrained decoding), with the rules' value shown on a disagreement.

**When the model and the rules disagree**, both values are kept: LEO shows the rules' value, flags the cell `needs_review` (`source_disagreement`), and stores the model's value as `alternative` in `claims.csv`. Which reader to show first, per field, is **not settled**. On synthetic notes, showing the model's value for seizure type scored better (F1 0.80 → 1.00 on 80 unused synthetic patients; 0.34 → 0.57 on the F-S letters) and for epilepsy type worse (0.975 → 0.938), with no difference for onset age and frequency. Those sets share a generator with the rules' development data and the F-S epilepsy-type reference is weak, so the default stays with the rules' value everywhere until disagreements from real notes have been adjudicated. The cost of that default is visible: on the F-S letters the reviewed micro-F1 is 0.68 instead of 0.71 with the seizure-type option (`--disagree-llm candidate`). To help settle it, `bin/leo disagreements RESULT.claims.csv` exports every disagreement for blind adjudication (the two values appear as A and B in a hidden order) and `bin/leo disagreements --score SHEET` reports per field how often each reader was right, with intervals. Protocol: `docs/DISAGREEMENT_ADJUDICATION.md`.

| Test set | n | Model alone | Rules alone | LEO auto-accepted | LEO reviewed |
|---|---|---|---|---|---|
| 40 held-out F-S letters (UK style, synthetic) | 40 letters | 0.70 | 0.66 | 0.66 | 0.68 |
| 30 synthetic US-style patients | 30 patients | 0.99 | 0.97 | 1.00 | 0.97 |

Micro-F1 over seven fields. What this does and does not show:

- Every test note is synthetic. Nothing here measures performance on real clinical notes.
- On the F-S letters, LEO's reviewed output (0.68) does not beat the model alone (0.70; paired difference -0.02, 95% CI -0.06 to +0.02). It beats the rules alone only narrowly (+0.02, CI -0.01 to +0.06). With a fine-tuned model (Arm H2, not offered by the app yet) the model alone scored 0.74 and LEO reviewed 0.69 (difference -0.05, CI -0.10 to -0.01). The fusion's value shown so far is the audit trail (quotes, sources, review flags), not higher accuracy.
- Seizure type is weak on the F-S letters (F1 0.34 reviewed, 0.56 for the model alone) with the default, because the rules' value is shown when the two disagree; this is the field where the candidate option helps most.
- Epilepsy type: the F-S reference says "unknown" when the diagnosis line names no type (25 of 38 letters). Where the reference names a type (13 letters) reviewed F1 is 1.00; over all 38 letters it is 0.42 because LEO often states a type where the reference says unknown. Whether those are errors was not adjudicated.
- Onset age has only 4 reference values on the F-S letters, so 1.00 there is weak evidence.
- Agreement is informative: values where model and rules agreed were right 83% (F-S) and 100% (synthetic) of the time; rules alone 25% and 86%; model alone 46% and 94%; where they disagreed 31% (16 values) and 12% (43 values).
- The synthetic US-style notes are close to saturated (the model alone scores 0.99) because they were written from the same plan as their reference; they cannot rank methods. The EpExtra rules were developed against these corpora.
- The live GPU path was compared with the evaluation outputs on 2026-10-02: same text for 30 of 40 F-S letters and 125 of 143 synthetic notes, and the scores moved by 0.01 or less (section 11).

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

**Current ASMs and rescue drugs.** `current_asms` is the maintenance regimen. As-needed rescue drugs (for example rectal diazepam, intranasal midazolam) go to a separate `rescue_medication` column and one-off doses given during the visit go to `acute_administration`. The F-S reference counts rescue drugs as current (it follows ExECT), so the F-S column above scores them in; the synthetic reference does not, so that column scores them out. Both are shown for what they are. Whether a rescue-only drug counts as "on an ASM" for your study is for you to decide.

Partly tested: rescue medication, acute administration and prior ASMs (only their effect on current ASMs was checked).

### Other phenotypes (rules only, synthetic)

Scored with the rules alone, on 80 synthetic patients the rules were not developed on, with each patient's notes joined into one document (MRI items: the 30 patients who have an MRI report). The model was not used, so these say how good the rules are, not LEO's two-reader result. "When answered" leaves out patients for whom the rules gave no value: the rules never infer that something is absent, so a note that never mentions hippocampal sclerosis gets no value, while the reference says "no".

| Phenotype | Result (80 held-out patients) |
|---|---|
| Etiology category | right for 77 of 80 |
| Drug resistance status | right for 76 of 80 |
| MRI findings (list) | precision 0.50, recall 0.93 (the rules also list findings the reference does not record) |
| MRI normal | 29 of 29 answered right (answered for 29 of 30) |
| Hippocampal sclerosis | 18 of 19 answered right (answered for 19 of 30) |
| Focal cortical dysplasia | 11 of 14 answered right (answered for 14 of 30) |
| Surgery history | the rules wrongly reported a procedure for 5 of 80 patients whose reference lists none |

Rule fixes made on 2026-10-02 (surgery options no longer count as history, negated MRI findings are not reported, drug-resistance statements read per sentence) raised drug resistance from 15 to 29 of 30 and cut surgery false alarms from 19 of 30 to 0 on the patients that showed the problems; the 80-patient figures above are the ones to rely on. Read drug resistance and surgery history as drafts to review. Not scoreable because the synthetic reference has no entry: semiology, focal onset features, failed ASMs, EEG findings, etiology details. Free-text questions are covered in section 11.

### Precision of accepted values, by agreement

| Values where | F-S letters | Synthetic US |
|---|---|---|
| Model and rules agree | 0.835 | 0.999 |
| They disagree (rules' value shown) | 0.312 (16 values) | 0.116 (43 values) |
| Model only | 0.455 | 0.943 |
| Rules only | 0.250 | 0.857 |

Definitions follow Fisher et al. 2017 and Scheffer et al. 2017 (ILAE) and Kwan et al. 2010 (drug resistance); the full citations are listed in the project's references document.

## 8. Web app

`bin/leo start` queues the server; `bin/leo status` prints the node, port and an SSH tunnel command; the page is `/leo/ui` (also linked from the extract page). Pick a panel or individual phenotypes (each item is marked "rules tested", "partly tested" or "not tested"), add predefined or typed questions, paste a note or upload a file, choose csv or xlsx, watch progress, download (csv comes as a zip) and delete the job. Jobs live in `data/leo_jobs/` for 24 hours (`MEDAI_LEO_JOB_TTL_H`). `bin/leo stop` cancels the Slurm job. The page links to this guide (`/leo/guide`, which redirects to the copy on GitHub; set `LEO_GUIDE_URL` to point elsewhere).

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

- Notes, outputs and job files can contain PHI. Run real notes only on approved secure compute with IRB approval. The server has no login. Started with `--local` it listens on this machine only (`127.0.0.1`); on a Slurm node it listens on the node so an SSH tunnel can reach it, and `--host` overrides either. Job folders are readable by the owner only and deleted after 24 hours; results are not encrypted on disk.
- The audit ledger is off by default (it would store note text).
- RxNorm and SNOMED CT are UMLS-licensed. They are not in git (`data/ontologies/*` is ignored except the manifest) and must not be redistributed.
- The UMLS key lives only in `.env` and is never printed.

## 10. Adapters

A flat-contract LoRA adapter (Arm H2) is used with `--adapter DIR` (arm becomes `L0C`). On the F-S letters H2 alone scored 0.74 against 0.70 for the base model with examples (difference +0.04, 95% CI +0.01 to +0.08); on the synthetic notes it scored 0.996 (30 patients) and 0.992 (80 patients) against 0.993 and 0.988 for the base model, which is saturated. The app's displayed figures are for the base model. Arm H adapters trained on the full phenotype contract are not used by this path.

## 11. Known limits

- Live GPU path: run on an L40S GPU on 2026-10-02 (evaluation protocol 10.12). The live model reproduces the stored evaluation text exactly for 30 of 40 F-S letters and 125 of 143 synthetic notes; the rest differ slightly (newer software) and the scores move by 0.01 or less.
- Long documents (10-40k characters, chunked; 30 synthetic patients, rerun 2026-10-02 after the rule fixes, with the seizure-type candidate option on): the model alone scores 0.991, LEO's auto-accepted values 0.970 and its reviewed output 0.967 (it was 0.928 before the rule fixes). The rules still lose accuracy on long joined text (0.932). Up to 20k characters, chunked and whole-document model runs scored 1.000 and 0.987 (11 documents).
- Free-text questions (synthetic, 30 patients, rerun with the stricter quote check): epilepsy type and onset age 30/30; hippocampal sclerosis 11/17; "currently taking this drug?" 94/114 (yes-answers: precision 0.78, recall 0.96); 2 of 90 unanswerable questions got an invented answer. The stricter check marks an answer `rejected` when its quote is not about the drug asked: of 15 false "yes" answers it rejected 11, and of the answers it still trusted (quote found, `needs_review`) 110 of 116 were right (95%, against 88% before). The price is that it also rejected 44 correct answers (they are still shown, marked untrusted). A located quote proves the words are in the note, not that they support the answer: always read the quote.
- Patient-level roll-up exists but is not measured; per-note rows are the supported output. The long-document figures above come from several visits joined into one text, which mixes visit states; they test chunking, not how a patient should be summarised.
- Not validated on real clinical notes yet (needs IRB and secure compute; plan in the evaluation protocol).
