# MetaCAT vs ConText (EpExtra / B1′), 2026-10-01

**Decision: keep medspaCy ConText [M3, M4] as the default for negation,
experiencer and temporality. Do not enable the job-159296 MetaCAT models.**
MetaCAT Presence costs 2.1 micro-F1 points on synth-v1. The other tasks make
no difference.

## Models
* **Job.** SLURM 159296 (`scripts/slurm_train_metacat.sh`,
  `scripts/train_metacat.py`). Bio_ClinicalBERT tokenizer and embeddings,
  BERT head, 5 epochs, lr 2e-5, class weights, 10% held out. Weights are in
  `checkpoints/metacat/{Presence,Experiencer,Temporality,Certainty}/`.
  Log: `logs/metacat_train_159296.out`.
* **Training data.** `data/metacat_training/silver.json`: 30,974 spans
  (`scripts/emit_metacat_silver.py`). Labels are ConText output, overridden
  where a synth-v3 plan or the F-S train silver set asserts a value.

Held-out scores from the training log (labels are silver, not gold):

| Task | Classes (held-out support) | Accuracy | Minority-class F1 |
|---|---|---|---|
| Presence | negated 451, affirmed 2,647 | 0.69 | negated 0.37 |
| Experiencer | family 27, patient 3,071 | 0.99 | family 0.00 (never predicted) |
| Temporality | current 2,595, hypothetical 84, past 419 | 0.50 | hypothetical 0.12, past 0.36 |
| Certainty | definite 3,098 (only class) | — | not trainable |

## Two problems found and fixed
1. **`services/metacat_backend.py` never applied a prediction.**
   * It called `MetaCAT.load(save_dir_path=…)` and `model.predict_one()`.
     Neither exists in MedCAT 2.9, and the exception was swallowed, so the
     backend silently did nothing.
   * It now loads models with `medcat.storage.serialisers.deserialise`. It
     builds the same token window as `MetaCAT.prepare_document`
     (`cntx_left`/`cntx_right` tokens around the entity) and calls
     `ml_utils.predict`.
2. **The saved models have no label map.**
   * MedCAT 2.9's `train_raw` computes `category_value2id` but stores it in
     the config only when one was given in advance. Ours started empty, so
     the saved models have `{}`.
   * The ids come from iterating a Python set, so they cannot be recomputed.
   * They were recovered from the per-class held-out support in the training
     log, which matches the silver label proportions (e.g. Presence class 0 =
     451 = 14.6% ≈ negated 15.4%). They are written to `label_map.json` in
     each task directory.
   * For future runs, set `config.general.category_value2id` before training.

## End-to-end evaluation
* **Command.** `scripts/run_medcat_rules_on_corpus.py --metacat
  checkpoints/metacat [--metacat-tasks …]` runs ConText first, then
  overwrites its flags with the MetaCAT labels.
* **Setup.** Same CDB (`data/medcat_cdb_epilepsy/`) and same scorer
  (`scripts/score_medcat_vs_gold.py`) as the ConText-only run.

| Run | F-S test 40 micro / macro | synth-v1 eval 100 micro / macro |
|---|---|---|
| ConText only (default) | 0.8064 / 0.6473 | 0.8192 / 0.7751 |
| MetaCAT Presence + Experiencer + Temporality | 0.8064 / 0.6468 | 0.7982 / 0.7485 |
| MetaCAT Presence only | — | 0.7982 / 0.7485 |
| MetaCAT Experiencer only | — | 0.8192 / 0.7751 |
| MetaCAT Temporality only | — | 0.8192 / 0.7751 |

**Where the loss comes from.** All of it is seizure frequency on synth-v1:
* true positives fall from 49 to 36 for `count_min`, `count_max` and
  `period`;
* the F1 for `period` falls from 0.84 to 0.69.

MetaCAT Presence marks seizure mentions as negated (e.g. "EEG showed …" and
"TLE" in EA0182), so the frequency rule drops them.

## Why, and what would help
* **The labels are mostly ConText's own output.** The best the model can do
  is copy ConText, and on held-out data it matches ConText only 69% of the
  time for Presence.
* **The labels are very unbalanced.** Family is 1.1% of spans and
  hypothetical 2.8%; Certainty has a single class.
* **What would help:** a gold-annotated meta-annotation set, e.g. a
  MedCATTrainer pass on F-S train letters, with each class adequately
  represented. MedCAT's MetaCAT papers train on human-labelled data [M2].
  Until then, ConText stays.

## Ablation inside E (not a third arm)

Opt-in `--context-engine {medspacy,sentence,negex}` (`MEDAI_LEO_CONTEXT_ENGINE`) swaps the
preprocessor on the same phenotype fields: medspaCy ConText (default, this document),
`rules.sentence_context`, or Chapman NegEx. Score IED present / current vs prior ASM — not
“ConText F1 vs EpExtra F1.” Default `medspacy` ≡ previous E. See `docs/ROLE_PLACEMENTS.md`.

Reproduce:
```bash
for c in fs_test_40 synth_v1_eval_100; do
  venv-medcat/bin/python scripts/run_medcat_rules_on_corpus.py --corpus $c \
      --metacat checkpoints/metacat --out-dir data/run_manifests_medcat_rules_${c}_metacat
done
```

References are listed in `docs/ONTOLOGY_SOURCES.md` §4.3.
