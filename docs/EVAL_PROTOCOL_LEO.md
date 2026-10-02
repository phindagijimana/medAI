# LEO evaluation protocol (frozen 2026-10-01)

How to read the results (what the headline numbers measure, what they say about the data, what they do not cover): `INTERPRETING_RESULTS.md`.

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

Paired difference, leo_review minus llm: +0.005 [-0.029, +0.045] with the policy, -0.022 [-0.062, +0.022] shipped. Seizure-type F1 of leo_review: 0.571 with the policy, 0.343 shipped (llm alone 0.563). Claim precision by agreement, shipped: agree 0.835 (85 scored), disagree 0.312 (16), llm_only 0.455 (22), specialist_only 0.250 (20).

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
