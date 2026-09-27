# MedAI-EPI — Release Notes

Every public release of the MedAI-EPI framework corresponds to a
git tag and (for v1.0+) a Zenodo software-record DOI. Numbers marked
`[TBD]` are populated at release cut.

---

## v1.0 — first citable release

- **Release date:** [TBD]
- **Git tag:** `v1.0`
- **Zenodo DOI (software record):** [TBD]
- **Corresponding manuscript:** Ndagijimana P *et al.*, "MedAI-EPI: an
  evidence-grounded epilepsy phenotyping framework for open-weight
  clinical LLMs." *[Target journal TBD]*, [TBD]. Preprint DOI: [TBD].

### What v1.0 releases

- **Framework code** — schema (v0.2.1, 6 modules + Evidence[T] wrapper),
  extraction pipeline (three-tier repair), prompt registry (M0 / M1 / M2
  × 6 modules), chunker, merger, tabular flatten, Flask service and CLI,
  evaluation harness, `Dockerfile.eval` reproducibility container.
- **LoRA adapter** — MedAI-EPI-tuned Med42-8B (rank 16, α 32,
  41.9M trainable params / 0.52% of the 8.07B base, ~168 MB safetensors),
  released on Hugging Face at `[TBD huggingface-repo-url]` under the
  upstream Med42-8B license
  (see [`docs/huggingface_model_card.md`](docs/huggingface_model_card.md)).
- **Synth-v1 corpus** — 500 patients × ~1000 documents (progress notes,
  MRI reports, EEG reports) with schema-conformant Evidence[T] targets,
  released on Zenodo at `[TBD zenodo-corpus-doi]` under CC-BY 4.0
  (see [`docs/zenodo_readme.md`](docs/zenodo_readme.md)).
- **Run manifests** — every extraction result from every paper table,
  replayable via the `Dockerfile.eval` container.

### Verified against

- Fonferko-Shadrach 2024 gold (n=200 clinic letters, adjudicated).
- EpiSynth pilot (n=60 documents, authorized-content G0 phenotypes).
- Synth-v1 held-out validation split (n=122 pairs).

### Dependencies

- Python 3.9+ (venv, no conda required)
- PyTorch 2.x with CUDA 12 for GPU inference; falls back to CPU (slow).
- transformers 4.4x, peft 0.11+, pydantic 2.x, flask 3.x.
- lm-format-enforcer 0.10 (schema-constrained decoding, optional).
- openai 1.x (only if using the OpenAI comparator backend).
- See `requirements.txt` and `Dockerfile.gpu` / `Dockerfile.eval` for
  full pinned versions.

### Reproducing paper tables

```bash
docker build -f Dockerfile.eval -t medai-epi-eval:v1.0 .
docker run --rm \
  -v $(pwd)/data/run_manifests:/data/run_manifests:ro \
  -v $(pwd)/data/gold:/data/gold:ro \
  -v $(pwd)/out:/out \
  medai-epi-eval:v1.0 \
  python -m eval.aggregator_cli \
    --manifests /data/run_manifests --gold /data/gold --out /out
```

Wall-clock: [TBD] min on a 4-core VM. No GPU required for reproduction
of scored tables.

### Citation (BibTeX)

```bibtex
@software{ndagijimana_medai_epi_v1_0,
  author       = {Ndagijimana, P. and [TBD co-authors]},
  title        = {{MedAI-EPI: v1.0}},
  month        = [TBD],
  year         = [TBD],
  publisher    = {Zenodo},
  version      = {v1.0},
  doi          = {[TBD]},
  url          = {[TBD]}
}
```

If you use the released LoRA adapter or corpus, please also cite the
corresponding manuscript ([TBD DOI]) and (if using the corpus) the
Fonferko-Shadrach 2024 clinic-letter annotation set (Zenodo IDs
8381080, 8356494, 8382589, 12520180; original CC-BY 4.0).

---

## Prior releases

*None — v1.0 is the first citable release. See git log for the
pre-release research history.*

---

## License summary

- Code: MIT (see `LICENSE`).
- LoRA adapter: inherits Med42-8B upstream license.
- Synth-v1 corpus: CC-BY 4.0.
- Fonferko-Shadrach corpus (redistributed unchanged): CC-BY 4.0.
