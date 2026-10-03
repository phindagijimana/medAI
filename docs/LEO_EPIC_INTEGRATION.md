# LEO and Epic: plan for a later use case

**Status: design only.** Nothing in this document is built, and LEO has never been run on Epic data or on any real US clinic notes. Statements about Epic and FHIR below come from general knowledge, not from your institution's Epic setup or from Epic's current documentation. Items marked **(confirm)** must be checked with your Epic analytics team and compliance office before anyone relies on them.

## 1. The use case

A researcher or clinic team wants LEO to read epilepsy notes that sit in the electronic health record and produce a table: one row per note, the original columns plus seizure type, medications, EEG and MRI findings, and so on. This is the same job as the spreadsheet workflow LEO already has ("seizure types for the first 100 subjects", see `LEO_USER_GUIDE.md`, section 8). The only new part is how notes get from Epic to LEO and how results get back.

**Research use only.** Using LEO output to guide care of a patient is a different thing (section 8).

## 2. What already exists and carries over

| Piece | Where | Relevance to Epic |
|---|---|---|
| Plain-words job description, editable and saved with results | `services/leo_job.py`, `bin/leo run`, web tab "Describe a job" | The same request ("first 100 subjects", "where note type is Progress Note") works on any table, whatever its source |
| Spreadsheet in, spreadsheet out (input columns kept) | `services/leo_batch.py` | Stage A below needs nothing else |
| Review of flagged values with quotes | Review tab, `bin/leo review/merge` | Needed before any value is used |
| One row per patient from per-note rows | `bin/leo rollup` | Epic exports are per note; analyses are per patient |
| US note clean-up (headers, templates) | `docs/US_NOTE_PREPROCESSING.md` | Written for Epic-style notes; **never quantified on real notes** |
| Runs on local hardware, no outside API | Slurm GPU node | Required: no patient text may leave institutional systems |

## 3. Three ways to connect, in order of risk

### Stage A. Export from the data warehouse, run LEO on the file (recommended first)

1. An approved analyst runs a query against the institution's Epic reporting database and exports notes to a file (CSV, Excel or Parquet). Epic's reporting databases are usually called Clarity and Caboodle **(confirm which your site uses and who can query them)**.
2. The file contains at least: note text, a patient identifier, a note date, and ideally note type and department. These become the text, subject, date and filter columns of the job description.
3. The file is placed on the secure compute system and processed with `bin/leo run "..." --input notes.xlsx`. Results come back as a file with the job description beside it.
4. Reviewers check flagged values in the Review tab. The result file goes back into the study's own data store.

Why first: no connection to Epic is needed, access is governed by the same approvals as any chart-review study, and everything already built works unchanged.

### Stage B. Read-only pull through FHIR

LEO would fetch notes itself instead of waiting for a file.

- Epic exposes FHIR APIs. Notes are normally `DocumentReference` resources whose content is a `Binary` (often HTML or RTF, which needs conversion to text) **(confirm which resource versions and note types your site exposes)**.
- A program (no human at the keyboard) usually authenticates with the SMART "backend services" method: the institution registers the app, issues it a key, and limits what it may read **(confirm)**.
- Epic offers a bulk-export route for cohorts and a public sandbox with fake patients for building and testing without real data **(confirm current availability)**.
- Work needed in LEO: a reader module that turns a list of patients and a note-type filter into the same table that Stage A takes from a file. After that step everything is identical.

Why second: needs the institution to register and approve an app, which takes weeks to months, and adds a live connection to protect.

### Stage C. Inside the Epic chart (launched from a patient record)

A SMART-on-FHIR app opened from Epic, or a CDS Hooks service, shows LEO's output while a clinician looks at a chart **(confirm what your site allows)**.

**Not recommended until the project has real-note accuracy figures and a regulatory decision** (section 8). It also changes the task: one patient, answers in seconds, a clinician reading them. LEO is built for batch runs with review, not for that.

### Out of scope

Writing anything back into Epic (problem list, discrete data, notes).

## 4. Data flow (Stage A and B)

```
Epic (reporting DB or FHIR)
   │  approved query / registered read-only app
   ▼
secure staging area  ──►  LEO on institutional compute (local Med42 + EpExtra, no external API)
   │                         │
   │                         ▼
   │                  result table + claims + job description + review decisions
   ▼                         │
 deleted per retention  ◄────┘  copied to the study's protected storage; LEO's job folder deleted
```

