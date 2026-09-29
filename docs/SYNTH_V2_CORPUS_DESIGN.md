# synth-v2 Corpus Design

**Status:** pipeline ready; 20-doc pilot validated; user can scale to 500.

## Goal

Diversify the synthetic training/eval corpus with US-style clinical prose (SOAP, discharge, ED, EMU, outpatient, progress) covering 8 phenotype profiles across 4 care settings. Fills the cross-domain gap MTSamples exposed (F-S/synth-v1 vocabulary alone yields F1=0.17→0.40 on US real notes).

## Non-goals

- Not replacing synth-v1 — additive.
- Not retraining LoRA in this pass — synth-v2 is inputs for a future LoRA v4.
- Not human-annotated — auto-annotated via semantic-plan-to-Evidence converter (same approach as synth-v1).

## Diversification axes

### Patient IDs
- **New range: P002000-P002299** (300 patients)
- **Disjoint from:** synth-v1 (P000500-P000999), F-S (EA0001-EA0200), synth-v1 held-out (Phase 6c)

### Phenotype profiles (weighted)
| Profile | Weight | Rationale |
|---|---:|---|
| Drug-resistant | 25% | Highest clinical utility; teaches AED-failure sequence |
| Presurgical evaluation | 25% | Rich semiology + EEG + MRI + surgery module coverage |
| Newly diagnosed | 15% | Single seizure, incomplete workup |
| Seizure-free on tx | 10% | Trains recognition of remission |
| Autoimmune epilepsy | 10% | Rare but paper-relevant (Graus 2016 criteria) |
| Developmental syndrome | 8% | Infantile — SCN1A, KCNQ2 |
| Status epilepticus history | 5% | Compound rule stress-test |
| EMU admission | 2% | Video-EEG semiology |

### Care settings
- Academic medical center (40%)
- Community neurology practice (30%)
- VA hospital (15%)
- Tertiary EMU (15%)

### Note types (500 total docs from 300 patients — some patients get 2 docs)
| Note type | N | Length target |
|---|---:|---|
| Outpatient neuro follow-up | 100 | ~800 words |
| SOAP clinic letter | 100 | ~1000 words |
| Discharge summary | 100 | ~1500 words |
| ED note | 100 | ~400 words |
| Progress note (inpatient) | 50 | ~300 words |
| EMU/vEEG report | 50 | ~1200 words |

### Generator models (held-out constraint)
- **250 docs via gpt-5.6-sol** (consistent with synth-v1 baseline)
- **250 docs via gpt-5.6-luna** (linguistic diversity)
- **NOT gpt-5.6-terra** — held-out for evaluation per project memory

## Output structure

```
data/episynth_corpus/v2/
├── documents/{PID}/{note_type}/output.txt
├── targets/{PID}.json                    # patient-level target phenotype
├── gold_v0_2_1/{PID}_{note_type}.json    # per-doc gold in v0.2.1 shape
├── patients/{PID}.json                   # semantic plans
├── manifest.csv                          # id, patient_id, note_type, care_setting,
│                                         # phenotype_profile, generator_model, tokens_used
├── run_metadata.json                     # models, timestamps, total cost
└── README.md
```

## Held-out split
- 100 docs from 50 patients (P002250-P002299) → `data/eval_corpora/synth_v2_eval_100/`
- Remaining 400 docs from 250 patients → available for LoRA v4 training pool

## LoRA v4 readiness
Combined training pool = 898 (synth-v1) + 400 (synth-v2) = 1,298 docs from 749 patients + 160 F-S train.

## CUI/SCTID enrichment (new vs synth-v1)
Gold labels retrofit CUI+SCTID from `rules/epilepsy_ontology.py` alongside enum values. Enables future concept-linker training on synth data.

## Execution

**Pilot (20 docs, validates end-to-end, ~3 min, ~$0.50):**
```bash
set -a && . ./.env && set +a
venv/bin/python scripts/synth_patient_sampler.py --n 20 --seed 0 --start-index 2000 \
    --out-dir data/episynth_corpus/v2/patients
venv/bin/python scripts/generate_synth_corpus.py \
    --plans-dir data/episynth_corpus/v2/patients \
    --out-root data/episynth_corpus/v2 \
    --model gpt-5.6-sol --doc-types progress_note,second
venv/bin/python scripts/convert_synth_corpus_targets.py \
    --corpus-dir data/episynth_corpus/v2
```

**Full 500 (scale to production, ~3-4 hours, ~$30-50):**
Same commands with `--n 300` (yields ~600 docs). Split into two runs: `--model gpt-5.6-sol` for patients P002000-P002149, then `--model gpt-5.6-luna` for P002150-P002299.

## Manuscript integration
- Table 2 (cross-corpus) gets synth-v2 F1 row alongside F-S/synth-v1/MTSamples
- Provenance table gets synth-v2 generator + gold-approach documentation

## Traceability
Every doc's `manifest.csv` row records: patient_id, note_type, care_setting, phenotype_profile, generator_model, tokens_input, tokens_output, cost_usd. `run_metadata.json` at the corpus root aggregates.
