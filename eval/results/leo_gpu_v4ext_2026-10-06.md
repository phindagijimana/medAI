# LEO with Med42-8B (GPU) vs rules-only, synthetic v4_ext set, 2026-10-06

Synthetic LLM-written notes only (`data/eval_corpora/synth_v4_ext`; MIMIC/restricted not touched). Reference = the generation plan
(`data/episynth_corpus/v4_ext/patients/*.json`). Measurement only; no repo code or docs were edited.

## Set and exposure
- **113 notes, 37 patients** (plans P005037-P005039 have no notes). One row per note (`data/leo_runs/v4ext_notes.csv`: patient_id, note_id, visit_date, text).
- **Not held out for the rules**: v4_ext was read while building the scorer and 13 patients were used to write the EEG rule fixes (EVAL_PROTOCOL 10.17, 10.20). The rules-only numbers are therefore optimistic. The model was not tuned on it.
- Other sets with gold (counts from `data/eval_corpora/*/manifest.csv`): synth_v3 493 notes / 100 patients and synth_v3_polish 492 / 100 (the 30-patient evaluation subset, 143 notes, was used to develop the v0.4/v0.5 rules; the other 80 patients, 399 notes, "ext" are unused), synth_v1_eval_100 102 notes / 51 patients (held-out for EpExtra), v2 300 plans with no note folder in `eval_corpora`. **No second set was run**: the only one near the 100-note limit (v1, 102 notes) is scored by `score_b0_on_synth_v1.py` / `score_leo_vs_synth_gold.py` from evaluation-harness run manifests, not from `leo batch` output, so it would need a new scorer; the others are 143-399 notes.