Rules for this flow:

- Notes stay inside institutional systems. No outside model API, no cloud copy.
- LEO keeps jobs in `data/leo_jobs/` for 24 hours by default (`MEDAI_LEO_JOB_TTL_H`). The folder is readable only by its owner. These files contain note text.
- The result file contains note text if the input columns are kept. Treat it like the input.
- Whether to de-identify before LEO sees the notes is a decision for the IRB and privacy office (section 5). LEO does not de-identify notes.

## 5. Approvals to have before real notes are used

- IRB determination or approval for the study, or a quality-improvement determination, whichever applies **(confirm which)**.
- Data access approval from whoever owns the Epic data, naming the variables, the cohort and the people.
- A decision on identifiers: full PHI on secure compute, a limited data set, or de-identified text. Name the person who approved it.
- Security review of the host (disk encryption, who can log in, backups, how files are deleted).
- Written retention rule for staged notes, job folders and result files.

## 6. What LEO must add before it is used on real patient data

These are gaps in the current code, not options.

| Gap | Today | Needed |
|---|---|---|
| Login | **Added 2026-10-03** (local users, hashed passwords; `LEO_LOCAL_DEPLOYMENT.md`). Off until the first user is added | Institutional single sign-on if the site requires it; HTTPS in front |
| Who did what | With login on, the signed-in user is recorded on every review decision | Same, tied to institutional identities |
| Audit log | **Added 2026-10-03** (`data/leo_audit.jsonl`, no note text). A plain file the app's account can edit | Tamper-resistant storage if compliance asks for it |
| Job isolation | **Added 2026-10-03**: with login on, a job is visible only to the user who started it | Review by the site's security office |
| Encryption | Relies on the host | Encrypted disk; HTTPS if the app is ever reachable over a network |
| Note-type and department filter | Job description can filter on any column the file has | Fine for Stage A; Stage B needs the same filter applied while pulling |
| Epic note formats | Preprocessor written, never measured | Measure on real notes: copied-forward text, smart phrases, templates, medication lists inside notes |
| Long runs | One Slurm job per run | Resume after failure for thousands of notes |

## 7. Accuracy: what is known and what is not

- LEO's figures come from synthetic notes and 40 to 160 UK-style clinic letters (Fonferko-Shadrach set). **No figure applies to Epic notes.**
- Epic notes differ from letters: many authors, templates, long copied-forward histories, medication lists that include drugs the patient no longer takes, and short hospital notes. These may lower accuracy, especially for current medications and seizure frequency.
- Before a result is used, a clinician-annotated sample of the local notes is needed (see `US_ANNOTATION_PLAN.md`): a few hundred notes, two reviewers on part of them, scored with `scripts/score_leo_vs_fs_gold.py` style metrics.
- Until then, every value stays a draft to be checked against its quote. A value that LEO accepted automatically is not proven correct.
- Measure how much review time per note LEO saves on the local sample, not only accuracy.

## 8. Research versus clinical use

Everything here assumes research use: a person reviews, results are used for study analysis, nothing is shown to treating clinicians in the chart.

Software that reads a patient's notes and presents information for care decisions may count as a regulated medical device or clinical decision support, depending on how it is used and presented. **I have not verified the current rules.** Ask the institution's compliance or regulatory office before Stage C or any clinical use, and do not describe LEO as validated for clinical use anywhere.

## 9. Suggested order of work

1. Confirm with the IRB and the Epic analytics team that a Stage A export is allowed and who may run it (section 5).
2. Add the login, per-user jobs and audit log (section 6) or fix access by an SSH tunnel to a single-user node.
3. Export a small set of notes (about 50), run `bin/leo run`, read the output with a clinician, and write down what goes wrong with Epic note formats.
4. Fix preprocessing from what step 3 shows; build the annotated sample (section 7) and score LEO on it.
5. Only if Stage A works and the accuracy is acceptable, ask for FHIR access (Stage B); build the reader against the sandbox first.
6. Revisit Stage C only after a regulatory answer.

## 10. Questions to settle with the institution

1. Which Epic reporting database holds notes, and who can run the export?
2. Are notes allowed on the HPC system, and in what identifier form?
3. Is there a FHIR sandbox, and who registers research apps?
4. Which note types should be read (neurology clinic, EEG reports, MRI reports, discharge summaries)?
5. Who owns the result table, and where does it live after the run?
