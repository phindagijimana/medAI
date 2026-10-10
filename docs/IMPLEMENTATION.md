# Implementation

LEO (runtime `leo-v0.9`; headline extras still the frozen D17 L1C / v0.5 files): how the tool is built, why each step exists, what it contributes, and where it fails. Operator commands: `LEO_USER_GUIDE.md`. Hosting (workstation / Slurm): `LEO_HOSTING.md`. Quoting numbers: `INTERPRETING_RESULTS.md`. Protocol: `EVAL_PROTOCOL_LEO.md`.

**One sentence.** A note goes through Prepare → two readers (rules + constrained Med42) → ontology candidates → fusion → a table a person can validate; clicks stay files until a versioned `leo learn`. Pipeline tag `leo-v0.9` (unknown+silent REVIEW; cluster-if / considered not current). Headline paper config remains the frozen F-S extras file.

Tested on synthetic notes only. Not clinical decision support.

## A to Z

```
note → Prepare → E (EpExtra) + L (Med42 L1C) + O (candidates)
                 → fuse → verify → phenotype row
                 → Validator (optional) → merge _final
                 → leo learn (optional, later version)
```

| Step | What happens | Code | Decided because |
|---|---|---|---|
| **1. Prepare** | Canonicalise US section headers, segment, hash. Long notes chunk at 8k chars (overlap 400); E still reads the whole note. | `us_note_preprocessing`, `chain_pipeline` | ExECT assumed UK letters; US headers and joined visits break rules (D16: one row per note). |
| **2. E — EpExtra** | MedCAT + ExECT-style field rules + medspaCy ConText. Drugs, types, EEG/MRI cues, status/time (“was stopped”, later-stop-wins, PLAN ≠ current). | `rules/`, `phenotype_assembler` | Specialist precision; lineage to Fonferko-Shadrach ExECT. Extra ILAE synonyms did not move F1. ICD/Orphanet/SCORE stay out of E. |
| **3. L — LLM** | Med42-8B, **flat** prompt, **two fixed examples**, schema-constrained greedy (`seed=0`). Arms X1C/P1C/F1C cover extra fields. | `flat_extract`, `chain_llm` L1C | M0–M2 schema-in-prompt echoed JSON (F3). Constrained decoding stops that. CoT / 70B / self-consistency not this job. |
| **4. O — ontology** | Retriever top-k (HPO, MONDO, EPIO, SNOMED, RxNorm). Exact match may auto-code. LLM picker of an index is **off** (lost to first-hit). | `ontology_candidates` | Model must not invent codes. Export ICD/Orphanet/SCORE is `--export-codes` after fusion, not gazetteers in E (D21). |
| **5. Fuse** | Same value → accept (`llm+specialist`). Clash → **show rules**, store model as `alternative`, flag `source_disagreement` (**D17**). LLM-only → review if quote locates. | `chain_llm.fuse` | Showing the model on seizure type helped synthetics (D15) but was withdrawn: that set shares a generator with the rules, and it would anchor reviewers (D17). |
| **6. Verify** | Quote in note; hard rejects; policy REVIEW (acute dose, rescue split, specialist-only drug, empty frequency, …). Opt-in `--quote-entail`. | `chain_pipeline._verify`, `LEO_ROUTING_RULES.md` | v0.4/v0.5: one-off IV ≠ current ASM; rescue ≠ maintenance (D11–D12). Quote-in-note ≠ quote-supports-cell. |
| **7. Publish** | Wide table + claims + provenance. `visit_summary` under 50 words from cells already on the row (`[?]` = review). Not a second LLM. | `leo_tabular`, D23 | Glance column without exam-QA summarisation. |
| **8. Validator** | Same store as download. Accept / Correct / Deny / Add missed. Why required on Deny/Correct. Which-reader on disagreement. 10% accepted audit. | `leo_review`, `/leo/ui` | Flagged-only review overfits to clashes. Tags beat free text as a training signal. Clicks are labels, not completions. |
| **9. Merge** | Copy with `_final` / `_review`. LEO columns untouched. 24 h job folder is scratch. | `leo merge` | Research table = what a person signed off. |
| **10. Learn** | `leo learn` on `reviewed.csv` or `--archive`. Loop A: routing JSON if ≥100/field CI gate. Loop B: threshold report. Loop C refused. Extract does not import this. | `leo_learn`, D24 | Cheapest F1 is which reader to show, then fusion thresholds, then rules. Fine-tune last. H2 fused **lost** F1. |

Permit use for training copies PHI into `data/leo_training/` so the job TTL can expire. It is not a Train button.