## How it was run
- Rules-only arm: `venv-medcat/bin/python eval/leo_v4ext_run.py --mode cpu --out data/leo_runs/v4ext_rules` (local CPU, 145 s).
- LEO + model arm: `sbatch data/leo_runs/run_gpu.sbatch` (Slurm job **169142**, partition `interactive`, `--gres=gpu:l40s.24g:1`, 8 CPUs, 64 GB; same script `leo batch` writes) which runs `eval/leo_v4ext_run.py --mode gpu --out data/leo_runs/v4ext_llm`. Node smdodwork05, NVIDIA L40S-24Q (24576 MiB). Started within seconds of submission.
- `eval/leo_v4ext_run.py` is a thin driver around the same code as `bin/leo batch --local` (`LeoRuntime.load(mode, arm="L1C")` -> `services.leo_batch.run_table` -> `write_outputs`; phenotypes = the `all` panel, no `--disagree-llm` override, i.e. shipped defaults, chunk 8000 chars, doc date = visit_date). I used it instead of `bin/leo batch` only because `leo batch` flattens structured claim values to text (e.g. the IED localization/laterality object), which the scorer needs; it additionally saves the raw claims, per-note seconds and samples `nvidia-smi` every 5 s. The usual output files (`v4ext_{rules,llm}.csv`, `.claims.csv`, `.provenance.json`) are written alongside.
- Scoring: `venv-medcat/bin/python eval/score_leo_v4ext_arms.py --out data/leo_runs/score_v4ext`. `scripts/score_extended_phenotypes.py` cannot take LLM-on output (it runs the specialist itself on each patient's joined notes), so this standalone scorer imports its stem tables and `has` / `canon` / `prf` helpers and re-implements its per-item rules (including the "key words in text" tests and the IED lobe/side conditions) on LEO's **per-note** claims. Added core items (epilepsy type, seizure type, onset age, current ASMs) are compared to EP_TYPE / SZ_TYPE / AGE_AT_ONSET_YEARS / CURRENT_ASMS of the plan (plan "absence_typical"/"myoclonic" mapped to LEO's "generalized_absence_typical"/"generalized_myoclonic"; "unknown_onset_*" seizure types skipped; onset age within 0.5 y).
- Per-patient aggregation (same for all arms): rejected claims dropped; scalar items = most frequent label across the patient's notes (ties: earlier note, accepted first); IED found = any note; lists = union. Rules-only: every claim is needs_review (LEO's `no_second_reader` rule, `single_reader`). **Because of per-note reading and voting, these rules-only numbers are not identical to `eval/results/leo_extended_phenotypes.md` (joined-text): e.g. EEG study type 31/37 here vs 24/37 there, rescue fp 8 vs 6, IED lobe 12/12 vs 8/8 answered.** Compare arms within this file, not to the older file. Sanity checks that do match the old file: background 37/37, IED found 17/27, ictal lobe/side 5/5 (old 4/5 answered 4), surgery 11 tp / 1 fp / 0 fn.
- Outcome per plan item: correct / wrong (answered, differs) / missing (not answered but the plan item's key words are in the notes) / not_reported (not answered and notes never state it; 0 everywhere because the generator wrote every item). Views of LEO+model: all claims (what a reviewer sees), accepted only (`leo_auto`), accepted and produced by both readers, and the model's own claims (any claim whose detectors include the LLM).

## Speed, GPU, errors
| | rules-only | LEO + Med42-8B |
|---|---|---|
| notes / errors (`rows_error`) | 113 / 0 | 113 / 0 (113 with LLM used) |
| mean s per note (min-max, median) | 1.28 (0.30-11.18, 1.22; first note 10.5 s = warm-up) | **11.62 (7.80-31.18, median 10.38, p90 15.06)** |
| wall for 113 notes | 145 s | 1313 s (21.9 min) + 140 s model load |
| GPU memory peak | - | **16 711 MiB** (`nvidia-smi` samples, 289 over the run; torch max allocated 15 910 MiB, reserved 16 182 MiB) of 24 576 MiB |

The earlier estimate of 16-18 s/note was pessimistic here: 11.6 s mean. The slowest notes (20-31 s) are the longest ones (8.1-9.8k chars, split into 2 chunks, plus the first note); time vs length r = 0.50. **Note-level errors: none** in either arm (all 113 `leo_status` = ok; `.err` log holds only the checkpoint-loading progress bar and the `torch_dtype` deprecation line).

## Results (37 patients, 113 notes)
Per item: correct / wrong / missing / not_reported (n = plan items). Plan items scored as in scripts/score_extended_phenotypes.py; core items added.

| item | n | rules-only (all claims, all needs_review) | LEO+model, all claims (reviewer view) | LEO+model, accepted claims only | LEO+model, accepted AND both readers | model's own claims only |
|---|---|---|---|---|---|---|
| epilepsy type (core) | 37 | 36 / 1 / 0 / 0 | 36 / 1 / 0 / 0 | 35 / 1 / 1 / 0 | 34 / 0 / 3 / 0 | 34 / 2 / 1 / 0 |
| seizure type (core) | 34 | 30 / 4 / 0 / 0 | 30 / 4 / 0 / 0 | 31 / 0 / 3 / 0 | 31 / 0 / 3 / 0 | 31 / 0 / 3 / 0 |
| age at onset (core) | 37 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 |
| EEG study type | 37 | 31 / 6 / 0 / 0 | 31 / 6 / 0 / 0 | 31 / 6 / 0 / 0 | 0 / 0 / 37 / 0 | 0 / 0 / 37 / 0 |
| EEG background | 37 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 37 / 0 / 0 / 0 | 0 / 0 / 37 / 0 | 0 / 0 / 37 / 0 |
| interictal discharges found | 27 | 17 / 0 / 10 / 0 | 17 / 0 / 10 / 0 | 17 / 0 / 10 / 0 | 0 / 0 / 27 / 0 | 0 / 0 / 27 / 0 |
| IED lobe | 12 | 12 / 0 / 0 / 0 | 12 / 0 / 0 / 0 | 12 / 0 / 0 / 0 | - | - |
| IED side | 12 | 11 / 1 / 0 / 0 | 11 / 1 / 0 / 0 | 11 / 1 / 0 / 0 | - | - |
| ictal onset lobe | 5 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 | 0 / 0 / 5 / 0 | 0 / 0 / 5 / 0 | 0 / 0 / 5 / 0 |
| ictal onset side | 5 | 5 / 0 / 0 / 0 | 5 / 0 / 0 / 0 | 0 / 0 / 5 / 0 | 0 / 0 / 5 / 0 | 0 / 0 / 5 / 0 |
| focal motor onset | 12 | 7 / 5 / 0 / 0 | 7 / 5 / 0 / 0 | 2 / 1 / 9 / 0 | 0 / 0 / 12 / 0 | 0 / 0 / 12 / 0 |
| focal non-motor onset | 15 | 8 / 7 / 0 / 0 | 8 / 7 / 0 / 0 | 1 / 6 / 8 / 0 | 0 / 0 / 15 / 0 | 0 / 0 / 15 / 0 |
| semiology: motor feature (lenient) | 34 | 26 / 0 / 8 / 0 | 26 / 0 / 8 / 0 | 0 / 0 / 34 / 0 | 0 / 0 / 34 / 0 | 0 / 0 / 34 / 0 |
| semiology: aura (lenient) | 13 | 7 / 0 / 6 / 0 | 7 / 0 / 6 / 0 | 0 / 0 / 13 / 0 | 0 / 0 / 13 / 0 | 0 / 0 / 13 / 0 |
| rescue drug | 22 | 21 / 0 / 1 / 0 | 21 / 0 / 1 / 0 | 3 / 0 / 19 / 0 | 3 / 0 / 19 / 0 | 3 / 0 / 19 / 0 |
| surgery procedure | 11 | 11 / 0 / 0 / 0 | 11 / 0 / 0 / 0 | 0 / 0 / 11 / 0 | 0 / 0 / 11 / 0 | 0 / 0 / 11 / 0 |

Where the plan has no value but a value was reported (patients; ideal 0):

| item | rules-only (all claims, all needs_review) | LEO+model, all claims (reviewer view) | LEO+model, accepted claims only | LEO+model, accepted AND both readers | model's own claims only |
|---|---|---|---|---|---|
| eeg_ictal_onset_reported_but_none | 14 | 14 | 0 | 0 | 0 |
| eeg_ied_reported_but_none | 4 | 4 | 4 | 0 | 0 |
| focal_motor_in_semiology_not_onset (not an error) | 16 | 16 | 1 | 0 | 0 |
| focal_nonmotor_in_semiology_not_onset (not an error) | 4 | 4 | 0 | 0 | 0 |
| focal_nonmotor_reported_but_unsupported | 5 | 5 | 1 | 0 | 0 |

Lists, tp / fp / fn (precision, recall):

| list | rules-only (all claims, all needs_review) | LEO+model, all claims (reviewer view) | LEO+model, accepted claims only | LEO+model, accepted AND both readers | model's own claims only |
|---|---|---|---|---|---|
| rescue drugs | 21 / 8 / 1 (0.724, 0.955) | 21 / 9 / 1 (0.7, 0.955) | 3 / 2 / 19 (0.6, 0.136) | 3 / 2 / 19 (0.6, 0.136) | 3 / 3 / 19 (0.5, 0.136) |
| surgery procedures | 11 / 1 / 0 (0.917, 1.0) | 11 / 1 / 0 (0.917, 1.0) | 0 / 0 / 11 (None, 0.0) | 0 / 0 / 11 (None, 0.0) | 0 / 0 / 11 (None, 0.0) |
| current ASMs (patient-level union) | 71 / 17 / 8 (0.807, 0.899) | 71 / 21 / 8 (0.772, 0.899) | 71 / 9 / 8 (0.887, 0.899) | 71 / 9 / 8 (0.887, 0.899) | 71 / 13 / 8 (0.845, 0.899) |

Claim level (scored field paths only; each claim judged against the plan of its patient):

| arm | verdict / source | correct | wrong | not scorable | precision | distinct (patient, field, value) precision |
|---|---|---|---|---|---|---|
| rules_only | review | 892 | 207 | 67 | 0.812 | 0.724 (373/515) |
| rules_only | review / specialist_only | 892 | 207 | 67 | 0.812 | 0.724 (373/515) |
| leo_llm | accept | 738 | 98 | 2 | 0.883 | 0.822 (315/383) |
| leo_llm | accept / both | 470 | 28 | 0 | 0.944 | 0.932 (177/190) |
| leo_llm | accept / specialist_only | 268 | 70 | 2 | 0.793 | 0.722 (143/198) |
| leo_llm | reject | 1 | 2 | 0 | 0.333 | 0.333 (1/3) |
| leo_llm | reject / model_only | 1 | 2 | 0 | 0.333 | 0.333 (1/3) |
| leo_llm | review | 180 | 116 | 69 | 0.608 | 0.52 (89/171) |
| leo_llm | review / both | 1 | 1 | 0 | 0.5 | 0.5 (1/2) |
| leo_llm | review / model_only | 26 | 7 | 4 | 0.788 | 0.778 (21/27) |
| leo_llm | review / specialist_only | 153 | 108 | 65 | 0.586 | 0.472 (67/142) |

Verdict shares (all claims, all field paths; reject = dropped):

- rules_only: reject 75, review 2800; of 2800 shown claims: review 100.0%
  - on the scored field paths: review 1166; review 100.0%
- leo_llm: accept 1743, reject 78, review 1124; of 2867 shown claims: accept 60.8%, review 39.2%
  - on the scored field paths: accept 838, reject 3, review 365; accept 69.7%, review 30.3%

## Reading the numbers
1. **On the extended fields the model changes nothing about what is found.** The model (flat contract L1C) only reads the core fields (epilepsy type, seizure type, onset age, frequency, ASMs, rescue). For EEG, semiology, focal onset and surgery there is no model claim at all (`model's own claims` column: all missing), so the "all claims" view of LEO+model is identical to rules-only on every extended item (31/37 study type, 17/27 IED, 7/12 and 8/15 focal onset, 26/34 motor features, 11/11 surgery ...).
2. **What LEO does change is the verdict, and for these fields it is not a cross-check.** Of 1,743 accepted claims in the LEO arm, claims produced by both readers (`accept / both`): 470 claims, 28 wrong, precision 0.944 (distinct patient-field-value 177/190 = 0.932). Accepted claims that **only the specialist produced** (`accept / specialist_only`, reason `accept_unanimous` with a single reader): 338 scored claims, 70 wrong, precision **0.793** (0.722 distinct). These are EEG study type (95 right / 17 wrong accepted), EEG IED findings (36/24), focal non-motor onset (**2 right / 19 wrong accepted**), focal motor onset (3 right / 3 wrong), epilepsy type/seizure type where the model said nothing. So an "accepted" EEG study type is wrong 6 of 37 patients (same as rules-only), and the 4 patients with IEDs reported although the plan has none stay in the accepted view. All-claims precision: rules-only 0.812 (distinct 0.724); LEO accepted 0.883 (0.822); LEO needs_review 0.608 (0.520).
3. **Share of claims**: LEO arm accepted 60.8% / needs_review 39.2% of 2,867 shown claims (69.7% / 30.3% on the scored field paths, 838 / 365); rules-only 0% / 100% by design. Accepted-claim precision per arm: rules-only n/a (none accepted); LEO 0.883 claim-level, 0.822 over distinct (patient, field, value). Accepted-and-both-read: 0.944 / 0.932, but that covers only the core fields (+ 6 rescue claims); the model-confirmed core current-ASM claims carry 25 wrong of 233 because a patient's plan is one regimen while notes span visits (visit-time mismatch, also seen in EVAL_PROTOCOL 10.5), so the real precision of these is higher than shown.
4. **Core fields (the only place the model acts).** Accepted-only seizure type: 31 right / 0 wrong / 3 missing versus all-claims (= rules) 30 / 4 / 0, i.e. LEO's acceptance rule removes the 4 wrong seizure types at the cost of 3 abstentions. Epilepsy type: rules 36/1/0; accepted 35/1/1; model alone 34/2/1. Onset age: 37/37 for all views. Current ASMs (patient union): rules tp/fp/fn 71/17/8; LEO all claims 71/21/8; accepted 71/9/8 (precision 0.887 vs 0.807).
5. **Where the model made things worse than rules.** (a) Reviewer view: +4 false-positive current ASMs (21 vs 17) and +1 rescue false positive (9 vs 8) from model-only claims that go to review (model's own claims: 13 fp ASMs); no recall gain. (b) The model's epilepsy type is wrong for 2 patients where rules are wrong for 1. (c) In the accepted-only view (`leo_auto`) recall on extended fields collapses because specialist-only claims there are needs_review: rescue drugs 3/22 (rules 21/22), surgery 0/11, ictal onset 0/5, semiology 0/47, focal motor 2/12 - that is the intended safety trade (those fields are not cross-checked), not an accuracy loss of the values, but a user who takes only accepted values would get almost none of them. (d) The IED, EEG study type and EEG background claims are accepted without any cross-check, so the "accepted" label there means "rule-detected", not "confirmed".
6. **Both arms**: EEG study type wrong 6/37, IEDs missed 10/27, focal motor onset wrong 5/12, non-motor wrong 7/15, ictal onset reported where the plan has none for 14 patients (all needs_review; 0 in the accepted view), 4 patients with IEDs reported where none (accepted), semiology motor feature missing 8/34 and aura 6/13 (lenient key-word match), rescue fp 8-9 (hypothetical / EMU-order sentences, see 10.17).

## Caveats
Synthetic, LLM-written notes that are tidier than real ones; plan = patient-level gold while notes are visits, so some "wrong" are visit-time mismatches; claim-level correctness uses the scorer's stem matching (lenient for semiology and focal onset) and counts a claim whose feature is only in the plan's semiology (not onset) as not scorable; v4_ext is not held out for the rules (see above); one run, greedy decoding, no confidence intervals (n = 5-37 per item). The scorer is new and was not unit-tested beyond reproducing the old scorer on items that do not depend on joining (background, IED found, surgery, ictal counts).

## Files
`eval/leo_v4ext_run.py`, `eval/score_leo_v4ext_arms.py` (new); results `eval/results/leo_gpu_v4ext_2026-10-06.{md,json}`; run outputs in `data/leo_runs/` (`v4ext_rules.*`, `v4ext_llm.*` incl. `.rawclaims.json`, `.stats.json`, Slurm logs `gpu_leo-v4ext_169142.{out,err}`, `run_gpu.sbatch`, `score_v4ext.{json,tables.md}`). Nothing committed or pushed.
