# How to read the LEO results

Status: 2026-10-10. Read this before quoting any figure from `EVAL_PROTOCOL_LEO.md`. Operator steps: `LEO_USER_GUIDE.md`. Design: `IMPLEMENTATION.md`.

Every figure comes from synthetic notes. Until real notes have been run under IRB approval on secure compute (`DEFERRED_BEYOND_MVP.md`), no result here says anything about real notes.

LEO’s job is not to beat the model on F1. It is to keep the cells where two readers agree (the **research extract**), **evaluate that table’s accuracy against gold**, flag clashes, and attach the note’s own words. On the 40 letters that accuracy is concordant PPV 71/82 = 0.866 (same band as C2 0.835; Alwakeel / Khan). That is not a trust study and not a claim that accepted cells are safe (auto-accept precision 0.85; pre-v0.9 leak 19/49, v0.9 rematch 20/49 — do not write rules from the hold-out list). Fusion exists so disagreement is a flag, not a silent guess. Judge LEO as that review instrument. The headline 0.68 vs 0.70 is the display policy (rules shown on a clash), not a broken extractor.

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
| **Triage: separating accept-band from review-band values** | Measured in part. Precision where the readers agree: 0.835 (F-S), 0.999 (synthetic); where they disagree: 0.31 and 0.12. Auto-accepted values have precision 0.85 against 0.74 for the model alone on F-S, at the price of coverage (recall 0.54). About one in six to seven accepted cells is still wrong versus gold. This gain is real but does not appear in the headline F1. |
| **Error capture: of the model's errors, how many does LEO flag?** | Computed on F-S 40 (no new GPU): `eval/results/leo_error_capture_fs40.md`, `scripts/score_leo_error_capture.py`. Oracle reviewer bound on 160 letters: `leo_oracle_review_fs160.md`. |
| **Reviewer workload** | Not computed. The share of claims routed is known per run (F-S, 414 claims: accept 0.41, review 0.56, reject 0.03; synthetic 30 patients, 2,796 claims: accept 0.62, review 0.36, reject 0.02); accuracy after review has not been scored. |
| **Audit trail** | Every value carries its quote, character offsets, source and reason code. Quote-in-note is presence, not support (`--quote-entail` off by default). Not an accuracy result; not a clinician or auditor study. |
| **Safe failure** | Values with no supporting words are rejected; with no model, nothing is marked accepted (`no_second_reader`); questions can return "not documented" (2 of 90 invented answers in the unanswerable controls). Opt-in extra detectors (`--ext-detector`, D18–D20) never auto-accept (`sidecar_only`), cannot un-accept E, and are **not** in the headline figures. `--ask-rag` / `--export-codes` / `--context-engine` (D21) likewise stay out of headline F-S / v4_ext files. |
| **Workflow** | Review tab, review file and merge, per-note output, optional roll-up, local and Slurm operation. Tested as software (333 tests), not for time saved. |
| **Breadth** | 41 extract phenotypes; the 7-field headline covers 5 of them. Thirty-four more have a rules-only figure; one (`mri_lesion`) has none. |

## 5. Analyses that measure usefulness (review instrument)

No new GPU runs are needed for the first two; they use the claim tables and manifests already in `data/` and `eval/results/`.

1. **Error capture.** Of the values where the model alone is wrong against the reference, the fraction LEO routes to review or rejects, against the fraction it accepts; and the fraction of values LEO flags that were in fact right (false alarms). **F-S 40 held-out, L1C, pre-v0.9:** 49 model-wrong of 124; 30/49 (0.61) not auto-accepted; **19/49** (0.39) accepted anyway; 16/41 flags already right. **v0.9 rematch:** 29/49 captured; **20/49** leak; 15/43 flags already right. Letter table: `eval/results/leo_error_capture_fs40.md`. Eight leaks are typed epilepsy vs gold `unknown`. Do not write rules from that hold-out list. No bootstrap. Synthetic-set capture is not run.
2. **Workload and post-review accuracy.** Share of values needing review, and F1 if a perfect reviewer may only pick among values the two readers already produced (cannot add missed facts). **Same 40 held-out letters as the headline:** oracle F1 0.796 [0.738, 0.849], +0.095 [0.056, 0.138] vs the model (`leo_paper_extras_fs40.md`). **160 F-S letters (L1):** +0.079 (`leo_oracle_review_fs160.md`). **Noisy-reviewer curve** (CPU, same pick constraint, *p* ∈ {0, 0.10, 0.25, 0.50, 1}): F1 0.858 → 0.846 → 0.834 → 0.746 → 0.605 (`leo_noisy_review_fs40.md`). *p* = 0 on this rematch is not a replacement for frozen 0.796. Not reviewer minutes. The 40-letter headline still scores `leo_review` as the uncorrected draft. Paired precision/recall CIs for C1/C3 are in the extras file.
3. **Reviewer time and agreement on real notes** (needs real notes and IRB): minutes per note against unaided abstraction; agreement between two reviewers (`DEFERRED_BEYOND_MVP.md`, `DISAGREEMENT_ADJUDICATION.md`).