## How major forks were decided

| Decision | Choice | Why | If we had chosen the other |
|---|---|---|---|
| Product | Phenotype **table** + review, not chat/exam-QA | Use is research cohorts from notes | MedQA F1 would not fill `seizure_type` |
| LLM contract | Flat L1C, constrained, greedy | M2 schema-echo (F3); H2 out of contract (F2) | Validity without populated fields |
| Default clash | **Rules shown** (D17) | Candidate policy not validated on real notes | Reviewers anchored on an untested display |
| Fusion + H2 | H2 **off** fusion | H2 alone +0.04 F1; fused reviewed **worse** | Adapter fights E on disagreement |
| Gazetteers | Stop adding ILAE strings to E | v4_ext rematch: headline F1 did not move | More synonyms, same holes (status, quotes) |
| Sidecars | `--ext-detector` opt-in, never auto-accept | Literature readers without dumping into E | Majority vote would un-accept good E cells |
| RAG / codes | Ask-only RAG; codes after Verify | Different job than extract | Guideline-echo; ICD intractable as DRE |
| Unit of output | Per **note** (D16) | Visits change (drug stopped) | Joined text mixes current/prior |
| Learning | Files + `leo learn`, not live adapter | IRB, hold-out, kappa; H2 lesson | Silent drift on production notes |
| Audit sample | 10% of **accepted** cells | Silent errors never appear in the flagged queue | Overfit to disagreements |

Deviations D1–D33 live in `EVAL_PROTOCOL_LEO.md`. Pipeline bumps: v0.1 E-only → v0.2 LLM fuse → v0.3 grounding → v0.4 acute/frequency → v0.5 rescue role → … → v0.9 unknown+silent / cluster-if. Headline extras stay the frozen D17 L1C files. A routing policy from real reviews is a new `leo-v0.x`, not a hot reload.

## Contributions

The numbers support an accept signal, not an F1 win and not a trust study.

1. **Two-reader extract with a quote.** Every cell can be traced to note text and to rules, model, or both. Quote-in-note is presence, not support.
2. **Disagreement is a flag**, not a silent pick. Both values survive (`alternative`). D17 shows the rules.
3. **Research extract** = accepted ∧ both readers. This is the table whose accuracy we evaluate (71/82 = 0.866 on the 40 letters). Higher precision at ~half the recall; accepted cells are not “safe.”
4. **Measured, not hoped.** Frozen protocol, D-log, `bin/leo evidence` read from scorer files. Unsupported claims stay as negatives (C5 vs L2C; no F1 win; not a trust study; not real notes; not “safe”; O does not raise C1). Handling: `WEAKNESSES.md`.
5. **Operator path.** Spreadsheet or “describe a job”, Validator, merge `_final`.
6. **Honest default.** D17 and H2-off-fusion are accuracy costs taken on purpose so the pilot does not teach on the wrong reader.
7. **Learning ladder.** Tags from Validator → Loop A routing → Loop B thresholds → rules; LoRA last and paused. Tooling: `leo learn`, `--emit-policy`, CI gate ≥100/field.

## Weaknesses

Living list (accounted for → next step): `docs/WEAKNESSES.md`.

Headline: no real-note F1; LEO does not beat the model (the accept band is the product); seizure type is weak under D17; assertion/time/quote support are the remaining extract holes; extra EEG/surgery/failed-ASM fields are drafts; H2 stays off fusion; Loop C paused.

**Still No (on purpose).** Do not flip D17 to `--disagree-llm candidate` (needs Loop A on real `reader_preferred`). Do not train the model to emit epilepsy-type `unknown` from these letters (gold convention; use the typed-only view). Do not make `--quote-entail` the default (16 gold-correct demoted). Loop A/B are scored, not applied.

## What is not this tool

Exam-QA tricks (chain-of-thought, bigger MedQA, 70B as default reader). Live fine-tune from doctor comments. Dumping SCORE/ICD/Orphanet into E. Treating Permit use for training as Train. Claiming real-note accuracy before IRB.

## Where to look in code

| Piece | Path |
|---|---|
| Orchestration | `services/chain_pipeline.py` |
| Fusion | `services/chain_llm.py` |
| Table / visit glance | `services/leo_tabular.py` |
| Validator store | `services/leo_review.py` |
| Learn A/B | `services/leo_learn.py` |
| CLI | `scripts/leo_cli.py` (`bin/leo`) |
| Web | `routes/leo.py`, `routes/leo_ui.html` |
| Fusion table | `docs/LEO_ROUTING_RULES.md` |
