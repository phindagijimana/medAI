# LEO evaluation protocol (frozen 2026-10-01)

How to read the results (what the headline numbers measure, what they say about the data, what they do not cover): `INTERPRETING_RESULTS.md`. Analyses the phenotype table can support: `INTERPRETING_RESULTS.md` §6. Operator: `LEO_USER_GUIDE.md`. Design: `IMPLEMENTATION.md`.

**Status:** v1.0, written before the LEO and Arm H results exist. Anything that changes after the first
scored run goes in the deviations log (§9), with a date and the reason. Shape A is part of the LEO
paper (decision 2026-10-01), so this document governs one study: the Med42-8B prompting/fine-tuning
arms **and** the LEO chain are scored on the same letters with the same code.

LEO = **L**LM (Med42-8B) + **E**pExtra (our ExECT-on-MedCAT port, arm B) + **O**ntology (candidate
retrieval over pinned HPO / MONDO / EPIO / SNOMED CT / RxNorm).

---

## 1. Audit findings that change the design

These were found on 2026-10-01 while wiring Med42-8B into the chain. They are recorded here because
each one would have silently distorted a headline number.

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| F1 | **"Valid" is not "populated".** M2 (schema in prompt) makes the model echo the JSON Schema until it hits the 4096-token limit. `smart_repair` wraps the echo into a module with every field "not documented", and that counts as `final_valid`. | Tuned v3 M2 `clinical_seizure`: 14/14 valid, **0** populated, 14/14 at 4096 tokens. Arm H (polish) M2 `clinical_seizure`: 13/13 valid, **0** populated, 13/13 at 4096 tokens (`medication` the same: 11/11 valid, 0 populated). Base M2: 0 valid. | Validity is reported as *schema-valid* and *populated-valid* (≥1 non-null field). Only populated-valid counts as the model producing output. |
| F2 | **Arm H was evaluated out of contract.** The LoRA adapters were trained on one prompt (`finetune_lora_epi.PROMPT_TEMPLATE`, the whole phenotype in one generation, `PATIENT_ID:` line prepended). The F-S test runner fed them the per-module M0/M1/M2 prompts instead. | Training script vs `scripts/run_med42_on_fs_test.py`. In-contract output (`ft_extract`) populates `clinical_seizure` and `medication` (checked on the first 3 letters). | Arm H is re-run in contract (`scripts/run_med42_ft_on_fs_test.py`). All earlier tuned-arm F-S numbers (v3, v3+constrained, v3-polish partial) are out-of-contract and are **not** used as Arm H. |
| F3 | **The M-prompt family is not usable on this model, and may not be usable on others.** Base M0/M1/M2 on the 40 held-out letters: 0 populated `clinical_seizure` modules out of 120; `medication` populated in 3/40 (M0), 8/40 (M1), 0/40 (M2). GPT-5.6-terra on the same prompts also scores 0.00–0.20 per field. | `eval/results/llm_arms_vs_fs_gold_fs_test_base.summary.md`, `…_gpt_terra.summary.md`. | The base-model arms are redefined on a *flat* prompt family (L0 zero-shot, L1 two-example; `services/flat_extract.py`). The M-family results stay in the paper as a reported negative result about schema-heavy prompting, not as the base-model comparator. |
| F4 | **The native-gold normaliser emits seizure-type labels that are not in the schema.** It produces `absence_typical`, `myoclonic`, `atonic`; the schema enum is `generalized_absence_typical`, `generalized_myoclonic`, `generalized_atonic`. | `scripts/score_llm_arms_vs_fs_gold.py::_SEIZURE_TYPE_RULES` vs `schema/enums.SeizureType`. | The LEO harness maps the three labels onto the enum, for every system alike (deviation D1). |
| F5 | **Two scoring conventions are in circulation.** B1′ = 0.8064 micro-F1 is on 24 fields against our silver labels (`score_medcat_vs_gold.py`); the LLM arms are on 7 fields against F-S native gold. | Both scorers. | The headline uses the 7-field native-gold harness for **every** system (§5). The 0.8064 figure stays as a secondary, EpExtra-only number and is never placed in the same table as the LLM arms. |
| F6 | **Arm H job 159294 ran out of wall-clock** (3 h limit) after 12 of 40 letters. | `sacct`: TIMEOUT 03:00:11. | Runners are resumable; the in-contract Arm H job is `scripts/slurm_med42_ft_fs_test.sh` (4 h). |

---

## 2. Question and claims

**Primary question.** Does a chain in which an LLM, a rules-plus-MedCAT specialist and an ontology layer
corroborate one another extract more *correct* and more *auditable* epilepsy phenotypes from US-style
notes than any one of them alone?

Claims the paper may make if, and only if, the pre-registered result supports them:

| Id | Claim | Supported when |
|---|---|---|
| C1 | LEO's auto-accepted output is more precise than either component alone. | Micro-precision of `leo_auto` exceeds `llm` and `specialist`, paired-bootstrap 95% CI of the difference excludes 0. |
| C2 | Specialist/LLM agreement is a reliable accept signal. | Claim precision in the `agree` category is higher than in `specialist_only` and `llm_only`, with non-overlapping 95% CIs. |
| C3 | The LLM channel adds recall that the specialist lacks. | `leo_review` micro-recall exceeds `specialist` micro-recall by a CI that excludes 0. |
| C4 | LEO limits unsupported content. | Share of LLM claims with a quote not in the note that reach ACCEPT is 0 by construction; the *rate* of unsupported LLM claims is reported for each LLM arm. |
| C5 | Fine-tuning helps the LLM channel. | Arm H (in contract) vs L0/L1 on `llm` micro-F1, paired CI excludes 0. |

A claim whose condition is not met is reported as not supported. None is dropped.

**How the paper now states this (2026-10-09).** The frozen question asked for more *correct* and more *auditable*. Headline F1 did not support “more correct.” The submission leads with C1/C2: the **research extract** is cells both readers accept; **its accuracy versus gold is concordant PPV** (71/82 = 0.866 on the 40 letters; agree 0.835). Agreement is an accept signal (higher than clash on this gold, not “clinically reliable”); auto-accept is more precise at reduced recall; reviewed-as-final is the wrong title row; C4 is quote presence, not support. C2’s word “reliable” in the table above is the pre-registered label; talks and the manuscript use “usable accept signal” / concordant PPV.

**Unsupported claims — how they are handled (none dropped).** Detail: `WEAKNESSES.md`.

| No | Handling |
|---|---|
| **C5** fine-tune helps | Not supported vs strongest base (H − L2C CI includes 0). H2 raised the model, lowered fused LEO. Default **L1C**; LoRA off fusion. Row stays in §3.3. |
| **Headline F1 win** | Reviewed−model −0.022, CI includes 0. Title states we do not beat Med42. Print the F1 row; do not title on it. |
| **Trust study** | Concordant PPV vs gold on synthetic letters. Not clinician trust, not an auditor study. |
| **Real notes / US EHR** | Not claimed. Confirmatory US notes still required (this §3). |
| **Accepted cells “safe”** | 0.85–0.87 PPV; 19/49 model-wrong cells still auto-accepted. Filter, not a chart. |
| **Ontology raises C1/C2** | O pins codes. Hygiene. Not shown to raise precision. |

Do not rewrite C1–C5.

---

## 3. Test sets (frozen)

| Role | Set | Gold | Status |
|---|---|---|---|
| **Primary** | Fonferko-Shadrach held-out letters **EA0161–EA0200** (40) | F-S clinician-adjudicated native gold, Zenodo 8356494 | Frozen. Never used for training, prompt design, rule tuning or example selection of any arm after 2026-09-22 (split contract `finetune_lora_epi._fs_pairs_train_test(seed=0)`). |
| Secondary | synth-v1 eval-100 | Generator ground truth | EpExtra and ontology only (no LLM arms were run on it). Descriptive. |
| Confirmatory | US clinician-annotated notes (40–100) | Two-annotator adjudicated | **Not yet available** (`docs/US_ANNOTATION_PLAN.md`). Required before any submission. |

Caveat the paper must carry: the 200 F-S letters are **synthetic** clinic letters (UK spelling, GP-letter style) written for the ExECT v2 annotation corpus, not real notes (Fonferko-Shadrach et al., J Biomed Semantics 2024). Results say nothing about real clinical text until the US set exists.
They are not US EHR notes, so the primary set measures the system, not US generalisation. US
generalisation is tested only on the confirmatory set.

---

## 3a. Test sets and arms as run (amendment, 2026-10-01)

Sections 3 and 4 are kept as frozen. This table states what exists now; the deviations log (section 9) explains each change.

| Role | Set | Gold | What was run |
|---|---|---|---|
| Target domain (US-style, synthetic) | `polish_val` (10 patients, unseen by the adapter) and `synth_v3` (20 patients, separate generation run), 143 notes | generator ground truth, patient level | Arm H, L0C, L1C; EpExtra; LEO (10.4, 10.6, 10.7). Saturated. |
| External benchmark (UK, synthetic letters) | F-S held-out EA0161 to EA0200 (40); development letters EA0081 to EA0120 for policy choice | F-S clinician-adjudicated native gold | L0, L1, L2, L1C, L2C, Arm H, EpExtra, LEO (10.1 to 10.3, 10.6, 10.7) |
| Confirmatory | clinician-annotated US notes | two-annotator adjudication | not available |

Arms as run, beyond the table in section 4: L2 (k=3 retrieved F-S letters, the built form of arm G) and the constrained twins L1C and L2C. Arm E (LLM ontology selection) is not built. The "7 arms with a result" count in section 4 is out of date.

---

## 4. Arms

Spec letters follow the Chain-of-Three compendium (`docs/CHAIN_OF_THREE_ALIGNMENT.md` §P3). "Run" means a
script exists and the result will be reproducible from manifests.

| Spec | Id | System | Prompt / adapter | Run script | State |
|---|---|---|---|---|---|
| A | B0 | Regex / keyword rules | – | `services/baseline_rules*.py` | Exists; **not yet scored on F-S native gold** |
| B | B1′ | EpExtra (MedCAT + ExECT-style rules) | – | `scripts/run_medcat_rules_on_corpus.py` | Done |
| C | L0 | Base Med42-8B, zero-shot, flat prompt | `flat_phenotype.L0.v1` | `scripts/run_med42_flat_on_fs_test.py` | Job 159301 |
| D | L1 | Base Med42-8B, two fixed examples, flat prompt | `flat_phenotype.L1.v1` | same | Job 159301 |
| E | L1+C | L1 plus ontology candidate selection by the LLM | – | – | **Not built** (needs the selection prompt; §6) |
| F | LEO(L1) | EpExtra + L1 + ontology, fused | – | `scripts/score_leo_vs_fs_gold.py` | Harness done; runs on L1 manifests |
| G | L-dyn | L1 with dynamically retrieved examples | – | – | **Not built** |
| H | FT | Tuned Med42-8B (v3-polish LoRA), in contract | `epilepsy_phenotype.FT.v1` | `scripts/run_med42_ft_on_fs_test.py` | Job 159300 |
| I | LEO(FT) | EpExtra + FT + ontology, fused | – | `scripts/score_leo_vs_fs_gold.py` | Harness done; runs on FT manifests |
| – | M0–M2 | Per-module schema prompts, base model | `module.M*.v1` | `scripts/run_med42_on_fs_test.py` | Done; reported as negative result (F3) |
| – | M-FT | Tuned model under M0–M2 prompts | – | – | Out of contract (F2); reported only as such |
| – | F0 | GPT-5.6-terra, research comparator | `module.M*.v1` | `scripts/run_gpt_on_fs.py` | Done; held-out tier only; never deployed |

**Primary contrast (pre-registered): arm I vs arm H vs arm B vs arm F.** Arms E and G are named in the
spec and are listed so a reader can see they are absent; the paper states that they were not run, not
that the framework "covers" them.

Arm count: 9 spec arms (A–I), of which 7 will have a result (A, B, C, D, F, H, I); E and G are
explicitly out of scope for the first submission.

**US clinical-NLP systems vs E (2026-10-07).** cTAKES, CLAMP, MetaMap, i2b2/n2c2 med/ADE
systems, and published EEG-report extractors are optional *external B-arms*, scored only on
fields they emit, on the same notes and gold as E. They are not synonym lists for E and a
B-arm run has **not** been scored. Vocabularies (SCORE, EpSO, Orphanet, ICD-10-CM, NINDS CDEs) and a second ConText
are not rival extractors. Policy: `docs/E_EXTERNAL_BASELINES.md`.

**Extra field-specialist detector (2026-10-07, D18 / 10.33).** Distinct from a B-arm: `--ext-detector ctakes`
is an opt-in *sidecar* in fusion on overlapping medication columns. Default LEO (flag off) is unchanged.
Not a scored accuracy arm. Contract: `docs/FIELD_SPECIALIST_DETECTORS.md`.

**Role placements (2026-10-07, D21 / 10.36).** RAG, SCORE/EpSO/ICD/Orphanet, and a second ConText
are useful in their own jobs, not inside the phenotype filler. `--ask-rag` is ask_/audit only;
`--export-codes` attaches O maps after extract; `--context-engine` ablates ConText inside E.
70B / chain-of-thought / self-consistency are not shipped. Default extract and D17 unchanged.
Contract: `docs/ROLE_PLACEMENTS.md`.

---

## 5. Metrics

Fields (seven, native gold): `current_asms` (multiset), `seizure_frequency.period`,
`.count_min`, `.count_max`, `epilepsy_type`, `predominant_seizure_type`, `age_at_onset_years`
(tolerance ±1 year). Primitives are imported from `scripts/score_llm_arms_vs_fs_gold.py`.
Drug names are canonicalised for gold, LLM and EpExtra alike (deviation D2).

**Primary endpoint.** Micro-F1 over the seven fields, per system, on the 40 letters.

**Systems scored from one LEO run** (`scripts/score_leo_vs_fs_gold.py`):

| System | Meaning |
|---|---|
| `llm` | The LLM arm alone (smart-repaired / parsed output). |
| `specialist` | EpExtra alone, taken through the claim path. |
| `leo_auto` | LEO claims routed ACCEPT. What would be trusted with no human. |
| `leo_review` | ACCEPT + REVIEW. What a reviewer sees. |

**Secondary.**
1. Per-field P/R/F1.
2. Paired bootstrap of micro-F1 differences (letters resampled, 2000 draws, seed 0): `leo_auto−llm`, `leo_review−llm`, `leo_review−specialist`, `leo_auto−specialist`.
3. Claim-level precision by detector agreement: `agree`, `disagree`, `specialist_only`, `llm_only`.
4. Output validity: schema-valid and **populated-valid** counts (F1).
5. Auto-accept coverage: accepted claims / all claims.

**Safety and auditability (descriptive).**
review rate, reject rate, ontology-grounded rate (claims with a code outside MEDAI-ENUM),
LLM claims whose quote is not in the note, and the number of codes whose release tag is not the pinned
release (must be 0).

**Retrieval (separate harness, §6).** Recall@1/@5/@10 and MRR for mention→concept candidates.

**Not reported as headline:** accuracy on fields without native gold (MRI, EEG, surgery); those are
descriptive only, as in the Shape A protocol (`docs/PROTOCOL_SHAPE_A.md` §2).

---

## 6. Retrieval evaluation

`scripts/eval_concept_retrieval.py` scores `OntologyCandidateService` against a mention→concept gold
set (`docs/CONCEPT_GOLD_SET.md`). Pre-registered thresholds and what they trigger are in
`docs/SCOPE_DECISIONS.md`. The LLM candidate-selection step (arm E) is built only if recall@5 is
materially above recall@1, because that gap is the only room a selector can use.

---

## 7. Decision rules

| Observation | Action |
|---|---|
| Arm H in contract is not populated-valid on ≥ 90% of letters | Report as is; no tuning on the test letters. Improve training data and re-evaluate on a *new* split only. |
| `llm_only` claim precision < 0.5 | Keep the rule that LLM-only claims never auto-accept (already enforced); report. |
| `agree` precision not above `specialist_only` precision | Claim C2 is dropped; fusion contributes recall only. |
| LEO(FT) does not beat both FT and B1′ on micro-F1 | State that fusion did not improve the primary endpoint; report the auditability results as the contribution. |

