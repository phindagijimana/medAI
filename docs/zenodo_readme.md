# MedAI-EPI synthetic corpus v1 — Zenodo record README

**Title:** MedAI-EPI synth-v1: a 500-patient synthetic epilepsy corpus with
schema-conformant phenotype targets

**Authors:** Ndagijimana P; [TBD co-authors]

**Zenodo record DOI:** [TBD]

**Release version:** v1 (2026-[TBD])

**License:** CC-BY 4.0

---

## Description

Synth-v1 is a 500-patient synthetic corpus of epilepsy clinical
documents released alongside the MedAI-EPI framework and its
accompanying manuscript. Every patient's phenotype was sampled from
an epidemiology-informed prior distribution, then each patient's
authorized clinical content was rendered as one progress note plus a
modality-appropriate second document (MRI report when an MRI finding
was drawn, EEG report otherwise) under a semantic-plan-constrained
prompt executed on OpenAI GPT-5.6-sol. The corpus is intended for:

- Training / validating open-source clinical-extraction models against
  a schema-conformant target set without exposing real patient data.
- Reproducing the MedAI-EPI paper's fine-tuning experiments.
- Benchmarking new extraction pipelines against a corpus whose ground
  truth is deterministic (traceable to the sampler seed).

**No real patient data is included.** All notes are synthetic and were
generated with `store=false` on the OpenAI API; no OpenAI-side retention
of the rendered prose.

---

## Contents

```
episynth_corpus/v1/
├── run_metadata.json         # sampler / generator versions, seeds
├── execution_manifest.csv    # per-document generator provenance (~1000 rows)
├── patients/                 # G0 sampled phenotypes (500 JSON files)
├── documents/                # G2 rendered documents
│   └── {PID}/
│       ├── progress_note/
│       │   ├── request.json    # exact prompt sent to the API
│       │   ├── response.json   # raw API response envelope
│       │   ├── output.txt      # rendered document text
│       │   └── metadata.json   # prompt / response hashes, generator id
│       └── {mri_report OR eeg_report}/
│           ├── request.json
│           ├── response.json
│           ├── output.txt
│           └── metadata.json
└── targets/                  # G3 Evidence[T]-wrapped phenotype targets
    └── {PID}/
        └── target_phenotype.json
```

- **N patients:** 500
- **N documents:** ~1000 (500 progress notes + 500 modality docs; a
  small number of patients yielded 2 docs of the same type — see
  execution_manifest.csv for the actual counts)
- **N target phenotypes:** 500 (`target_phenotype.json` per patient)
- **Uncompressed size:** ~[TBD] MB
- **Compressed archive:** `synth_v1.tar.gz` ([TBD] MB)

---

## Provenance and reproducibility

- **G0 (latent truth):** `scripts/synth_patient_sampler.py` seed 0 →
  500 patients over an ILAE-2017-informed prior distribution.
- **G1 (authorized content):** `required_assertions` list per patient
  bounding the generator's licensed content.
- **G2 (rendered documents):** OpenAI `gpt-5.6-sol`, deterministic
  decoding, `store=false`. Every request and response envelope is
  archived under `documents/{PID}/{doc_type}/`.
- **G3 (schema targets):** deterministic converter
  (`scripts/convert_synth_corpus_targets.py`) maps G0 → v0.2.1
  `EpilepsyPhenotype` Evidence[T] structures.

Because G3 is a deterministic function of G0, these targets are
**silver** labels — used for training and validation-loss early
stopping in the fine-tune, **not** for scoring gold. Held-out
evaluation in the paper uses either the Fonferko-Shadrach
clinician-adjudicated gold or the EpiSynth pilot's G0 authorized
content.

---

## Intended use

- Yes: training / evaluating clinical NLP models; benchmarking
  structured-extraction pipelines; teaching / demoing epilepsy
  phenotyping; reproducing MedAI-EPI paper results.
- No: clinical decision-making; substitution for real patient data in
  regulatory submissions; medical advice.

---

## Ethics

No human-subjects data — the corpus is entirely synthetic. IRB not
required for redistribution or downstream use, but users are still
bound by their institution's AI-generated-content policies and by the
CC-BY 4.0 license terms.

---

## Citation

If you use synth-v1, please cite both the Zenodo record and the
corresponding manuscript:

```bibtex
@dataset{medai_epi_synth_v1,
  author       = {Ndagijimana, P. and [TBD co-authors]},
  title        = {{MedAI-EPI synth-v1: a 500-patient synthetic epilepsy corpus}},
  month        = [TBD],
  year         = [TBD],
  publisher    = {Zenodo},
  version      = {v1},
  doi          = {[TBD]},
  url          = {[TBD]}
}
```

Plus the paper: [TBD manuscript DOI].

---

## Contact

Peace Ndagijimana — [TBD contact email] — for corrections, questions
about corpus regeneration, or downstream-use collaborations.