Each result goes into `EVAL_PROTOCOL_LEO.md` as a dated section, with the question and the decision rule written before the run.

## 6. Analyses the phenotype table can support (not yet on real notes)

Section 5 measures whether LEO is a useful *review instrument*. This section is the other question: once cells pass the research-extract filter (`accepted` **and** `specialist+llm`; `LEO_USER_GUIDE.md`), what *epidemiology* the columns can feed. Those tables have not been shown to match a chart review. Do not treat this as clinical decision support. Design: `docs/IMPLEMENTATION.md`.

The extract is a rectangular table (per note, or per patient via `bin/leo rollup`) of ILAE phenotypes, drugs, EEG/MRI and surgery.

| Family | What you can count or join | Bound |
|---|---|---|
| Clinic description | ILAE 2017 epilepsy/seizure type, onset age, frequency / seizure-free | Core five fields only have measured F1, and only on synthetic notes. |
| Medication / DRE | Current ASM lists, polytherapy, an ILAE 2010-style resistance label | Resistance is inferred; it is not a trial-adequacy audit (Kwan et al. 2010). |
| Imaging–EEG | MRI normal/HS/FCD, IEDs, ictal onset, derived concordance | Mostly rules-only synthetic scores; concordance inherits three localizations. |
| Surgery / devices | Resection, VNS, RNS, DBS as listed | Over-calls plans as history. |
| Longitudinal | Per-note rows: drug and frequency change across visits | Roll-up hides change; its accuracy is unmeasured. `visit_summary` is under 50 words from that row’s cells, not a second extract. |
| Linkage | Etiology specifics; NINDS CDE correspondence | Needs IRB. Mapping: `docs/NINDS_CDE_MAPPING.md` (not an exporter). |

A worked check that **field error moves a cohort number**: `scripts/cohort_demo.py` (onset-age median/IQR, polytherapy ≥2 ASMs, temporal-lobe mention on the F-S letters; gold vs extract). That is utility of the *table*, not a leaderboard.

Do not compute incidence, survival, trial eligibility or surgical decisions from unreviewed cells.

## 7. Research-extract strata and quote-entail CI (2026-10-13)

Views only. Frozen extras stay **71/82 = 0.866**. Current-chain extract is 74/84 = 0.881 (`leo_extract_strata_fs40.md`). Do not mix the two rows.

Convention rule (fixed): `epilepsy_type` and gold is `unknown` and pred is `focal` / `generalized`. That slice is 0/8. Residual extract PPV is **74/76 = 0.974** [0.933, 1.000]. The two residual misses (EA0186 seizure type; EA0188 frequency) both entail. Do not recode gold; do not train `unknown`.

`--quote-entail` on the same 40 letters (`leo_quote_entail_bootstrap_fs40.md`): Δ auto-P +0.044 [−0.008, 0.106] includes 0; Δ auto-R −0.081 [−0.124, −0.040]; residual Δ extract-PPV −0.005 [−0.017, 0.000]; 12 gold-correct cells demoted. **Default stays off.** Same hold-out as 10.49 — description, not a confirmatory flip.

## Change log

| date | change |
|---|---|
| 2026-10-13 | Extract strata + quote-entail letter-bootstrap (10.51). Frozen 71/82 untouched. Default `--quote-entail` stays off. |
| 2026-10-09 | Unsupported claims (C5, F1 win, trust, real notes, “safe”, O raises C1) tabulated in `writing/contributions.md` §3.1. |
| 2026-10-10 | Manuscript + TRIPOD-LLM + `writing/supplement_leo_accept_errors.md` updated from the rematch. D17 / quote-entail default / train-unknown / Loop A/B apply stay No. Frozen extras 0.796 / 71/82 untouched. |
| 2026-10-10 | v0.9 rematch (10.50): leak list 20 cells; noisy curve run. D17 / quote-entail default / train-unknown / Loop A/B apply stay No. Frozen extras 0.796 / 71/82 untouched. |
| 2026-10-09 | Quote-entail scored (10.49): default stays off. Research-extract misses listed (10 on current chain; 8 are gold `unknown`). Frozen extras remain 71/82. |
| 2026-10-09 | Aligned wording with `writing/contributions.md`: accept signal vs gold, not “trusted cells”; 0.85 ≠ safe. |
| 2026-10-07 | Stated the mission: LEO is a review instrument (quote, source, review flag, ontology id, both readers on a clash). Added §6: analyses the phenotype table can support. §5 error-capture and oracle-review paths filled. |
| 2026-10-02 | Page created from the review of the long-document and F-S results. |