No threshold is tuned on the primary set. Rules, prompts, normalisers and the fusion tolerance were
fixed before the first LEO run on these letters (the fusion numeric tolerance of 1.0 equals the
scorer's own tolerance).

---

## 8. Reproduction

```bash
# GPU, resumable
sbatch scripts/slurm_med42_ft_fs_test.sh          # arm H, in contract
sbatch scripts/slurm_med42_flat_fs_test.sh        # arms L0, L1

# CPU
venv-medcat/bin/python scripts/score_leo_vs_fs_gold.py \
    --llm L0=data/run_manifests_fs_test_flat:L0 \
    --llm L1=data/run_manifests_fs_test_flat:L1 \
    --llm armH=data/run_manifests_fs_test_ft_v3_polish:FT \
    --out eval/results/leo_vs_fs_gold
```

Tests: `venv-medcat/bin/python -m pytest tests/ -q`.

---

## 9. Deviations log

| Id | Date | Deviation | Reason | Effect |
|---|---|---|---|---|
| D1 | 2026-10-01 | Gold `absence_typical`/`myoclonic`/`atonic` mapped to the schema enum names in the LEO harness. | F4. | Affects all systems alike; arm-scorer numbers for these labels differ. |
| D2 | 2026-10-01 | Drug names canonicalised on gold, LLM and EpExtra in the LEO harness. | The F-S gold uses a key convention (e.g. `sodiumvalproate`); a raw string compare penalises any system that writes "valproate". | LLM-alone drug scores here can exceed the arm table. |
| D3 | 2026-10-01 | Arm H re-run in contract; earlier tuned-arm F-S numbers withdrawn as Arm H. | F2. | Replaces v3 / v3+constrained / v3-polish partial results. |
| D4 | 2026-10-01 | Base-model comparators are the flat arms L0/L1, not M0–M2. | F3. | M-family retained as a negative result. |
| D5 | 2026-10-01 | Value grounding added to the pipeline (`ground_value`, leo-v0.3): an LLM value whose quote is not in the note is located by the system (drug name, age, frequency, type keyword) and the located span becomes the claim's evidence. Specialist placeholder values (`undefined`, `not_assessed`) are no longer emitted as claims. | §10.2: 26 of 29 Arm H quotes were rejected because the adapter learned templated evidence text, not because values were wrong. | Moves Arm H leo_review from 0.664 to 0.676 (grounded). Reported with and without grounding (`--no-ground`). |
| D6 | 2026-10-01 | Two extra epilepsy_type views (`typed`, `abstain`) added to the scorer; excluded from micro. | Native gold defaults to `unknown` for 25 of 38 held-out letters; the base prompt cannot output `unknown`. | Micro-F1 unchanged by construction; the `epilepsy_type` row alone is not interpretable. |
| D7 | 2026-10-01 | Flat arms L2 (k=3 retrieved F-S training letters), L1C and L2C (L1/L2 prompts with schema-constrained decoding) added. | Few-shot and decoding comparators requested after §10.2; L2 left 4 of 40 letters empty or off-schema. | Arms are additions; L0/L1 numbers are unchanged. |
| D8 | 2026-10-01 | Fusion policy `disagree_primary={predominant_seizure_type: llm}`, chosen on development letters EA0081-EA0120 (arms L1C, L2C), then applied once to the held-out letters. | Dev sweep of six policies (§10.3); only this field helped on both arms. | Reported beside the unchanged-policy rows; the held-out letters were not used to choose it. |
| D9 | 2026-10-01 | Second test set: US-style synthetic notes (synth-v3-polish validation patients and synth-v3 patients), scored per patient with every system's per-note output aggregated over the patient's notes. Seizure-free is read as count 0 for every system (`SEIZURE_FREE_AS_ZERO`, set only by the synthetic scorer). | The F-S letters are UK documents; the target is US notes. The synthetic gold is patient-level while each note shows part of it. | F-S numbers unchanged (flag defaults off). |
| D10 | 2026-10-01 | `--disagree-llm all four scalar fields` run on the synthetic set as an exploratory sensitivity check, not as the policy. | The policy of D8 was chosen on F-S dev letters; the synthetic set must not be used to choose it. | Reported separately and labelled exploratory. |
| D11 | 2026-10-01 | `leo-v0.4`: (a) one-off drug administrations (IV load, parenteral dose with a clock time) are moved to `medication.acute_administration`, REVIEW, outside `current_asms`; (b) a specialist-only drug is REVIEW (`specialist_only_unconfirmed`) when the LLM listed other drugs but not this one; (c) empty frequency placeholders are dropped and `_freq_agree` needs a jointly stated field; (d) a frequency the specialist marked PROBABLE (its only cause is an "about/approximately N" quantifier) is read as asserted. Each has a switch in `ChainConfig`: `acute_administration_filter`, `specialist_only_drug_review`, `drop_empty_frequency`, `approx_frequency_is_asserted`. | (a)-(c) come from the error diagnostic of 10.5 and from inspecting example outputs; (d) from the low `leo_auto` frequency recall seen after (c). All four were found on the same synthetic/F-S test notes they are scored on, so the gain is an upper bound until a set not used here is run. | `leo_review` unchanged by (d); F-S held-out and synthetic re-scored, see 10.6. The acute rule is a text-pattern rule; home rescue (buccal/intranasal PRN) is deliberately not matched. |
| D12 | 2026-10-01 | `leo-v0.5`: drug role. As-needed rescue drugs move to `medication.rescue_medication` (switch `rescue_role_split`); both scorers report "current ASM" with and without rescue (`rescue_as_current`). F-S default: rescue counts (ExECT guideline); synthetic default: it does not. | The two gold sets use different conventions (SCOPE_DECISIONS D6); the literature separates rescue from daily medication but does not say whether a research list of current ASMs includes it. | Rescue-in view on F-S is identical to v0.4 (the rule moved 1 drug in 40 letters); maintenance-only view is the new number. Rule cues were written from the ExECT guideline and the literature, then checked on these notes, so treat the effect as unvalidated on an unused set. |
| D13 | 2026-10-01 | Reporting order. The synthetic US-style set (`polish_val` + `synth_v3`, patient level) is the target-domain set for every statement about US-style notes. F-S is reported as the UK external benchmark in its own table, labelled UK, never pooled with the synthetic set. Endpoints, scorers and the F-S held-out split are unchanged. | The target is US notes and F-S is UK spelling and letter style; mixing them confuses what a number says. | F-S is not dropped: it is the only gold written independently of our generator, and the only link to published ExECT figures. The synthetic set is saturated (LLM 0.99 to 1.00), so alone it cannot separate arms; a harder slice from the existing gold (prior, denied, hedged and hypothetical drugs and seizures) is required before an accuracy claim. |
| D14 | 2026-10-01 | Unused-set validation, hard slices and Arm H2, **written before the results are in**. (a) New synthetic sets: `ext` (the other 80 synth-v3 patients, 399 notes), `v1v2` (51 synth-v1 + 50 synth-v2 held-out patients, 202 short single-visit notes), `polish90` (the 90 polish training patients, 443 notes, base-model arm L1C only because Arm H trained on them). (b) Hard slices are scored on patients whose plan marks stopped drugs (`PRIOR_ASMS`), denied, hedged or hypothetical findings, using all-field F1 on those patients plus stopped-drug leakage (a plan prior drug that appears in the patient's `current_asms`). (c) Arm H2 is trained on the flat contract with verbatim spans and run with constrained decoding. Analyses fixed in advance: LLM-wins-on-disagreement (D8) is judged on `ext` and `v1v2` with the same three fields; v0.4/v0.5 gains are judged on `ext`; no threshold or rule is changed after looking at these sets. | The v0.4/v0.5 rules and the D8 policy were found on the 30-patient set they were scored on. The slices give a harder test from gold that already exists. H2 removes two defects of Arm H (targets the note does not state; templated evidence), so a gain over Arm H and over L2C can be attributed to fine-tuning on the same contract. | `v1v2` notes are short and EpExtra rules were developed on v1/v2-type corpora, so that set favours the specialist; `ext` shares a generator with the development set. Slice tags (denied, hedged, hypothetical) do not map to a scored field, so those slices measure robustness to such text, not accuracy on the findings. Slice sizes on the 30-patient set are 4 to 5 patients (CIs wide); `polish90` exists to raise them. |
| D15 | 2026-10-02 | Per-field policy for model-rules disagreements, decided on the unused sets named in D14. On a disagreement both values still go to review; the policy only chooses the one shown. **Seizure type: the model's value. Epilepsy type, onset age, seizure frequency: the rules' value.** Recorded as the *candidate policy* (`--disagree-llm candidate`). It was first made the default and then withdrawn as the default the same day (D17). | The check fixed in D14 was run: `--disagree-llm` on the four scalar fields (epilepsy type, seizure type, onset age, frequency period) against the default, on `ext` (80 patients) and `v1v2` (101 patients), arm L1C. Seizure type: reviewed F1 0.803 to 1.000 on `ext`, 1.000 to 1.000 on `v1v2`, 0.34 to 0.57 on the F-S letters (where it was chosen). Epilepsy type: 0.975 to 0.938 on `ext` (the rules were right more often), unchanged on `v1v2`. Onset age and frequency: no difference. | The rule was chosen on F-S development letters, confirmed on one synthetic set (`ext`) and tied on another (`v1v2`); the synthetic sets share a generator with the rules' development data, so the confirmation is weaker than it looks. `v1v2` has too few disagreements (8 to 18 claims) to say anything about precision. Epilepsy type was judged on synthetic notes only. The headline numbers were re-scored under this policy (10.13) and then the default was reverted (D17), so the app shows the no-override figures. |
| D16 | 2026-10-02 | Unit of output = the note. Several notes per patient give several rows, each with its own answer; no patient-level value is computed unless asked (`bin/leo rollup`, `services/leo_rollup.py`: the latest note that states a value per field, never mixed across notes, with source row and date). | Each visit is independent in the use case of the project's users; mixing notes would hide changes over time (a drug stopped, a new seizure type). | The patient-level scorers (synthetic gold) join each patient's notes, which is a different task from the per-note rows the app produces; long joined documents (10.12) are therefore a stress test, not the supported mode. |
| D17 | 2026-10-02 | The shipped default is **no override**: on a disagreement LEO shows the rules' value for every field and keeps the model's value as the claim's `alternative`. The D15 policy stays available as `--disagree-llm candidate`. A tool exports disagreements for blind adjudication and scores them (`bin/leo disagreements`, `services/leo_disagree.py`); protocol and decision rule in `DISAGREEMENT_ADJUDICATION.md`. The app's displayed figures are again the no-override files (`leo_vs_fs_gold_v05_default`, `leo_vs_synth_gold_v05_maint`). | A review of D15: its support is synthetic notes that share a generator with the rules' development data, 18 F-S letters with a seizure-type reference, and an F-S epilepsy-type reference that cannot separate model errors from unadjudicated inferences. A per-field policy should rest on adjudicated disagreements from real notes, and a displayed value that has not been tested should not anchor the reviewers who produce that data. | The default costs accuracy where the candidate helped: F-S reviewed micro-F1 0.678 against 0.705 (L1C), 0.690 against 0.724 (H2); seizure-type F1 0.34 against 0.57 (L1C). That cost is accepted for the pilot. No threshold was tuned on these sets to reach D17. |
| D18 | 2026-10-07 | Opt-in extra detector `--ext-detector ctakes` (`MEDAI_LEO_EXT_DETECTOR`). Savova-style ASM dictionary + Chapman NegEx + Uzuner 2010 status on overlapping med paths. Detector name `ctakes`. Agree → append detector; status mismatch → `sidecar_alternative` / `*_sidecar`; sidecar-only → REVIEW `sidecar_only`. **Never auto-accepts, never demotes an E+L accept, not a majority vote.** Flag off = previous LEO. B1 and trained frequency/type/HS heads not registered (need new training). Java cTAKES binary not required. | Literature field specialists that emit existing LEO cells, without dumping lexicons into E or flipping D17. | Headline F-S / v4_ext files not re-run (sidecar off by default). Unit tests: `tests/test_ext_detectors.py`. See 10.33. |
| D19 | 2026-10-07 | Same `--ext-detector` slot, still off by default: `freq` (current stated rate + seizure-free), `stated-type` (explicit ILAE / epilepsy-type phrases only), `hs` (HS/FCD mention + NegEx; never `false` if MRI unmentioned). Not copies of E (no MedCAT, no CPS map, no ExECT JAPE). Same fusion as D18. `--ext-detector b1` / `xie` / `decker` still raise. | Xie/Decker/HS *tasks* without Penn/Decker weights or BioClinicalBERT training. | Headline files not re-run. Tests: `tests/test_ext_detectors.py`. See 10.34. |
| D20 | 2026-10-07 | Guideline stated-only sidecars on leftover weak cells: `fail-reason`, `rescue-if`, `ictal`, `eeg-done`, `dre`, `first-feature` (`services/ext_detectors/guideline.py`). High precision when the note states the fact; not a published clinic-letter F1. Silence cannot demote an E+L accept. `--ext-detector engel` raises (no catalogue column). `acute_administration` stays on `ctakes`. Strings not dumped into E. | ILAE/ACNS/NINDS/Kwan/Pina-Garza language as third readers without training. | Headline files not re-run. Tests: `tests/test_ext_detectors.py`. See 10.35. Literature map: `docs/FIELD_SPECIALIST_DETECTORS.md` §9. |
| D21 | 2026-10-07 | Place RAG, SCORE/EpSO/ICD/Orphanet, and a second ConText in their jobs without touching the extract table. `--ask-rag` retrieves Fisher/Scheffer/Kwan/ACNS paraphrases for guideline *questions* only (not L1C). `--export-codes` maps already-extracted values to G40.x / Orphanet / SCORE / EpSO after fusion (never gazetteers in E; ICD intractable not used for ILAE DRE). `--context-engine {medspacy,sentence,negex}` ablates the preprocessor inside E. 70B, chain-of-thought, and self-consistency are **not** wired (greedy seed-0 contract stays). Flags off = previous LEO. | Each tool solves a different job than “fill seizure_type.” Dumping them into E causes guideline-echo, code collisions, and ConText-vs-phenotype confusion. | Headline files not re-run. Tests: `tests/test_role_placements.py`. See 10.36. `docs/ROLE_PLACEMENTS.md`. |
| D22 | 2026-10-07 | Measured-failure techniques, not gazetteers or exam-QA. E: “was stopped”, PLAN/PMH status, later stop/fail wins, “that drug” deixis. Fusion opt-in `--quote-entail` (REVIEW `quote_not_entailed`). Routing: `--disagree-llm policy:FILE` from `--emit-policy` (min 100 scored cases); D17 unchanged. LoRA stays off fusion (`docs/LORA_FLAT_CONTRACT.md`). Constrained L1C kept. BIO NER field heads blocked until trained. Active learning **plan only**. | Headline F1 did not move from extra strings; remaining holes are status, quote support, and which reader to show. | Tests: `tests/test_measured_failures.py`. See 10.37. `docs/MEASURED_FAILURE_TECHNIQUES.md`, `docs/ACTIVE_LEARNING_PLAN.md`. |
| D23 | 2026-10-07 | Per-note `visit_summary` column: under 50 words from this visit’s already-extracted key items. Review cells marked `[?]`. Drug lists capped at three names. Rebuilt on `leo rollup` from the rolled-up cells (latest stated per field), not a bag of visit prose. Not a new reader; not scored; D17 unchanged. | Users asked for a glance column; a second LLM summary would be exam-QA, not phenotyping. | Tests: `tests/test_leo_app.py`. See 10.38. |
| D24 | 2026-10-07 | `bin/leo learn` scores Loop A (routing from `reader_preferred`) and Loop B (Accept/Correct/Deny + 10% accepted audit) from `reviewed.csv` / `data/leo_training/`. Policy JSON only if the ≥100/field CI gate passes. `--apply` / `--lora` / `--few-shot` / `--bio` refused. Extract and D17 unchanged. Loop C paused. | Validator clicks were stored but unused; learning must be a versioned command, not a live adapter. | Tests: `tests/test_leo_learn.py`. See 10.39. `docs/ACTIVE_LEARNING_PLAN.md`. |
| D25 | 2026-10-07 | Full v4_ext rematch with all 10 shipped `--ext-detector` names into **new** prefixes (`v4ext_rules_sidecar`, `v4ext_llm_sidecar`). Sidecar-only never ACCEPT. Default extract / D17 / Arm E unchanged. Headline, `_ecues`, and `_fix` files not overwritten. | Sidecars were unit-tested and 3-note plugged; the 113-note all-claims view was unscored. | CPU + GPU 113/113 scored (10.40). Sidecars stay opt-in. |
| D26 | 2026-10-08 | `leo-v0.6`, three field-level changes. (1) Seizure type agrees at two levels: the onset class (focal / generalized / unknown onset) is fused as its own field `clinical_seizure.seizure_onset_class`, so the class can be ACCEPT while the subtype stays REVIEW; scorers add a `predominant_seizure_type|class` view. (2) EpExtra current ASMs: one per-drug "current at this visit" decision from clause-level stop / plan / ongoing cues (replaces D22's sentence-status edits, which drifted: a drug listed as taken was dropped when another sentence said "previously tried"); standard abbreviations (LEV, LTG, ...) and misspellings within 1-2 letters (`rules/asm_surface.py`). (3) "Unknown" epilepsy type with one definition (`schema.enums.UNKNOWN_EPILEPSY_TYPE_DEFINITION`): EpExtra emits it when the note says epilepsy without a type, and stops inferring a type from seizure types; fusion keeps an LLM "unknown" for this field; flat prompt v2 (`MEDAI_FLAT_PROMPT_VERSION=v2`) offers it to the model, v1 stays the default and is byte-identical. Evidence panel reads the v06 files. | Borrowed from the UK field-level methods (Fang et al. 2025 coarse seizure-type scoring; ExECT medication temporality and spelling tolerance; ExECT "unknown" epilepsy type). The F-S gold is "unknown" for 25 of 38 letters, and the model could not say it. | Rules were written while looking at the 40 held-out letters (and two v4_ext notes for the bare-after-stop rule); the 160 F-S stress letters confirm the direction. Tests: `tests/test_seizure_class.py`, `tests/test_medication_current.py`, `tests/test_unknown_epilepsy_type.py`. See 10.41. |
| D27 | 2026-10-08 | EpExtra EEG location: scalp electrode names (10-20 / 10-10) fill a lobe or side that no location word gave, for interictal discharges and ictal onset (`rules/eeg_electrodes.py`). Odd left, even right, z midline; T3-T6 and P7-P10 temporal; central electrodes give no lobe; mixed lobes give no lobe. A lone electrode needs an EEG cue ("maximal at", "phase reversal at", "electrode", "over"). Electrodes never add a lobe to a generalized discharge. | Borrowed from PEEP (Cui et al. 2014, `docs/REFERENCES.md`), which normalised electrodes to anatomy through EpSO. US EEG reports often give the location only as electrodes. | v4_ext rules-only rerun identical to 10.41 (no score change). Tests: `tests/test_eeg_electrodes.py`. See 10.42. |
| D28 | 2026-10-08 | `leo-v0.7`, two seizure-outcome fields (`services/seizure_free.py`). (1) `clinical_seizure.seizure_free` (yes/no) is read off each reader's current seizure frequency (seizure free or zero counts = yes; a positive count = no; a positive count among other seizure types turns yes into no) and fused on its own, like the onset class. (2) `clinical_seizure.date_of_last_seizure`: rules only, explicit dates only ("last event July 2016", "no seizures since Christmas 2015"), latest date in the note; durations give no date; all-numeric dates keep only unambiguous parts. No model reads it, so it is reviewed when the model ran. Both scored as extra views (not in the micro-F1). Default output panel (`core`) unchanged. | Borrowed from the Penn outcome work (Xie et al. Epilepsia 2023; Ojemann et al. J Healthc Inform Res 2025; `writing/further_LEO.md` U1-U2): seizure freedom and date of last seizure are separate, extractable outcomes. | Date rule written from development letters EA0001-EA0160 only; held-out letters read only when scoring. Headline numbers unchanged. Tests: `tests/test_seizure_free.py`. See 10.43. |
| D29 | 2026-10-09 | Medication context in n2c2 2022 CMED terms (`rules/med_context.py`): each drug mention gets disposition, action (Start / Stop / Increase / Decrease / UniqueDose / OtherChange), negation, temporality, certainty and actor, built from EpExtra's existing clause cues; `casi_status` maps the per-drug "current at visit" decision to CASI's active / discontinued / neither. Nothing EpExtra emits changes. External scorer `scripts/score_casi_medication_status.py` (gold drug names given; context only). | `writing/further_LEO.md` M1-M2: context, not drug names, is the hard part of medication extraction, and CASI is a small public US test of it. | **External score not run**: the CASI set is gated on Hugging Face (terms + login) and no token is configured; CMED needs an n2c2 data-use agreement. Tests: `tests/test_med_context.py` (sentences written for the test). See 10.44. |
| D30 | 2026-10-09 | `leo-v0.8`, PNES flag (`rules/pnes.py`): `clinical_seizure.pnes_status` = pnes_only / pnes_and_epilepsy / pnes_possible, rules only. New reason `pnes_documented` (REVIEW): with PNES only, seizure frequency, other frequencies, seizure free, date of last seizure, seizure type, onset class and epilepsy type cells are not auto-accepted; with dual diagnosis only the four count/outcome cells; possible PNES changes no routing. Switch `pnes_check`. | Hamid et al. (Epilepsy Behav 2013; `writing/further_LEO.md` U6): PNES letters contaminate epilepsy cohorts, and a seizure count in a dual-diagnosis letter may include non-epileptic events. | Rule written from development letters (16 of EA0001-EA0160 mention PNES). The two held-out PNES letters (EA0174, EA0198) had been read during exploration before the rule was written, so they are not a blind test. F-S gold has no PNES label; no accuracy is claimed. Headline unchanged. Tests: `tests/test_pnes.py`. See 10.45. |
| D31 | 2026-10-09 | IED attributes and EEG-report sections. `IedFinding` gains optional `frequency_band`, `recurrence` and `dispersal` (`rules/eeg_attributes.py`; SACAR). On TUH-style EEG reports (DESCRIPTION OF THE RECORD, or INTRODUCTION + IMPRESSION headers), IED / background / ictal-onset / seizures-captured findings come from description and impression only, not history or the introduction (`rules/eeg_sections.py`). Clinic letters have no those headers and are unchanged. Pipeline stays `leo-v0.8`. External scorer `scripts/score_tuh_eeg_attributes.py`. | Maldonado and Harabagiu, J Biomed Inform 2019 and LREC 2020 (`writing/further_LEO.md` G1–G2): LEO's IED fields covered only type, lobe and side, and history mentions of a prior EEG should not count as this study's findings. | F-S letters are not EEG reports, so the headline score does not move. **TUH score not run**: needs a Temple data-use agreement. Tests: `tests/test_eeg_attributes.py`. See 10.46. |
| D32 | 2026-10-09 | Author-type classifier (`services.note_author`) from the signature block only, and a silent-prospective plan (10.47). Weak-label wrappers for four EpExtra fields (`rules/weak_labels.py`, `scripts/emit_weak_labels.py`) so a Trove label model can be trained later. No classifier is trained; extract and fusion unchanged. | Ojemann et al. 2025 (author type); Wissel et al. 2019 (prospective drop); Fries et al. 2021 Trove (`writing/further_LEO.md` U1, U4, M3). | F-S letters are almost all unsigned, so no author-stratified F1 is reported. Tests: `tests/test_note_author.py`, `tests/test_weak_labels.py`. See 10.47–10.48. |
| D33 | 2026-10-10 | `leo-v0.9` (CPU). (1) Error-capture lists accepted model-wrong cells (pre-v0.9 19/49; rematch **20/49**); do not write rules from that hold-out list. (2) EpExtra current ASMs: cluster-if / “not prescribed yet” / “can also use” / “may be considered” are planned, written from EA0001–160 examples; a prescribed cluster rescue the patient already takes stays current; sidecars stay opt-in. (3) Fusion: one reader `unknown` (epilepsy type / onset class) and the other silent → REVIEW `unknown_silent` (default on; switch `unknown_silent_review`). Both-unknown still agrees. Not chosen by looking at EA0161–200. (4) Noisy-reviewer curve on stored claims (`leo_noisy_review_fs40`). **Not done:** D17 flip, quote-entail default, Loop A/B apply, real notes, train `unknown`. Headline extras file not overwritten. | Extract quality is leak rate and concordant PPV, not headline F1. Unknown from one reader is abstention. Leak did not fall. | Tests: `tests/test_medication_current.py`, `tests/test_chain_llm.py`. See 10.50. |

Amendments below this line, newest last.

---

## 10. Results log (append-only)

### 10.1 Flat base arms L0 and L1, 2026-10-01

Run: `scripts/score_leo_vs_fs_gold.py --llm L0=... --llm L1=...`; output `eval/results/leo_vs_fs_gold_flat.{json,md}`.
40 held-out letters; 38 (L0) and 39 (L1) have a schema-valid, populated LLM phenotype. Bootstrap over letters.
Arm H is not scored yet (job still running).

Micro-F1 on the seven native-gold fields (95% CI):

| system | with L0 | with L1 |
|---|---|---|
| llm alone | 0.679 [0.601, 0.752] | 0.700 [0.640, 0.765] |
| specialist (EpExtra) | 0.655 [0.582, 0.723] | 0.655 [0.582, 0.723] |
| leo_auto | 0.587 [0.500, 0.674] | 0.584 [0.500, 0.667] |
| leo_review | 0.662 [0.601, 0.723] | 0.674 [0.611, 0.734] |

Paired differences (micro-F1): leo_review − llm −0.017 [−0.070, +0.043] (L0), −0.028 [−0.073, +0.022] (L1);
leo_review − specialist +0.008 [−0.016, +0.034] (L0), +0.019 [−0.003, +0.045] (L1);
leo_auto − specialist −0.067 [−0.130, −0.005] (L0), −0.070 [−0.132, −0.014] (L1);
leo_auto − llm −0.092 [−0.171, −0.019] (L0), −0.117 [−0.198, −0.036] (L1).

Claim precision by detector agreement (correct / scored claims; claims with no gold reference are not scored):
`agree` 0.805 (L0), 0.823 (L1); `specialist_only` 0.323 (10 of 31) and 0.368; `llm_only` 0.375 (6 of 16) and 0.500;
`disagree` 0.111 and 0.200 (9 and 10 scored). Counts are small; no CI is computed yet for these.

Reading against the claims in §2:

| claim | status | why |
|---|---|---|
| C1 auto-accepted output is more precise than both components | **Not supported** | leo_auto micro-P 0.747 / 0.740 is above the specialist (0.695) but below LLM alone (0.763 / 0.818). Its micro-F1 is lower than both because auto-accept discards recall (R 0.483 vs 0.612 / 0.619). |
| C2 agreement is a reliable accept signal | **Supported on point estimates**; CIs pending | `agree` 0.81 to 0.82 against 0.32 to 0.50 for the single-source categories; the single-source categories have only 12 to 38 scored claims, so a claim-level bootstrap must be added before the statement is made. |
| C3 LLM adds recall that the specialist lacks | **Not shown** | leo_review R 0.660 vs specialist 0.619 (point estimates); F1 difference CI includes 0. A recall-specific CI is not computed yet. |
| C4 limits unsupported content | Holds by construction; rate reported | 2 LLM claims with a quote not in the note among 31 LLM claims lacking a specialist match (L0); none accepted (also verified by `scripts/smoke_chain_http.py`). |
| C5 fine-tuning helps | Pending | needs Arm H. |

Observations that bear on the framing, without tuning anything:

- A base 8B model with a plain flat prompt (L0/L1) is at least as good as the rule-based specialist on these
  seven fields (0.68 to 0.70 vs 0.655); the CIs overlap and the LLM-vs-specialist paired contrast has not been
  computed. This weakens any narrative where the specialist is needed for accuracy.
- Fusion buys *triage* rather than F1: the agreed subset is about 0.8 precise, but requiring agreement for
  auto-accept loses about a quarter of the recall. With review included, LEO is statistically indistinguishable
  from either component on F1.
- `epilepsy_type` is poor for every system (F1 0.32 to 0.47). Finding F4 (label vocabulary mismatch between the
  gold and the schema enums) is the first suspect and should be checked before interpreting this field.
- These results use the 7-field native gold only. They say nothing about US notes.

Per decision rules in §7: the row "LEO(FT) does not beat both FT and B1′" is evaluated when Arm H is scored.
Open: add the paired llm-vs-specialist contrast and claim-level bootstrap CIs to the scorer (additions, not tuning;
record as D5 when done).

### 10.2 Arm H (fine-tuned, in contract), 2026-10-01

Run: job 159300 (40 letters, 36 populated at generation, 39 schema-valid at scoring with the salvage code); output
`eval/results/leo_vs_fs_gold_armH.{json,md}`. Same scorer, same 40 letters.

| system | micro P | micro R | micro F1 [95% CI] |
|---|---:|---:|---|
| llm alone (Arm H) | 0.874 | 0.660 | 0.752 [0.688, 0.819] |
| specialist | 0.695 | 0.619 | 0.655 [0.582, 0.723] |
| leo_auto | 0.747 | 0.503 | 0.602 [0.517, 0.679] |
| leo_review | 0.699 | 0.633 | 0.664 [0.596, 0.731] |

Paired micro-F1: leo_review − llm −0.089 [−0.157, −0.016]; leo_auto − llm −0.152 [−0.248, −0.054];
leo_review − specialist +0.010 [+0.000, +0.025]; leo_auto − specialist −0.053 [−0.117, +0.003].

Claim precision: `agree` 0.863 (80 scored), `llm_only` 0.600 (10), `specialist_only` 0.300 (40), `disagree` 0.000 (7).
Of 29 LLM claims with no specialist match, **26 had a quote that is not in the note** and were rejected.

Claims:

| claim | status | why |
|---|---|---|
| C1 | **Not supported** | leo_auto micro-P 0.747 is below Arm H alone (0.874). |
| C2 | Supported on point estimates (CIs pending) | `agree` 0.86 vs 0.30 and 0.60. |
| C3 | **Not supported** | leo_review R 0.633 vs specialist 0.619; F1 difference CI [0.000, +0.025] is at the boundary and tiny. |
| C4 | Holds, but costly | no unsupported claim is accepted; yet 26 of 29 LLM-only claims fail the quote check, which discards LLM recall. |
| C5 | Point estimate positive, paired test pending | Arm H 0.752 vs L1 0.700 and L0 0.679 (separate CIs overlap). Needs the paired contrast between arms. |

Decision rule (§7): LEO(FT) does **not** beat both FT alone and B1′ on micro-F1. LEO(FT) is significantly worse than
FT alone. The statement to make is that fusion did not improve the primary endpoint; the contribution is
auditability (every accepted claim has a verified span and a recorded agreement), not accuracy.

Open diagnostic, not yet explained: why 26 of 29 fine-tuned-model LLM-only claims fail the quote check. Candidates are
paraphrased quotes (the training targets may have used normalised `evidence_text`), quotes spanning line breaks or
tables that `locate_quote` does not match, or genuine hallucination. Look at the 26 quotes against the letters before
changing `locate_quote`; any change is an amendment (D5), not a silent fix, because it moves the headline.

### 10.3 Quote diagnosis, few-shot, constrained decoding, fusion policy, 2026-10-01

Scripts: `scripts/diag_llm_quotes.py`, `scripts/run_med42_flat_on_fs_test.py` (arms L0, L1, L2, L1C, L2C),
`scripts/score_leo_vs_fs_gold.py`; jobs `slurm_med42_flat_l2.sh` (159302) and `slurm_med42_flat_constrained.sh` (159304).
Results: `eval/results/leo_vs_fs_gold_v03.*` (L0, L1, L2, Arm H), `..._v03c.*` (L2, L1C, L2C, Arm H),
`..._v03_policy.*` (policy applied), `..._dev.*` (development letters). Letters are the synthetic F-S letters (JBS 2024); all
numbers are on synthetic text and say nothing about US notes.

**Why Arm H quotes failed.** Of 177 field quotes, 24 are verbatim. The adapter reproduces the templated
`evidence_text` of its training targets ("levetiracetam 250.0 mg twice daily", "age at onset 8"). The values are mostly
right; the strings are not in the letter. Fix in the pipeline (D5); the training-side fix (retrain on verbatim gold spans,
"Arm H2") is not done.

**Base model, held-out micro-F1 of the LLM alone** (95% letter-bootstrap CI):

| arm | decoding | micro-F1 | letters with no usable output |
|---|---|---:|---:|
| L0 zero-shot | free | 0.679 [0.601, 0.752] | |
| L1 two synthetic examples | free | 0.700 [0.640, 0.765] | |
| L2 k=3 retrieved F-S letters | free | 0.678 [0.591, 0.757] | 4 |
| L1C | constrained | 0.700 [0.642, 0.761] | 0 |
| L2C | constrained | 0.736 [0.667, 0.803] | 0 |
| Arm H (fine-tuned) | free | 0.752 [0.688, 0.819] | 1 |

Paired: L2C − L2 **+0.059 [+0.017, +0.110]** (constraint helps the same prompt); L2C − specialist +0.082
[+0.011, +0.158]; Arm H − specialist +0.098 [+0.026, +0.169]; **Arm H − L2C +0.016 [−0.061, +0.098]**. So C5 holds against zero-shot on the point estimate only, and the fine-tuned adapter is **not
distinguishable from retrieved few-shot with constrained decoding** on 40 letters. Retrieved examples alone did not
help (L2C − L1C +0.036 [−0.016, +0.095]; free-decoding L2 − L1C −0.022 [−0.077, +0.032]); what helped was constraining the output. L2 failed
on letters EA0164, EA0173, EA0182, EA0189 (bare nulls or strings instead of `{value, quote}`); L2C has none, every
quote is verbatim (2 of 22 LLM-only claims have a quote not in the note, against 17 of 29 for Arm H before grounding).
Constrained generation also stops at the closing brace (about 10 s a letter against 22 s).

**Fusion policy (development letters, leo_review micro-F1, L1C / L2C).** No policy 0.625 / 0.629; period→llm 0.630 /
0.627; predominant_seizure_type→llm **0.664 / 0.669**; epilepsy_type→llm 0.617 / 0.629; period + type 0.669 / 0.667;
all three 0.661 / 0.667. Only `predominant_seizure_type` helped on both arms with no loss elsewhere, so the
adopted policy is that field alone (D8). The same sweep on the base arms also shows the LLM beating EpExtra on
seizure-frequency period (0.78-0.87 against 0.47) and on current_asms (0.82-0.86 against 0.78) at the field level.

**Held-out, with the policy** (micro P / R / F1):

| system | L1C | L2C | Arm H |
|---|---|---|---|
| llm alone | 0.737 / 0.667 / 0.700 | 0.811 / 0.673 / 0.736 | 0.874 / 0.660 / 0.752 |
| specialist alone | 0.695 / 0.619 / 0.655 | same | same |
| leo_auto | 0.758 / 0.490 / 0.595 | 0.781 / 0.510 / 0.617 | 0.747 / 0.503 / 0.602 |
| leo_review | 0.692 / 0.687 / 0.689 | 0.729 / 0.714 / **0.722** | 0.714 / 0.680 / 0.697 |
| leo_review − llm | −0.010 [−0.046, +0.030] | −0.015 [−0.052, +0.027] | −0.056 [−0.116, +0.009] |
| leo_review − specialist | +0.036 [−0.006, +0.079] | **+0.069 [+0.020, +0.120]** | **+0.043 [+0.011, +0.079]** |

Claim precision for L2C: `agree` 0.835 (99 scored; CI in the json), `llm_only` 0.615, `disagree` 0.125,
`specialist_only` 0.37 (§10.1). Accepted claims that fail the quote check: 0 in every arm.

Claims after this segment:

| claim | status | why |
|---|---|---|
| C1 (auto-accept precision above LLM alone) | **Not supported** | leo_auto micro-P 0.75-0.78 against 0.81-0.87 for the LLM alone, with recall 0.49-0.51. |
| C2 (agreement predicts correctness) | **Supported** | `agree` 0.84-0.86 against `specialist_only` 0.30-0.37 and `disagree` ≤0.13; CIs excluding zero for agree minus specialist_only. |
| C3 (leo_review beats the specialist) | **Supported with L2C and Arm H** | +0.069 [+0.020, +0.120], +0.043 [+0.011, +0.079]; not with L1C. |
| C4 (no unsupported claim accepted) | **Supported** | 0 accepted claims fail the quote check once values are grounded. |
| C5 (fine-tuning beats base prompting) | **Not supported against the strongest base arm** | Arm H − L2C +0.016 [−0.061, +0.098]. |

Decision rule (§7): LEO does not beat the LLM alone. leo_review is statistically level with it (all three CIs include
zero) and above the specialist; what LEO adds over the LLM alone is a per-claim record of agreement, a verified span for
every accepted claim, and a review queue whose agree tier is about 85% precise. State that, not an accuracy gain.

**Not yet tried / next steps for LEO.** (1) Arm H2: retrain the adapter on verbatim gold-span evidence and with
constrained decoding at inference; the cheapest way to find out whether fine-tuning can beat L2C. (2) Repeat L2C with k=5
and with an "unknown" option for `epilepsy_type`. (3) Confirm on 160 bank letters by leave-one-out (more power than 40
letters) before any claim about few-shot against fine-tuning. (4) Real US notes; none of this transfers by assumption.

### 10.4 US-style synthetic notes (synth-v3-polish / synth-v3), 2026-10-01

Data: `services/synth_eval.py`; runs: `scripts/slurm_med42_synth_eval.sh` (jobs 159309-159312; Arm H in three shards,
base arms L0C and L1C); scorer `scripts/score_leo_vs_synth_gold.py`; results `eval/results/leo_vs_synth_gold.*` and
`..._policy_all.*` (exploratory).

**Design.** The Arm H adapter was trained on synth-v3-polish patients P004000-P004099 except a 10-patient validation
split (seed 0). Test strata: `polish_val` = those 10 patients (same distribution, unseen by the adapter; its
validation loss chose the checkpoint, a minor optimistic bias), `synth_v3` = 20 of P003000-P003099, a separate generation
run with its own patient plans that the adapter never saw. 143 notes (141 for Arm H: two did not finish). Gold =
`target_phenotype.json`, patient-level; every system's per-note output is aggregated over the patient (drugs: union;
scalars: majority vote; frequency: vote on the triple), so the patient is the unit scored and resampled. The L2 arms are not
run (they retrieve F-S letters).

**Held-out micro-F1 (patients, 95% CI), pooled over 30 patients.**

| system | Arm H | L0C | L1C |
|---|---|---|---|
| llm alone | 1.000 [1.000, 1.000] | 0.989 [0.978, 0.998] | 0.993 [0.982, 1.000] |
| specialist (EpExtra) | 0.952 [0.921, 0.980] | same | same |
| leo_auto | 0.846 (P 0.966, R 0.752) | 0.842 | 0.842 |
| leo_review | 0.952 | 0.950 | 0.950 |
| leo_review, LLM wins scalar disagreements (exploratory) | 0.968 [0.942, 0.989] | not run | 0.970 [0.951, 0.987] |

By stratum, Arm H: `polish_val` llm 1.000, specialist 0.987; `synth_v3` llm 1.000, specialist 0.935.

Claim precision (Arm H, pooled): `agree` 0.980 (701 scored), `llm_only` 1.000 (30), `specialist_only` 0.778 (90),
`disagree` 0.027 (37). Accepted claims whose quote is not in the note: 0. For L0C, `specialist_only` precision is 0.49.

**What this shows and does not show.**

1. The synthetic set is saturated. A zero-shot base model with constrained decoding reaches 0.989 and the adapter 1.000
   on notes the adapter never saw (P003xxx). The notes are generated from the same plan as the gold and state the facts
   plainly, so the set cannot separate base prompting from fine-tuning (no C5 conclusion) and cannot support a claim about
   LEO against the LLM alone. It does confirm the plumbing: the chain runs end to end on US-style notes, with
   verbatim quotes and no unsupported accepted claim.
2. Agreement still carries information on this set: `agree` 0.98 against `disagree` 0.03 (CI of the difference
   +0.89 to +0.99) and `specialist_only` 0.78 (+0.09 to +0.33). On `disagree` claims the specialist is nearly always the wrong
   one here, so letting the LLM win scalar disagreements raises `leo_review` from 0.952 to 0.968; that setting was not
   chosen on these data (D10), and on F-S the best policy was narrower (D8). A policy that depends on the corpus is a
   finding to report, not a result to tune on.
3. `leo_auto` has recall 0.75 because auto-accept requires both detectors; frequency counts are the weakest field
   (0.57 F1 for `count_min`), where "seizure-free" is represented differently by the detectors. Look there before
   claiming an auto-accept rate.
4. The EpExtra rules were developed against these corpora, so the specialist score (0.95) is favourable to the
   specialist; the gap to the LLM is therefore not inflated against it.

Not done: a real US test. Everything here is synthetic text with the gold from the same generator. A harder synthetic set
(longer notes, conflicting visits, historical drugs, negations) or the clinician-annotated US notes
(`docs/US_ANNOTATION_PLAN.md`) is needed before any accuracy claim for LEO.

### 10.5 Where wrong claims come from on the synthetic notes, 2026-10-01

`scripts/diag_synth_claim_errors.py` (diagnostic only; 141 / 143 notes; wrong / scored claims, Arm H and L1C agree to within a few claims).

| category, field | wrong / scored (Arm H) | reading |
|---|---:|---|
| disagree, `predominant_seizure_type` | 22 / 22 | the specialist side is always the wrong one |
| disagree, `age_at_onset_years` | 9 / 9 | same |
| agree, `seizure_frequency` | 14 / 123 | both detectors agree, gold differs: the gold is the patient's final frequency, an earlier note can state another one (time, not extraction) |
| specialist_only, `current_asms` | 11 / 41 | 9 are acute or rescue drugs (lorazepam, midazolam) from EMU/ED notes that the gold does not list as maintenance ASMs; only 2 are drugs the gold lists as stopped |
| specialist_only, `epilepsy_type` | 5 / 19 | |

Consequences. (1) Negation and "stopped drug" handling is not the main error source on this set; acute/rescue benzodiazepines and
visit-time mismatch are. (2) The F-S gold counts every non-negated prescription as current (including rescue forms), the synthetic gold
does not: the "what is a current ASM" convention differs between the two gold sets and must be a stated scope setting, not a hard-coded
rule. (3) Claim-level precision on longitudinal notes is understated by visit-time mismatch; patient-level scores are the fairer view.
(4) The LLM-wins-on-disagreement policy is supported by 31 of 31 wrong specialist values in the two scalar fields, but it was suggested by
test data; confirm it on a set not yet used (synth-v2 or synth-v1 notes already on disk, no new generation) before adopting it.

### 10.6 leo-v0.4: acute administrations, specialist-only drugs, frequency fusion, 2026-10-01

Config changes are listed in deviation D11. Tests: 260 pass (22 in `tests/test_leo_v04.py`). Result files: `eval/results/leo_vs_fs_gold_v04b_policy.*`, `eval/results/leo_vs_synth_gold_v04b.*` (v0.3 files kept for comparison; `_v04` = fixes a-c without d).

**Examples (3 notes re-run).** Midazolam 10 mg, lorazepam 4 mg and levetiracetam IV load in an ED/EMU note now appear as REVIEW under `medication.acute_administration`, no longer as accepted `current_asms`; a specialist-only midazolam in a note whose LLM listed three other drugs is REVIEW `specialist_only_unconfirmed`; a frequency the two detectors agree on is ACCEPT instead of REJECT `offsets_unresolved`.

**Synthetic (143 notes, 30 patients, patient-level; precision / recall of `leo_auto`)**

| arm | v0.3 | v0.4 (a-c) | v0.4 (a-d) |
|---|---|---|---|
| Arm H | 0.966 / n.r. | 0.988 / 0.752 | 0.991 / 0.991 |
| L0C | n.r. | 1.000 / 0.743 | 1.000 / 0.996 |
| L1C | n.r. | 1.000 / 0.743 | 1.000 / 0.996 |

`leo_review` is unchanged by (d) (Arm H 0.961, L0C 0.959, L1C 0.959). `agree` precision is about 1.0. The set is saturated (LLM 0.99 to 1.00), so these numbers show that the routing no longer withholds correct claims and no longer accepts wrong ones; they do not rank the arms.

**F-S held-out letters (40; fusion policy `predominant_seizure_type` to LLM; `leo_auto` precision / recall / F1)**

| arm | v0.3 | v0.4 (a-c) | v0.4 (a-d) | `leo_review` F1 (v0.3 to v0.4) |
|---|---|---|---|---|
| L1C | 0.758 / 0.490 / 0.595 | 0.840 / 0.463 / 0.596 | 0.851 / 0.544 / 0.664 | 0.689 to 0.705 |
| L2C | 0.781 / 0.510 / 0.617 | 0.877 / 0.483 / 0.623 | 0.874 / 0.565 / 0.686 | 0.722 to 0.736 |
| Arm H | 0.747 / 0.503 / 0.602 | 0.830 / 0.497 / 0.621 | 0.829 / 0.592 / 0.690 | not changed in kind |

`agree` claim precision on F-S: 0.835 (L1C), 0.877 (L2C), 0.896 (Arm H); `specialist_only` precision 0.25 to 0.31 (this is why single-source drugs go to review). `leo_review` vs LLM: L1C +0.005 [-0.029, +0.045], L2C +0.000 [-0.033, +0.035], Arm H -0.058 [-0.119, +0.006]; vs specialist alone +0.051, +0.084, +0.040 (the first two intervals exclude 0). The review-time pipeline therefore matches the LLM on F-S and beats the specialist alone; it does not beat the LLM.

**What this does not show.** (1) The four changes were designed after looking at these notes; confirm on an unused set (synth-v2 or synth-v1 notes already on disk need LLM runs only). (2) The acute rule scores only text patterns; on F-S, whose gold counts rescue prescriptions as current, it did not fire on any of the 40 held-out letters (L2C run, `acute_rerouted` = 0 in the scorer JSON). (3) Approximate frequencies now auto-accept when both sources agree; a reviewer will still see "about" in the evidence span. (4) The remaining wrong `agree` frequency claims on longitudinal notes are visit-time mismatch, not extraction errors.

**Reproduce 10.6** (`venv-medcat`, `PYTHONPATH=/tmp/flask_site`; no GPU needed, LLM outputs are replayed from run manifests):

```
scripts/score_leo_vs_fs_gold.py --llm L1C=data/run_manifests_fs_test_flat_c:L1C \
  --llm L2C=data/run_manifests_fs_test_flat_c:L2C --llm armH=data/run_manifests_fs_test_ft_v3_polish:FT \
  --disagree-llm predominant_seizure_type --out eval/results/leo_vs_fs_gold_v04b_policy
scripts/score_leo_vs_synth_gold.py --bootstrap 500 --llm armH=data/run_manifests_synth_eval_ft:FT \
  --llm L0C=data/run_manifests_synth_eval_flat:L0C --llm L1C=data/run_manifests_synth_eval_flat:L1C \
  --out eval/results/leo_vs_synth_gold_v04b
```

To ablate one change, set its `ChainConfig` flag to `False` (names in D11). Routing rules in one place: `docs/LEO_ROUTING_RULES.md`.

### 10.7 leo-v0.5: rescue role and the two "current ASM" views, 2026-10-01

Tests: 275 pass (15 new in `tests/test_leo_rescue.py`); `scripts/smoke_chain_http.py` all checks passed. Files: `eval/results/leo_vs_fs_gold_v05_{rescue_in,maint}.*`, `eval/results/leo_vs_synth_gold_v05_{maint,rescue_in}.*`.

**Synthetic (30 patients, 143 notes; `current_asms`, precision / recall / F1)**

| system (arm) | v0.4, rescue not split | v0.5, maintenance-only view | v0.5, maintenance + rescue view |
|---|---|---|---|
| specialist alone | 0.897 / 1.000 / 0.946 | 0.968 / 1.000 / 0.984 | 0.884 / 1.000 / 0.938 |
| `leo_review` (L1C) | 0.884 / 1.000 / 0.938 | 0.953 / 1.000 / 0.976 | 0.871 / 1.000 / 0.931 |
| `leo_review` (Arm H) | 0.897 / 1.000 / 0.946 | 0.968 / 1.000 / 0.984 | 0.884 / 1.000 / 0.938 |
| `leo_auto` (any arm) | 0.984 to 1.000 / 1.000 | unchanged | unchanged |

Reading. Splitting rescue out removes most remaining false-positive drugs on the maintenance-regimen gold (precision +0.07) with no recall loss. The same split scored against "rescue counts" is worse than not splitting (0.884 vs 0.897), which is what the gold convention predicts: the synthetic gold does not list rescue drugs.

**F-S held-out letters (40; `current_asms`, F1)**: the rescue rule moved 1 drug (midazolam, EA0165), which the F-S gold lists as current (ExECT convention). Rescue-in view is identical to v0.4: `leo_review` L1C 0.840, L2C 0.855, Arm H 0.859. Maintenance-only view: 0.831, 0.846, 0.850 (one gold drug becomes a miss). The acute rule moved 0 drugs.

**Not shown.** (1) The rule has fired on 1 F-S drug; its precision on US notes is untested. (2) Cues were written from the guideline and the literature and then inspected on these notes. (3) The `llm` system has no role split. (4) Which view is the headline for US research output is a clinician decision (SCOPE_DECISIONS D6).

### 10.8 Unused sets, hard slices, Arm H2 (running, 2026-10-01)

Plan and rationale are in D14. Runs submitted: `ext` (L1C, Arm H), `v1v2` (L1C, Arm H), `polish90` (L1C), Arm H2 training (`scripts/slurm_finetune_med42_h2.sh`, data `data/finetune_data/flat_polish_{train,val}.jsonl`).

**Tool check on the existing 30 patients** (`eval/results/leo_vs_synth_gold_slices30.*`): the slice scorer runs; only the 10 `polish_val` patients carry distractor tags (5 stopped-drug, 4 denied, 5 hedged, 4 hypothetical, 10 any), the 20 `synth_v3` patients carry none. With 4 to 5 patients per slice this is a smoke test, not a result.

**Arm H2 training data** (`scripts/emit_flat_training_pairs.py`): 468 note-level pairs from the 100 polish patients (24 skipped because the gold frequency could not be located although the note talks about frequency; same 10 validation patients as Arm H). A gold field is kept only if a span supporting it is found in that note; the span becomes the quote. Grounded share of gold facts: epilepsy type 98.5%, seizure type 98.4%, age at onset 100%, current drugs 100%, seizure frequency 83.8% (the rest are notes that do not state it). The trainer drops 22 of 419 training rows (5%, the longest notes) so that no completion is truncated; H2 has not seen the longest notes. Finding on Arm H's data: its completion is the patient-level gold with templated evidence strings, and most tokens are schema boilerplate, so its near-zero validation loss does not measure extraction.

**Pipeline note (not changed here).** `chain_llm.ground_value` misses frequencies with a hyphenated word between the count and "per" ("2 focal impaired-awareness seizures per year") and "once monthly". This affects only arms whose own quote is not verbatim (Arm H). Changing it would alter published numbers, so it is listed in `docs/FUTURE_WORK.md` instead.

### 10.9 Evidence for the shipped configuration, 2026-10-01 (these are the figures the app shows again after D17)

Why. The F-S numbers in 10.6 and 10.7 were scored with `--disagree-llm predominant_seizure_type`, but the live runtime ships with no override (`LeoRuntime.disagree_llm = ()`; the override stays off until it is confirmed on an unused set, D8). The app shows accuracy figures to users, so they must come from the configuration it runs. The F-S held-out letters were re-scored with the shipped settings, replaying the same L1C manifests (`data/run_manifests_fs_test_flat_c`, no new model run):

```
venv-medcat/bin/python scripts/score_leo_vs_fs_gold.py --llm L1C=data/run_manifests_fs_test_flat_c:L1C \
  --out eval/results/leo_vs_fs_gold_v05_default
```

The synthetic figures in 10.7 (`leo_vs_synth_gold_v05_maint`, arm L1C) already used no override. The app reads both files (`services/leo_evidence.py`); `tests/test_leo_app.py` checks that the displayed numbers equal the file contents and that the arm is L1C.

**F-S held-out letters, L1C, micro-F1 (95% CI), seven fields, rescue drugs count as current**

| system | policy `predominant_seizure_type`→LLM (10.7) | shipped default (this run) |
|---|---|---|
| llm | 0.700 [0.642, 0.761] | 0.700 [0.642, 0.761] |
| specialist | 0.655 [0.582, 0.723] | 0.655 [0.582, 0.723] |
| leo_auto | 0.664 [0.584, 0.734] | 0.664 [0.584, 0.734] |
| leo_review | 0.705 [0.644, 0.767] | 0.678 [0.613, 0.743] |

Paired difference, leo_review minus llm: +0.005 [-0.029, +0.045] with the policy, -0.022 [-0.062, +0.022] shipped. Seizure-type F1 of leo_review: 0.571 with the policy, 0.343 shipped (llm alone 0.563). Claim precision by agreement, shipped: agree 0.835 (85 scored) **[0.75, 0.91]**, disagree 0.312 (16) **[0.11, 0.53]**, llm_only 0.455 (22) **[0.25, 0.65]**, specialist_only 0.250 (20) **[0.07, 0.46]**. Agree minus disagree +0.52 [+0.31, +0.73]; minus llm_only +0.38 [+0.16, +0.60]; minus specialist_only +0.58 [+0.36, +0.78] (`leo_vs_fs_gold_v05_default.md`). **C2 is supported on these CIs** for the shipped configuration (the earlier “CIs pending” notes in §10.1–10.2 refer to unconstrained L0/L1).

Reading. With the shipped default, LEO's reviewed output does not beat the model alone on the F-S letters, and it is worse than the model on seizure type, where the specialist's value survives a disagreement. The audit trail (quote, source, review flag) is the contribution shown so far, not higher accuracy. The policy that lets the model win seizure-type disagreements removes most of the gap, but it was chosen on F-S development letters; the unused-set check in 10.8 decides whether to ship it.

**Related changes in the same release.** (1) With no LLM (one reader) nothing is reported as accepted: `leo_tabular` marks every value `needs_review` with reason `no_second_reader`, because specialist-only claims were right 25% of the time here (86% on the synthetic notes). (2) Phenotypes carry an evidence level: five are `measured`; (at that time) rescue, one-off administration and prior ASMs were `indirect`; since 10.16 only one-off administration is (only their effect on `current_asms` was scored; the earlier label "scored" overstated this); drug resistance is inferred by rule (`rules/compound.py`), so it is not a quote and not tested. (3) The F-S gold sets epilepsy type to "unknown" when the diagnosis line names none (25 of 38 letters), so the all-letters F1 of 0.42 mixes errors with unadjudicated inferences; the typed-only view (13 letters) is 1.00.

### 10.10 Specialist on the extra phenotypes (synthetic, CPU), 2026-10-01

`scripts/score_extra_phenotypes.py` -> `eval/results/leo_extra_phenotypes.{json,md}` (30 evaluation patients) and `leo_extra_phenotypes_ext.{json,md}` (80 other patients, `MEDAI_SYNTH_SET=ext`). Specialist only (no LLM), each patient's notes joined; reference = the synthetic target files. Only phenotypes with reference entries can be scored: etiology category and drug resistance (all patients), MRI items (patients with an MRI report). The catalogue level `rules_only` marked these seven phenotypes; section 10.16 later added rescue and prior drugs, failed drugs, etiology details and EEG background, so twelve carry it.

**First run (rules as of 2026-10-01, 30 patients).** Etiology category 28/30; drug resistance 15/30 (all 10 resistant found, 9 of 20 responsive called resistant, 6 unanswered); MRI findings precision 0.50 recall 0.88; MRI normal 0/2; hippocampal sclerosis 6/6 found, 2 false alarms; surgery: a procedure reported for 19 of 30 patients whose reference lists none (VNS/RNS/DBS and "epilepsy surgery" mentioned as options).

**Rule fixes (2026-10-02, `rules/sentence_context.py`, `rules/fields/surgery.py`, `rules/fields/mri.py`, `rules/compound.py`; 23 tests in `tests/test_sentence_rules.py`).** (1) Surgery: a mention counts as history only when the sentence is not negated, hedged or a list of options, and a bare "surgery" needs a history cue (s/p, underwent, had, implanted, prior ...). (2) MRI: negated and hedged findings are not reported as present; "no hippocampal sclerosis" and "no FCD" now give False; a "normal" finding no longer counts as a positive finding in the overall-normal rule. (3) Drug resistance: an explicit statement ("responding well", "seizure-free on", "drug-resistant") is read at sentence level and the later statement wins. "Accuracy (all)" counts a yes/no finding the note never mentions as wrong, because the reference says False; the rules never infer absence, so the tables also give "when answered".

| Phenotype | 30 patients (rules were developed on these) | 80 held-out patients (`ext`) |
|---|---|---|
| etiology category | 28/30 | 77/80 |
| drug resistance | 29/30 (was 15/30) | 76/80 |
| MRI normal | 16/16 answered (16 of 17 patients answered) | 29/29 answered (of 30) |
| hippocampal sclerosis | 10/10 answered (10 of 17 answered) | 18/19 answered (of 30) |
| focal cortical dysplasia | 7/7 answered (7 of 17) | 11/14 answered (of 30) |
| MRI findings, list | precision 0.52, recall 0.88 | precision 0.50, recall 0.93 |
| surgery false alarms | 0 of 30 (was 19) | 5 of 80 |

The 30-patient column shows what the fixes do on the data that suggested them; quote the held-out column. Held-out and development patients come from the same generator, so neither says how the rules do on real notes. MRI findings precision stays at 0.50 because the rules also list findings the reference does not record. Detailed EEG findings (study type, background, ictal onset), semiology, focal onset features and surgery have no reference entries and stay untested. An earlier version of this section said the same of failed/prior/rescue drugs and etiology details; that was wrong, the generation plans and the F-S gold do contain them. They are scored in section 10.16.

### 10.11 Chunking of long documents, 2026-10-01

The chunker split at every section header, so a 26,000-character document (five notes joined) became 24 chunks, many only a few dozen characters (an "Allergies" line, a medication list apart from its history): 24 model calls, each reading a fragment. LEO now calls `chunk_text(..., pack=True)`, which joins neighbouring sections up to `max_chars` (8,000) and keeps the headers between them: the same document gives 5 chunks of at most 7,848 characters. Other callers keep the old behaviour. Accuracy on long documents is measured by `scripts/leo_gpu_validate.py long` (Slurm job 160614) and questions by `... ask` (job 160615); results will be appended when the jobs finish.

### 10.12 Real-model checks on a GPU, 2026-10-02 (Slurm jobs 160613-160615; NVIDIA L40S, torch 2.14, python 3.11)

`scripts/leo_gpu_validate.py`; raw results `eval/results/leo_gpu_*.json`, rescored tables `eval/results/leo_vs_fs_gold_v05_live.md` and `leo_vs_synth_gold_v05_live.md`. Synthetic data only.

**Smoke.** Med42-8B loads in LEO's runtime (6 s from cache) and one note plus one question run end to end.

**Live model vs the evaluation outputs.** The evaluation used python 3.9 / torch 2.7. Same prompts, greedy, constrained decoding, regenerated: the generated text is identical for 30 of 40 F-S letters and 125 of 143 synthetic notes; the parsed values are identical for 32/40 and 126/143. The web app's code path gave the same parsed output as the script on the 5 notes checked per set. Differences are in drug lists, frequency, onset and seizure type, consistent with floating-point differences in the newer stack. Rescored with the unchanged scorers (micro-F1, F-S 40 letters): model alone 0.712 (was 0.700), specialist 0.655, leo_auto 0.672 (0.664), leo_review 0.680 (0.678); leo_review minus model -0.032 [-0.079, +0.018] (was -0.022 [-0.062, +0.022]). Synthetic US (30 patients): model 0.993, specialist 0.987/0.963 by stratum, leo_auto 1.000/0.997, leo_review 0.981/0.963. Conclusion unchanged: LEO is statistically tied with the model alone on F-S and does not beat it; agreement precision is 0.84 (F-S) and 1.00 (synthetic) when the readers agree, 0.29 and 0.06-0.30 when they disagree.

**Long documents (chunked, 30 patients, 10-40k characters, 3-7 chunks, 34-89 s each).** Patient-level micro-F1: model alone 0.991, specialist 0.932, leo_auto 0.970 (precision 1.00, recall 0.942), leo_review 0.928. Chunking works for the model (0.991 on documents up to 40k characters, against 0.993 per note). The specialist loses accuracy on long joined text (0.932 against 0.971 per note) and drags LEO with it. On the 11 documents of up to 20k characters, chunked and whole-document model runs scored 1.000 and 0.987 (n = 11: no evidence of a difference).

**Questions (30 patients, joined notes).** Epilepsy type 30/30 and onset age 30/30 answers equal the reference (3 of the type answers were flagged `rejected` because the quote was not found verbatim). Hippocampal sclerosis yes/no 11/17 (5 not documented, 1 rejected, 1 false yes). "Currently taking X?" 91/114 equal to the reference; for yes: precision 0.74, recall 0.96 (52 true yes, 18 false yes, 2 missed). Of the 168 answers whose quote was located, 148 (88%) were right. Unanswerable controls (blood type, pet, shoe size): 88/90 `not_documented`, 2 invented answers (2.2%). **Caveat found while checking the false yeses:** for two of three false "yes" answers inspected the drug name does not appear anywhere in the document, yet the quote check passed (the quote located was other text); in the third the note does list the drug. So a located quote shows the words are in the note, not that they support the answer. The harness now saves the quote with each answer so this can be examined.

### 10.13 Disagreement policy per field (candidate), Arm H2 (2026-10-02)

Decision D15, default withdrawn by D17. All numbers are synthetic notes; arm L1C unless stated; scorer outputs are in `eval/results/`.

**What the literature and ExECT say.** ExECT has no arbitration: it is a rules pipeline, so there is no second reader to disagree with. Its published results (ExECT v1 medication precision/recall 96.1/94.0, overall F1 86.1; ExECT v2 per-item F1 about 0.87, seizure frequency the lowest at 0.66) show where a rules-only reader is weakest, which is what a model reader is for. Work on rules plus language-model hybrids points the same way: rules filter or verify model output, disagreement between readers is an error signal that should go to a person, and the choice of which reader to trust should come from evidence for each field, not from a majority vote or one global rule. Nothing found fixes a winner for a particular epilepsy field, so the choice is measured here (sources are web summaries; primary papers were not all opened; see `REFERENCES.md`).

**The check (D14, run once).** Default (rules' value shown on a disagreement) against `--disagree-llm epilepsy_type,predominant_seizure_type,age_at_onset_years,seizure_frequency.period` (model's value shown), same manifests.

| set | field | reviewed F1, rules shown | reviewed F1, model shown | model alone |
|---|---|---:|---:|---:|
| `ext` (80 patients, 399 notes) | predominant seizure type (n=66) | 0.803 | 1.000 | 1.000 |
| `ext` | epilepsy type (n=80) | 0.975 | 0.938 | 0.938 |
| `ext` | onset age, frequency period | 1.000, 0.991 | 1.000, 0.991 | 1.000, 1.000 |
| `v1v2` (101 patients, 202 notes) | seizure type (n=89), epilepsy type (n=101) | 1.000, 0.995 | 1.000, 0.995 | 1.000, 0.995 |
| F-S letters (40; seizure type chosen on dev letters) | seizure type (n=18) | 0.34 | 0.57 | 0.56 |

Micro-F1 of the reviewed output: `ext` 0.968 with the rules' value, 0.984 with the model's value on all four fields (model alone 0.988). On `ext` the claims shown after a disagreement were right 23% of the time with the rules' value and 61% with the model's (the four-field setting also moved epilepsy type, so this is not seizure type alone). `v1v2` has 8 to 18 disagreement claims, too few to read.

**Candidate policy.** Seizure type: show the model's value. Epilepsy type: show the rules' value (the model-wins setting lowered it on `ext`). Onset age and seizure frequency: rules' value, since nothing separated the readers. Both values stay in the output and every disagreement is flagged `source_disagreement`, so the policy changes what a reader sees first, not whether a person looks. Limits: see D15.

**Candidate policy re-scored** (replaying the L1C manifests with `--disagree-llm predominant_seizure_type`; `leo_vs_fs_gold_v05_candidate.*`, `leo_vs_synth_gold_v05_candidate.*`). The shipped default (D17) gives, from `leo_vs_fs_gold_v05_default` and `leo_vs_synth_gold_v05_maint`: F-S reviewed 0.678 (reviewed minus model -0.022 [-0.062, +0.022]), synthetic reviewed 0.969 (-0.024 [-0.053, -0.004]). Candidate policy:

| test set | model alone | rules alone | LEO auto | LEO reviewed | reviewed minus model |
|---|---:|---:|---:|---:|---|
| 40 F-S letters | 0.700 | 0.655 | 0.664 | 0.705 | +0.005 [-0.029, +0.045] |
| 30 synthetic US patients | 0.993 | 0.971 | 0.998 | 0.978 | -0.015 [-0.040, 0.000] |

Claim precision by agreement, F-S: agree 0.835, disagree 0.500 (8 scored), model only 0.500, rules only 0.250; synthetic: agree 0.999, disagree 0.227, model only 0.932, rules only 0.857. So with the policy LEO is tied with the model alone on the F-S letters (before: -0.022) and 0.015 below it on the near-saturated synthetic set. The earlier default (10.9) is the shipped one (D17). The live-GPU outputs of 10.12 re-scored under the candidate policy (`leo_vs_*_v05_live_candidate.*`, same manifests as 10.12): F-S model 0.712, rules 0.655, auto 0.672, reviewed 0.707 (reviewed minus model -0.004 [-0.039, +0.036]); synthetic identical to the table above.

**Arm H2 on the F-S letters** (flat contract, LoRA on verbatim spans, constrained decoding, zero-shot prompt; candidate policy: `leo_vs_fs_gold_v05_h2_candidate.*`; shipped default: `leo_vs_fs_gold_v05_h2.*`, reviewed 0.690, reviewed minus model alone -0.054 [-0.103, -0.006], seizure-type F1 0.34 against 0.62 for the model alone): H2 alone 0.743 [0.682, 0.803] against 0.700 for the base model with two examples (L1C); H2 minus L1C +0.043 [+0.010, +0.083]. With the rules: auto 0.691, reviewed 0.724, reviewed minus model alone -0.019 [-0.048, +0.010]. Per field (H2 alone / LEO reviewed): current ASMs 0.931 / 0.859, seizure type 0.621 / 0.629, seizure frequency period 0.615 / 0.692. For comparison from 10.2 and 10.3 (older configuration): Arm H 0.752, L2C 0.736. So fine-tuning on the verbatim contract moves the model alone about as far as few-shot retrieval does, and the rules again do not add accuracy to it (they lower the drug list, which shows rescue and other drugs the model leaves out). Synthetic H2 runs (`data/run_manifests_synth_eval_h2*`) were still running when this was written; append them here when scored.

### 10.14 Question quote check, patient roll-up, hardening (2026-10-02)

(1) `services/leo_ask.py` rejects a yes/no or drug answer whose quote is not about the drug asked (`quote_off_topic`; the sentence containing the quote is also checked). This addresses the false yeses found in 10.12; tests in `tests/test_leo_app.py`. Its effect is measured in 10.15. (2) `bin/leo rollup` / `services/leo_rollup.py`: optional patient-level table from per-note rows (D16). (3) The server listens on 127.0.0.1 unless it runs under Slurm (`--host` overrides); job folders are mode 0700. (4) Long-document rerun with the new chunk packing and rule fixes: 10.15.

### 10.15 GPU reruns after the fixes, default restored, adjudication tooling (2026-10-02)

**Questions (Slurm job 164255; same 30 patients, joined notes, stricter quote check; `eval/results/leo_gpu_ask.json`).** Epilepsy type 30/30 and onset age 30/30 (3 type answers `rejected`: quote not found). Hippocampal sclerosis yes/no 11/17 (5 not documented, 1 rejected). "Currently taking X?" 94/114 equal to the reference (0.825; before 91/114), yes-answers: precision 0.78 (52 true yes, 15 false yes), recall 0.96 (2 missed). Unanswerable controls: 88/90 `not_documented`, 2 invented (2.2%, as before). Of the 15 false yes, 11 were `rejected` by the new check. Across epilepsy type, onset, hippocampal sclerosis and drug questions, 116 answers kept `needs_review` (quote found and on topic): 110 right (95%; before, 148 of 168, 88%). The check also rejected 44 correct answers, which are shown but marked untrusted: it trades recall of trusted answers for precision. Not examined: why those 44 were rejected (brand names, a quote naming a different drug in the same sentence).

**Long documents (job 164256; 30 patients, 3-7 chunks; `eval/results/leo_gpu_long.json`).** Patient-level micro-F1: model alone 0.991, specialist 0.932, leo_auto 0.970, leo_review 0.967 (before the rule fixes 0.928). This run was made after the code default had been set to the candidate policy for about an hour, so its reviewed figure includes the seizure-type override; the other columns do not depend on it. Up to 20k characters (11 documents): chunked 1.000, whole document 0.987. As in 10.12, each document is one patient's visits joined, which mixes visit states; it tests chunking, not the supported per-note mode (D16).

**Default restored (D17).** Code: `DEFAULT_DISAGREE_LLM = ()`, `--disagree-llm candidate` for the seizure-type policy; tests updated. The app reads `leo_vs_fs_gold_v05_default` and `leo_vs_synth_gold_v05_maint` again. Live-GPU manifests re-scored under the default: `leo_vs_fs_gold_v05_live`, `leo_vs_synth_gold_v05_live`; under the candidate policy: `*_live_candidate`.

**Arm H2, shipped default (L1C and H2 on the same notes).** F-S letters (`leo_vs_fs_gold_v05_h2`): H2 alone 0.743, rules 0.655, auto 0.691, reviewed 0.690 (reviewed minus H2 alone -0.054 [-0.103, -0.006]); candidate policy 0.724 (10.13). Synthetic 30 patients (`leo_vs_synth_gold_v05_h2`): H2 alone 0.996, L1C 0.993; reviewed 0.971 and 0.969. Synthetic 101 patients, `v1v2` (`leo_vs_synth_gold_v1v2_h2`): all systems 0.997 to 0.999 for the models, reviewed equal to model alone (saturated). `ext`, 80 patients (`leo_vs_synth_gold_ext_h2`): H2 alone 0.992, L1C 0.988; reviewed 0.969 and 0.968. The per-field pattern behind D15 repeats with H2: seizure type 0.788 reviewed (rules' value shown) against 0.985 for the model alone, epilepsy type 0.975 reviewed against 0.949 for the model alone. So the pattern is not specific to L1C, but it is still the same synthetic generator.

**Disagreement tooling.** `services/leo_disagree.py`, `bin/leo disagreements` (export for blind adjudication; `--score` tally per field with Wilson intervals), 2 tests. Protocol and decision rule: `docs/DISAGREEMENT_ADJUDICATION.md`. Not exercised on real adjudications.

### 10.16 Phenotypes scored from the generation plans and the F-S gold (specialist only, no LLM), 2026-10-02

`scripts/score_plan_phenotypes.py` -> `eval/results/leo_plan_phenotypes.{json,md}`. This corrects section 10.10, which said that failed/prior/rescue drugs and etiology details have no reference. The synthetic plans (`data/episynth_corpus/{v3,v3_polish}/patients/<pid>.json`) list `PRIOR_ASMS` (with the reason each was stopped) and `ETIOLOGY_SPECIFICS` (gene, variant, antibody). The F-S gold has prescriptions with Frequency As_Required, EEG results (Normal / Abnormal) and EpilepsyCause. Still unscored: detailed EEG findings, semiology, focal onset features, surgery. Specialist only, notes of a patient joined. All data are synthetic or F-S letters, so none of this speaks to real clinic notes.

**Stopped (prior) drugs** (reference: the plan lists them only for the polish patients; precision is a lower bound because the generator may mention a stopped drug that is not in the plan).

| Stratum | Patients (with a stopped drug) | Precision | Recall | F1 | Stopped drug listed as current |
|---|---|---|---|---|---|
| polish90 (adapter trained on these; rules developed on this corpus) | 90 (65) | 0.54 | 0.885 | 0.671 | 25 patients |
| polish_val (10, held out from the adapter) | 10 (5) | 0.42 | 0.80 | 0.55 | 2 patients |

Reason on drugs both found: intolerance is called intolerance for 84 of 93 drugs, but a drug stopped for inefficacy is called inefficacy for only 4 of 23 (12 called intolerance, 7 unspecified). In the ILAE sense (stopped for inadequate seizure control, which is what drug resistance depends on) failed drugs score precision 0.40, recall 0.15 (4 right, 6 wrong, 23 missed; held-out: 0 of 2). **Finding:** the rules find stopped drugs reasonably (recall about 0.8-0.9), but they cannot yet separate "failed" from "stopped for side effects", and they sometimes list a stopped drug as current. Treat prior drugs as a list to review, and failed drugs as not usable without the model or the reviewer. This is a rule gap worth a fix (see FUTURE_WORK).

**Etiology specifics** (gene, variant, antibody). 27 patients with a specific in the plan (v3 eval 1, ext 12, polish 13, held-out polish 1): gene, variant and antibody correct every time (7/7, 7/7, 5/5 on the ext patients), no false alarms on the patients with none. The numbers are small and the generator writes these with a limited vocabulary; this shows the rules handle that vocabulary, not that real reports will parse.

**F-S letters** (rescue = prescription with Frequency As_Required, 9 in 200 letters; EEG = letters with an EEG result, 67 in 200; cause = EpilepsyCause present).

| Letters | Rescue tp / fp / fn | Coarse EEG result: answered / right | EEG results missed | Cause present: recall, precision |
|---|---|---|---|---|
| held-out EA0161-EA0200 (40) | 1 / 0 / 0 | 8 of 14 reference results / 8 | 6 | 5 of 5 / 5 of 12 |
| all 200 | 6 / 6 / 3 | 38 of 67 / 37 | 29 | 24 of 28 (0.86) / 24 of 75 (0.32) |

Rescue: of the 6 false alarms, one is a naming mismatch (reference "buccalmidazolam", rules "midazolam": really a hit), two (EA0069, EA0087) are the letter suggesting the family might consider buccal midazolam (a proposal, not an existing rescue drug), and the others were not examined. Adjusted for the naming case the figures are 7 / 5 / 2, still only 9 reference prescriptions. EEG: when the rules give a result it is nearly always right (37 of 38), but they give none for 29 of 67 letters (recall 0.57), so EEG is a partial detector. Cause: recall is good, precision low; F-S annotates a cause only when the letter states one, and the rules also report etiology terms the annotators did not mark, so precision here mixes real errors with annotation convention (not yet separated by reading the letters).

Not a LEO result: LEO (with the model) was not run on these. These are the specialist's numbers; the model's behaviour on them is untested.

### 10.17 Extended synthetic set: EEG findings, semiology, focal onset, rescue, surgery (specialist only, no LLM), 2026-10-02

**Set.** `scripts/synth_extended_plan.py` adds five plan fields (EEG_STUDY, SEMIOLOGY, FOCAL_ONSET, RESCUE_MEDS, SURGERY_HISTORY) to ordinary sampled patients (P005000-P005039; plans in `data/episynth_corpus/v4_ext/`), and `scripts/generate_synth_v3_corpus.py` adds a directive that makes the generator state them. Notes by `gpt-5.6-sol`. The run stopped when the OpenAI account ran out of credit: **113 notes for 37 of the 40 patients** (P005037-P005039 not generated). Values are drawn to agree with epilepsy type, seizure type and MRI; the mix is a coverage fixture, not prevalence (rescue drugs for 24 of 40 patients, surgery for 13). Scorer `scripts/score_extended_phenotypes.py` -> `eval/results/leo_extended_phenotypes.{json,md}`: the specialist's claims over a patient's notes joined, against the plan.

**Exposure.** I read examples from every failure category while building the scorer, so these 37 patients are not a clean test for any rule written from here on. A rule fix needs a new batch of patients (a few dollars of generation).

| Item | Result (37 patients) |
|---|---|
| EEG background, normal vs slowing | 37 of 37 |
| EEG study type | 13 of 37 (all answered) |
| Interictal discharges found | 17 of 27 patients that have them; where found, lobe right 8 of 8 and side 8 of 10 |
| Ictal onset (lobe, side) | 4 of 5 each; reported for 20 patients where the plan has none |
| Focal motor onset | 7 of 12 |
| Focal non-motor onset | 8 of 15 |
| Semiology (lenient key words) | 19 of 34 motor features and 3 of 13 auras found, among those the notes mention |
| Rescue drugs | 21 tp, 6 fp, 1 fn (precision 0.78, recall 0.95) |
| Surgery | 11 tp, 1 fp, 0 fn (precision 0.92, recall 1.0) |

**What the failures are (checked by reading sentences).**
- *Study type, real rule error.* The rules read "inpatient video-EEG monitoring may be considered" in a plan, and "stored electrocorticography not available" in a device note, as the patient's EEG study. The context filters that fixed surgery (options, hedged, negated) are not applied to EEG.
- *Ictal onset, real rule error.* "No ictal onset was captured" is read as an onset, taking the lobe of the discharges; an unrelated "seizure onset at age 28" can also trigger it. Negation is not handled.
- *Interictal discharges missed.* Cases such as "bilateral generalized interictal epileptiform discharges" and "right occipital interictal epileptiform discharges were reported" were not detected; 10 of 27 missed.
- *Rescue false positives: 6 of 6 are not clear errors.* Three are hospital orders ("lorazepam IV PRN per EMU protocol"), a home rescue rule gap; three are "should she have a cluster, use nasal midazolam", a rescue instruction that came from the plan's hypothetical triggers, not its RESCUE_MEDS field. Whether that is a rescue medication is a clinical convention to settle (D-item), and the plan contradicts itself here.
- *Focal onset "false alarms" are mostly my reference.* In 16 (motor) and 5 (non-motor) cases the plan leaves the onset field empty but lists the same feature as semiology or aura; the scorer now counts these separately. Only 4 non-motor values had no support in the plan.
- *Onset right-or-wrong:* 5 of 12 motor and 7 of 15 non-motor onsets differ from the plan; the sentences were not read, and the plan itself may be ambiguous between onset and semiology.

**Not shown.** The model (second reader) was not run; LEO's combined result on these fields is unknown. The notes are LLM-written from the plan, so they are tidier and more explicit than real letters.

### 10.18 Stress test of the model table on 160 more F-S letters (2026-10-02; Slurm jobs 165774-165778)

Question: do the 40-letter results (L0 0.68, L1 0.70, L2 0.74, first adapter 0.75, second adapter 0.74) hold on more letters? None of these models was trained on F-S letters, so EA0001-EA0160 are unseen by them (L2 retrieves from the F-S bank with the letter itself excluded; letters EA0081-EA0120 were used earlier to choose the fusion policy, not to tune the models). Same prompts, same old python 3.9 / torch 2.7 stack as the 40-letter table; scorer `scripts/score_leo_vs_fs_gold.py --pids EA0001..EA0160`, results `eval/results/stress_fs160.{json,md}` (four-arm file `stress_fs160_partial.*` is superseded). The first adapter (arm H, training prompt, free decoding) finished later (job 165777, 3 h 45 min) and is included.

| Model alone (micro-F1, 160 letters, 95% CI) | 160 letters | same arm on the 40 held-out letters |
|---|---|---|
| L0 base, zero-shot | 0.656 [0.617, 0.693] | 0.679 |
| L1 base, two examples | 0.688 [0.652, 0.722] | 0.700 |
| L2 base, retrieved examples | 0.662 [0.621, 0.699] | 0.736 |
| H first adapter, free decoding | 0.716 [0.683, 0.748] | 0.752 |
| H2 second adapter, constrained | 0.707 [0.669, 0.741] | 0.743 |
| EpExtra rules alone | 0.652 [0.615, 0.685] | 0.655 |

Paired differences (resampling letters): H - L0 +0.060 [+0.023, +0.096]; H - L1 +0.028 [-0.002, +0.057]; H - L2 +0.054 [+0.016, +0.093]; H - H2 +0.009 [-0.024, +0.043]; H - rules +0.064 [+0.024, +0.104]; H2 - L0 +0.051 [+0.022, +0.081]; H2 - L1 +0.018 [-0.004, +0.042]; H2 - L2 +0.045 [+0.009, +0.081]; L1 - L0 +0.032 [+0.001, +0.063]; L2 - L0 +0.007 [-0.035, +0.049]; H2 - rules +0.054 [+0.017, +0.090]; L0 - rules +0.004 [-0.040, +0.036].

LEO on the same letters (default policy, rules' value shown on a disagreement), reviewed micro-F1: with L0 0.661, L1 0.672, L2 0.673, H 0.664, H2 0.675 (rules alone 0.652). LEO reviewed minus the model alone: L0 +0.005 [-0.028, +0.039]; L1 -0.016 [-0.043, +0.011]; L2 +0.010 [-0.028, +0.049]; H -0.052 [-0.087, -0.019]; H2 -0.032 [-0.061, -0.002]. Arm H also has the problem noted in 10.2: 139 of its claims fail the quote check (reject rate 0.096, against 0.02-0.03 for the others), so part of its drop inside LEO is rejected claims. Auto-accepted precision 0.82-0.84 against 0.74-0.86 for the model alone, at lower recall. Claim precision when model and rules agree 0.80-0.89; when they disagree 0.27-0.35.

Reading:
- On 40 letters L2 looked best among the base arms (0.736); on 160 it is no better than zero-shot (0.662 vs 0.656). The 40-letter ordering was partly chance.
- Fine-tuning (H, H2) is ahead of zero-shot by 0.05-0.06 and of retrieved examples by 0.045-0.054, with intervals that exclude zero, but only 0.019-0.028 ahead of two fixed examples, intervals that include zero. The two adapters do not differ (+0.009 [-0.024, +0.043]).
- The base model alone is no more accurate than the rules alone (0.656 vs 0.652) on these seven fields.
- LEO's reviewed score is nearly the same whichever model feeds it (0.661-0.675); fine-tuning raises the model alone, not LEO.
- All figures use the F-S reference conventions (for example "unknown" epilepsy type when no type is named), so they bound agreement with F-S annotators, not clinical truth.

### 10.19 Perfect-reviewer upper bound and review workload, 160 F-S letters (2026-10-03)

`scripts/score_leo_oracle_review.py` -> `eval/results/leo_oracle_review_fs160.{json,md}`; same 160 letters and manifests as 10.18, specialist plus each model, default fusion policy, no GPU. **No human reviewed anything.** `leo_review` in the other tables is the *draft* a reviewer would be shown. `oracle_pick` is what a *perfect* reviewer would leave if she could only choose among what the readers produced: accepted values stay (so accepted errors stay); for a scalar field with a flagged value and no accepted one she picks the correct one among LEO's shown value, the model's and the rules' (else leaves it empty); each flagged drug is kept only if the reference lists it; values neither reader produced stay missing.

| Model feeding LEO | model alone | leo_auto | leo_review (draft) | oracle_pick | oracle minus model alone |
|---|---|---|---|---|---|
| L0 base zero-shot | 0.656 | 0.648 | 0.661 | 0.769 | +0.114 [+0.088, +0.142] |
| L1 base two examples | 0.688 | 0.669 | 0.672 | 0.767 | +0.079 [+0.058, +0.101] |
| L2 base retrieved | 0.662 | 0.644 | 0.673 | 0.766 | +0.103 [+0.071, +0.137] |
| H first adapter | 0.716 | 0.669 | 0.664 | 0.768 | +0.051 [+0.025, +0.079] |
| H2 second adapter | 0.707 | 0.677 | 0.675 | 0.789 | +0.083 [+0.062, +0.104] |

Workload (default policy): 5.2-5.9 flagged claims per letter on average (median 5, 90th percentile 9-10). Of the items a reviewer has to decide (fields with a flagged value and no accepted one, plus flagged drugs; 252-353 across the 160 letters) only 17-24% are already right as shown.

Reading and limits:
- Once a perfect reviewer is in the loop, LEO ends above the model alone (+0.05 to +0.11) and above the draft (about +0.10). The reason is precision: oracle precision is 0.85-0.87 against 0.74-0.86 for the model alone, with recall at least as high (0.69-0.72). The two readers together hold more correct values than either, and a reviewer can pick them.
- This is an upper bound, not a result. Real reviewers make errors and disagree with each other. The reviewer-time cost is not measured.
- Part of the gain is the oracle dropping flagged values that the F-S reference does not list. A real reviewer would keep some of these if they are true but unannotated, so the F-S figure overstates the gain to an unknown degree.
- Candidates are the readers' own predictions; a model value that fusion rejected for an unfound quote can still be picked, so the bound is slightly generous. Values neither reader produced stay missing (reviewer-added values are deferred).
- Accepted errors remain. The review tier is where the benefit comes from, so the claim that LEO gains accuracy rests on reviewers actually resolving the flagged values; that needs the blind adjudication in `docs/DISAGREEMENT_ADJUDICATION.md`.

### 10.20 EEG rule fixes: advised or absent studies, negated and planned ictal onset (specialist only, 2026-10-03)

**Change** (`rules/fields/eeg_extra.py`): an EEG study type is no longer taken from a sentence that advises, plans or awaits it (recommend, refer, consider, would, may, if ...), says it was not available, performed or declined, or has "no/not/without" just before it; an "ictal onset" phrase is no longer taken from a sentence with a negation, a plan or a purpose ("could not be localised", "to localise the seizure onset"). A study that is done and a later sentence that advises another one are kept apart (unit tests in `tests/test_rules_p2.py`).

**Result on the same 37 synthetic patients as 10.17** (`eval/results/leo_extended_phenotypes.{json,md}`, regenerated):

| Item | Before | After |
|---|---|---|
| EEG study type right | 13 of 37 | 24 of 37 |
| Ictal onset reported where the plan has none | 20 patients | 13 patients |
| Ictal lobe / side right (of 5) | 4 / 4 | 4 / 4 |
| EEG background, interictal discharges, focal onset, semiology, rescue, surgery | unchanged | unchanged |

**Limits.** I read examples from these 37 patients when I found the errors (10.17), so the improvement is on data the fix was written from; it is not a held-out result. A fresh batch of patients is needed for that. 13 study types are still wrong (most often "video-EEG" where the plan says routine or prolonged), and 13 patients still get an onset that the plan does not have. The fixes drop true statements that share a sentence with a negation or plan word; the cost in recall is not measured on real letters. Nothing here applies to real notes.

### 10.21 Focal motor / non-motor onset: first prominent feature (2026-10-06)

**Change** (`rules/fields/focal_onset.py`): a motor or non-motor feature is reported as *onset* only when it is (a) in a sentence that names the onset type ("motor onset", "autonomic onset"), or (b) in the first part of the sentence, before "then" / "followed by" / "progresses to", and that part has an onset cue ("begins with", "starts with", "aura of") or the word "aura", or (c) a "focal/partial seizure with X" sentence with no evolution word (the previous tests). Features that appear only after an evolution cue are not onset. Planned, advised, family-history and sentence-level negated mentions are skipped. "tonic-clonic" is not read as tonic or clonic.

**Split.** Development = even last digit of the patient id (P005000, P005002, …); held-out = odd. Note text of held-out patients was not read when writing the rule.

| field | development (right/wrong/missing) | held-out | all |
|---|---|---|---|
| focal_motor_onset | 5 / 1 / 1 (n=7) | 2 / 2 / 1 (n=5) | 7 / 3 / 2 (n=12) |
| focal_nonmotor_onset | 5 / 4 / 0 (n=9) | 6 / 0 / 0 (n=6) | 11 / 4 / 0 (n=15) |

Before (joined notes, 10.17): motor 7 of 12 right (all answered), non-motor 8 of 15. Motor recall is unchanged; 2 patients are now missing instead of wrong. Non-motor improved (11 of 15), and the held-out half of that field was 6 of 6. Other scored fields in 10.17 were unchanged (EEG study type still 24 of 37). v4_ext examples were already looked at in 10.17, so even the held-out half is not a fully clean test. n is tiny.

**Limits.** Tiny n; synthetic notes; the ILAE onset vs later-semiology distinction is hard in real letters too.

### 10.22 Second reader for the extended fields, and "accepted" only when two readers cover the field (2026-10-06)

**Change.** The model reader used by LEO (arm L1C, `services/flat_extract.py`) still reads five fields. A second, separate call (arm X1C, `services/ext_extract.py`) reads EEG study type, EEG background, interictal discharges (present and site), ictal onset lobe/side, focal motor and non-motor onset, rescue drugs, and surgery/stimulators that were done. The prompt and two worked examples were written before any evaluation of X1C; they are synthetic and were not tuned on v4_ext. Rescue drugs are emitted under `medication.current_asms` so the existing role split can pair them with the specialist; the pipeline ignores them when deciding whether the *maintenance* list was confirmed. Semiology *text*, MRI, etiology, drug resistance, prior and failed ASMs have no second reader: when the model ran, those specialist-only claims go to review with reason `no_second_reader` (switch `ChainPipelineConfig.require_second_reader_for_uncovered_fields`, env `MEDAI_LEO_REQUIRE_SECOND_READER=0` or CLI `--no-ext-reader` to reproduce earlier numbers). Numbers from 10.1–10.20 used the previous policy, under which a specialist-only claim on an unread field could be labelled accepted.

**First GPU measurement (job 169144, 2026-10-06).** 113 v4_ext notes, 37 patients, 56.1 min, 0 errors (`eval/results/leo_gpu_v4ext_x1c_2026-10-06`). Compared with rules alone on the same notes: EEG study type 36/37 (rules 31/37); IED present 27/27 for the model's own claims (rules 17/27, 10 misses — those extras stay in review, so auto-accept stays 17/27); focal non-motor onset 11/15 (rules 8/15); focal motor onset still 7/12 reviewed (model 3/12). Ictal onset 5/5 either way. Rescue auto-accept precision 0.913 (rules all-claims 0.724). Claim precision when both readers accept a scored field: 0.961. Synthetic notes; the prompt was not edited after this run.

### 10.23 Arm E: ontology selection from a retrieved list (2026-10-06)

**Change.** The retriever already proposed HPO/SNOMED/RxNorm ids. Exact label/synonym hits (score ≥ 0.9) still stamp the code with no model call. Fuzzy hits *can* go to a batched constrained decode (`services/onto_select.py`, arm E): the model may pick a 1-based index on that mention's list or abstain. A choice outside the list is discarded. The model never writes an id of its own. A **code** is `code_accepted` only when the *value* is accepted and the match is `exact` or `selected` (not `MEDAI-ENUM`). `--accepted-only` blanks suggestion codes. Columns: `concept_*`, `ontology_match`, `code_accepted`, `ontology_candidates` in `claims.csv`; `<id>_code`, `_system`, `_code_status` in the wide table. The picker is off by default after the GPU gate below; on: `--ontology-select` / `MEDAI_LEO_ONTOLOGY_SELECT=1`.

**Gate.** `eval/eval_concept_selection.py` (CPU: lexical R@1 vs gold-in-top-5 ceiling vs overlap heuristic; `--mode gpu` for the real selector). Ship the selector as a *measured* win only if selected R@1 exceeds lexical R@1 on scorable reachable mentions (`docs/CONCEPT_GOLD_SET.md`). Real-note code adjudication uses `bin/leo disagreements --kind codes`.

**GPU gate (job 169145, 2026-10-06).** 956 scorable reachable mentions, 19.8 min. Lexical R@1 0.555 (531); gold in top-5 0.744 (711); Arm E selector 0.335 (320). Gate **fail**. Exact label/synonym hits (score ≥ 0.9) still stamp without a model call. The picker is off by default (`--ontology-select` / `MEDAI_LEO_ONTOLOGY_SELECT=1` to turn it on). Ranking, not the prompt, is the remaining problem if we retry this.

### 10.24 Ontology routing covers the extract catalogue (2026-10-06)

**Change.** Candidate routing (`_FIELD_ONTOLOGY_ROUTE` / `_FIELD_SCOPE_ROUTE`) now includes every coded extract field the specialist and X1C already fill: EEG study type, IED present/site, ictal onset lobe/side, surgery, rescue and acute drugs, MRI HS/FCD/lesion site, awareness, other seizure types, etiology free text. Drug mentions search the supplementary `Medication` dictionary first (not the current/prior/failed *status* enum); etiology details search `EtiologyDetails`. ICD-10-CM and Orphanet stay out (SCOPE_DECISIONS D3/D5). Age, frequency and free-text semiology stay uncoded (quantities / narrative). The table gained the columns the other two readers already produced but the catalogue omitted: `other_seizure_types`, `awareness`, `eeg_ied_present`, `eeg_ied_findings`, `mri_lesion`.

### 10.25 Full phenotype extract: P1C, catalogue, ranking (2026-10-06)

**Change.** The model still cannot dump the whole schema in one JSON (F1–F3). A third constrained call (arm P1C, `services/pheno_extract.py`) reads the remaining closed-vocabulary extract fields: awareness, other seizure types, etiology category, status epilepticus, MRI (normal / HS / FCD / findings / lesion lobe and side), prior and failed ASMs, non-drug therapies, EEG seizures captured, and clinician localization. It is on with X1C (`--ext-reader`; off with H2 unless that flag is passed). Expect about three times the model time per note vs L1C alone. Free-text semiology, etiology details and derived drug resistance stay specialist-only.

The extract catalogue now lists those specialist fields as columns (`status_epilepticus_history`, `non_drug_therapies`, `eeg_seizures_captured`, `clinical_localization`, `adverse_effects_text`): 33 extract phenotypes. Accuracy for the new columns is the existing rules-only checks, not a new patient-level table. P1C itself is unmeasured.

Ontology ranking (no new sources; ICD-10-CM / Orphanet still out): UK/US spelling is folded before scoring; generic parents (`Seizure`, `epilepsy`) are demoted when the mention names a child; a token-overlap rerank applies when the top hit is below 0.9; etiology mentions also search the already-loaded Comorbidity, BirthHistory and CausativeAntibody dictionaries; `Kepra` and `zobisamide` are synonyms of levetiracetam and zonisamide. Arm E stays off.

### 10.26 Full v0.2.1 schema: F1C + remaining extract columns (2026-10-06)

**Change.** A fourth constrained call (arm F1C, `services/full_extract.py`) reads the leftover schema fields: semiology, etiology details, adverse effects, etiology specifics (gene / variant / antibody / pathogen / metabolic / tumor), drug resistance *as stated*, other seizure frequencies, EEG seizures-captured count, MRI-negative and field strength, alternative localization, and concordance (+ notes). Integrated `clinical`/`eeg`/`mri` localization copies are still filled by the rules from the primary/ictal/lesion claims. Extra readers stay on one switch (`--ext-reader`); expect about four times L1C-only model time. ICD-10-CM / Orphanet / EpSO stay out (D3–D5).

The extract table is 41 phenotypes. New columns: `other_seizure_frequencies`, `etiology_specifics`, `eeg_seizures_captured_count`, `mri_negative`, `mri_field_strength`, `alternative_localization`, `concordance`, `concordance_notes`. F1C is unmeasured.

Ontology routes added for MRI-negative, alternative localization, concordance, non-drug therapies and drug resistance (release scopes). Quantities and free-text notes remain uncoded.

### 10.27 Effectiveness follow-up (2026-10-06)

What was still hanging “effective” after 10.26, and what this pass did.

**GPU score for P1C and F1C.** Job **170942** finished (113/113 notes, 0 errors, mean 70.6 s/note). Extra-column scores are in 10.29 (`eval/results/v4ext_p1c_f1c.tables.md`). Extra readers do not change the five-field F-S headline.

**Ontology rank-1 after the ranking patches.** CPU remeasure (`eval/results/concept_selection_rank_2026-10-06`): lexical R@1 **0.566** (was 0.555), gold-in-top-5 ceiling 0.742, token-overlap pick 0.607 (CPU gate pass, as before). Room for Arm E is still ~0.18. The GPU Arm E gate is re-run with the F-S *letter* as selector context (the 10.23 GPU run concatenated mentions and is not a fair test of the picker). Arm E stays **off** unless that GPU selected R@1 beats lexical R@1. Job **170943**: `data/leo_runs/run_gpu_arme.sbatch`.

**LEO vs model alone on the five scored fields.** Extra readers (X1C/P1C/F1C) do not cover epilepsy type, seizure type, onset age, frequency, or current ASMs. The F-S reviewed figure remains 0.68 vs model 0.70 (10.12 / 10.16). Fusion’s measured value on those fields is still the audit trail, not higher accuracy. Changing the default disagreement policy is not a scoring re-run; it waits on adjudication.

**Real notes.** Still deferred (IRB + secure compute). All numbers remain synthetic.

**Disagreement policy.** Default stays rules-on-disagree. Candidate `--disagree-llm candidate` is unchanged. Export pack from the existing X1C GPU claims: `data/leo_runs/v4ext_llm_x1c.disagreements.csv` (89 cases). Score after a human fills `truth` / keeps `key_A_is` off the adjudicator copy (`bin/leo disagreements --score`).

**Reviewer add missed value.** Shipped: decision `add`, merge `added_by_reviewer`, Review tab scope “Values LEO missed”, `leo review --misses`. Learning from reviews stays deferred until real review data exist.

**Commit.** This wave is the coverage readers, ranking patches, add-value, and the eval/job scripts above.

### 10.28 Rank-1 misses, plan-adjudicated disagreements, focal motor (2026-10-06)

**Rank-1 miss dump** (`eval/results/concept_selection_rank_2026-10-06.misses.csv`): 415 lexical misses (168 gold in top-5, 247 not). Biggest not-in-top-5 piles: “generalised tonic clonic seizures” ranked under *Clonic seizure*; “sodium valproate” lost to a shorter RxNorm valproate; “JME” returned nothing. Bare “mri”/“eeg” (129) already have gold in the top-5; those need letter context (Arm E), not a synonym. Fixes: hyphen folding; short-parent substring penalty; high Jaccard as 0.88; overlap as a sort key even on 0.9 hits; JME → `C0270853` via EtiologyDetails.

**Disagreements vs the v4_ext plan** (not a clinician; does not change D17): 89 cases, `eval/adjudicate_v4ext_disagreements.py`. Where they disagree, the model matched the plan more often than the rules on seizure type (22/24 vs 1/24), EEG study type (14/20 vs 3/20), focal non-motor (9/10 vs 1/10) and onset age (4/4 vs 0/4). EEG background favoured the rules (4/6 vs 2/6). Blind copy: `data/leo_runs/v4ext_llm_x1c.disagreements.blind.csv`.

**Focal motor.** 14 plan-positive patients on the X1C run. Versive head turning is not an enum value; ILAE groups it under tonic. Rules+prompt now map versive / forced head turning → `tonic`, and the v4_ext scorer accepts tonic for a versive plan. Evolution after “followed by” is still not onset (P005012 spasms after a sensory aura stay missing, which is ILAE-correct). X1C prompt version `v1.1`. The P1C+F1C GPU re-score (10.29) left motor at 7 / 4 / 1 in the reviewer view.

### 10.29 Mission display, P1C/F1C plan scores (2026-10-07)

LEO’s job, as written: read a note, fill a phenotype table, and attach the note’s own words, which reader said it (model, rules, or both), whether a person should look, and an ontology id the model is not allowed to invent. Fusion is there so disagreement becomes a flag, not a silent guess.

**Display.** The wide table now has `<id>_alternative` after `<id>_why`. On a clash the recorded value stays the rules’ (D17). The model’s value is visible in the table, the extract UI (“Other reader”), the Review tab, and the About sheet. Default disagreement policy is unchanged. Arm E stays off.

**P1C/F1C scored from the existing GPU run** (`data/leo_runs/v4ext_llm_p1c_f1c`, no new extract). Plan on the 37 scored patients: etiology 18 structural / 9 unknown / 4 genetic / 3 immune / 2 infectious / 1 metabolic; DRE 22 responsive / 15 resistant; MRI finding present for 23 (9 HS, 5 FCD, 4 white-matter, plus encephalomalacia / vascular / incidental / normal). Reviewer view (all non-rejected claims) vs rules-only:

| item | n | rules-only | LEO reviewer view | model only |
|---|---|---|---|---|
| etiology category | 37 | 35 / 1 / 1 | 35 / 1 / 1 | 28 / 0 / 9 |
| drug resistance | 37 | 37 / 0 / 0 | 37 / 0 / 0 | 37 / 0 / 0 |
| MRI finding | 23 | 18 / 3 / 2 | 18 / 5 / 0 | 18 / 5 / 0 |
| MRI hippocampal sclerosis | 23 | 11 / 5 / 0 (+7 not in text) | 17 / 4 / 0 | 17 / 0 / 4 |
| MRI focal cortical dysplasia | 23 | 8 / 0 / 0 (+15 not in text) | 17 / 0 / 0 | 17 / 0 / 0 |
| MRI normal | 23 | 21 / 0 / 1 | 23 / 0 / 0 | 21 / 0 / 2 |

Cells are correct / wrong / missing. Etiology and DRE were already strong for the rules; the extra readers do not lift them and the model-only etiology column misses 9. MRI bools are where P1C earns its keep: the model fills HS and FCD the rules left blank, without a new false alarm on FCD. MRI finding label is not better (two extra wrongs, no misses). Five-field F-S remains 0.68 reviewed vs 0.70 model (10.12). These columns exist so a person can see both readers and the quote, not so the headline F1 moves.

Full table: `eval/results/v4ext_p1c_f1c.tables.md`.

### 10.30 Leftover E cues rematch + two fixes (2026-10-07)

Rematch on the same 113 v4_ext notes after leftover US strings (ACNS / RxNorm / i2b2 / Fisher / ExECT). Jobs **172426** (CPU, 113/113, 86 s) and **172425** (GPU L1C+extra readers, 113/113, 2 h 12 min). Outputs: `data/leo_runs/v4ext_rules_ecues.*`, `data/leo_runs/v4ext_llm_ecues.*`. Did not overwrite `v4ext_rules` / `v4ext_llm_p1c_f1c`. Plan scores: `eval/results/v4ext_ecues.tables.md`.

**Headline did not move.** Epilepsy type, seizure type, current ASMs, EEG study type value counts are identical to 10.29. GPU accept share 52.5% (was 52.7%). Both-readers accepted precision 0.969 (was 0.968). No more gazetteers on this set.

**What the rematch found**

- `LTM` in these notes is mostly planned; E still does not call that a completed study (good). Eight `prolonged` study types were already captured without the new `LTM` token in the evidence column.
- `LPDs` matched **negated** lists (“No … LPDs, GPDs”). False IED-other findings. Fixed: sentence-level negation for IED fallback (`rules/fields/eeg.py`).
- One GPU note still treated `escalate to LTM` as a rescue drug (model). E did not. Fixed: `is_eeg_study_token` drops LTM / VEEG / EMU / cEEG / ECoG / sEEG on medication claims, including LLM-only (`rules/fields/medication.py`, `services/chain_pipeline.py`).
- First-feature leftover words blanked 41 CPU motor-onset cells; plan wrongs 5→3, misses +2. GPU reviewer view unchanged. Left as-is.

**Measured option, not the default (D17 unchanged).** `--disagree-llm ied-silent` accepts an LLM-only `eeg.ied_present` when the rules were silent. On this plan, IED-found is 18/27 for accepted (follows E) vs 27/27 in the reviewer view / model-only column. Shipping that as the default would auto-accept model-only IEDs; it stays opt-in. Seizure-type display remains `--disagree-llm candidate` (not default).

**Research extract.** Use GPU cells with `*_status=accepted` and `*_source=specialist+llm` (both readers). `--accepted-only` blanks review cells. CPU-only runs accept nothing. Not real-note evidence.

### 10.31 Post-fix rematch (LPD negation + EEG-acronym not-a-drug) (2026-10-07)

Same 113 v4_ext notes. New prefixes so 10.30 files stay: `data/leo_runs/v4ext_rules_fix.*` (CPU job **173227**, interactive, 113/113, 84 s) and `data/leo_runs/v4ext_llm_fix.*` (GPU job **173225**, interactive L40S 24G, running). CPU tables: `eval/results/v4ext_fix.tables.md` (rules-only until GPU finishes). D17 default unchanged.

**CPU (LPD).** Four notes had `LPDs` in IED cells under 10.30 (`P005006_V03`, `P005008_V03`, `P005020_V03`, `P005030_V03`). After sentence-level negation: **zero**. IED-found plan score stayed 18 / 0 / 9 (the two notes that lost `ied_present` were false positives). Spurious `eeg_ied_reported_but_none` 4→2. IED side 11 / 1 → 12 / 0. Headline epilepsy type / seizure type / ASMs / study type unchanged. CPU rescue never listed `ltm`.

**GPU (LTM-as-drug).** Job **173225** finished: 113/113 notes, 0 errors, wall 8004 s (~2 h 13 min). Tables: `eval/results/v4ext_fix.tables.md` (now includes the model columns). `P005020_V04` rescue is `diazepam` (accept) and `midazolam` (review, specialist-only); **no `ltm`**. GPU accept share 52.4% (10.30 was 52.5%). Both-readers accepted precision 0.969 (unchanged). Rescue accepted 21 / 2 / 1 (0.913, 0.955). EEG study type reviewer view 36 / 1 vs rules 31 / 6. IED-found accepted still 18 / 27 (D17; model-only view 27 / 27). Headline files not overwritten. D17 unchanged.

### 10.32 Paper materials (2026-10-07)

Canonical manuscript `writing/MedAI_EPI_Manuscript_LEO.md`; index `writing/PAPER_MATERIALS.md`. C2 letter-level bootstrap CIs from the shipped F-S file are now copied into §10.9 (they were already in `leo_vs_fs_gold_v05_default.md`). Error capture: `scripts/score_leo_error_capture.py` → `eval/results/leo_error_capture_fs40.*`. **C1/C3 paired P/R CIs, oracle on the same 40 letters, LEO polytherapy/onset, research extract:** `scripts/score_leo_paper_extras.py` → `eval/results/leo_paper_extras_fs40.*` (no new GPU; L1C manifests). C1 **supported** on precision (auto−llm ΔP +0.114 [0.051, 0.181]; auto−specialist +0.156 [0.106, 0.210]); auto F1 still does not beat the model. C3 **supported** on recall (reviewed−specialist ΔR +0.068 [0.034, 0.104]). Oracle F1 0.796 vs model +0.095 [0.056, 0.138]. Efficiency from stored manifests: `leo_efficiency_fs40.md` (mean 10.7 s generate() on L40S). The 160-letter oracle file remains a supplement. TRIPOD and journal plan updated. D17 unchanged. The v05_default F1 file was **not** overwritten.

### 10.33 Extra field-specialist detector (opt-in sidecar, 2026-10-07)

**Change (D18).** Default LEO is still L1C + optional X1C/P1C/F1C, EpExtra, D17 rules-shown, Arm E off. An extra literature detector may be turned on with `--ext-detector ctakes` (`MEDAI_LEO_EXT_DETECTOR=ctakes`). It is independent of `--ext-reader`. Flag off: previous fusion.

This is **not** a B-arm vs E (`docs/E_EXTERNAL_BASELINES.md` still unscored) and **not** a dump into E. It is a named sidecar on overlapping medication columns. Contract: `docs/FIELD_SPECIALIST_DETECTORS.md`. Routing: `docs/LEO_ROUTING_RULES.md` §1 extra detectors, `_verify` step 8 `sidecar_only`.

**What was implemented (no new training)**

| Id | Method | Code | Overlapping paths |
|---|---|---|---|
| S1 | Savova 2010-style dictionary NER of ASM names (RxNorm lexicon already in the repo) + Chapman 2001 NegEx in the sentence before the mention | `services/ext_detectors/ctakes_meds.py` | mention spans |
| S2 | Uzuner 2010 medication status on those spans: current / discontinued / failed; planned dropped; PRN → `rescue_medication`; one-off → `acute_administration` (same `drug_role` as LEO) | same module | `medication.current_asms`, `prior_asms`, `failed_asms`, `rescue_medication`, `acute_administration` |

Detector name on claims: `ctakes`. Fusion attach: `services/ext_detectors/attach.py` (`SidecarIndex`). Pipeline flag: `ChainPipelineConfig.ext_detectors`. CLI: `scripts/leo_cli.py --ext-detector`. Provenance: `LeoRuntime.versions()["ext_detectors"]`. Claim field: `sidecar_alternative` (`schema/claim.py`); wide column `*_sidecar`; claims.csv `sidecar_alternative`. Reason code: `sidecar_only`.

**Fusion (does not change default verdicts)**

- E/L agree and sidecar agrees → append `ctakes` to `detectors`; ACCEPT stays ACCEPT.
- Same drug, different role → `sidecar_alternative`; verdict unchanged.
- Sidecar only → REVIEW `sidecar_only`; never ACCEPT.
- Research extract remains `accepted` ∧ `specialist+llm` (`_sources` still maps to specialist/llm only).

**What was not implemented (need training or a new column)**

- S3 B1 BioClinicalBERT (`--ext-detector b1` raises). Xie frequency, Decker type, AutoHS-style HS, Adelson Engel (schema has Engel; not an extract catalogue column). Java cTAKES / CLAMP binaries. Majority vote.

**Tests (no GPU).** `tests/test_ext_detectors.py`: flag off has no `ctakes` detector; agree keeps ACCEPT; sidecar-only is REVIEW; i2b2 `d/c'd` → prior vs current; planned dropped; NegEx skips denied drugs. Existing `tests/test_chain_llm.py` / `tests/test_leo_app.py` unchanged with the flag off.

**Not scored as headline.** v4_ext with this flag (and the later shipped names) is 10.40, new prefixes, not a default-LEO delta.

### 10.34 No-train frequency / stated-type / HS sidecars (2026-10-07)

**Change (D19).** Same opt-in slot as 10.33. Three dictionary+NegEx detectors cover the Xie / Decker / HS *jobs* without fine-tuning BioClinicalBERT or loading unpublished weights. Default LEO (flag off) is unchanged. D17 unchanged. B1 still not registered.

| Flag | Code | Overlapping paths | Independence from E |
|---|---|---|---|
| `freq` | `services/ext_detectors/freq.py` | `clinical_seizure.seizure_frequency` | Current stated rate only (skip historical / hypothetical). Seizure-free vs counts. Not the ExECT JAPE port |
| `stated-type` | `services/ext_detectors/stated_type.py` | `epilepsy_type`, `predominant_seizure_type` | Explicit ILAE 2017 phrases only. No seizure→epilepsy inference. No CPS / grand mal / secondarily-generalized map |
| `hs` | `services/ext_detectors/hs.py` | `mri.hippocampal_sclerosis`, `mri.focal_cortical_dysplasia` | Mention + Chapman NegEx in MRI context. Silent (not `false`) when the note never talks about MRI |

Shared sentence window: `services/ext_detectors/span.py`. Same-path value mismatch on these scalar fields → `sidecar_alternative` (medication list items still use the D18 same-drug / different-role rule). Repeatable: `--ext-detector freq --ext-detector stated-type --ext-detector hs`.

**Not implemented.** Trained B1 / Xie / Decker / AutoHS heads. Extra Med42 call. Majority vote. Strings dumped into E.

**Tests.** Current “about 2 per month”; seizure-free beats old rate; hypothetical/historical skipped; CPS silent; GTCS does not infer epilepsy type; HS true on MTS; HS false only with MRI; sidecar-only REVIEW. Flag off: previous tests unchanged.

### 10.35 Guideline stated-only sidecars for remaining holes (2026-10-07)

**Change (D20).** Same opt-in slot. No published no-train clinic-letter F1 exists for these cells; the detectors copy **guideline phrases**, not Penn/Mayo/West Virginia University weights. Default LEO frozen. D17 frozen.

| Flag | Source | Paths | Behaviour |
|---|---|---|---|
| `fail-reason` | NINDS CDE discontinuation reason; Kwan 2010 | `failed_asms` / `prior_asms` | Efficacy or ADE → failed; wean while seizure-free → prior; silent if no reason |
| `rescue-if` | Pina-Garza 2024; Epilepsy Foundation; NINDS workshop | `rescue_medication` | Home PRN only. Instructional if-clause and inpatient PRN skipped |
| `ictal` | ACNS Hirsch 2013/2021 | `seizures_captured`, `ictal_onset_lobe` / `_laterality` | Lobe only if captured; “no ictal onset” → `seizures_captured=false` |
| `eeg-done` | ACNS + ExECT skip as sidecar | `eeg.study_type` | Emit only if performed/obtained, not recommended |
| `dre` | Kwan 2010 (our task; Xie 2022/2023 do not extract DRE) | `drug_resistance_status` | Explicit “drug-resistant / intractable / refractory epilepsy” only; no two-drug inference |
| `first-feature` | Fisher 2017 instruction manual | `focal_motor_onset`, `focal_nonmotor_onset` | Requires “begins with / onset with” in the same sentence |

**Not registered.** `engel` (Wieser/Adelson): schema has Engel/ILAE class; not a LEO phenotype. `acute_administration`: already on `ctakes` (Uzuner one-off); extra LLM prompts unchanged.

**Cannot claim.** Biswal/Westover and Frontiers 2025 EEG-report keyword F1 (wrong document type); Xie/Decker count F1 (need training); Wissel surgery *candidacy*; Zhang 2025 ChatGPT semiology; Liu DDC-reason AUC (no weights).

**Tests.** Efficacy vs wean vs silent drug; home PRN vs if-cluster instruction; no-ictal-onset → false not a lobe; recommended video-EEG silent; DRE phrase vs two-failed-ASM silent; first-feature needs onset cue; sidecar-only REVIEW. Flag off unchanged.

### 10.36 Role placements: RAG, O export codes, ConText ablation (2026-10-07)

**Change (D21).** Default extract frozen. D17 frozen. Three opt-in tools, each in its own job, none inside the phenotype filler. 70B / CoT / self-consistency not shipped.

| Flag | Job | Not a job |
|---|---|---|
| `--ask-rag` | Open-book QA on Kwan DRE, Fisher first-feature, ACNS LTM-vs-drug (`dre_kwan`, `first_feature`, `ltm_sense`) | Filling `seizure_type` from a span already in the note |
| `--export-codes` | After E/L emit a value, attach ICD-10-CM G40.x / Orphanet / SCORE / EpSO on `Claim.export_codes` | Gazetteers in E; ICD intractable as ILAE DRE; inventing LPDs from SCORE |
| `--context-engine sentence\|negex` | Ablation of negation/experiencer/historical inside E vs default medspaCy ConText | A third phenotype arm scored as “ConText F1 vs EpExtra F1” |

Quote for ask still must sit in the note (guideline echo → `offsets_unresolved`). Export codes do not change verdicts. `medspacy` is the default engine (`docs/METACAT_EVAL.md`). Corpus: `data/guidelines/ilae_ask.json`. Maps: `services/o_code_maps.py`. Ablation: `services/context_engine.py`. Tests: `tests/test_role_placements.py`. Contract: `docs/ROLE_PLACEMENTS.md`.

### 10.37 Measured-failure techniques (2026-10-07)

**Change (D22).** No new ILAE synonyms. Constrained L1C kept. H2 still not fused by default. `--quote-entail` and `--disagree-llm policy:FILE` are opt-in; D17 frozen. Span/BIO NER names raise until trained. Active learning is documented, not coded (`docs/ACTIVE_LEARNING_PLAN.md`).

E status/time (on): `was stopped` → prior; PLAN hypothetical / PMH historical on current mentions; later stop/fail of the same drug drops current; “stopped that drug” binds the last ASM. Roll-up remains latest-note, not a bag of visits.

Tests: `tests/test_measured_failures.py`. Map: `docs/MEASURED_FAILURE_TECHNIQUES.md`.

### 10.38 Visit glance column (2026-10-07)

**Change (D23).** `visit_summary` is a display column on each per-note row: under 50 words from cells already on that row, with field keywords (epilepsy, seizure, onset, frequency, ASM, EEG, HS, MRI, surgery). `[?]` marks `needs_review`. Lists are capped at three names. Fusion, ACCEPT/REVIEW, and D17 are unchanged. On `bin/leo rollup` the column is rebuilt from the latest-stated-per-field cells. Not scored.

### 10.39 Learning from validator files (2026-10-07)

**Change (D24).** `bin/leo learn FILE.reviewed.csv` (or `--archive`) runs Loop A and Loop B on Validator labels. It does not change extract. A routing JSON is written only with `--emit-policy` when a field meets the disagreement CI gate (`DISAGREEMENT_ADJUDICATION.md` §3.7). Apply that file later with `--disagree-llm policy:FILE` on a new `leo-v0.x`. `leo learn --apply` and Loop C flags are refused. Headline F-S / v4_ext files not re-run.

Tests: `tests/test_leo_learn.py`. Plan: `docs/ACTIVE_LEARNING_PLAN.md`.

### 10.40 Opt-in sidecar rematch on v4_ext (2026-10-07)

**Change (D25).** Same 113 notes / 37 patients. Driver `eval/leo_v4ext_run.py --ext-detector` (repeatable; all 10 shipped names). New prefixes so 10.30 / 10.31 files stay: `data/leo_runs/v4ext_rules_sidecar.*` (CPU, this node, 113/113, 91.3 s, 0 errors) and `data/leo_runs/v4ext_llm_sidecar.*` (GPU job **173255**, interactive L40S 24G, 113/113, 0 errors, wall 7873 s / 2 h 11 min). Score: `eval/results/v4ext_sidecar.tables.md`. Default LEO still has sidecars **off**. D17 unchanged. Do not quote as a headline delta.

**CPU, all claims (reviewer view; every cell needs_review).** Sidecar-only claims: **408**, ACCEPT **0**. `sidecar_alternative` on **145** overlapping cells. Extra claims vs `v4ext_rules_fix`: +395 (2820 → 3215). Detector hits: ctakes 531, stated-type 172, fail-reason 140, rescue-if 112, dre 110, ictal 104, eeg-done 90, freq 69, hs 68, first-feature 45.

Headline fields **did not move** vs 10.31 rules-only: epilepsy type 36/1, seizure type 30/4, onset age 37/0, EEG study type 31/6, IED-found 18/0/9, HS 11/5/0/7, DRE 37/0, surgery 11/0.

What moved (all-claims only — sidecar-only stays REVIEW, so it cannot enter a research extract):

| item | 10.31 rules-only | sidecar on |
|---|---|---|
| focal motor onset | 7 / 3 / 2 | 8 / 4 / 0 |
| rescue drug (item) | 21 / 0 / 1 | 22 / 0 / 0 |
| rescue list P / R | 0.724 / 0.955 (FP 8) | 0.579 / 1.0 (FP 16) |
| current ASMs P / R | 0.807 / 0.899 (FP 17) | 0.689 / 0.899 (FP 32) |
| scored-path claim P | 0.838 | 0.829 |

Sidecars fill some misses and add false list items into the reviewer queue. That is the contract: never auto-accept, never demote an E+L accept.

**GPU (173255).** Sidecar-only **251**, ACCEPT **0**. `sidecar_alternative` 160. Accept share 51.2% (10.31 fix was 52.4%). Both-readers accepted precision 0.968 (was 0.969). Core scalars match 10.31 GPU (epilepsy type, seizure type, onset, EEG study type 36/1, IED-found accepted 18/27, DRE 37/0). Rescue both-readers 22 / 3 / 0 (0.88, 1.0) vs fix 21 / 2 / 1 (0.913, 0.955): miss filled, one extra FP. Current ASMs both-readers 72 / 16 / 7 (0.818) vs 71 / 10 / 8 (0.877). Reviewer-view lists are noisier (ASM P 0.581). **Keep opt-in.** Headline / `_ecues` / `_fix` files not overwritten.

**Validator + `leo learn` (synthetic clicks, not training).** CPU: flagged 2233, misses 2400, accepted_audit **0**. GPU: flagged 1435, accepted_audit **140** (`eval/results/v4ext_sidecar.gpu.accepted_audit.csv`). Four pipeline-test clicks in `eval/results/v4ext_sidecar_synth.reviewed.csv` (do **not** `--archive`). `bin/leo learn` → policy `{}`, `applied=False`. `--apply` and `--lora` exit 1 as designed.

### 10.41 leo-v0.6: onset class, current-at-visit ASMs, "unknown" epilepsy type (2026-10-08)

**Change (D26).** Rules in `LEO_ROUTING_RULES.md` 3.5-3.7. No new model run is needed for (1) and (2):
the stored LLM manifests are re-fused. (3) uses stored v1 manifests (no "unknown" from the model); the
v2 prompt run is below.

**40 held-out letters (EA0161-EA0200), L1C, micro-F1.** Files: `eval/results/leo_vs_fs_gold_v06.*`;
per-step files `_v06_onset`, `_v06_meds`, `_v06_etype` (intermediate, before the bare-after-stop rule;
same numbers on these 40 letters).

| step | llm | specialist | leo_auto | leo_review |
|---|---:|---:|---:|---:|
| shipped leo-v0.5 (`_v05_default`) | 0.700 | 0.655 | 0.664 | 0.678 |
| current code + onset class | 0.700 | 0.626 | 0.641 | 0.669 |
| + current-at-visit ASMs | 0.700 | 0.689 | 0.683 | 0.694 |
| + "unknown" epilepsy type = leo-v0.6 | 0.700 | 0.763 | 0.704 | 0.773 |

The second row is lower than the shipped row because of drift, not the onset class: the D22 medication
status edits (made after the shipped run, never rescored) dropped current drugs that another sentence
called "previously tried". The class is not in the micro score. The current-at-visit rule replaces those
edits. Paired, leo-v0.6: leo_review − llm
+0.073 [+0.013, +0.135] (was −0.022 [−0.062, +0.022]); leo_auto − specialist −0.059 [−0.103, −0.019].
Per field: current ASMs specialist 0.915, leo_auto 0.909, leo_review 0.887; epilepsy type specialist and
leo_review 0.737, leo_auto 0.492 (the v1 model cannot say "unknown", so the gold's 25 "unknown" letters
cannot agree); typed-only view 0.96 for specialist and leo_review (13 letters). Onset class (18 letters
with a gold seizure type): llm 0.813, specialist 0.857, leo_auto 0.882, leo_review 0.857; the subtype
itself stays low (leo_auto 0.308). Claims: accept 0.462, review 0.513, reject 0.025.

**160 stress letters (EA0001-EA0160), micro-F1.** File `eval/results/stress_fs160_v06.*`
(leo-v0.5: specialist 0.652, leo_review 0.661-0.675).

| arm | llm | specialist | leo_auto | leo_review | onset class leo_review (n=92) |
|---|---:|---:|---:|---:|---:|
| L0 | 0.656 | 0.702 | 0.668 | 0.713 | 0.894 |
| L1 | 0.688 | 0.702 | 0.696 | 0.720 | 0.900 |
| L2 | 0.662 | 0.702 | 0.688 | 0.722 | 0.900 |
| H | 0.716 | 0.702 | 0.703 | 0.713 | 0.888 |
| H2 | 0.707 | 0.702 | 0.689 | 0.724 | 0.906 |

Specialist current ASMs 0.842 (0.819 before the bare-after-stop rule), epilepsy type 0.621. Epilepsy-type
variants on these letters: leo-v0.5 0.419; "unknown" with type inference from seizure types 0.508;
"unknown" without inference (shipped) 0.621. The typed-only view did not move (about 0.97), so the gain is
the letters that name no type.

**v4_ext (113 US-style notes).** `eval/results/v4ext_v06.tables.md` against `v4ext_fix`. Only the
rules-only column is re-run (the LEO+model columns reuse the stored v0.5 GPU claims). Rules-only current
ASMs 71 / 15 / 8 (P 0.826) vs 71 / 17 / 8 (0.807); rescue list FP 8 → 4; scored-path claim precision
0.838 → 0.843. Every core and extended item is unchanged. The first v0.6 run had two new current-ASM
false positives (P005036, P005022: a drug mentioned without a cue after it was stopped); the
bare-after-stop rule removed them.

**Synthetic (US-style, maintenance view).** `eval/results/leo_vs_synth_gold_v06_maint.*`.
L1C, 30 patients: specialist 0.971 → 0.978, leo_review 0.969 → 0.976, leo_auto 0.998 (unchanged), llm
0.993; leo_review − llm −0.024 [−0.053, −0.004] → −0.017 [−0.045, +0.000]. Accept share 0.618 → 0.688.
Onset class (26 patients): llm 1.000, specialist / leo_auto / leo_review 0.962. Same pattern for armH and
L0C. Nothing got worse on the notes EpExtra was developed on.

**Flat prompt v2 (model may say "unknown").** GPU job 179541 (`scripts/slurm_med42_flat_v2.sh`, L1C,
40 held-out letters, `data/run_manifests_fs_test_flat_c_v2`). Completed 2026-10-08 (13 min, exit 0).
Scored with
`venv-medcat/bin/python scripts/score_leo_vs_fs_gold.py --llm L1C=data/run_manifests_fs_test_flat_c:L1C --llm L1Cv2=data/run_manifests_fs_test_flat_c_v2:L1C --out eval/results/leo_vs_fs_gold_v06_v2`.

| | v1 (L1C) | v2 (L1Cv2) |
|---|---|---|
| llm micro-F1 | 0.700 | 0.714 (paired diff 0.014, CI [−0.026, +0.057]) |
| leo_auto micro-F1 | 0.704 | 0.699 |
| leo_review micro-F1 | 0.773 | 0.770 |
| leo_review − llm | +0.073 [0.013, 0.135] | +0.056 [−0.003, +0.113] |
| `epilepsy_type` llm / leo_auto | 0.333 / 0.492 | 0.427 / 0.516 |
| `epilepsy_type|typed` llm / leo_auto (13 letters) | 0.923 / 0.917 | 0.769 / 0.818 |
| `epilepsy_type|abstain` leo_auto | 0.737 | 0.684 |
| accept share | 0.462 | 0.467 |

v2 helps the model on letters with no stated type (it can now say "unknown"), but it hurts on the 13
letters that do state a type: the model says "unknown" where the letter names the type. LEO's reviewed
output is unchanged and auto-accept barely moves. **Decision: v1 stays the default.** v2 remains
available via `MEDAI_FLAT_PROMPT_VERSION=v2`.

**Caveat.** The medication and epilepsy-type rules were written while reading errors on the 40
held-out letters, so those 40 are no longer a clean test of them. The 160 stress letters and v4_ext are
the check. The onset-class gold is a mapping of the F-S seizure-type keyword gold, not an annotation.

Tests: `tests/test_seizure_class.py`, `tests/test_medication_current.py`,
`tests/test_unknown_epilepsy_type.py`; `tests/test_leo_app.py` reads the v06 evidence files.

### 10.42 EEG electrode names as locations (2026-10-08)

**Change (D27).** `rules/eeg_electrodes.py`, used by `rules/fields/eeg.py` (interictal discharges) and
`rules/fields/eeg_extra.py` (ictal onset lobe and side). Location words still win; electrodes only fill
an empty lobe or side. Source: PEEP (Cui et al., J Biomed Inform 2014), which read electrode names
through EpSO.

**v4_ext rules-only rerun.** `data/leo_runs/v4ext_rules_v06e.*`, scored in `eval/results/v4ext_v06e.*`.
The first version added 6 claims, all scored wrong: generalized spike-and-wave "with bifrontal
predominance at Fp1/Fp2 and F3/F4" got lobe frontal. For a generalized discharge the electrodes give its
predominance, not a focus, so electrodes no longer add a lobe when the side is diffuse/generalized. After
that the claims file and every table are identical to `v4ext_rules_v06` / `v4ext_v06`. In these 113 notes
every finding near an electrode name also has a lobe or side word, so the rule has nothing to fill. It is
kept for EEG reports that give the location only as electrodes ("sharp waves maximal at T8"); no scored
set measures that yet. The F-S letters have no gold for EEG location.

### 10.43 leo-v0.7: seizure freedom and date of last seizure (2026-10-08)

**Gold.** From the F-S `SeizureFrequency` entities (non-negated). A letter is seizure free when every entity
has `NumberOfSeizures` 0, and not seizure free when any has a positive or present-but-uncounted frequency
(`scripts/score_leo_vs_fs_gold.fs_seizure_free_gold`): 29 of 40 held-out letters have a value (11 yes, 18 no).
Last-seizure dates are the `YearDate`(-`MonthDate`) of "0 seizures since <date>" entities, one per seizure type;
a predicted date is right if it matches any of them at the gold's precision. 18 of 200 letters have one (4
held out).

**40 held-out letters, L1C** (`eval/results/leo_vs_fs_gold_v07.*`). The headline micro-F1 and every per-field
number are identical to v0.6 (llm 0.700, specialist 0.763, auto 0.704, review 0.773; review − llm +0.073
[0.013, 0.135]). Claim precision by category is unchanged (the new fields are not in it). The new claims add 40
claims over 40 letters: 17 agree, 1 disagree, 16 model-only, 6 rules-only; accept share 0.462 → 0.438.

| view (extra, not in micro) | n | llm | specialist | leo_auto | leo_review |
|---|---:|---:|---:|---:|---:|
| `seizure_free` | 29 | 0.852 | 0.667 | 0.343 | 0.830 |
| `date_of_last_seizure` | 4 | — (not read) | 0.750 | 0.000 (always review) | 0.750 |

The model reads seizure freedom better than the rules. Auto-accept is low because the rules often give no
frequency, so the model's value is model-only and goes to review.

**Date rule, rules only, 200 letters** (`scripts/score_last_seizure_fs.py`, `eval/results/leo_last_seizure_fs200.*`):
development 14 of 14 right; held-out 3 of 4. The held-out miss is a misspelt month ("Novemebr 2015" read as 2015
only); left unfixed because it was seen on a held-out letter. The rule also gave dates in 4 letters with no gold
date (for example "last episode was on 31st August 2018"); the gold marks dates only on zero-seizure entities, so
these are not counted.

**Synthetic (maintenance view).** `eval/results/leo_vs_synth_gold_v07_maint.*`: micro-F1 identical to v0.6 for
armH, L0C and L1C. The synthetic gold has no seizure-free or last-seizure column, so the new fields are not
scored there.

**Not done.** The model is not asked for the date, and the visit date is not in the prompt (Ojemann et al. found
"dates in context" the best prompt). That needs a prompt v3 and a GPU run; durations ("seizure free for 7
months") would then become dates relative to the visit.

### 10.44 Medication context in CMED terms; CASI external test pending (2026-10-09)

`rules/med_context.cmed_context(text, start, end)` re-expresses EpExtra's clause-level medication cues in the
five CMED dimensions (Mahajan et al., J Biomed Inform 2023) plus disposition. It reads, it does not decide:
EpExtra's current / prior lists are unchanged, so no score in 10.43 moves.

| EpExtra mention class | CMED action | CMED temporality |
|---|---|---|
| stop | Stop | Past |
| planned | Start | Future |
| past | (none) | Past |
| current, with an increase / reduce / switch / one-off cue | Increase / Decrease / OtherChange / UniqueDose | Present (Future if "will", "plan") |
| current or bare, no change cue | (none; NoDisposition) | Present |

Negation ("declined", "not started", "never took"), certainty (Conditional for "if / unless / should seizures";
Hypothetical for "consider / may / option / discuss") and actor (Patient for "she stopped", "ran out",
"self-discontinued"; Physician for "I recommend", "we will", "please") are separate cue lists.

**External test.** `scripts/score_casi_medication_status.py` scores `casi_status` on the CASI medication-status
test set (Agrawal et al., EMNLP 2022; 100 snippets; active / discontinued / neither; macro F1 as in the paper).
The gold drug names are given, because most CASI drugs are not ASMs and EpExtra's linker is epilepsy-only; a
name not found verbatim counts as wrong. **Not run**: the dataset is gated (`mitclinicalml/clinical-ie`;
accept the terms, then `huggingface-cli login` or `HF_TOKEN`), and no token is configured here. Once the CSV
is in `data/external/casi_medication_status/`, run the script; no rule may be changed after seeing it.

### 10.45 leo-v0.8: PNES flag (2026-10-09)

**Development letters (EA0001-EA0160).** 16 letters mention PNES. The flag matches a manual reading of all 16:
3 PNES only (EA0076 "more likely to be dissociative seizures" after "I do not think that these are epileptic
seizures", probable; EA0102; EA0120), 12 dual diagnosis (epilepsy, or a named epileptic seizure type such as
"complex partial seizures" in the diagnosis list, EA0038), 1 possible (EA0129 "keep in mind the possibility").
Three fixes during development, all from development letters: letterheads ("The epilepsy service") are not a
diagnosis; "does not need epilim for epilepsy as she has non epileptic seizures" is not an epilepsy statement;
named epileptic seizure types count as epilepsy.

**Held-out letters (EA0161-EA0200).** EA0174 ("I wonder if these could be non epileptic rather than epileptic
seizures") is flagged possible; EA0198 ("Probable non-epileptic psychogenic seizures" with complex partial
seizures) is flagged dual diagnosis, probable. Both read during exploration, so not blind.

**Effect on the F-S score** (`eval/results/leo_vs_fs_gold_v08.*`, arm L1C): micro-F1 identical to v0.7
(llm 0.700, specialist 0.763, leo_auto 0.704, leo_review 0.773; leo_review - llm +0.073 [0.013, 0.135]).
One new claim (the EA0198 flag, REVIEW); EA0198's frequency cells were already in review, so no accepted claim
moved (accept share 0.438 -> 0.436 from the larger denominator). The flag is a safety rule for real clinic
letters; this corpus has no PNES gold and cannot measure its benefit.

### 10.46 IED attributes and EEG-report sections (2026-10-09)

`rules/eeg_attributes.py` fills optional `IedFinding` fields from a ±80 character window: frequency band
(delta / theta / alpha / beta / gamma, from a band word or from Hz), recurrence (rare … continuous),
dispersal (focal / regional / multifocal / hemispheric / generalized). Dispersal is not inferred from lobe
alone. `rules/eeg_sections.py` treats a note as an EEG report only when it has `DESCRIPTION OF THE RECORD`,
or both `INTRODUCTION` and `IMPRESSION` as labeled headers. On those reports, IED, background, ictal onset
and seizures-captured findings are taken from description / impression / findings / clinical correlation,
not from history, medications or the introduction. A clinic letter with a lone `Impression:` is not an EEG
report, so F-S and synthetic letters are unchanged.

**External test.** `scripts/score_tuh_eeg_attributes.py` scores a JSONL conversion of the TUH / SACAR
annotations (Maldonado and Harabagiu, LREC 2020). **Not run**: Temple registration and a data-use agreement
are required; do not change the rules after seeing that file.

### 10.47 Author-type stratification and silent prospective plan (2026-10-09)

`services.note_author.note_author` reads the signature block (from `Yours`, or short trailing lines that are
not a plan). Body mentions ("I will ask the epilepsy nurse") do not set the author.

**F-S letters** (`scripts/classify_fs_authors.py`, `eval/results/fs_author_types.*`): 159 of 160 development
letters and all 40 held-out letters are unsigned. One development letter signs as a consultant neurologist.
LEO cannot report Ojemann-style epileptologist vs general-neurologist F1 on this corpus. When a US clinic
corpus with signed notes is available, add the author label as a stratum to `score_leo_vs_fs_gold.py` and
report micro-F1 by stratum before changing any rule.

**Silent prospective plan** (Wissel et al., Epilepsia 2019; not started). Pre-register the fields (core
panel plus seizure free), the accept/review split, and the analysis (letter-clustered PPV and NPV with 95%
CIs). Run LEO on upcoming clinic letters without showing the output in the record. A clinician reviews every
auto-accepted cell in a 10% audit and every review cell that would have entered a research extract. Do not
change care. Stop after a fixed calendar window or N letters, whichever comes first. Expect the
retrospective F1 to fall (Wissel: AUC 0.90 → 0.79). Record the drop as a dated deviation; do not retune on
the prospective notes.

### 10.48 Weak labels from EpExtra (2026-10-09)

`rules/weak_labels.py` wraps four existing rules as labeling functions (epilepsy type, seizure free, PNES
status, IED present). `scripts/emit_weak_labels.py` writes JSONL for a Trove label model (Fries et al. 2021).
No model is trained. Add further fields only after their rules are frozen. This is the deferred Loop C in
`docs/ACTIVE_LEARNING_PLAN.md`, not a live third reader.

### 10.49 Quote-entail rematch and research-extract misses (2026-10-09)

`scripts/score_leo_quote_entail_fs.py` on stored L1C (`data/run_manifests_fs_test_flat_c`), current
pipeline, 40 held-out letters. No GPU. Headline v05/v08 files not overwritten. Default
`quote_entail` stays **off** (D22).

| setting | auto P | auto R | auto F1 | reviewed F1 | research extract |
|---|---:|---:|---:|---:|---|
| default (off) | 0.870 | 0.592 | 0.704 | 0.773 | 74/84 = 0.881 |
| `--quote-entail` | 0.910 | 0.483 | 0.631 | 0.773 | 62/69 = 0.899 |

28 claims demoted `quote_not_entailed`; **16 were gold-correct**. Of 10 default research-extract
misses, 3 fail the lexical entail check; 2 of those 3 are “Juvenile Myoclonic Epilepsy” (lexicon
wants `JME`) and “symptomatic epilepsy” — not Windisch unsupported quotes. 8 of 10 misses are
typed epilepsy vs gold `unknown` (diagnosis-line convention). List:
`eval/results/leo_research_extract_misses_fs40.md`. Frozen paper extras remain 71/82 = 0.866
(`leo_paper_extras_fs40.md`, earlier pipeline). Do not retune the entail lexicon on these letters.
Do not flip the default: precision rose by dumping recall and correct cells.

### 10.50 leo-v0.9 leak list, ASM status, unknown-silent, noisy reviewer (2026-10-10)

CPU only. Headline extras / v05 files not overwritten. D17 and `--quote-entail` default unchanged. Loop A/B not applied. Do not train `unknown`.

- **Leak list.** `scripts/score_leo_error_capture.py` on stored L1C. Pre-v0.9: **19/49** (`leo_error_capture_fs40_pre_v09.md`). v0.9 rematch: **20/49** accepted anyway (0.41); 29/49 captured; 15/43 flags already right. Table: `leo_error_capture_fs40.md`. How to read the 20 rows: `writing/supplement_leo_accept_errors.md`. Eight epilepsy-type rows are still typed vs gold `unknown`. ASM accepted-anyway 6→7. **Do not write E/fusion from the hold-out table.** Leak did not fall; that is expected (development-letter rules, F-S rescue-as-current, gold multiplicity). Manuscript §3.4 updated.
- **Current ASMs.** Cluster-if / “not prescribed yet” / “can also use” / “may be considered” are planned (EA0001–160). A rescue the patient already takes stays current. Sidecars stay opt-in. Tests: `tests/test_medication_current.py`.
- **Unknown + silent.** Default REVIEW `unknown_silent`. Switch `unknown_silent_review`. Not chosen on EA0161–200. Epilepsy-type flags 15→19 (more gold-`unknown` now reviewable). Tests: `tests/test_chain_llm.py`.
- **Noisy reviewer.** `scripts/score_leo_noisy_review.py` → `eval/results/leo_noisy_review_fs40.*`. Same 40 letters, seed 0:

| p(error) | P | R | F1 |
|---:|---:|---:|---:|
| 0.00 | 0.896 | 0.823 | 0.858 |
| 0.10 | 0.894 | 0.803 | 0.846 |
| 0.25 | 0.868 | 0.803 | 0.834 |
| 0.50 | 0.788 | 0.707 | 0.746 |
| 1.00 | 0.634 | 0.578 | 0.605 |

*p* = 0 is not a replacement for frozen extras oracle **0.796**. The rise is mostly `unknown_silent` putting gold-`unknown` into the review set. Not minutes.

**Not done:** D17 flip; `--quote-entail` default; entail lexicon on hold-out; train `unknown`; Loop A/B apply; real notes; agent. Headline F1 unchanged.

### 10.51 Research-extract strata and quote-entail letter-bootstrap (2026-10-13)

CPU only. Stored L1C. `scripts/score_leo_extract_strata_fs.py`. Frozen extras / `leo_quote_entail_fs40` not overwritten.

Convention rule (fixed): `epilepsy_type` and gold `unknown` and pred `focal`/`generalized`. Current-chain extract **74/84 = 0.881** [0.805, 0.946]; convention **0/8**; residual **74/76 = 0.974** [0.933, 1.000]. Residual misses: EA0186 FBTCS vs FUA; EA0188 day vs month (both entail). Tables: `leo_extract_strata_fs40.md`.

Quote-entail bootstrap (same 40; exploratory): Δ auto-P +0.044 [−0.008, 0.106] includes 0; Δ auto-R −0.081 [−0.124, −0.040]; residual Δ extract-PPV −0.005 [−0.017, 0.000]; 12 gold-correct demoted. **Default stays off.** `leo_quote_entail_bootstrap_fs40.md`.

**Not done:** D17 flip; `--quote-entail` default; train `unknown`; recode gold; Loop A/B apply. Headline 71/82 untouched.
