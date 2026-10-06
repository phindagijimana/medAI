# How to read the LEO results

Status: 2026-10-02. Read this before quoting any figure from `EVAL_PROTOCOL_LEO.md` or `LEO_USER_GUIDE.md`.

Every figure comes from synthetic notes. Until real notes have been run under IRB approval on secure compute (`DEFERRED_BEYOND_MVP.md`), no result here says anything about real notes.

## 1. What the headline numbers measure

One thing: whether the value in LEO's output equals the value in a reference, over seven fields (epilepsy type, seizure type, onset age, seizure frequency in three parts, current ASMs), as micro-F1.

| System | What it is |
|---|---|
| model alone | Med42-8B, no rules |
| rules alone | EpExtra, no model |
| LEO auto-accepted | only values LEO accepted without review |
| LEO reviewed | every value LEO returns, **including those flagged for review, counted as if they were answers** |

"LEO reviewed" is the output **before a person looks at it**. It is not the end product. In use a reviewer corrects the flagged values, so the comparison that matches the use case is the model alone against LEO plus a reviewer, together with the reviewer's effort. That comparison has not been made. The tie between LEO reviewed and the model alone therefore says LEO adds no accuracy before review; it does not say LEO adds nothing.

## 2. Long documents: the numbers and what they allow

Stage `long` of `scripts/leo_gpu_validate.py`: 30 synthetic patients, each patient's notes (several visits) joined into one document of 10 to 40 thousand characters, 3 to 7 chunks of at most 8,000 characters. Patient-level micro-F1, no confidence intervals (not bootstrapped).

| | First run (before the rule fixes) | Rerun 2026-10-02 |
|---|---|---|
| model alone | 0.991 | 0.991 |
| rules alone | 0.932 | 0.932 |
| LEO auto-accepted | 0.970 (precision 1.00, recall 0.94) | 0.970 |
| LEO reviewed | 0.928 | 0.967 (precision 0.95, recall 0.99) |
| time per patient | 34 to 89 s | 1,668 s for 30, about 56 s each |

What this supports:

- **Chunking does not hurt the model.** 0.991 on long documents against 0.993 per note. This is a sanity result on synthetic text, not a validation on real long notes.
- **The rules lose accuracy on long joined text** (0.932 against 0.971 per note). In the reviewed output the loss is mostly extra drugs listed as current (10 false positives in 61 true ones): a drug stopped at an earlier visit looks current when visits are joined.
- **Chunked against whole-document cannot be compared fairly.** Only 11 documents (up to 20 thousand characters) fit unchunked: 1.000 chunked, 0.987 whole, a difference of about one value, no evidence either way.
- **The test is a stress test, not the supported mode.** LEO answers per note (D16). A joined document asks "what is true of this patient overall?", which mixes visit states. The result tests chunking, not patient summarisation.
- The rerun used the seizure-type candidate policy for part of the day (the code default was changed and reverted); the reviewed figure includes it, the other columns do not depend on it (`EVAL_PROTOCOL_LEO.md` 10.15).

## 3. What the statistics say about the data

Several results describe the data more than LEO.

| Observation | What it says about the data |
|---|---|
| Same model: 0.70 on the F-S letters, 0.99 on the synthetic US notes | The sets differ in difficulty and in how the reference was made, not only in style. |
| Synthetic notes: the model alone scores 0.99 | Saturated. The notes were written from the same plan as their reference, so they cannot rank methods. The rules were also developed on the same generators. |
| F-S epilepsy type "unknown" in 25 of 38 letters | The reference is a keyword rule over the diagnosis line. It cannot tell a model error from an unadjudicated inference, so the all-letters F1 (0.42) mixes the two; the typed-only view (13 letters) is 1.00. |
| F-S reference values: 4 for onset age, 18 for seizure type | Some field scores rest on a handful of values; their intervals are wide. |
| Rescue drugs count as current in the F-S gold, not in the synthetic gold | A labelling convention changes the score of identical output (D6). |
| Disagreement precision rests on 16 (F-S) and 43 (synthetic) values | Too few to rely on; cells under the candidate policy have 8. |
| Joined multi-visit documents | They mix visit states; patient-level and per-note scores answer different questions. |

Consequence: a tie on F-S means "as accurate as the model on 40 letters with this reference", not "equivalent to the model".

## 4. What the numbers do not cover

LEO is more than an accuracy figure. The roles below are either only partly measured or not measured.

| Role | Evidence now |
|---|---|
| **Triage: separating reliable from unreliable values** | Measured in part. Precision where the readers agree: 0.835 (F-S), 0.999 (synthetic); where they disagree: 0.31 and 0.12. Auto-accepted values have precision 0.85 against 0.74 for the model alone on F-S, at the price of coverage (recall 0.54). This gain is real but does not appear in the headline F1. |
| **Error capture: of the model's errors, how many does LEO flag?** | Not computed. Can be computed from existing outputs (section 5). |
| **Reviewer workload** | Not computed. The share of claims routed is known per run (F-S, 414 claims: accept 0.41, review 0.56, reject 0.03; synthetic 30 patients, 2,796 claims: accept 0.62, review 0.36, reject 0.02); accuracy after review has not been scored. |
| **Audit trail** | Every value carries its quote, character offsets, source and reason code. Not an accuracy result; its worth is the ability to check. Not tested with clinicians. |
| **Safe failure** | Values with no supporting words are rejected; with no model, nothing is marked accepted (`no_second_reader`); questions can return "not documented" (2 of 90 invented answers in the unanswerable controls). |
| **Workflow** | Review tab, review file and merge, per-note output, optional roll-up, local and Slurm operation. Tested as software (333 tests), not for time saved. |
| **Breadth** | 28 extract phenotypes; the 7-field headline covers 5 of them. Twenty-one more have a rules-only figure; one (`mri_lesion`) has none. |

## 5. Analyses that would measure usefulness (planned, not run)

No new model runs are needed for the first two; they use the claim tables and manifests already in `data/` and `eval/results/`.

1. **Error capture.** Over the F-S letters and the synthetic sets: of the values where the model alone is wrong against the reference, the fraction LEO routes to review or rejects, against the fraction it accepts; and the fraction of values LEO flags that were in fact right (false alarms). Report per field with intervals.
2. **Workload and post-review accuracy.** The share of values needing review, and the accuracy of the output if every flagged value were replaced by the reference value (an upper bound that assumes a perfect reviewer) and by a noisy reviewer (a stated error rate). Compare with the model alone at the same effort.
3. **Reviewer time and agreement on real notes** (needs real notes and IRB): minutes per note against unaided abstraction; agreement between two reviewers (`DEFERRED_BEYOND_MVP.md`, `DISAGREEMENT_ADJUDICATION.md`).

Each result goes into `EVAL_PROTOCOL_LEO.md` as a dated section, with the question and the decision rule written before the run.

## Change log

| date | change |
|---|---|
| 2026-10-02 | Page created from the review of the long-document and F-S results. |
