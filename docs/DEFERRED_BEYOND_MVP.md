# Deferred beyond the MVP

Status: 2026-10-02. Decision: **deferred by the project lead.** These three items are not part of the MVP and are not scheduled. This page records what exists today, what is missing, what each item depends on, and what must not be claimed until they are done.

Related: `FUTURE_WORK.md` (LEO in the app, items 5 and 6), `LEO_USER_GUIDE.md` (sections 8, 9, 11), `EVAL_PROTOCOL_LEO.md`, `DISAGREEMENT_ADJUDICATION.md`, `US_ANNOTATION_PLAN.md`, `CORPUS_OUTREACH.md`.

## The one sentence that applies to everything

> Until real clinical notes have been run under IRB approval on secure compute, no result in this project says anything about real notes. Every accuracy figure is from synthetic text.

## 1. Reviewers adding a value LEO missed

**Deferred.** Depends on real review data.

| | |
|---|---|
| What exists | The Review tab and `bin/leo review` / `merge` let a reviewer accept, correct or reject a value LEO found. Decisions are stored append-only (`<out>.reviews.jsonl`) and as the latest decision per value (`<out>.reviewed.csv`). A field LEO did not find (`not_found`) is not offered for review. |
| What is missing | A reviewer cannot say "the note states a value here that LEO missed". |
| Consequence | Review data measures **precision** (of the values LEO produced, how many were right) but not **recall** (of the values in the note, how many LEO found). Any figure computed from review files overstates quality for that reason. The review files must not be quoted as an accuracy measurement of LEO's recall. |
| What it would take | An "add a value" action in the Review tab: pick the field, type the value, select the supporting words in the note (stored with offsets). A new decision type (`add`) in the review log, new `_review` code `added_by_reviewer`, and `_final` filled from the reviewer's value. A rule for fields where a value was found but the reviewer adds a second one (lists such as drugs). Tests for the log, merge and CSV/Excel outputs. |
| When it pays off | Only once reviewers work on real notes; on synthetic notes the generator already provides the full reference, so recall is measurable without it. |
| Do not claim | Recall, sensitivity, or "no missed values" from review data without this feature. |

## 2. Learning from review decisions

**Deferred.** Depends on real review data (and so on item 1 and on real notes). Nothing in LEO learns from review today; the decisions are stored, not used.

Order of work once data exists, each step shipped as a new pipeline version with the evaluation re-run, never as a live change:

| Step | What | Needs |
|---|---|---|
| a | Per-field rates of accepted / corrected / rejected from reviewer decisions | real reviewed notes; counts per field large enough for intervals (roughly 100 per field or the interval is too wide to use) |
| b | Reviewers add missed values (item 1), so recall can be measured | the add-value feature |
| c | Recalibrate which claims are auto-accepted, and the per-field disagreement policy (`DISAGREEMENT_ADJUDICATION.md`), from decisions, then test on notes the rules never saw | a held-out set fixed in advance; a rule written before looking, so the thresholds are not tuned on the test notes |
| d | Retrain an adapter on corrected values and their quotes | IRB approval and secure compute for training on note text; a frozen evaluation set that no corrected note comes from |

Requirements that apply to every step:

- **Reviewer reliability.** At least a subset reviewed by two people, with agreement reported (kappa), because a single reviewer's decisions are a noisy label.
- **No leakage.** Notes used to calibrate or train are never the notes used to report accuracy.
- **Synthetic corrections do not count.** Corrections made on synthetic notes say nothing about real notes and must not be used to retrain a model or tune a threshold.
- **Selection bias.** Reviewers see the values LEO flagged (and, if they choose, a sample of the accepted ones). Rates computed from flagged values alone do not describe the accepted values; a random sample of accepted values must be audited as well.
- **Privacy.** Review files contain note text and are PHI (`LEO_USER_GUIDE.md` section 9).

## 3. Real clinical notes

**Deferred.** Needs IRB approval and secure compute. Until then the project uses synthetic notes only; real notes are not needed for the MVP (decision, 2026-10-02).

Gates, all required before any real note touches LEO:

1. **IRB approval** (or documented exemption) and any data use agreement for the note source.
2. **Secure compute.** The app has no login. Started with `--local` it listens on this machine only; under Slurm it listens on the node, reachable by an SSH tunnel. Job folders are readable by the owner only and are deleted after 24 hours, but results are not encrypted on disk and the process runs as the user. That is acceptable for synthetic data and not for patient data without an approved environment. Needed first: an approved enclave or equivalent, access control, encryption at rest, an audit trail of who ran what, and a decision on retention.
3. **De-identification status** of the notes, stated in the protocol (identified, limited data set, de-identified), and the handling that follows from it.
4. **A reference.** Clinician-annotated notes to score against (`US_ANNOTATION_PLAN.md`: sampling, guideline, two annotators, adjudication). Without it, review of LEO's output is the only signal, and it measures precision only (item 1).
5. **An evaluation protocol written before the run** (as for the synthetic sets): the fields, the metrics, the decision rules, the sample size.

What the first real-note run is for: a small set, reviewed by hand, to find the failure modes the synthetic notes cannot show (hedging, copy-forward text, abbreviations, dictation artefacts, conflicting history, other centres' style). The results are recorded in `EVAL_PROTOCOL_LEO.md` as a new dated section, never merged into the synthetic figures.

Until then, these statements stay true and stay in the guide: LEO has been tested on synthetic notes only; the displayed accuracy is not a prediction for real notes; the epilepsy-specific rules were developed on the same generators as two of the test sets; the policy for model-versus-rules disagreements is a candidate, not a finding.

## Change log

| date | change |
|---|---|
| 2026-10-02 | Page created. Items 1 to 3 deferred beyond the MVP by the project lead. |
