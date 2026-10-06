# Model-versus-rules disagreements: policy status and adjudication protocol

Status: 2026-10-02. Companion to `EVAL_PROTOCOL_LEO.md` (D15, D17, 10.13) and `LEO_ROUTING_RULES.md` section 1.

## 1. Current position

When Med42-8B (the model) and EpExtra (the rules) give different values for a single-value field, LEO keeps both and flags the cell `needs_review` (`source_disagreement`). One value is shown; the other is stored as the claim's `alternative` (column `alternative` in `<out>.claims.csv`).

| Setting | Shown on a disagreement | When to use |
|---|---|---|
| **Default (pilot)** | the rules' value, every field | all pilot work, and any run whose disagreements will be adjudicated |
| `--disagree-llm candidate` | the model's value for seizure type, the rules' value elsewhere | only to reproduce the synthetic results below; not validated on real notes |
| `--disagree-llm FIELD,...` | the model's value for the named fields | experiments |

Why the default is "rules everywhere" and not the candidate policy:

- The candidate policy was chosen on 40 F-S development letters and checked on two synthetic sets that share a generator with the rules' development data. Real notes (hedging, copy-forward text, conflicting history) were not tested.
- On the F-S letters only 18 letters carry a seizure-type reference, and its confidence interval is wide. The F-S epilepsy-type reference is a keyword rule over the diagnosis line ("unknown" in 25 of 38 letters), so it cannot tell a model error from an unadjudicated inference.
- Using one reader's value as the displayed value anchors the reviewer. For the data in section 3 to be usable, the displayed value should not be a guess we have not tested. Showing the rules' value everywhere is the more conservative choice: it is the ExECT behaviour, and the model's value is still visible to the reviewer as the alternative.

## 2. What the synthetic evidence says (not a verdict)

| Field | Reviewed F1, rules shown | Reviewed F1, model shown | Set |
|---|---:|---:|---|
| seizure type | 0.80 | 1.00 | 80 unused synthetic patients |
| seizure type | 1.00 | 1.00 | 101 synthetic patients (tie) |
| seizure type | 0.34 | 0.57 | 18 F-S letters (policy chosen here) |
| epilepsy type | 0.975 | 0.938 | 80 unused synthetic patients |
| epilepsy type | 0.995 | 0.995 | 101 synthetic patients (tie) |
| onset age, frequency | no difference | | both sets |

Details and files: `EVAL_PROTOCOL_LEO.md` 10.13 and `eval/results/leo_vs_*_candidate.*`, `leo_vs_synth_gold_{ext,v1v2}_{default,llmwins}.*`. This is a hypothesis to test on real notes, not a finding.

## 3. Protocol to settle it on real notes (needs IRB and secure compute)

1. **Run** the pilot notes with the default setting and keep `<out>.claims.csv`.
2. **Export** the cases: `bin/leo disagreements RESULT.claims.csv` writes `RESULT.disagreements.csv`. Each row is one disagreement, with the two readings in a hidden, reproducible order (`reading_A`, `reading_B`; the key is in `key_A_is`). The sheet holds the evidence quote, so it is PHI.
3. **Blind the sheet.** Keep one copy with `key_A_is`; give the adjudicator a copy without that column. The adjudicator also needs the note itself.
4. **Adjudicate.** Fill `truth` per row: `A`, `B`, `both` (both readings are acceptable, for example a synonym), `neither` (give `true_value`), or `unclear`. Rules agreed in advance and written into the study protocol before the first sheet is opened:
   - what counts as the correct value for the field (for seizure type: the ILAE 2017 operational classification, as written in the note, not an inference);
   - what to do when the note states several seizure types or conflicting diagnoses (`unclear`, with a comment);
   - what to do when the note names no epilepsy type (the reference is "unknown", not a guess).
5. **Two adjudicators** for at least a subset (suggest 20% or 50 cases per field, whichever is larger), so agreement (Cohen's kappa) is reported. Disagreements between adjudicators go to a third reader.
6. **Score**: `bin/leo disagreements --score SHEET_WITH_KEY --shown rules` prints, per field, how often the rules were right, how often the model was right, and the counts for both/neither/unclear, with Wilson 95% intervals.
7. **Decide per field**, fixed in advance: switch a field to the model's value only if the model is right more often than the rules with the lower end of its interval above the rules' rate (or the model's rate exceeds the rules' by a margin written in the protocol), on at least 100 scored cases for that field. Otherwise keep the rules' value. Fields below 100 cases stay on the default.
8. **Version it.** A change of policy is a new pipeline version (`leo-v0.6`) with the evaluation re-run; it is never a live change. Record it as a dated deviation (D-number) in `EVAL_PROTOCOL_LEO.md`.

How many cases: the standard error of a proportion near 0.8 with 100 cases is about 0.04, so a 0.1 difference between readers is detectable; smaller differences need hundreds. Disagreements are a minority of values: the synthetic runs produced 22 disagreement claims over 143 notes and 132 over 399 notes, across all fields. Reaching 100 cases for one field may therefore take several hundred notes; real notes may differ.

## 4. Limits of this protocol

- It measures which reader is right when they disagree. It does not measure cases where both are wrong in the same way (those never reach the sheet), so it cannot replace a random-sample audit of accepted values.
- Adjudicating from the note, not from the chart, measures extraction accuracy, not clinical truth.
- Results from one centre's notes will not transfer unchanged to another's.

## 5. Extra sheets (accepted values and codes)

The same CLI writes two other adjudication files from `RESULT.claims.csv` (PHI: they contain quotes):

    bin/leo disagreements --kind accepted RESULT.claims.csv   # sample of accepted values (default 50)
    bin/leo disagreements --kind codes RESULT.claims.csv      # quote, selected id, top-5 candidates
    bin/leo disagreements --score-codes RESULT.codes.csv      # after filling truth: correct|wrong|abstain_ok|unclear

Protocol additions, same blinding rules as section 3:

- **Accepted sample.** Disagreements miss cases where both readers are wrong in the same way. Adjudicate `truth` as `correct` / `wrong` / `unclear` against the note (not the chart).
- **Codes.** For each row, the five candidates are in `candidates`. Fill `truth` (`correct` if `selected_id` is the right concept, `wrong` if it is a different concept, `abstain_ok` if leaving MEDAI-ENUM was right, `unclear` otherwise). Optional `true_system` / `true_id` when correcting.

